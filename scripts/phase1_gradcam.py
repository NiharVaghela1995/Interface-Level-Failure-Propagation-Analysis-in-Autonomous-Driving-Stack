"""
scripts/phase1_gradcam.py
==========================
Phase 1: GradCAM + MC Dropout + Loop 2 Planning Demo

Research objective (V&V framing):
  Establish baseline failure propagation signature:
  sensor degradation → attention shift (Loop 1 diagnostic) →
  uncertainty increase → planning adaptation (Loop 2 response).

Key results:
  - GradCAM attention shift under glare: ~0.011
  - MC Dropout uncertainty: clean vs glare measured per scene
  - Loop 2: velocity, TTC, lateral margin adapt to uncertainty
  - Dataset: nuScenes mini, CAM_FRONT, scene 0

Usage:
  # Local / RunPod
  NUSCENES_DATAROOT=/data/nuscenes python scripts/phase1_gradcam.py

  # Google Colab
  NUSCENES_DATAROOT=/content/nuscenes python scripts/phase1_gradcam.py
"""

import os
import sys
import json
import warnings
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from PIL import Image

warnings.filterwarnings('ignore')

# ── Add project root to path so utils/ is importable ─────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sensor_degradation import apply_glare, apply_lidar_dropout
from utils.uncertainty import mc_dropout_passes, enable_dropout, uncertainty_scalar
from utils.trust import mc_trust, rebalance_trust, trust_to_planning_mode
from utils.planning import frenet_planner, planning_delta, PLANNING_PARAMS
from utils.metrics import safety_margin, coverage_percentage

# ── Config ────────────────────────────────────────────────────────────────────
NUSCENES_DATAROOT = os.environ.get('NUSCENES_DATAROOT', '/data/nuscenes')
OUTPUT_DIR        = os.environ.get('OUTPUT_DIR', 'reports')
SCREENSHOTS_DIR   = 'screenshots/phase1'
SCENE_IDX         = 0
SAMPLE_ADVANCE    = 5        # skip first N samples for a richer scene
GLARE_INTENSITY   = 0.6
DROPOUT_RATE      = 0.35
MC_PASSES         = 20
DEVICE            = 'cuda' if __import__('torch').cuda.is_available() else 'cpu'

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ── Step 1: Load nuScenes data ────────────────────────────────────────────────
print("Loading nuScenes mini...")
from nuscenes.nuscenes import NuScenes

nusc = NuScenes('v1.0-mini', dataroot=NUSCENES_DATAROOT)
print(f"Loaded {len(nusc.scene)} scenes, {len(nusc.sample)} samples")

scene = nusc.scene[SCENE_IDX]
sample_token = scene['first_sample_token']

for _ in range(SAMPLE_ADVANCE):
    sample = nusc.get('sample', sample_token)
    if sample['next']:
        sample_token = sample['next']

sample   = nusc.get('sample', sample_token)
cam_token  = sample['data']['CAM_FRONT']
cam_data   = nusc.get('sample_data', cam_token)
lidar_token = sample['data']['LIDAR_TOP']
lidar_data  = nusc.get('sample_data', lidar_token)

img_path   = os.path.join(NUSCENES_DATAROOT, cam_data['filename'])
lidar_path = os.path.join(NUSCENES_DATAROOT, lidar_data['filename'])

img    = Image.open(img_path).convert('RGB')
points = np.fromfile(lidar_path, dtype=np.float32).reshape(-1, 5)  # x,y,z,intensity,ring

print(f"Scene: {scene['description']}")
print(f"LiDAR points: {len(points)}")

# ── Step 2: Apply sensor degradation (via utils) ──────────────────────────────
img_glare    = apply_glare(img, intensity=GLARE_INTENSITY)
points_rain  = apply_lidar_dropout(points, dropout_rate=DROPOUT_RATE,
                                   rng=np.random.default_rng(42))

