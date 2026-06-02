"""
scripts/phase6_injection.py
============================
Phase B (Phase 6): Interface-Level Failure Injection Framework

Research contribution:
  Injects synthetic failures at 4 specific interface points in the AV
  perception-planning pipeline. Measures how injected failures propagate
  downstream using the Failure Propagation Coefficient (FPC).

  FPC > 1.0 → interface AMPLIFIES failures (fragile boundary)
  FPC = 1.0 → failure transmitted unchanged
  FPC < 1.0 → interface ATTENUATES failures (robust boundary)
  FPC = 0.0 → failure fully isolated

Interface injection points:
  IP1 — Sensor input      (already characterized in Phases 1–5)
  IP2 — Perception output (corrupt SegFormer logits / feature map)
  IP3 — Trust output      (corrupt Loop 1 trust weights before planning)
  IP4 — Planning output   (corrupt planned velocity before execution)

SOTIF trigger scenarios tested (from Phase 4a):
  T1 — Direct sunlight / glare        (glare=0.45, dropout=0.0)
  T2 — Rain / LiDAR dropout           (glare=0.0,  dropout=0.35)
  T3 — Combined glare + rain          (glare=0.45, dropout=0.35)
  T4 — Pedestrian + degraded sensors  (glare=0.60, dropout=0.50)
  T5 — Extreme combined failure       (glare=0.75, dropout=0.65)

Usage:
  NUSCENES_DATAROOT=/data/nuscenes python scripts/phase6_injection.py
"""

import os
import sys
import json
import warnings
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sensor_degradation import apply_glare, apply_lidar_dropout
from utils.uncertainty import mc_dropout_passes, enable_dropout, uncertainty_scalar
from utils.trust import mc_trust, rebalance_trust, trust_to_planning_mode
from utils.planning import frenet_planner, planning_delta, PLANNING_PARAMS
from utils.metrics import (propagation_coefficient, normalize_delta,
                            interface_fragility_score)

# ── Config ────────────────────────────────────────────────────────────────────
NUSCENES_DATAROOT = os.environ.get('NUSCENES_DATAROOT', '/data/nuscenes')
OUTPUT_DIR        = os.environ.get('OUTPUT_DIR', 'reports')
SCREENSHOTS_DIR   = 'screenshots/phase6'
SAMPLE_ADVANCE    = 8
MC_PASSES         = 15
INJECTION_SEED    = 42

import torch
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ── SOTIF trigger scenario definitions (from Phase 4a) ───────────────────────
SOTIF_SCENARIOS = {
    'T1': {'name': 'Direct sunlight / glare',
           'glare': 0.45, 'dropout': 0.00,
           'asil': 'ASIL B', 'sotif_region': 'Known unsafe'},
    'T2': {'name': 'Rain / LiDAR dropout',
           'glare': 0.00, 'dropout': 0.35,
           'asil': 'ASIL C', 'sotif_region': 'Known unsafe'},
    'T3': {'name': 'Combined glare + rain',
           'glare': 0.45, 'dropout': 0.35,
           'asil': 'ASIL C', 'sotif_region': 'Unknown unsafe'},
    'T4': {'name': 'Pedestrian + degraded sensors',
           'glare': 0.60, 'dropout': 0.50,
           'asil': 'ASIL D', 'sotif_region': 'Unknown unsafe'},
    'T5': {'name': 'Extreme combined failure',
           'glare': 0.75, 'dropout': 0.65,
           'asil': 'ASIL D', 'sotif_region': 'Unknown unsafe'},
}

# Injection severities: low / medium / high
INJECTION_SEVERITIES = [0.25, 0.50, 0.75]

# ── Data structures ───────────────────────────────────────────────────────────
@dataclass
class InjectionResult:
    scenario_id:      str
    scenario_name:    str
    injection_point:  str    # IP1 / IP2 / IP3 / IP4
    severity:         float
    # Upstream (at injection point)
    injected_delta:   float  # normalized magnitude of injected perturbation
    # Downstream (measured at planning output)
    velocity_clean:   float
    velocity_degraded: float
    delta_velocity:   float
    ttc_clean:        float
    ttc_degraded:     float
    delta_ttc:        float
    mode_clean:       str
    mode_degraded:    str
    mode_changed:     bool
    # Propagation metric
    fpc:              float  # Failure Propagation Coefficient


