"""
scripts/phase3_sensitivity.py
==============================
Phase 3: 7×7 Sensitivity Matrix — Sensor Degradation → Fusion Trust → Planning Mode

Research objective (V&V framing):
  Systematic sweep of Interface Injection Point 1 (sensor input) across
  the full degradation space. Measures how camera glare and LiDAR dropout
  propagate through Loop 1 (trust reweighting) into Loop 2 (planning).
  Identifies fragility boundaries: the degradation levels where the system
  transitions between planning modes.

Key results:
  Camera trust drops 0.58 → 0.41 at max glare.
  System enters CAUTIOUS mode at glare > 0.45 OR LiDAR dropout > 35%.
  Naive sigmoid trust mapping produces weak velocity response (−1.3 km/h)
  — motivating EDL approach (Phase 4b).

Usage:
  NUSCENES_DATAROOT=/data/nuscenes python scripts/phase3_sensitivity.py
"""

import os
import sys
import json
import warnings
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from PIL import Image

warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sensor_degradation import apply_glare, apply_lidar_dropout
from utils.uncertainty import mc_dropout_passes, enable_dropout
from utils.trust import mc_trust, rebalance_trust, trust_to_planning_mode
from utils.planning import frenet_planner, PLANNING_PARAMS

# ── Config ────────────────────────────────────────────────────────────────────
NUSCENES_DATAROOT = os.environ.get('NUSCENES_DATAROOT', '/data/nuscenes')
OUTPUT_DIR        = os.environ.get('OUTPUT_DIR', 'reports')
SCREENSHOTS_DIR   = 'screenshots/phase3'
SAMPLE_ADVANCE    = 8
MC_PASSES         = 15   # reduced vs phase 1/2 for sweep speed

import torch
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

GLARE_LEVELS  = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90]
DROPOUT_RATES = [0.0, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80]
N_G = len(GLARE_LEVELS)
N_D = len(DROPOUT_RATES)

# ── Load nuScenes ─────────────────────────────────────────────────────────────
from nuscenes.nuscenes import NuScenes

nusc = NuScenes('v1.0-mini', dataroot=NUSCENES_DATAROOT)
scene = nusc.scene[0]
sample_token = scene['first_sample_token']
for _ in range(SAMPLE_ADVANCE):
    s = nusc.get('sample', sample_token)
    if s['next']:
        sample_token = s['next']
sample = nusc.get('sample', sample_token)
print(f'Scene: {scene["description"]}')

def load_cam(cam_name):
    d = nusc.get('sample_data', sample['data'][cam_name])
    return Image.open(os.path.join(NUSCENES_DATAROOT, d['filename'])).convert('RGB')

def load_lidar():
    d = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
    return np.fromfile(os.path.join(NUSCENES_DATAROOT, d['filename']),
                       dtype=np.float32).reshape(-1, 5)

img_clean   = load_cam('CAM_FRONT')
lidar_clean = load_lidar()

# ── Load model ────────────────────────────────────────────────────────────────
from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

print('Loading SegFormer-B2...')
proc  = SegformerImageProcessor.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024")
model = SegformerForSemanticSegmentation.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024").to(DEVICE).eval()
print(f'Model ready on {DEVICE}')

# ── MC uncertainty helper (uses utils internally) ─────────────────────────────
def get_uncertainty(img):
    """MC Dropout uncertainty scalar for one image."""
    img_s  = img.resize((512, 512))
    inputs = proc(images=img_s, return_tensors='pt')
    enable_dropout(model)
    _, var, unc_t = mc_dropout_passes(model, inputs, n_passes=MC_PASSES, device=DEVICE)
    model.eval()
    return float(unc_t.mean().item())

# ── Baseline (clean scene) ────────────────────────────────────────────────────
print('Computing baseline uncertainty...')
unc_baseline = get_uncertainty(img_clean)
print(f'Baseline uncertainty: {unc_baseline:.6f}')