mask_c = (np.abs(points[:,0]) < 40) & (np.abs(points[:,1]) < 40)
mask_r = (np.abs(points_rain[:,0]) < 40) & (np.abs(points_rain[:,1]) < 40)

# Fig 1: raw sensor data comparison
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
axes[0,0].imshow(img);       axes[0,0].set_title('Camera: CLEAN', color='green'); axes[0,0].axis('off')
axes[0,1].imshow(img_glare); axes[0,1].set_title(f'Camera: GLARE (intensity={GLARE_INTENSITY})', color='red'); axes[0,1].axis('off')
axes[1,0].scatter(points[mask_c,1], points[mask_c,0], c=points[mask_c,2],
                  cmap='plasma', s=0.4, vmin=-2, vmax=3)
axes[1,0].set_xlim(-40,40); axes[1,0].set_ylim(-10,60); axes[1,0].set_aspect('equal')
axes[1,0].set_title(f'LiDAR: CLEAN ({len(points[mask_c])} pts)', color='green')
axes[1,1].scatter(points_rain[mask_r,1], points_rain[mask_r,0], c=points_rain[mask_r,2],
                  cmap='plasma', s=0.4, vmin=-2, vmax=3)
axes[1,1].set_xlim(-40,40); axes[1,1].set_ylim(-10,60); axes[1,1].set_aspect('equal')
axes[1,1].set_title(f'LiDAR: RAIN dropout ({len(points_rain[mask_r])} pts, {DROPOUT_RATE*100:.0f}% dropped)', color='red')
plt.suptitle('Interface Injection Point 1: Sensor Degradation', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/01_sensor_conflict.png', dpi=150, bbox_inches='tight')
plt.close()
print("Fig 1 saved.")

# ── Step 3: Load SegFormer backbone ───────────────────────────────────────────
print("Loading SegFormer-B2 backbone...")
import torch
from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

processor = SegformerImageProcessor.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024"
)
model = SegformerForSemanticSegmentation.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024"
).to(DEVICE)
model.eval()
print(f"Model on {DEVICE}")

img_small       = img.resize((512, 512))
img_glare_small = img_glare.resize((512, 512))

# ── Step 4: GradCAM saliency (Loop 1 diagnostic) ─────────────────────────────

def get_saliency(input_img):
    """Gradient-based saliency — shows what the model attends to."""
    inputs = processor(images=input_img, return_tensors='pt').to(DEVICE)
    pv = inputs['pixel_values'].requires_grad_(True)
    model.zero_grad()
    out = model(pixel_values=pv).logits
    out[:, 11].mean().backward()   # class 11 = person (Cityscapes)
    grad = pv.grad.squeeze().cpu().detach().numpy()
    sal  = np.abs(grad).max(axis=0)
    sal  = (sal - sal.min()) / (sal.max() - sal.min() + 1e-8)
    return sal

print("Computing GradCAM saliency...")
from pytorch_grad_cam.utils.image import show_cam_on_image
sal_clean = get_saliency(img_small)
sal_glare = get_saliency(img_glare_small)

shift = float(np.mean(np.abs(sal_clean - sal_glare)))

overlay_clean = show_cam_on_image(np.array(img_small)/255.0, sal_clean)
overlay_glare = show_cam_on_image(np.array(img_glare_small)/255.0, sal_glare)

fig, axes = plt.subplots(2, 2, figsize=(16, 10))
axes[0,0].imshow(img_small);       axes[0,0].set_title('Input: Clean'); axes[0,0].axis('off')
axes[0,1].imshow(img_glare_small); axes[0,1].set_title('Input: Glare', color='red'); axes[0,1].axis('off')
axes[1,0].imshow(overlay_clean);   axes[1,0].set_title('GradCAM: Clean', color='green'); axes[1,0].axis('off')
axes[1,1].imshow(overlay_glare);   axes[1,1].set_title(f'GradCAM: Glare (shift={shift:.4f})', color='red'); axes[1,1].axis('off')
plt.suptitle('Loop 1 Diagnostic: Attention Shift Under Sensor Degradation', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/04_gradcam_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"GradCAM shift: {shift:.4f}")