# ── Load nuScenes + model (shared across all injection runs) ──────────────────
from nuscenes.nuscenes import NuScenes
from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

print("Loading nuScenes mini...")
nusc = NuScenes('v1.0-mini', dataroot=NUSCENES_DATAROOT)
scene = nusc.scene[0]
sample_token = scene['first_sample_token']
for _ in range(SAMPLE_ADVANCE):
    s = nusc.get('sample', sample_token)
    if s['next']:
        sample_token = s['next']
sample = nusc.get('sample', sample_token)

cam_data  = nusc.get('sample_data', sample['data']['CAM_FRONT'])
lid_data  = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
img_base  = Image.open(os.path.join(NUSCENES_DATAROOT, cam_data['filename'])).convert('RGB')
pts_base  = np.fromfile(os.path.join(NUSCENES_DATAROOT, lid_data['filename']),
                        dtype=np.float32).reshape(-1, 5)

print(f"Scene: {scene['description']}")
print(f"LiDAR points: {len(pts_base)}")

print("Loading SegFormer-B2...")
proc  = SegformerImageProcessor.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024")
model = SegformerForSemanticSegmentation.from_pretrained(
    "nvidia/segformer-b2-finetuned-cityscapes-1024-1024").to(DEVICE).eval()
print(f"Model ready on {DEVICE}")


# ── Core inference: clean pipeline (no injection) ────────────────────────────
def run_clean_pipeline(img: Image.Image, lidar_pts: np.ndarray,
                       unc_baseline: float) -> Dict:
    """Run full pipeline on clean/scenario inputs. Returns all intermediate values."""
    img_s  = img.resize((512, 512))
    inputs = proc(images=img_s, return_tensors='pt')
    enable_dropout(model)
    _, _, unc_t = mc_dropout_passes(model, inputs, n_passes=MC_PASSES, device=DEVICE)
    model.eval()
    unc = float(unc_t.mean().item())

    cam_t, lid_t = rebalance_trust(
        camera_raw_trust   = mc_trust(unc, unc_baseline),
        lidar_dropout_rate = 0.0
    )
    mode = trust_to_planning_mode(cam_t, lid_t)
    plan = frenet_planner(mode, cam_t, lid_t)

    return {
        'uncertainty': unc,
        'camera_trust': cam_t,
        'lidar_trust':  lid_t,
        'mode':         mode,
        'plan':         plan,
        # Store logits for IP2 injection
        '_logits': _get_logits(img_s),
    }


def _get_logits(img_s: Image.Image) -> torch.Tensor:
    """Get raw logits for IP2 injection."""
    inputs = proc(images=img_s, return_tensors='pt').to(DEVICE)
    with torch.no_grad():
        logits = model(**inputs).logits
    return logits.cpu()


# ── Injection Point 2: Corrupt perception output (logits) ────────────────────
def inject_ip2(img: Image.Image, lidar_pts: np.ndarray,
               severity: float, unc_baseline: float,
               rng: np.random.Generator) -> Dict:
    """
    IP2: Add structured noise to SegFormer logits before trust computation.
    Simulates: quantization error, feature map corruption, adversarial
               perturbation, domain shift in perception backbone.

    Injection: logits += N(0, severity × logit_std) per spatial location
    """
    img_s   = img.resize((512, 512))
    logits  = _get_logits(img_s)

    # Structured noise proportional to logit magnitude
    noise_std = float(logits.std().item()) * severity
    noise     = torch.tensor(
        rng.normal(0, noise_std, logits.shape).astype(np.float32)
    )
    logits_corrupted = logits + noise

    # Compute uncertainty from corrupted logits (variance of softmax)
    probs_corrupted = torch.softmax(logits_corrupted, dim=1)
    unc_corrupted   = float(probs_corrupted.var(dim=1).mean().item())

    # Propagate through Loop 1 and Loop 2
    cam_t, lid_t = rebalance_trust(
        camera_raw_trust   = mc_trust(unc_corrupted, unc_baseline),
        lidar_dropout_rate = 0.0
    )
    mode = trust_to_planning_mode(cam_t, lid_t)
    plan = frenet_planner(mode, cam_t, lid_t)

    return {
        'uncertainty':  unc_corrupted,
        'camera_trust': cam_t,
        'lidar_trust':  lid_t,
        'mode':         mode,
        'plan':         plan,
        'noise_std':    noise_std,
    }


