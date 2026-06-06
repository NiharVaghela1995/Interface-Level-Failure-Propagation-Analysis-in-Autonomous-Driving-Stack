"""
scripts/stage3_haz08_emergency.py
===================================
HAZ-08: EMERGENCY/MRC trigger under extreme combined sensor failure
Scenario: Ego approaches pedestrian under extreme combined glare +
LiDAR dropout — designed to trigger CONSERVATIVE and EMERGENCY regimes.
SOTIF: T5 (extreme combined failure)
Safety goal: SG3 (CONSERVATIVE regime), SG5 (MRC trigger)
ASIL: B (H6 — complete perception failure → MRC required)

Key difference from HAZ-01:
  HAZ-01: moderate degradation → CAUTIOUS
  HAZ-08: extreme degradation → CONSERVATIVE → EMERGENCY
  Uses high glare (0.7-0.9) + high LiDAR dropout (0.5-0.8)
  to push uncertainty above CONSERVATIVE_THRESHOLD (0.60)

Four-configuration mitigation campaign:
  Config 0: Baseline (no loops)
  Config 1: Loop 1 only (adaptive trust)
  Config 2: Loop 2 only (uncertainty planner)
  Config 3: Combined (both loops)
"""

import sys, time, math, json, os
from datetime import datetime

sys.path.append('/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg')
sys.path.append('/home/carla/PythonAPI/carla')
import carla

# ── Configuration ─────────────────────────────────────────────────────────────

# High severity combinations designed to trigger CONSERVATIVE/EMERGENCY
DEGRADATION_COMBOS = [
    (0.0,  0.0),   # Clean baseline
    (0.5,  0.5),   # Medium combined
    (0.75, 0.65),  # High combined — should trigger CONSERVATIVE
    (0.9,  0.8),   # Extreme combined — should trigger EMERGENCY
]

CONFIGS = {0: 'baseline', 1: 'loop1_only', 2: 'loop2_only', 3: 'combined'}

# Thresholds from Phase 3
CAUTIOUS_THRESHOLD     = 0.20
CONSERVATIVE_THRESHOLD = 0.55
EMERGENCY_THRESHOLD    = 0.80

# Throttle per mode
THROTTLE = {
    'NORMAL':       0.6,
    'CAUTIOUS':     0.4,
    'CONSERVATIVE': 0.15,
    'EMERGENCY':    0.0,
}

def compute_camera_trust(glare_severity, loop1_active):
    """Sigmoid trust formula from Phase 3."""
    import math
    if loop1_active:
        cam_trust = 1.0 / (1.0 + math.exp(6.0 * (glare_severity - 0.4)))
    else:
        cam_trust = 0.58
    return cam_trust

def compute_lidar_trust(lidar_dropout, loop1_active):
    """LiDAR trust degrades with dropout."""
    if loop1_active:
        lidar_trust = max(0.0, 1.0 - lidar_dropout)
    else:
        lidar_trust = 0.42
    return lidar_trust

def compute_mode(cam_trust, lidar_trust, loop2_active):
    """Extended mode computation including EMERGENCY."""
    fused_unc = 1.0 - (0.6 * cam_trust + 0.4 * lidar_trust)
    if not loop2_active:
        return 'NORMAL', fused_unc
    if fused_unc >= EMERGENCY_THRESHOLD:
        return 'EMERGENCY', fused_unc
    elif fused_unc >= CONSERVATIVE_THRESHOLD:
        return 'CONSERVATIVE', fused_unc
    elif fused_unc >= CAUTIOUS_THRESHOLD:
        return 'CAUTIOUS', fused_unc
    return 'NORMAL', fused_unc

