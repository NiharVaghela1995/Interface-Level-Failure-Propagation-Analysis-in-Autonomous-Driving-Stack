"""
scripts/phase5_benchmark.py
============================
Phase 5: Open-Loop Corruption Benchmark — 8 Corruptions × 5 Severities

Research objective (V&V framing):
  Systematic ODD coverage sweep across all sensor corruption types at
  multiple severity levels. Measures how each corruption type propagates
  through the pipeline: sensor input → uncertainty → trust → planning mode.
  Produces the corruption impact ranking used to prioritize SOTIF trigger
  conditions in Phase 4a.

Key results:
  Fog:   29.9% mean uncertainty increase (most impactful)
  Snow:   8.7% mean uncertainty increase (least impactful)
  CONSERVATIVE mode triggered by: glare, brightness, darkness, fog,
                                   motion_blur, snow, rain at high severity

Usage:
  NUSCENES_DATAROOT=/data/nuscenes python scripts/phase5_benchmark.py
"""

import os
import sys
import json
import warnings
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sensor_degradation import (
    apply_glare, apply_brightness, apply_darkness, apply_fog,
    apply_motion_blur, apply_snow, apply_rain,
    apply_lidar_dropout, lidar_density_ratio,
    CORRUPTION_TYPES
)
from utils.uncertainty import mc_dropout_passes, enable_dropout
from utils.trust import mc_trust, rebalance_trust
from utils.planning import frenet_planner, trust_to_planning_mode

# ── Config ────────────────────────────────────────────────────────────────────
NUSCENES_DATAROOT = os.environ.get('NUSCENES_DATAROOT', '/data/nuscenes')
OUTPUT_DIR        = os.environ.get('OUTPUT_DIR', 'reports')
SCREENSHOTS_DIR   = 'screenshots/phase5'
SAMPLE_ADVANCE    = 5
MC_PASSES         = 15

import torch
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

SEVERITIES = [0.2, 0.4, 0.6, 0.8, 1.0]

# ── Corruption dispatcher ─────────────────────────────────────────────────────
# Maps corruption name → (camera_fn, lidar_type, affected_sensors)
# Camera functions now call utils directly instead of inline definitions.

RNG_SNOW = np.random.default_rng(42)
RNG_RAIN = np.random.default_rng(43)

def _clean(img, s):      return img
def _glare(img, s):      return apply_glare(img, intensity=s)
def _brightness(img, s): return apply_brightness(img, intensity=s * 0.4 / 1.0)
def _darkness(img, s):   return apply_darkness(img, intensity=s * 0.35 / 1.0)
def _fog(img, s):        return apply_fog(img, intensity=s)
def _motion(img, s):     return apply_motion_blur(img, intensity=s)
def _snow(img, s):       return apply_snow(img, intensity=s, rng=RNG_SNOW)
def _rain(img, s):       return apply_rain(img, intensity=s, rng=RNG_RAIN)

CORRUPTIONS = {
    #  name        cam_fn       lidar_type        affected_sensors
    "clean":       (_clean,     "none",           "baseline"),
    "glare":       (_glare,     "none",           "camera"),
    "brightness":  (_brightness,"none",           "camera"),
    "darkness":    (_darkness,  "none",           "camera"),
    "fog":         (_fog,       "fog_dropout",    "camera+lidar"),
    "motion_blur": (_motion,    "none",           "camera"),
    "snow":        (_snow,      "snow_noise",     "camera+lidar"),
    "rain":        (_rain,      "rain_dropout",   "camera+lidar"),
}

def apply_lidar_corruption(pts: np.ndarray, lidar_type: str, severity: float) -> np.ndarray:
    """Apply LiDAR corruption matching the camera corruption type."""
    rng = np.random.default_rng(42)
    if lidar_type == "rain_dropout":
        return apply_lidar_dropout(pts, dropout_rate=severity * 0.8, rng=rng)
    elif lidar_type == "fog_dropout":
        dist = np.sqrt(pts[:, 0]**2 + pts[:, 1]**2)
        return pts[dist < 50 * (1 - severity * 0.6)]
    elif lidar_type == "snow_noise":
        noisy = pts.copy()
        noisy[:, :3] += rng.normal(0, severity * 0.3, pts[:, :3].shape)
        return noisy
    return pts   # "none"