# ── Injection Point 3: Corrupt trust weights ─────────────────────────────────
def inject_ip3(clean_state: Dict, severity: float,
               rng: np.random.Generator) -> Dict:
    """
    IP3: Directly perturb Loop 1 trust weights before they reach the planner.
    Simulates: fusion module failure, incorrect calibration, sensor
               misidentification, trust model mismatch.

    Injection: camera_trust *= (1 - severity × U[0,1])
               trust weights renormalized to sum = 1
    """
    cam_t_clean = clean_state['camera_trust']
    lid_t_clean = clean_state['lidar_trust']

    # Attenuate camera trust by severity
    perturbation = rng.uniform(0, severity)
    cam_t_corrupted = cam_t_clean * (1.0 - perturbation)
    cam_t_corrupted = max(cam_t_corrupted, 0.05)

    # Renormalize
    total = cam_t_corrupted + lid_t_clean
    cam_t = cam_t_corrupted / total
    lid_t = lid_t_clean / total

    mode = trust_to_planning_mode(cam_t, lid_t)
    plan = frenet_planner(mode, cam_t, lid_t)

    return {
        'uncertainty':  clean_state['uncertainty'],
        'camera_trust': cam_t,
        'lidar_trust':  lid_t,
        'mode':         mode,
        'plan':         plan,
        'perturbation': perturbation,
    }


# ── Injection Point 4: Corrupt planning output ────────────────────────────────
def inject_ip4(clean_state: Dict, severity: float,
               rng: np.random.Generator) -> Dict:
    """
    IP4: Perturb the planned velocity/trajectory before execution.
    Simulates: trajectory optimizer failure, motion primitive mismatch,
               actuator latency, numerical instability in planner.

    Injection: velocity += N(0, severity × 5.0 km/h)
               clipped to [0, 50] km/h operational range
    """
    clean_plan = clean_state['plan']

    vel_noise   = rng.normal(0, severity * 5.0)
    vel_corrupt = float(np.clip(
        clean_plan['velocity_kmh'] + vel_noise, 0, 50
    ))

    # Rebuild plan with corrupted velocity
    corrupted_plan = dict(clean_plan)
    corrupted_plan['velocity_kmh'] = vel_corrupt

    # Determine implied mode from corrupted velocity
    if vel_corrupt < 20:
        corrupted_plan['mode'] = 'EMERGENCY'
    elif vel_corrupt < 30:
        corrupted_plan['mode'] = 'CONSERVATIVE'
    elif vel_corrupt < 40:
        corrupted_plan['mode'] = 'CAUTIOUS'
    else:
        corrupted_plan['mode'] = 'NORMAL'

    return {
        'uncertainty':  clean_state['uncertainty'],
        'camera_trust': clean_state['camera_trust'],
        'lidar_trust':  clean_state['lidar_trust'],
        'mode':         corrupted_plan['mode'],
        'plan':         corrupted_plan,
        'vel_noise':    vel_noise,
    }


# ── Full injection sweep ──────────────────────────────────────────────────────
def compute_fpc(clean_state: Dict, corrupted_state: Dict,
                injected_delta_normalized: float) -> float:
    """
    Compute FPC from clean and corrupted pipeline states.
    Uses velocity as the primary downstream measurement.
    """
    downstream_delta = abs(
        corrupted_state['plan']['velocity_kmh'] -
        clean_state['plan']['velocity_kmh']
    )
    downstream_normalized = normalize_delta(downstream_delta, 'velocity_kmh')
    return propagation_coefficient(injected_delta_normalized, downstream_normalized)