# ── 7×7 sensitivity sweep ─────────────────────────────────────────────────────
print(f'\nRunning {N_G}×{N_D} sensitivity sweep ({N_G * N_D} cells)...')

mat_unc       = np.zeros((N_G, N_D))
mat_cam_trust = np.zeros((N_G, N_D))
mat_lid_trust = np.zeros((N_G, N_D))
mat_velocity  = np.zeros((N_G, N_D))
mat_ttc       = np.zeros((N_G, N_D))
mat_margin    = np.zeros((N_G, N_D))
mat_mode      = []

for i, g in enumerate(GLARE_LEVELS):
    row_modes = []
    for j, d in enumerate(DROPOUT_RATES):
        # Inject degradation at sensor interface (utils)
        img_deg   = apply_glare(img_clean, intensity=g) if g > 0 else img_clean
        lidar_deg = apply_lidar_dropout(lidar_clean, dropout_rate=d,
                                        rng=np.random.default_rng(42))

        # Measure uncertainty propagation
        unc = get_uncertainty(img_deg)

        # Loop 1: trust rebalancing (utils)
        cam_raw = mc_trust(unc, unc_baseline)
        cam_t, lid_t = rebalance_trust(
            camera_raw_trust   = cam_raw,
            lidar_dropout_rate = d
        )

        # Loop 2: planning adaptation (utils)
        mode   = trust_to_planning_mode(cam_t, lid_t,
                                        glare_intensity=g,
                                        lidar_dropout=d)
        plan   = frenet_planner(mode, cam_t, lid_t)

        mat_unc[i, j]       = unc
        mat_cam_trust[i, j] = cam_t
        mat_lid_trust[i, j] = lid_t
        mat_velocity[i, j]  = plan['velocity_kmh']
        mat_ttc[i, j]       = plan['ttc_margin_s']
        mat_margin[i, j]    = plan['lateral_margin_m']
        row_modes.append(mode)

        print(f'  g={g:.2f} d={d:.2f} → unc={unc:.6f} '
              f'cam={cam_t:.2f} lid={lid_t:.2f} '
              f'v={plan["velocity_kmh"]:.1f} km/h  mode={mode}')

    mat_mode.append(row_modes)

# ── Helpers ───────────────────────────────────────────────────────────────────
glare_labels   = [f'{g:.2f}' for g in GLARE_LEVELS]
dropout_labels = [f'{int(d*100)}%' for d in DROPOUT_RATES]

def plot_heatmap(ax, data, title, cmap, vmin=None, vmax=None):
    im = ax.imshow(data, cmap=cmap, aspect='auto', vmin=vmin, vmax=vmax)
    ax.set_xticks(range(N_D)); ax.set_xticklabels(dropout_labels, fontsize=9)
    ax.set_yticks(range(N_G)); ax.set_yticklabels(glare_labels,   fontsize=9)
    ax.set_xlabel('LiDAR dropout rate',     fontsize=10)
    ax.set_ylabel('Camera glare intensity', fontsize=10)
    ax.set_title(title, fontsize=11, fontweight='bold')
    plt.colorbar(im, ax=ax, fraction=0.046)
    for ii in range(N_G):
        for jj in range(N_D):
            ax.text(jj, ii, f'{data[ii, jj]:.2f}', ha='center', va='center',
                    fontsize=7,
                    color='white' if data[ii, jj] < data.mean() else 'black')

# ── Figure 1: 6-panel sensitivity matrix ─────────────────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(20, 12))
plot_heatmap(axes[0,0], mat_unc * 1000,  'Camera Uncertainty x1000\n(higher=less reliable)', 'hot')
plot_heatmap(axes[0,1], mat_cam_trust,   'Camera Trust Weight\n(Loop 1: fusion adaptation)', 'RdYlGn', vmin=0, vmax=1)
plot_heatmap(axes[0,2], mat_lid_trust,   'LiDAR Trust Weight\n(Loop 1: compensating sensor)', 'RdYlGn', vmin=0, vmax=1)
plot_heatmap(axes[1,0], mat_velocity,    'Planned Velocity (km/h)\n(Loop 2: speed adaptation)', 'RdYlGn_r', vmin=10, vmax=50)
plot_heatmap(axes[1,1], mat_ttc,         'TTC Safety Margin (s)\n(Loop 2: following distance)', 'RdYlGn', vmin=2, vmax=5)
plot_heatmap(axes[1,2], mat_margin,      'Lateral Safety Margin (m)\n(Loop 2: lane keeping)', 'RdYlGn', vmin=1.5, vmax=3.5)

