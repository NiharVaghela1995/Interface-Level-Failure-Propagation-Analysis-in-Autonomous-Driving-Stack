"""
Phase 3: 7x7 Sensitivity Matrix — Sensor Degradation → Fusion Trust → Planning Mode
Run on RunPod with: python phase3_sensitivity.py
"""

import torch, numpy as np, matplotlib.pyplot as plt
import os, json, warnings
from PIL import Image
from nuscenes.nuscenes import NuScenes
from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
from pytorch_grad_cam.utils.image import show_cam_on_image
warnings.filterwarnings('ignore')

DATAROOT = '/workspace/av_research/data/nuscenes'
RESULTS  = '/workspace/av_research/results'
REPO     = '/workspace/av-perception-planning-research'
os.makedirs(RESULTS, exist_ok=True)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f'Device: {device} | {torch.cuda.get_device_name(0)}')

nusc = NuScenes('v1.0-mini', dataroot=DATAROOT)
scene = nusc.scene[0]
sample_token = scene['first_sample_token']
for _ in range(8):
    s = nusc.get('sample', sample_token)
    if s['next']: sample_token = s['next']
sample = nusc.get('sample', sample_token)
print(f'Scene: {scene["description"]}')

def load_cam(cam_name):
    d = nusc.get('sample_data', sample['data'][cam_name])
    return Image.open(os.path.join(DATAROOT, d['filename']))

def load_lidar():
    d = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
    return np.fromfile(os.path.join(DATAROOT, d['filename']), dtype=np.float32).reshape(-1,5)