# ── Step 5: MC Dropout uncertainty (via utils) ────────────────────────────────
print("Running MC Dropout uncertainty estimation...")
enable_dropout(model)

inputs_clean = processor(images=img_small, return_tensors='pt')
inputs_glare = processor(images=img_glare_small, return_tensors='pt')

_, var_clean, unc_clean_t = mc_dropout_passes(model, inputs_clean, n_passes=MC_PASSES, device=DEVICE)
_, var_glare, unc_glare_t = mc_dropout_passes(model, inputs_glare, n_passes=MC_PASSES, device=DEVICE)

model.eval()

mu_clean = float(unc_clean_t.mean().item())
mu_glare = float(unc_glare_t.mean().item())

unc_map_clean = var_clean[0].mean(0).cpu().numpy()
unc_map_glare = var_glare[0].mean(0).cpu().numpy()

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
axes[0].imshow(img_small); axes[0].set_title('Input'); axes[0].axis('off')
im1 = axes[1].imshow(unc_map_clean, cmap='hot'); plt.colorbar(im1, ax=axes[1])
axes[1].set_title(f'Uncertainty: CLEAN\nu={mu_clean:.5f}', color='green'); axes[1].axis('off')
im2 = axes[2].imshow(unc_map_glare, cmap='hot'); plt.colorbar(im2, ax=axes[2])
axes[2].set_title(f'Uncertainty: GLARE\nu={mu_glare:.5f}', color='red'); axes[2].axis('off')
plt.suptitle('MC Dropout: Uncertainty Signal Triggering Adaptive Behavior', fontsize=12, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/05_uncertainty_maps.png', dpi=150, bbox_inches='tight')
plt.close()
print(f"Uncertainty — clean: {mu_clean:.5f}, glare: {mu_glare:.5f}, increase: {((mu_glare/mu_clean)-1)*100:.1f}%")

# ── Step 6: Loop 1 trust rebalancing (via utils) ──────────────────────────────
unc_baseline = mu_clean

cam_trust_clean, lid_trust_clean = rebalance_trust(
    camera_raw_trust=mc_trust(mu_clean, unc_baseline),
    lidar_dropout_rate=0.0
)
cam_trust_glare, lid_trust_glare = rebalance_trust(
    camera_raw_trust=mc_trust(mu_glare, unc_baseline),
    lidar_dropout_rate=DROPOUT_RATE
)

mode_clean = trust_to_planning_mode(cam_trust_clean, lid_trust_clean)
mode_glare = trust_to_planning_mode(cam_trust_glare, lid_trust_glare, glare_intensity=GLARE_INTENSITY)

# ── Step 7: Loop 2 planning adaptation (via utils) ────────────────────────────
plan_clean = frenet_planner(mode_clean, cam_trust_clean, lid_trust_clean)
plan_glare = frenet_planner(mode_glare, cam_trust_glare, lid_trust_glare)
delta      = planning_delta(plan_clean, plan_glare)

# Fig: planning adaptation bar chart
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
categories  = ['Velocity\n(km/h)', 'TTC margin\n(seconds)', 'Lateral margin\n(meters)']
clean_vals  = [plan_clean['velocity_kmh'], plan_clean['ttc_margin_s'], plan_clean['lateral_margin_m']]
glare_vals  = [plan_glare['velocity_kmh'], plan_glare['ttc_margin_s'], plan_glare['lateral_margin_m']]
x = np.arange(len(categories))
axes[0].bar(x - 0.2, clean_vals, 0.35, label='Clean scene', color='green', alpha=0.7)
axes[0].bar(x + 0.2, glare_vals, 0.35, label='Glare scene',  color='red',   alpha=0.7)
axes[0].set_xticks(x); axes[0].set_xticklabels(categories)
axes[0].legend(); axes[0].grid(True, alpha=0.3, axis='y')
axes[0].set_title('Loop 2: Planning Behavior Change Under Sensor Degradation', fontweight='bold')

summary = (
    f"EXPERIMENTAL RESULTS SUMMARY\n"
    f"{'='*33}\n\n"
    f"Scene: {scene['description'][:40]}\n\n"
    f"LOOP 1 — Sensor conflict diagnosis:\n"
    f"  Attention shift under glare: {shift:.4f}\n"
    f"  Uncertainty increase: {((mu_glare/mu_clean)-1)*100:.1f}%\n\n"
    f"LOOP 2 — Planning adaptation:\n"
    f"  Clean  → {plan_clean['mode']:12s} @ {plan_clean['velocity_kmh']:.0f} km/h\n"
    f"  Glare  → {plan_glare['mode']:12s} @ {plan_glare['velocity_kmh']:.0f} km/h\n"
    f"  Speed reduction:  {-delta['delta_velocity_kmh']:.1f} km/h\n"
    f"  TTC increase:     +{delta['delta_ttc_s']:.1f}s\n"
    f"  Lateral increase: +{delta['delta_lateral_m']:.1f}m"
)
axes[1].axis('off')
axes[1].text(0.05, 0.95, summary, transform=axes[1].transAxes,
             fontsize=9, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
plt.suptitle('Active Perception & Uncertainty-Aware Planning: Two Feedback Loops Demonstrated',
             fontsize=12, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/07_summary.png', dpi=150, bbox_inches='tight')
plt.close()
print("Summary figure saved.")

# ── Step 8: Save JSON results ─────────────────────────────────────────────────
results = {
    "phase": "1",
    "title": "GradCAM + MC Dropout + Loop 2 Planning Demo",
    "scene": scene['description'],
    "sample_token": sample_token,
    "loop1_diagnostics": {
        "attention_shift_clean_vs_glare": shift,
        "uncertainty_clean":     mu_clean,
        "uncertainty_glare":     mu_glare,
        "uncertainty_increase_pct": ((mu_glare / mu_clean) - 1) * 100,
    },
    "loop1_trust": {
        "camera_trust_clean": cam_trust_clean,
        "lidar_trust_clean":  lid_trust_clean,
        "camera_trust_glare": cam_trust_glare,
        "lidar_trust_glare":  lid_trust_glare,
    },
    "loop2_planning": {
        "clean":            plan_clean,
        "glare":            plan_glare,
        "delta":            delta,
    },
    "config": {
        "glare_intensity":  GLARE_INTENSITY,
        "dropout_rate":     DROPOUT_RATE,
        "mc_passes":        MC_PASSES,
        "backbone":         "SegFormer-B2 (cityscapes pretrained)",
        "dataset":          "nuScenes mini v1.0",
    }
}

out_path = os.path.join(OUTPUT_DIR, 'phase1_results.json')
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"Results saved: {out_path}")

# ── Summary print ─────────────────────────────────────────────────────────────
print("\n=== PHASE 1 COMPLETE ===")
print(f"  GradCAM attention shift:   {shift:.4f}")
print(f"  Uncertainty clean/glare:   {mu_clean:.5f} / {mu_glare:.5f}")
print(f"  Uncertainty increase:      {((mu_glare/mu_clean)-1)*100:.1f}%")
print(f"  Planning mode clean/glare: {plan_clean['mode']} / {plan_glare['mode']}")
print(f"  Speed reduction:           {-delta['delta_velocity_kmh']:.1f} km/h")
print(f"  TTC increase:              +{delta['delta_ttc_s']:.2f}s")
print(f"  Output figures:            {SCREENSHOTS_DIR}/")
print(f"  Results JSON:              {out_path}")