print("\nComputing clean baseline uncertainty...")
img_base_s     = img_base.resize((512, 512))
inputs_base    = proc(images=img_base_s, return_tensors='pt')
enable_dropout(model)
_, _, unc_base_t = mc_dropout_passes(model, inputs_base, n_passes=MC_PASSES, device=DEVICE)
model.eval()
unc_baseline = float(unc_base_t.mean().item())
print(f"Baseline uncertainty: {unc_baseline:.6f}")

# Run sweep: 5 scenarios × 3 injection points (IP2–IP4) × 3 severities
# IP1 already covered by Phases 1–5
all_results: List[InjectionResult] = []

print(f"\nRunning injection sweep: {len(SOTIF_SCENARIOS)} scenarios × "
      f"3 injection points × {len(INJECTION_SEVERITIES)} severities...\n")

for t_id, scenario in SOTIF_SCENARIOS.items():
    print(f"{'='*60}")
    print(f"Scenario {t_id}: {scenario['name']} "
          f"(glare={scenario['glare']}, dropout={scenario['dropout']})")
    print(f"  SOTIF region: {scenario['sotif_region']} | ASIL: {scenario['asil']}")

    # Apply scenario-level sensor degradation (IP1)
    img_scenario  = apply_glare(img_base, intensity=scenario['glare']) \
                    if scenario['glare'] > 0 else img_base
    pts_scenario  = apply_lidar_dropout(pts_base, dropout_rate=scenario['dropout'],
                                        rng=np.random.default_rng(INJECTION_SEED)) \
                    if scenario['dropout'] > 0 else pts_base

    # Clean pipeline state for this scenario
    clean_state = run_clean_pipeline(img_scenario, pts_scenario, unc_baseline)
    print(f"  Clean state: unc={clean_state['uncertainty']:.6f} "
          f"cam={clean_state['camera_trust']:.3f} "
          f"mode={clean_state['mode']} "
          f"v={clean_state['plan']['velocity_kmh']:.1f} km/h")

    for sev in INJECTION_SEVERITIES:
        rng = np.random.default_rng(INJECTION_SEED + int(sev * 100))

        # ── IP2: Perception output injection ──────────────────────────────
        ip2_state = inject_ip2(img_scenario, pts_scenario, sev, unc_baseline, rng)
        ip2_injected_delta = normalize_delta(
            abs(ip2_state['uncertainty'] - clean_state['uncertainty']), 'uncertainty')
        ip2_fpc = compute_fpc(clean_state, ip2_state, ip2_injected_delta)
        delta_ip2 = planning_delta(clean_state['plan'], ip2_state['plan'])

        all_results.append(InjectionResult(
            scenario_id=t_id, scenario_name=scenario['name'],
            injection_point='IP2', severity=sev,
            injected_delta=ip2_injected_delta,
            velocity_clean=clean_state['plan']['velocity_kmh'],
            velocity_degraded=ip2_state['plan']['velocity_kmh'],
            delta_velocity=delta_ip2['delta_velocity_kmh'],
            ttc_clean=clean_state['plan']['ttc_margin_s'],
            ttc_degraded=ip2_state['plan']['ttc_margin_s'],
            delta_ttc=delta_ip2['delta_ttc_s'],
            mode_clean=clean_state['mode'],
            mode_degraded=ip2_state['mode'],
            mode_changed=delta_ip2['mode_changed'],
            fpc=ip2_fpc,
        ))
        print(f"  IP2 sev={sev:.2f}: unc_delta={ip2_injected_delta:.3f} "
              f"Δv={delta_ip2['delta_velocity_kmh']:+.1f} "
              f"mode_change={delta_ip2['mode_changed']} FPC={ip2_fpc:.3f}")

        # ── IP3: Trust weight injection ────────────────────────────────────
        ip3_state = inject_ip3(clean_state, sev, rng)
        ip3_injected_delta = normalize_delta(
            abs(ip3_state['camera_trust'] - clean_state['camera_trust']), 'trust')
        ip3_fpc = compute_fpc(clean_state, ip3_state, ip3_injected_delta)
        delta_ip3 = planning_delta(clean_state['plan'], ip3_state['plan'])

        all_results.append(InjectionResult(
            scenario_id=t_id, scenario_name=scenario['name'],
            injection_point='IP3', severity=sev,
            injected_delta=ip3_injected_delta,
            velocity_clean=clean_state['plan']['velocity_kmh'],
            velocity_degraded=ip3_state['plan']['velocity_kmh'],
            delta_velocity=delta_ip3['delta_velocity_kmh'],
            ttc_clean=clean_state['plan']['ttc_margin_s'],
            ttc_degraded=ip3_state['plan']['ttc_margin_s'],
            delta_ttc=delta_ip3['delta_ttc_s'],
            mode_clean=clean_state['mode'],
            mode_degraded=ip3_state['mode'],
            mode_changed=delta_ip3['mode_changed'],
            fpc=ip3_fpc,
        ))
        print(f"  IP3 sev={sev:.2f}: trust_delta={ip3_injected_delta:.3f} "
              f"Δv={delta_ip3['delta_velocity_kmh']:+.1f} "
              f"mode_change={delta_ip3['mode_changed']} FPC={ip3_fpc:.3f}")

        # ── IP4: Planning output injection ────────────────────────────────
        ip4_state = inject_ip4(clean_state, sev, rng)
        ip4_injected_delta = normalize_delta(
            abs(ip4_state['plan']['velocity_kmh'] - clean_state['plan']['velocity_kmh']),
            'velocity_kmh')
        ip4_fpc = compute_fpc(clean_state, ip4_state, ip4_injected_delta)
        delta_ip4 = planning_delta(clean_state['plan'], ip4_state['plan'])

        all_results.append(InjectionResult(
            scenario_id=t_id, scenario_name=scenario['name'],
            injection_point='IP4', severity=sev,
            injected_delta=ip4_injected_delta,
            velocity_clean=clean_state['plan']['velocity_kmh'],
            velocity_degraded=ip4_state['plan']['velocity_kmh'],
            delta_velocity=delta_ip4['delta_velocity_kmh'],
            ttc_clean=clean_state['plan']['ttc_margin_s'],
            ttc_degraded=ip4_state['plan']['ttc_margin_s'],
            delta_ttc=delta_ip4['delta_ttc_s'],
            mode_clean=clean_state['mode'],
            mode_degraded=ip4_state['mode'],
            mode_changed=delta_ip4['mode_changed'],
            fpc=ip4_fpc,
        ))
        print(f"  IP4 sev={sev:.2f}: vel_delta={ip4_injected_delta:.3f} "
              f"Δv={delta_ip4['delta_velocity_kmh']:+.1f} "
              f"mode_change={delta_ip4['mode_changed']} FPC={ip4_fpc:.3f}")