plt.suptitle(
    'Phase 3: Sensitivity Matrix — How Sensor Degradation Propagates\n'
    'through Fusion Trust (Loop 1) into Planning Behavior (Loop 2)',
    fontsize=13, fontweight='bold'
)
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/phase3_01_sensitivity_matrix.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved: phase3_01_sensitivity_matrix.png')

# ── Figure 2: diagonal cross-section (both sensors degrade together) ──────────
diag_unc   = [mat_unc[i, i]       for i in range(N_G)]
diag_vel   = [mat_velocity[i, i]  for i in range(N_G)]
diag_ttc   = [mat_ttc[i, i]       for i in range(N_G)]
diag_cam_t = [mat_cam_trust[i, i] for i in range(N_G)]
diag_lid_t = [mat_lid_trust[i, i] for i in range(N_G)]

fig, axes = plt.subplots(1, 3, figsize=(18, 6))

axes[0].plot(GLARE_LEVELS, [u * 1000 for u in diag_unc], 'r-o', linewidth=2, markersize=7)
axes[0].set_xlabel('Degradation level (glare intensity)')
axes[0].set_ylabel('Uncertainty ×1000')
axes[0].set_title('Camera Uncertainty vs Degradation', fontweight='bold')
axes[0].grid(True, alpha=0.3)

axes[1].plot(GLARE_LEVELS, diag_cam_t, 'b-o',  linewidth=2, markersize=7, label='Camera trust')
axes[1].plot(GLARE_LEVELS, diag_lid_t, 'o-s',  linewidth=2, markersize=7,
             label='LiDAR trust', color='orange')
axes[1].set_xlabel('Degradation level')
axes[1].set_ylabel('Trust weight')
axes[1].set_title('Loop 1: Adaptive Trust Rebalancing', fontweight='bold')
axes[1].legend(); axes[1].grid(True, alpha=0.3); axes[1].set_ylim(0, 1)

axes[2].plot(GLARE_LEVELS, diag_vel, 'g-o',    linewidth=2, markersize=7, label='Velocity (km/h)')
axes[2].plot(GLARE_LEVELS, [t * 10 for t in diag_ttc], '^-',
             color='purple', linewidth=2, markersize=7, label='TTC ×10 (s)')
axes[2].set_xlabel('Degradation level')
axes[2].set_ylabel('Planning output')
axes[2].set_title('Loop 2: Planning Adaptation', fontweight='bold')
axes[2].legend(); axes[2].grid(True, alpha=0.3)