# ── Load nuScenes ─────────────────────────────────────────────────────────────
from nuscenes.nuscenes import NuScenes

print("Loading nuScenes mini...")
nusc = NuScenes('v1.0-mini', dataroot=NUSCENES_DATAROOT)
print(f"Loaded {len(nusc.scene)} scenes")

scene = nusc.scene[0]
sample_token = scene['first_sample_token']
for _ in range(SAMPLE_ADVANCE):
    s = nusc.get('sample', sample_token)
    if s['next']:
        sample_token = s['next']
sample = nusc.get('sample', sample_token)

cam_data  = nusc.get('sample_data', sample['data']['CAM_FRONT'])
lid_data  = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
img_clean = Image.open(os.path.join(NUSCENES_DATAROOT, cam_data['filename'])).convert('RGB')
pts_clean = np.fromfile(os.path.join(NUSCENES_DATAROOT, lid_data['filename']),
                        dtype=np.float32).reshape(-1, 5)

# ── Load model ────────────────────────────────────────────────────────────────
from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

print("Loading SegFormer-B2...")
proc  = SegformerImageProcessor.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024")
model = SegformerForSemanticSegmentation.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024").to(DEVICE).eval()
print(f"Model ready on {DEVICE}")

# ── MC uncertainty helper ─────────────────────────────────────────────────────
def get_uncertainty(img: Image.Image) -> tuple:
    """Returns (confidence, uncertainty_scalar) via MC Dropout."""
    img_s  = img.resize((512, 512))
    inputs = proc(images=img_s, return_tensors='pt')
    enable_dropout(model)
    _, var, unc_t = mc_dropout_passes(model, inputs, n_passes=MC_PASSES, device=DEVICE)
    model.eval()
    # confidence = mean of max class probability
    inputs2 = proc(images=img_s, return_tensors='pt').to(DEVICE)
    with torch.no_grad():
        logits = model(**inputs2).logits
        conf   = float(torch.softmax(logits, dim=1)[0].max(0).values.mean().item())
    return conf, float(unc_t.mean().item())

# ── Baseline ──────────────────────────────────────────────────────────────────
print("\nComputing baseline...")
base_conf, base_unc = get_uncertainty(img_clean)
print(f"Baseline: conf={base_conf:.3f}  unc={base_unc:.6f}")

# ── Full benchmark sweep ──────────────────────────────────────────────────────
print(f"\nRunning {len(CORRUPTIONS)} corruptions × {len(SEVERITIES)} severities "
      f"({len(CORRUPTIONS)*len(SEVERITIES)} cells)...")

results = {}
for corr_name, (cam_fn, lid_type, affected) in CORRUPTIONS.items():
    results[corr_name] = {'affected_sensors': affected, 'severities': {}}

    for sev in SEVERITIES:
        img_corr = cam_fn(img_clean, sev)
        pts_corr = apply_lidar_corruption(pts_clean, lid_type, sev)

        conf, unc = get_uncertainty(img_corr)

        # Loop 1: trust rebalancing (utils)
        lidar_drop = 1.0 - lidar_density_ratio(pts_corr, pts_clean)
        cam_t, lid_t = rebalance_trust(
            camera_raw_trust   = mc_trust(unc, baseline_uncertainty=base_unc),
            lidar_dropout_rate = lidar_drop
        )

        # Loop 2: planning (utils)
        mode = trust_to_planning_mode(cam_t, lid_t)
        plan = frenet_planner(mode, cam_t, lid_t)

        results[corr_name]['severities'][str(sev)] = {
            'confidence':       conf,
            'uncertainty':      unc,
            'camera_trust':     cam_t,
            'lidar_ratio':      lidar_density_ratio(pts_corr, pts_clean),
            'regime':           mode,
            'velocity_kmh':     plan['velocity_kmh'],
            'unc_increase_pct': float((unc - base_unc) / (base_unc + 1e-10) * 100),
        }

    avg_unc = np.mean([v['uncertainty']   for v in results[corr_name]['severities'].values()])
    avg_vel = np.mean([v['velocity_kmh']  for v in results[corr_name]['severities'].values()])
    print(f"  {corr_name:15s}  avg_unc={avg_unc:.6f}  avg_vel={avg_vel:.1f} km/h")