def add_glare(img, intensity):
    arr = np.array(img, dtype=np.float32)
    h,w = arr.shape[:2]
    Y,X = np.ogrid[:h,:w]
    mask = np.exp(-((X-w//2)**2+(Y-h//3)**2)/(w*0.12)**2)
    return Image.fromarray(np.clip(arr+mask[:,:,None]*intensity*255,0,255).astype(np.uint8))

def lidar_dropout(pts, rate, seed=42):
    np.random.seed(seed)
    if rate == 0: return pts
    return pts[np.random.random(len(pts)) > rate]

img_clean   = load_cam('CAM_FRONT')
lidar_clean = load_lidar()

print('Loading SegFormer...')
proc  = SegformerImageProcessor.from_pretrained("nvidia/segformer-b2-finetuned-cityscapes-1024-1024")
model = SegformerForSemanticSegmentation.from_pretrained("nvidia/segformer-b2-finetuned-cityscapes-1024-1024").to(device).eval()
print('Model ready')

def mc_uncertainty(img, n=15):
    img_s = img.resize((512,512))
    inp   = proc(images=img_s, return_tensors='pt').to(device)
    model.train()
    preds = []
    with torch.no_grad():
        for _ in range(n):
            preds.append(torch.softmax(model(**inp).logits,dim=1).cpu().numpy())
    model.eval()
    preds = np.array(preds)
    var   = preds.var(axis=0)[0].mean(axis=0)
    conf  = float(preds.mean(axis=0)[0].max(axis=0).mean())
    return float(var.mean()), conf

def compute_trust(unc_val, unc_baseline, lidar_pts, lidar_baseline):
    unc_ratio  = unc_val / (unc_baseline + 1e-10)
    cam_trust  = 1.0 / (1.0 + np.exp(3.0 * (unc_ratio - 1.2)))
    lidar_ratio= len(lidar_pts) / (len(lidar_baseline) + 1e-10)
    lid_trust  = lidar_ratio ** 0.5
    total = cam_trust + lid_trust + 1e-8
    return cam_trust/total, lid_trust/total

class UAPlanner:
    def plan(self, cam_trust, lid_trust):
        combined = 1.0 - (0.6*cam_trust + 0.4*lid_trust)
        velocity = 50.0 * (1.0 - 0.8*combined)
        ttc      = 2.0  + 3.0*combined
        margin   = 1.5  + 2.0*combined
        mode = 'CONSERVATIVE' if combined > 0.5 else 'CAUTIOUS' if combined >= 0.25 else 'NORMAL'
        return {'velocity':velocity,'ttc':ttc,'margin':margin,'combined_unc':combined,'mode':mode}

planner = UAPlanner()

glare_levels  = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90]
dropout_rates = [0.0, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80]

print(f'\nRunning {len(glare_levels)}x{len(dropout_rates)} sensitivity sweep...')
unc_baseline, _ = mc_uncertainty(img_clean)
print(f'Baseline uncertainty: {unc_baseline:.6f}')

mat_unc      = np.zeros((len(glare_levels), len(dropout_rates)))
mat_conf     = np.zeros((len(glare_levels), len(dropout_rates)))
mat_velocity = np.zeros((len(glare_levels), len(dropout_rates)))
mat_ttc      = np.zeros((len(glare_levels), len(dropout_rates)))
mat_margin   = np.zeros((len(glare_levels), len(dropout_rates)))
mat_cam_trust= np.zeros((len(glare_levels), len(dropout_rates)))
mat_lid_trust= np.zeros((len(glare_levels), len(dropout_rates)))

for i, g in enumerate(glare_levels):
    for j, d in enumerate(dropout_rates):
        img_deg   = add_glare(img_clean, g) if g > 0 else img_clean
        lidar_deg = lidar_dropout(lidar_clean, d)
        unc, conf = mc_uncertainty(img_deg)
        ct, lt    = compute_trust(unc, unc_baseline, lidar_deg, lidar_clean)
        plan      = planner.plan(ct, lt)
        mat_unc[i,j]       = unc
        mat_conf[i,j]      = conf
        mat_velocity[i,j]  = plan['velocity']
        mat_ttc[i,j]       = plan['ttc']
        mat_margin[i,j]    = plan['margin']
        mat_cam_trust[i,j] = ct
        mat_lid_trust[i,j] = lt
        print(f'  g={g:.2f} d={d:.2f} -> unc={unc:.6f} cam={ct:.2f} lid={lt:.2f} v={plan["velocity"]:.1f}km/h mode={plan["mode"]}')

print('\nGenerating figures...')
glare_labels   = [f'{g:.2f}' for g in glare_levels]
dropout_labels = [f'{int(d*100)}%' for d in dropout_rates]

def plot_heatmap(ax, data, title, cmap, vmin=None, vmax=None):
    im = ax.imshow(data, cmap=cmap, aspect='auto', vmin=vmin, vmax=vmax)
    ax.set_xticks(range(len(dropout_rates))); ax.set_xticklabels(dropout_labels, fontsize=9)
    ax.set_yticks(range(len(glare_levels)));  ax.set_yticklabels(glare_labels, fontsize=9)
    ax.set_xlabel('LiDAR dropout rate', fontsize=10)
    ax.set_ylabel('Camera glare intensity', fontsize=10)
    ax.set_title(title, fontsize=11, fontweight='bold')
    plt.colorbar(im, ax=ax, fraction=0.046)
    for ii in range(len(glare_levels)):
        for jj in range(len(dropout_rates)):
            ax.text(jj, ii, f'{data[ii,jj]:.2f}', ha='center', va='center',
                    fontsize=7, color='white' if data[ii,jj] < data.mean() else 'black')

fig, axes = plt.subplots(2, 3, figsize=(20, 12))
plot_heatmap(axes[0,0], mat_unc*1000,   'Camera Uncertainty x1000', 'hot')
plot_heatmap(axes[0,1], mat_cam_trust,  'Camera Trust (Loop 1)', 'RdYlGn', vmin=0, vmax=1)
plot_heatmap(axes[0,2], mat_lid_trust,  'LiDAR Trust (Loop 1)',  'RdYlGn', vmin=0, vmax=1)
plot_heatmap(axes[1,0], mat_velocity,   'Planned Velocity (km/h)', 'RdYlGn_r', vmin=10, vmax=50)
plot_heatmap(axes[1,1], mat_ttc,        'TTC Safety Margin (s)',   'RdYlGn', vmin=2, vmax=5)
plot_heatmap(axes[1,2], mat_margin,     'Lateral Margin (m)',      'RdYlGn', vmin=1.5, vmax=3.5)
plt.suptitle('Phase 3: Sensitivity Matrix — Sensor Degradation → Fusion Trust → Planning', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{RESULTS}/phase3_01_sensitivity_matrix.png', dpi=150, bbox_inches='tight')
print('Saved: phase3_01_sensitivity_matrix.png')

diag_unc      = [mat_unc[i,i]       for i in range(len(glare_levels))]
diag_velocity = [mat_velocity[i,i]  for i in range(len(glare_levels))]
diag_ttc      = [mat_ttc[i,i]       for i in range(len(glare_levels))]
diag_cam_t    = [mat_cam_trust[i,i] for i in range(len(glare_levels))]
diag_lid_t    = [mat_lid_trust[i,i] for i in range(len(glare_levels))]

fig, axes = plt.subplots(1, 3, figsize=(18, 6))
axes[0].plot(glare_levels, [u*1000 for u in diag_unc], 'r-o', linewidth=2, markersize=7)
axes[0].set_xlabel('Degradation level'); axes[0].set_ylabel('Uncertainty x1000')
axes[0].set_title('Camera Uncertainty vs Degradation', fontweight='bold'); axes[0].grid(True, alpha=0.3)
axes[1].plot(glare_levels, diag_cam_t, 'b-o', linewidth=2, markersize=7, label='Camera trust')
axes[1].plot(glare_levels, diag_lid_t, 'orange', marker='s', linewidth=2, markersize=7, label='LiDAR trust')
axes[1].set_xlabel('Degradation level'); axes[1].set_ylabel('Trust weight')
axes[1].set_title('Loop 1: Adaptive Trust Rebalancing', fontweight='bold')
axes[1].legend(); axes[1].grid(True, alpha=0.3); axes[1].set_ylim(0,1)
axes[2].plot(glare_levels, diag_velocity, 'g-o', linewidth=2, markersize=7, label='Velocity (km/h)')
axes[2].plot(glare_levels, [t*10 for t in diag_ttc], 'purple', marker='^', linewidth=2, markersize=7, label='TTC x10 (s)')
axes[2].set_xlabel('Degradation level'); axes[2].set_ylabel('Planning output')
axes[2].set_title('Loop 2: Planning Adaptation', fontweight='bold')
axes[2].legend(); axes[2].grid(True, alpha=0.3)
plt.suptitle('Phase 3: Cross-Section — Both Sensors Degrade Simultaneously', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{RESULTS}/phase3_02_cross_section.png', dpi=150, bbox_inches='tight')
print('Saved: phase3_02_cross_section.png')

modes = []
for i in range(len(glare_levels)):
    row = []
    for j in range(len(dropout_rates)):
        plan = planner.plan(mat_cam_trust[i,j], mat_lid_trust[i,j])
        row.append(plan['mode'])
    modes.append(row)

mode_map = {'NORMAL':0,'CAUTIOUS':1,'CONSERVATIVE':2}
mode_num  = np.array([[mode_map[m] for m in row] for row in modes])
from matplotlib.colors import ListedColormap
fig, ax = plt.subplots(figsize=(10,7))
cmap = ListedColormap(['#2ecc71','#f39c12','#e74c3c'])
im = ax.imshow(mode_num, cmap=cmap, aspect='auto', vmin=0, vmax=2)
ax.set_xticks(range(len(dropout_rates))); ax.set_xticklabels(dropout_labels, fontsize=10)
ax.set_yticks(range(len(glare_levels)));  ax.set_yticklabels(glare_labels, fontsize=10)
ax.set_xlabel('LiDAR dropout rate', fontsize=12); ax.set_ylabel('Camera glare intensity', fontsize=12)
ax.set_title('Planning Mode Distribution\nGreen=NORMAL  Orange=CAUTIOUS  Red=CONSERVATIVE', fontsize=12, fontweight='bold')
for i in range(len(glare_levels)):
    for j in range(len(dropout_rates)):
        ax.text(j, i, modes[i][j][:4], ha='center', va='center', fontsize=8, fontweight='bold', color='white')
plt.colorbar(im, ax=ax, ticks=[0,1,2], fraction=0.046).set_ticklabels(['NORMAL','CAUTIOUS','CONSERVATIVE'])
plt.tight_layout()
plt.savefig(f'{RESULTS}/phase3_03_mode_map.png', dpi=150, bbox_inches='tight')
print('Saved: phase3_03_mode_map.png')

results = {
    'phase':3, 'scene':scene['description'],
    'baseline_uncertainty': unc_baseline,
    'glare_levels': glare_levels,
    'dropout_rates': dropout_rates,
    'sensitivity_matrix': {
        'uncertainty': mat_unc.tolist(),
        'velocity_kmh': mat_velocity.tolist(),
        'ttc_margin_s': mat_ttc.tolist(),
        'lateral_margin_m': mat_margin.tolist(),
        'camera_trust': mat_cam_trust.tolist(),
        'lidar_trust': mat_lid_trust.tolist(),
    },
    'key_findings': {
        'max_velocity_reduction_kmh': float(mat_velocity[0,0]-mat_velocity[-1,-1]),
        'camera_trust_at_max_glare': float(mat_cam_trust[-1,0]),
        'lidar_trust_at_max_dropout': float(mat_lid_trust[0,-1]),
    }
}
with open(f'{RESULTS}/phase3_results.json','w') as f:
    json.dump(results,f,indent=2)

print('\n=== PHASE 3 COMPLETE ===')
print(f'Camera trust at max glare:   {results["key_findings"]["camera_trust_at_max_glare"]:.2f}')
print(f'LiDAR trust at max dropout:  {results["key_findings"]["lidar_trust_at_max_dropout"]:.2f}')