print(f"\nSweep complete. {len(all_results)} total injection runs.")

# ── Build FPC summary matrices ────────────────────────────────────────────────
injection_points = ['IP2', 'IP3', 'IP4']
scenario_ids     = list(SOTIF_SCENARIOS.keys())

# Mean FPC per (scenario × injection_point) across severities
fpc_matrix = np.zeros((len(scenario_ids), len(injection_points)))
for i, t_id in enumerate(scenario_ids):
    for j, ip in enumerate(injection_points):
        fpcs = [r.fpc for r in all_results
                if r.scenario_id == t_id and r.injection_point == ip]
        fpc_matrix[i, j] = np.mean(fpcs) if fpcs else 0.0

# Mode change rate per (scenario × injection_point)
mode_change_matrix = np.zeros((len(scenario_ids), len(injection_points)))
for i, t_id in enumerate(scenario_ids):
    for j, ip in enumerate(injection_points):
        changes = [r.mode_changed for r in all_results
                   if r.scenario_id == t_id and r.injection_point == ip]
        mode_change_matrix[i, j] = np.mean(changes) if changes else 0.0

# Per-injection-point fragility scores (utils)
ip_fragility = {}
for ip in injection_points:
    fpcs = [r.fpc for r in all_results if r.injection_point == ip]
    ip_fragility[ip] = interface_fragility_score(fpcs)