# ── Build matrices ────────────────────────────────────────────────────────────
corr_names = list(CORRUPTIONS.keys())
sev_labels = [str(s) for s in SEVERITIES]

unc_mat   = np.array([[results[c]['severities'][str(s)]['uncertainty']
                        for s in SEVERITIES] for c in corr_names])
trust_mat = np.array([[results[c]['severities'][str(s)]['camera_trust']
                        for s in SEVERITIES] for c in corr_names])
vel_mat   = np.array([[results[c]['severities'][str(s)]['velocity_kmh']
                        for s in SEVERITIES] for c in corr_names])

avg_unc_increase = {
    c: np.mean([results[c]['severities'][str(s)]['unc_increase_pct']
                for s in SEVERITIES])
    for c in corr_names
}
sorted_corr  = sorted(avg_unc_increase.items(), key=lambda x: x[1], reverse=True)
names_sorted = [x[0] for x in sorted_corr]
vals_sorted  = [x[1] for x in sorted_corr]

regime_counts = {}
for c in corr_names:
    counts = {'NORMAL': 0, 'CAUTIOUS': 0, 'CONSERVATIVE': 0}
    for s in SEVERITIES:
        r = results[c]['severities'][str(s)]['regime']
        counts[r] = counts.get(r, 0) + 1
    regime_counts[c] = counts

# ── Figure: 6-panel benchmark summary ────────────────────────────────────────
print("\nGenerating benchmark figure...")
fig, axes = plt.subplots(2, 3, figsize=(20, 12))

def add_heatmap(ax, mat, title, cmap, vmin=None, vmax=None, fmt='.5f'):
    im = ax.imshow(mat, cmap=cmap, aspect='auto', vmin=vmin, vmax=vmax)
    ax.set_xticks(range(len(SEVERITIES))); ax.set_xticklabels(sev_labels)
    ax.set_yticks(range(len(corr_names))); ax.set_yticklabels(corr_names)
    ax.set_title(title, fontweight='bold')
    plt.colorbar(im, ax=ax, fraction=0.046)
    for i in range(len(corr_names)):
        for j in range(len(SEVERITIES)):
            val = mat[i, j]
            ax.text(j, i, f'{val:{fmt}}', ha='center', va='center', fontsize=7,
                    color='white' if val > mat.mean() else 'black')

add_heatmap(axes[0,0], unc_mat,   'Camera Uncertainty per Corruption', 'hot', fmt='.5f')
add_heatmap(axes[0,1], trust_mat, 'Camera Trust Loop 1',               'RdYlGn', vmin=0, vmax=1, fmt='.2f')
add_heatmap(axes[0,2], vel_mat,   'Planned Velocity km/h Loop 2',      'RdYlGn_r', vmin=30, vmax=50, fmt='.0f')

# Regime distribution bar chart
x = np.arange(len(corr_names)); w = 0.25
axes[1,0].bar(x-w, [regime_counts[c].get('NORMAL',0)       for c in corr_names],
              w, label='NORMAL',       color='#2ecc71', alpha=0.8)
axes[1,0].bar(x,   [regime_counts[c].get('CAUTIOUS',0)     for c in corr_names],
              w, label='CAUTIOUS',     color='#f39c12', alpha=0.8)
axes[1,0].bar(x+w, [regime_counts[c].get('CONSERVATIVE',0) for c in corr_names],
              w, label='CONSERVATIVE', color='#e74c3c', alpha=0.8)
axes[1,0].set_xticks(x)
axes[1,0].set_xticklabels(corr_names, rotation=30, ha='right', fontsize=9)
axes[1,0].set_title('Regime Distribution per Corruption', fontweight='bold')
axes[1,0].legend(fontsize=9); axes[1,0].grid(True, alpha=0.3, axis='y')