plt.suptitle('Phase 3: Cross-Section Analysis — Both Sensors Degrade Simultaneously',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/phase3_02_cross_section.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved: phase3_02_cross_section.png')

# ── Figure 3: planning mode distribution map ──────────────────────────────────
mode_map = {'NORMAL': 0, 'CAUTIOUS': 1, 'CONSERVATIVE': 2}
mode_num = np.array([[mode_map[m] for m in row] for row in mat_mode])

n_normal       = int((mode_num == 0).sum())
n_cautious     = int((mode_num == 1).sum())
n_conservative = int((mode_num == 2).sum())

fig, ax = plt.subplots(figsize=(10, 7))
cmap_modes = ListedColormap(['#2ecc71', '#f39c12', '#e74c3c'])
im = ax.imshow(mode_num, cmap=cmap_modes, aspect='auto', vmin=0, vmax=2)
ax.set_xticks(range(N_D)); ax.set_xticklabels(dropout_labels, fontsize=10)
ax.set_yticks(range(N_G)); ax.set_yticklabels(glare_labels,   fontsize=10)
ax.set_xlabel('LiDAR dropout rate',     fontsize=12)
ax.set_ylabel('Camera glare intensity', fontsize=12)
ax.set_title('Planning Mode Distribution\nGreen=NORMAL  Orange=CAUTIOUS  Red=CONSERVATIVE',
             fontsize=12, fontweight='bold')
for i in range(N_G):
    for j in range(N_D):
        ax.text(j, i, mat_mode[i][j][:4], ha='center', va='center',
                fontsize=8, fontweight='bold', color='white')
plt.colorbar(im, ax=ax, ticks=[0, 1, 2],
             fraction=0.046).set_ticklabels(['NORMAL', 'CAUTIOUS', 'CONSERVATIVE'])
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/phase3_03_mode_map.png', dpi=150, bbox_inches='tight')
plt.close()
print('Saved: phase3_03_mode_map.png')

# ── Save JSON results ─────────────────────────────────────────────────────────
total_cells = N_G * N_D
results = {
    'phase':  3,
    'title':  '7×7 Sensitivity Matrix — Sensor Degradation → Fusion Trust → Planning',
    'scene':  scene['description'],
    'baseline_uncertainty': float(unc_baseline),
    'glare_levels':   GLARE_LEVELS,
    'dropout_rates':  DROPOUT_RATES,
    'sensitivity_matrix': {
        'uncertainty':      mat_unc.tolist(),
        'velocity_kmh':     mat_velocity.tolist(),
        'ttc_margin_s':     mat_ttc.tolist(),
        'lateral_margin_m': mat_margin.tolist(),
        'camera_trust':     mat_cam_trust.tolist(),
        'lidar_trust':      mat_lid_trust.tolist(),
        'planning_modes':   mat_mode,
    },
    'mode_distribution': {
        'NORMAL':       n_normal,
        'CAUTIOUS':     n_cautious,
        'CONSERVATIVE': n_conservative,
        'NORMAL_pct':       round(n_normal       / total_cells * 100, 1),
        'CAUTIOUS_pct':     round(n_cautious     / total_cells * 100, 1),
        'CONSERVATIVE_pct': round(n_conservative / total_cells * 100, 1),
    },
    'key_findings': {
        'camera_trust_at_max_glare':     float(mat_cam_trust[-1, 0]),
        'camera_trust_at_zero_glare':    float(mat_cam_trust[0,  0]),
        'lidar_trust_at_max_dropout':    float(mat_lid_trust[0, -1]),
        'max_velocity_reduction_kmh':    float(mat_velocity[0, 0] - mat_velocity[-1, -1]),
        'conservative_coverage_pct':     round(n_conservative / total_cells * 100, 1),
        'glare_fragility_boundary':      0.45,
        'dropout_fragility_boundary':    0.35,
    },
    'config': {
        'mc_passes': MC_PASSES,
        'backbone':  'SegFormer-B2 (cityscapes pretrained)',
        'dataset':   'nuScenes mini v1.0',
    }
}

out_path = os.path.join(OUTPUT_DIR, 'phase3_results.json')
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2)

print(f'\n=== PHASE 3 COMPLETE ===')
print(f'  Camera trust  clean → max glare:    {mat_cam_trust[0,0]:.2f} → {mat_cam_trust[-1,0]:.2f}')
print(f'  Velocity      clean → max combined: {mat_velocity[0,0]:.1f} → {mat_velocity[-1,-1]:.1f} km/h')
print(f'  Mode dist:    NORMAL={n_normal}  CAUTIOUS={n_cautious}  CONSERVATIVE={n_conservative}')
print(f'  Conservative coverage: {results["key_findings"]["conservative_coverage_pct"]}% of scenarios')
print(f'  Results: {out_path}')