print("\n=== INTERFACE FRAGILITY SUMMARY ===")
for ip, score in ip_fragility.items():
    flag = "⚠ FRAGILE" if score['fragile'] else "✓ robust"
    print(f"  {ip}: mean_FPC={score['mean_fpc']:.3f}  "
          f"max_FPC={score['max_fpc']:.3f}  {flag}")

# ── Figure 1: FPC matrix + mode change matrix ─────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# FPC heatmap
im1 = axes[0].imshow(fpc_matrix, cmap='RdYlGn_r', aspect='auto', vmin=0, vmax=2)
axes[0].set_xticks(range(len(injection_points)))
axes[0].set_xticklabels(injection_points, fontsize=11)
axes[0].set_yticks(range(len(scenario_ids)))
axes[0].set_yticklabels(
    [f"{t_id}: {SOTIF_SCENARIOS[t_id]['name'][:25]}" for t_id in scenario_ids],
    fontsize=9)
axes[0].set_title('Failure Propagation Coefficient\n(FPC > 1.0 = fragile interface)',
                  fontweight='bold', fontsize=11)
plt.colorbar(im1, ax=axes[0], fraction=0.046)
for i in range(len(scenario_ids)):
    for j in range(len(injection_points)):
        v = fpc_matrix[i, j]
        axes[0].text(j, i, f'{v:.2f}', ha='center', va='center',
                    fontsize=11, fontweight='bold',
                    color='white' if v > 1.0 else 'black')

# Mode change rate heatmap
im2 = axes[1].imshow(mode_change_matrix, cmap='RdYlGn_r', aspect='auto', vmin=0, vmax=1)
axes[1].set_xticks(range(len(injection_points)))
axes[1].set_xticklabels(injection_points, fontsize=11)
axes[1].set_yticks(range(len(scenario_ids)))
axes[1].set_yticklabels([t_id for t_id in scenario_ids], fontsize=10)
axes[1].set_title('Planning Mode Change Rate\n(fraction of severity levels causing mode switch)',
                  fontweight='bold', fontsize=11)
plt.colorbar(im2, ax=axes[1], fraction=0.046)
for i in range(len(scenario_ids)):
    for j in range(len(injection_points)):
        v = mode_change_matrix[i, j]
        axes[1].text(j, i, f'{v:.0%}', ha='center', va='center',
                    fontsize=11, fontweight='bold',
                    color='white' if v > 0.5 else 'black')

# Per-IP fragility bar chart
means = [ip_fragility[ip]['mean_fpc'] for ip in injection_points]
maxes = [ip_fragility[ip]['max_fpc']  for ip in injection_points]
x = np.arange(len(injection_points))
bars = axes[2].bar(x, means, 0.5,
                   color=['#e74c3c' if f['fragile'] else '#2ecc71'
                          for f in ip_fragility.values()],
                   alpha=0.8, label='Mean FPC')
axes[2].scatter(x, maxes, color='black', zorder=5, s=80, label='Max FPC')
axes[2].axhline(1.0, color='gray', linestyle='--', linewidth=2, alpha=0.8,
                label='FPC=1.0 (neutral)')
axes[2].set_xticks(x)
axes[2].set_xticklabels(
    [f"{ip}\n({'FRAGILE' if ip_fragility[ip]['fragile'] else 'robust'})"
     for ip in injection_points], fontsize=10)
axes[2].set_ylabel('Failure Propagation Coefficient')
axes[2].set_title('Interface Fragility Summary\nRed = FPC > 1.0 (amplifies failures)',
                  fontweight='bold', fontsize=11)
axes[2].legend(fontsize=9); axes[2].grid(True, alpha=0.3, axis='y')
for bar, v in zip(bars, means):
    axes[2].text(bar.get_x() + bar.get_width()/2, v + 0.02,
                f'{v:.3f}', ha='center', fontsize=10, fontweight='bold')

