"""
scripts/stage4_fpc_recalibration.py
=====================================
Recalibrates the Failure Propagation Coefficient (FPC) to express
propagation against a SAFETY OUTCOME (collision probability) rather
than a TTC-delta proxy.

The documents specify:
  "FPC can finally be expressed against a *safety* outcome rather
   than a planning proxy."

Original FPC (proxy):
  FPC = |delta_TTC_normalized| / injected_severity
  Problem: TTC is a planning proxy, not a safety outcome directly.
  High FPC values (37, 100) are artifacts of the normalization formula.

Recalibrated FPC (safety outcome):
  FPC = P(collision | injection) / P(collision | baseline)
  
  Where P(collision) is estimated from:
    - Direct collision flag (binary — most reliable)
    - TTC-based collision probability: P = exp(-TTC / TTC_threshold)
    - Combined: weighted average

This gives FPC values in [0, ∞) where:
  FPC > 1.0 = injection increases collision probability (amplifies)
  FPC = 1.0 = injection has no effect
  FPC < 1.0 = injection reduces collision probability (attenuates)
  FPC = 0.0 = injection eliminates collision probability (isolates)

Run locally. Usage: python3 scripts/stage4_fpc_recalibration.py
"""

import json, os, math
from datetime import datetime

OUTPUT_DIR = 'results/stage4'
os.makedirs(OUTPUT_DIR, exist_ok=True)

TTC_THRESHOLD = 1.5   # seconds — safety threshold
TTC_SCALE = 0.5       # scale factor for sigmoid

def ttc_to_collision_prob(ttc):
    """
    Convert TTC to collision probability estimate.
    P(collision) = 1 / (1 + exp((TTC - threshold) / scale))
    At TTC=0: P=1.0 (certain collision)
    At TTC=1.5: P=0.5 (threshold)
    At TTC=3.0: P~0.05 (low probability)
    """
    if ttc is None or ttc > 900:
        return 0.0
    return 1.0 / (1.0 + math.exp((ttc - TTC_THRESHOLD) / TTC_SCALE))

def compute_safety_fpc(baseline_metrics, injected_metrics):
    """
    Compute FPC against safety outcome.

    Returns dict with:
      fpc_collision: binary collision-based FPC
      fpc_ttc_prob: TTC-probability-based FPC
      fpc_combined: weighted combination
      baseline_collision_prob: estimated P(collision) for baseline
      injected_collision_prob: estimated P(collision) for injected
    """
    # Binary collision
    base_coll = 1.0 if baseline_metrics.get('collision', False) else 0.0
    inj_coll = 1.0 if injected_metrics.get('collision', False) else 0.0

    # TTC-based probability
    base_ttc = baseline_metrics.get('min_ttc', 999)
    inj_ttc = injected_metrics.get('min_ttc', 999)

    base_prob_ttc = ttc_to_collision_prob(base_ttc)
    inj_prob_ttc = ttc_to_collision_prob(inj_ttc)

    # Combined probability (collision flag dominates if present)
    base_prob = 0.7 * base_coll + 0.3 * base_prob_ttc
    inj_prob = 0.7 * inj_coll + 0.3 * inj_prob_ttc

    # FPC = ratio of collision probabilities
    if base_prob < 0.001:
        # Baseline is already safe — measure absolute risk
        fpc_combined = inj_prob
    else:
        fpc_combined = inj_prob / base_prob

    # Binary FPC
    if base_coll < 0.001:
        fpc_collision = inj_coll  # absolute risk
    else:
        fpc_collision = inj_coll / base_coll

    # TTC-prob FPC
    if base_prob_ttc < 0.001:
        fpc_ttc = inj_prob_ttc
    else:
        fpc_ttc = inj_prob_ttc / base_prob_ttc

    return {
        'fpc_collision': round(fpc_collision, 4),
        'fpc_ttc_prob': round(fpc_ttc, 4),
        'fpc_combined': round(fpc_combined, 4),
        'baseline_collision_prob': round(base_prob, 4),
        'injected_collision_prob': round(inj_prob, 4),
        'baseline_ttc': base_ttc,
        'injected_ttc': inj_ttc,
    }

# ── Load all results and recalibrate ──────────────────────────────────────────

scenario_files = {
    'HAZ-01': 'results/stage3/haz01_v2.json',
    'HAZ-02': 'results/stage3/haz02_cutin.json',
    'HAZ-03': 'results/stage3/haz03_occlusion.json',
    'HAZ-04': 'results/stage3/haz04_fog.json',
    'HAZ-05': 'results/stage3/haz05_rain.json',
    'HAZ-06': 'results/stage3/haz06_night.json',
    'HAZ-07': 'results/stage3/haz07_construction.json',
    'HAZ-08': 'results/stage3/haz08_emergency.json',
}