# Uncertainty increase vs severity line plot
colors_l = plt.cm.Set1(np.linspace(0, 1, len(corr_names)))
for i, c in enumerate(corr_names):
    unc_pct = [results[c]['severities'][str(s)]['unc_increase_pct'] for s in SEVERITIES]
    axes[1,1].plot(SEVERITIES, unc_pct, 'o-', color=colors_l[i],
                   linewidth=2, markersize=6, label=c, alpha=0.85)
axes[1,1].set_xlabel('Severity'); axes[1,1].set_ylabel('Uncertainty increase %')
axes[1,1].set_title('Uncertainty Increase vs Severity', fontweight='bold')
axes[1,1].legend(fontsize=8, ncol=2); axes[1,1].grid(True, alpha=0.3)
axes[1,1].axhline(y=0, color='gray', linestyle='--', alpha=0.5)

# Corruption impact ranking bar chart
bar_colors = ['#e74c3c' if v > 10 else '#f39c12' if v > 5 else '#2ecc71'
              for v in vals_sorted]
axes[1,2].barh(range(len(names_sorted)), vals_sorted, color=bar_colors, alpha=0.85)
axes[1,2].set_yticks(range(len(names_sorted)))
axes[1,2].set_yticklabels(names_sorted)
axes[1,2].set_xlabel('Mean uncertainty increase %')
axes[1,2].set_title('Corruption Impact Ranking', fontweight='bold')
axes[1,2].grid(True, alpha=0.3, axis='x')
for i, v in enumerate(vals_sorted):
    axes[1,2].text(v+0.1, i, f'{v:.1f}%', va='center', fontsize=9, fontweight='bold')

plt.suptitle('Phase 5: nuScenes-C Corruption Benchmark\n'
             '8 corruption types × 5 severities',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/phase5_01_corruption_benchmark.png',
            dpi=150, bbox_inches='tight')
plt.close()
print("Saved: phase5_01_corruption_benchmark.png")

# ── Save JSON results ─────────────────────────────────────────────────────────
conservative_corruptions = [
    c for c in corr_names
    if any(results[c]['severities'][str(s)]['regime'] == 'CONSERVATIVE'
           for s in SEVERITIES)
]

results_json = {
    'phase':           5,
    'title':           'nuScenes-C Corruption Benchmark',
    'corruption_types': list(CORRUPTIONS.keys()),
    'severities':      SEVERITIES,
    'baseline': {
        'confidence':  float(base_conf),
        'uncertainty': float(base_unc),
    },
    'corruption_results': {
        c: {
            'affected_sensors': results[c]['affected_sensors'],
            'mean_unc_increase_pct': float(avg_unc_increase[c]),
            'severities': results[c]['severities'],
        }
        for c in corr_names
    },
    'corruption_ranking': [
        {'corruption': c, 'mean_unc_increase_pct': float(v)}
        for c, v in sorted_corr
    ],
    'key_findings': {
        'most_impactful':            sorted_corr[0][0],
        'most_impactful_pct':        round(sorted_corr[0][1], 1),
        'least_impactful':           sorted_corr[-1][0],
        'least_impactful_pct':       round(sorted_corr[-1][1], 1),
        'conservative_corruptions':  conservative_corruptions,
    },
    'config': {
        'mc_passes': MC_PASSES,
        'backbone':  'SegFormer-B2 (cityscapes pretrained)',
        'dataset':   'nuScenes mini v1.0 CAM_FRONT',
    }
}

out_path = os.path.join(OUTPUT_DIR, 'phase5_results.json')
with open(out_path, 'w') as f:
    json.dump(results_json, f, indent=2)

print(f'\n=== PHASE 5 COMPLETE ===')
print(f'  Most impactful:  {sorted_corr[0][0]} ({sorted_corr[0][1]:.1f}%)')
print(f'  Least impactful: {sorted_corr[-1][0]} ({sorted_corr[-1][1]:.1f}%)')
print(f'  CONSERVATIVE triggered by: {conservative_corruptions}')
print(f'  Results: {out_path}')