plt.suptitle('Phase 6: Interface-Level Failure Propagation Analysis\n'
             'FPC measures how injected upstream failures amplify at downstream interfaces',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/phase6_01_fpc_matrix.png', dpi=150, bbox_inches='tight')
plt.close()
print("Saved: phase6_01_fpc_matrix.png")

# ── Figure 2: FPC vs severity per injection point ────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

colors_t = plt.cm.Set1(np.linspace(0, 1, len(scenario_ids)))

for j, ip in enumerate(injection_points):
    for i, t_id in enumerate(scenario_ids):
        sev_vals, fpc_vals = [], []
        for r in all_results:
            if r.scenario_id == t_id and r.injection_point == ip:
                sev_vals.append(r.severity)
                fpc_vals.append(r.fpc)
        if sev_vals:
            axes[j].plot(sev_vals, fpc_vals, 'o-',
                        color=colors_t[i], linewidth=2, markersize=8,
                        label=f"{t_id} ({SOTIF_SCENARIOS[t_id]['asil']})")

    axes[j].axhline(1.0, color='gray', linestyle='--', lw=2, alpha=0.7,
                   label='FPC=1.0 (neutral)')
    axes[j].fill_between([0.2, 0.8], [1.0, 1.0], [3.0, 3.0],
                         alpha=0.05, color='red', label='Fragile zone')
    axes[j].set_xlabel('Injection severity'); axes[j].set_ylabel('FPC')
    axes[j].set_title(f'{ip}: FPC vs Injection Severity\n'
                     f'(fragility={ip_fragility[ip]["mean_fpc"]:.3f} mean)',
                     fontweight='bold', fontsize=11)
    axes[j].legend(fontsize=8); axes[j].grid(True, alpha=0.3)
    axes[j].set_ylim(0, max(3.0, max(r.fpc for r in all_results
                                      if r.injection_point == ip) + 0.5))

plt.suptitle('Phase 6: FPC vs Injection Severity per Interface Point\n'
             'How fragility scales with perturbation magnitude',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/phase6_02_fpc_vs_severity.png', dpi=150, bbox_inches='tight')
plt.close()
print("Saved: phase6_02_fpc_vs_severity.png")

# ── Figure 3: Propagation chain visualization ─────────────────────────────────
fig, axes = plt.subplots(len(SOTIF_SCENARIOS), 1, figsize=(16, 4 * len(SOTIF_SCENARIOS)))

for idx, (t_id, scenario) in enumerate(SOTIF_SCENARIOS.items()):
    ax = axes[idx]
    # For each injection point, get mean velocity delta across severities
    ip_deltas = {}
    for ip in ['IP1'] + injection_points:
        if ip == 'IP1':
            # IP1 = sensor-level delta (clean baseline vs scenario baseline)
            clean_run = run_clean_pipeline(img_base, pts_base, unc_baseline)
            scen_img  = apply_glare(img_base, scenario['glare']) \
                        if scenario['glare'] > 0 else img_base
            scen_pts  = apply_lidar_dropout(pts_base, scenario['dropout'],
                                            rng=np.random.default_rng(INJECTION_SEED)) \
                        if scenario['dropout'] > 0 else pts_base
            scen_run  = run_clean_pipeline(scen_img, scen_pts, unc_baseline)
            ip_deltas['IP1'] = abs(scen_run['plan']['velocity_kmh'] -
                                   clean_run['plan']['velocity_kmh'])
        else:
            deltas = [abs(r.delta_velocity) for r in all_results
                      if r.scenario_id == t_id and r.injection_point == ip]
            ip_deltas[ip] = np.mean(deltas) if deltas else 0.0

    ip_labels = ['IP1\n(Sensor\ninput)', 'IP2\n(Perception\noutput)',
                 'IP3\n(Trust\nweights)', 'IP4\n(Planning\noutput)']
    ip_keys   = ['IP1', 'IP2', 'IP3', 'IP4']
    delta_vals = [ip_deltas.get(k, 0) for k in ip_keys]
    bar_c = ['#3498db', '#e67e22', '#e74c3c', '#9b59b6']

    bars = ax.bar(range(4), delta_vals, color=bar_c, alpha=0.85, width=0.6)
    ax.set_xticks(range(4)); ax.set_xticklabels(ip_labels, fontsize=10)
    ax.set_ylabel('Mean |Δvelocity| km/h')
    ax.set_title(f'{t_id}: {scenario["name"]} | {scenario["asil"]} | {scenario["sotif_region"]}',
                fontweight='bold', fontsize=11)
    ax.grid(True, alpha=0.3, axis='y')
    for bar, v in zip(bars, delta_vals):
        ax.text(bar.get_x() + bar.get_width()/2, v + 0.1,
               f'{v:.1f}', ha='center', fontsize=10, fontweight='bold')

    # Arrow showing propagation chain
    for k in range(3):
        ax.annotate('', xy=(k+1-0.1, max(delta_vals)*0.5),
                   xytext=(k+0.1, max(delta_vals)*0.5),
                   arrowprops=dict(arrowstyle='->', color='gray', lw=2))

plt.suptitle('Phase 6: Failure Propagation Chain per SOTIF Scenario\n'
             'Mean |Δvelocity| at each interface injection point',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(f'{SCREENSHOTS_DIR}/phase6_03_propagation_chain.png', dpi=150, bbox_inches='tight')
plt.close()
print("Saved: phase6_03_propagation_chain.png")

# ── Save JSON results ─────────────────────────────────────────────────────────
results_json = {
    'phase': '6',
    'title': 'Interface-Level Failure Propagation Analysis',
    'methodology': {
        'injection_points': {
            'IP1': 'Sensor input (characterized in Phases 1–5)',
            'IP2': 'Perception output — SegFormer logit corruption',
            'IP3': 'Trust output — Loop 1 trust weight perturbation',
            'IP4': 'Planning output — velocity trajectory perturbation',
        },
        'scenarios': {t_id: s for t_id, s in SOTIF_SCENARIOS.items()},
        'severities': INJECTION_SEVERITIES,
        'metric': 'FPC = |downstream_delta_normalized| / |injected_delta_normalized|',
    },
    'interface_fragility': {
        ip: {k: round(v, 4) if isinstance(v, float) else v
             for k, v in score.items()}
        for ip, score in ip_fragility.items()
    },
    'fpc_matrix': {
        t_id: {ip: round(float(fpc_matrix[i, j]), 4)
               for j, ip in enumerate(injection_points)}
        for i, t_id in enumerate(scenario_ids)
    },
    'mode_change_matrix': {
        t_id: {ip: round(float(mode_change_matrix[i, j]), 3)
               for j, ip in enumerate(injection_points)}
        for i, t_id in enumerate(scenario_ids)
    },
    'all_injection_runs': [asdict(r) for r in all_results],
    'key_findings': {
        'most_fragile_interface': max(ip_fragility.items(),
                                      key=lambda x: x[1]['mean_fpc'])[0],
        'most_fragile_fpc':       round(max(s['mean_fpc']
                                       for s in ip_fragility.values()), 4),
        'fragile_interfaces':     [ip for ip, s in ip_fragility.items()
                                   if s['fragile']],
        'robust_interfaces':      [ip for ip, s in ip_fragility.items()
                                   if not s['fragile']],
        'highest_fpc_scenario':   max(all_results, key=lambda r: r.fpc).scenario_id,
        'total_mode_changes':     sum(1 for r in all_results if r.mode_changed),
    },
    'config': {
        'mc_passes':  MC_PASSES,
        'backbone':   'SegFormer-B2 (cityscapes pretrained)',
        'dataset':    'nuScenes mini v1.0 scene 0',
        'rng_seed':   INJECTION_SEED,
    }
}

out_path = os.path.join(OUTPUT_DIR, 'phase6_results.json')
with open(out_path, 'w') as f:
    json.dump(results_json, f, indent=2)

print(f'\n=== PHASE 6 COMPLETE ===')
print(f"  Total injection runs:    {len(all_results)}")
print(f"  Most fragile interface:  {results_json['key_findings']['most_fragile_interface']} "
      f"(FPC={results_json['key_findings']['most_fragile_fpc']:.3f})")
print(f"  Fragile interfaces:      {results_json['key_findings']['fragile_interfaces']}")
print(f"  Total mode changes:      {results_json['key_findings']['total_mode_changes']}")
print(f"  Results: {out_path}")