print("=" * 70)
print("FPC RECALIBRATION — Safety Outcome Based")
print("FPC = P(collision|injected) / P(collision|baseline)")
print("=" * 70)

all_recalibrated = {}

for haz_id, filepath in scenario_files.items():
    if not os.path.exists(filepath):
        print(f"\n{haz_id}: file not found — {filepath}")
        continue

    with open(filepath) as f:
        data = json.load(f)

    print(f"\n{'='*70}")
    print(f"{haz_id}: {data.get('scenario', '')}")
    print(f"{'='*70}")

    recalibrated_results = []

    # Handle different JSON structures
    results = data.get('results', [])
    for r in results:
        configs = r.get('configs', {})
        baseline = configs.get('baseline')
        if not baseline:
            continue

        sev_key = r.get('severity', r.get('glare', r.get('darkness',
                  r.get('debris_severity', r.get('rain_severity', '?')))))

        print(f"\n  Severity/param: {sev_key}")
        print(f"  {'Config':12} {'Old FPC':8} {'New FPC':8} "
              f"{'P(coll|base)':12} {'P(coll|inj)':11} {'TTC_base':8} {'TTC_inj':8}")
        print(f"  {'-'*75}")

        row_results = {'param': sev_key, 'configs': {}}

        for config_name, metrics in configs.items():
            if not metrics:
                continue

            fpc_data = compute_safety_fpc(baseline, metrics)
            old_fpc = metrics.get('fpc', 0.0)

            print(f"  {config_name:12} {old_fpc:8.4f} "
                  f"{fpc_data['fpc_combined']:8.4f} "
                  f"{fpc_data['baseline_collision_prob']:12.4f} "
                  f"{fpc_data['injected_collision_prob']:11.4f} "
                  f"{str(fpc_data['baseline_ttc']):8} "
                  f"{str(fpc_data['injected_ttc']):8}")

            row_results['configs'][config_name] = {
                'old_fpc': old_fpc,
                'fpc_combined': fpc_data['fpc_combined'],
                'fpc_collision': fpc_data['fpc_collision'],
                'fpc_ttc_prob': fpc_data['fpc_ttc_prob'],
                'baseline_collision_prob': fpc_data['baseline_collision_prob'],
                'injected_collision_prob': fpc_data['injected_collision_prob'],
            }

        recalibrated_results.append(row_results)

    all_recalibrated[haz_id] = recalibrated_results

# ── Cross-scenario FPC summary ─────────────────────────────────────────────────

print(f"\n{'='*70}")
print("CROSS-SCENARIO FPC SUMMARY (safety-outcome based)")
print("Loop 2 only — all severities averaged")
print(f"{'='*70}")
print(f"{'Scenario':8} {'Mean FPC (old)':14} {'Mean FPC (new)':14} {'Interpretation':30}")
print("-" * 70)

for haz_id, results in all_recalibrated.items():
    old_fpcs = []
    new_fpcs = []
    for r in results:
        loop2 = r['configs'].get('loop2_only')
        if loop2:
            old_fpcs.append(loop2['old_fpc'])
            new_fpcs.append(loop2['fpc_combined'])

    if old_fpcs:
        mean_old = sum(old_fpcs) / len(old_fpcs)
        mean_new = sum(new_fpcs) / len(new_fpcs)
        if mean_new < 0.5:
            interp = "Strong attenuation"
        elif mean_new < 1.0:
            interp = "Attenuation"
        elif mean_new == 1.0:
            interp = "Transmission"
        else:
            interp = "Amplification"
        print(f"{haz_id:8} {mean_old:14.4f} {mean_new:14.4f} {interp:30}")

# ── Save recalibrated results ──────────────────────────────────────────────────

output = {
    'timestamp': datetime.now().isoformat(),
    'method': 'safety_outcome_based_fpc',
    'formula': 'FPC = P(collision|injected) / P(collision|baseline)',
    'ttc_threshold': TTC_THRESHOLD,
    'ttc_scale': TTC_SCALE,
    'note': 'Old FPC used TTC-delta proxy. New FPC uses collision probability directly.',
    'results': all_recalibrated
}

out_path = f'{OUTPUT_DIR}/fpc_recalibrated.json'
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\nSaved: {out_path}")
print("\nFPC RECALIBRATION COMPLETE")