def run_haz08(world, bp_lib, glare_severity, lidar_dropout,
              config_id, config_name, n_steps=120):
    loop1 = config_id in [1, 3]
    loop2 = config_id in [2, 3]

    spawn_points = world.get_map().get_spawn_points()
    vehicle_bp = bp_lib.find('vehicle.tesla.model3')
    ped_bp = bp_lib.find('walker.pedestrian.0001')

    ego = world.spawn_actor(vehicle_bp, spawn_points[0])

    # Pedestrian 25m ahead — closer than HAZ-01 to increase urgency
    ped_loc = carla.Location(
        x=spawn_points[0].location.x + 25,
        y=spawn_points[0].location.y,
        z=spawn_points[0].location.z + 1.0
    )
    pedestrian = world.spawn_actor(ped_bp, carla.Transform(ped_loc))

    metrics = {
        'min_distance': 999.0,
        'min_ttc': 999.0,
        'collision': False,
        'mode_changes': 0,
        'modes_triggered': set(),
        'final_mode': 'NORMAL',
        'mean_speed': 0.0,
        'glare_severity': glare_severity,
        'lidar_dropout': lidar_dropout,
        'config': config_name,
        'scenario': 'HAZ-08_emergency',
        'emergency_triggered': False,
        'conservative_triggered': False,
    }

    prev_mode = 'NORMAL'
    speeds = []

    for step in range(n_steps):
        world.tick()

        vel = ego.get_velocity()
        speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2) * 3.6
        dist = ego.get_location().distance(pedestrian.get_location())

        cam_trust = compute_camera_trust(glare_severity, loop1)
        lidar_trust = compute_lidar_trust(lidar_dropout, loop1)
        mode, fused_unc = compute_mode(cam_trust, lidar_trust, loop2)

        metrics['modes_triggered'].add(mode)
        if mode == 'EMERGENCY':
            metrics['emergency_triggered'] = True
        if mode == 'CONSERVATIVE':
            metrics['conservative_triggered'] = True

        if mode != prev_mode:
            metrics['mode_changes'] += 1
        prev_mode = mode

        throttle = THROTTLE[mode]
        brake = 0.8 if mode == 'EMERGENCY' else 0.0
        ego.apply_control(carla.VehicleControl(
            throttle=throttle, brake=brake))

        if speed > 0.5:
            ttc = dist / (speed / 3.6)
            metrics['min_ttc'] = min(metrics['min_ttc'], ttc)

        metrics['min_distance'] = min(metrics['min_distance'], dist)
        speeds.append(speed)

        if step % 20 == 0:
            print(f"    step={step:3d} speed={speed:.1f}km/h "
                  f"dist={dist:.1f}m cam_t={cam_trust:.3f} "
                  f"lid_t={lidar_trust:.3f} unc={fused_unc:.3f} "
                  f"mode={mode}")

        if dist < 2.5:
            metrics['collision'] = True
            break

    metrics['final_mode'] = mode
    metrics['mean_speed'] = round(sum(speeds)/len(speeds), 2) if speeds else 0
    metrics['min_distance'] = round(metrics['min_distance'], 3)
    metrics['min_ttc'] = round(
        metrics['min_ttc'], 3) if metrics['min_ttc'] < 900 else None
    metrics['modes_triggered'] = list(metrics['modes_triggered'])

    pedestrian.destroy()
    ego.destroy()
    return metrics

def compute_fpc(baseline, injected, glare_sev, lid_sev):
    severity = max(glare_sev, lid_sev)
    if severity == 0.0 or not baseline['min_ttc'] or not injected['min_ttc']:
        return 0.0
    delta = abs(baseline['min_ttc'] - injected['min_ttc']) / baseline['min_ttc']
    return round(delta / severity, 4)

def main():
    print("=" * 60)
    print("HAZ-08: EMERGENCY/MRC scenario — extreme combined failure")
    print("SOTIF T5 | ASIL B | SG3 CONSERVATIVE + SG5 MRC")
    print("=" * 60)

    client = carla.Client('localhost', 2000)
    client.set_timeout(20.0)
    world = client.get_world()
    bp_lib = world.get_blueprint_library()

    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05
    world.apply_settings(settings)

    print(f"Map: {world.get_map().name}")
    total = len(DEGRADATION_COMBOS) * len(CONFIGS)
    print(f"Runs: {len(DEGRADATION_COMBOS)} combos x {len(CONFIGS)} configs = {total}")

    all_results = []
    run_id = 0

    for glare, lidar_drop in DEGRADATION_COMBOS:
        print(f"\n=== Glare={glare:.2f} LiDAR_dropout={lidar_drop:.2f} ===")
        config_results = {}

        for cid, cname in CONFIGS.items():
            print(f"\n  Config: {cname}")
            try:
                m = run_haz08(world, bp_lib, glare, lidar_drop, cid, cname)
                config_results[cname] = m
                run_id += 1
                print(f"  -> dist={m['min_distance']:.1f}m "
                      f"ttc={m['min_ttc']}s "
                      f"collision={m['collision']} "
                      f"mode={m['final_mode']} "
                      f"CONSERVATIVE={m['conservative_triggered']} "
                      f"EMERGENCY={m['emergency_triggered']}")
            except Exception as e:
                print(f"  ERROR {cname}: {e}")
                import traceback
                traceback.print_exc()
                config_results[cname] = None

        baseline = config_results.get('baseline')
        if baseline:
            for cname, m in config_results.items():
                if m and cname != 'baseline':
                    m['fpc'] = compute_fpc(
                        baseline, m, glare, lidar_drop)

        all_results.append({
            'glare': glare,
            'lidar_dropout': lidar_drop,
            'configs': config_results
        })

    print("\n=== CAMPAIGN SUMMARY ===")
    print(f"{'Glare':6} {'Lid':6} {'Config':12} {'TTC':8} "
          f"{'Coll':6} {'Mode':12} {'CONS':5} {'EMRG':5}")
    for r in all_results:
        for cname, m in r['configs'].items():
            if m:
                print(f"{r['glare']:6.2f} {r['lidar_dropout']:6.2f} "
                      f"{cname:12} {str(m['min_ttc']):8} "
                      f"{str(m['collision']):6} {m['final_mode']:12} "
                      f"{str(m['conservative_triggered']):5} "
                      f"{str(m['emergency_triggered']):5}")

    os.makedirs('/home/carla/results', exist_ok=True)
    out = {
        'timestamp': datetime.now().isoformat(),
        'scenario': 'HAZ-08_emergency_mrc',
        'sotif_trigger': 'T5_extreme_combined_failure',
        'asil': 'B',
        'safety_goals': ['SG3_conservative_regime', 'SG5_mrc_trigger'],
        'total_runs': run_id,
        'results': all_results
    }
    path = '/home/carla/results/haz08_emergency.json'
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {path}")
    print(f"Total runs: {run_id}")

    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("CAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
