"""
scripts/stage3_haz03_occlusion.py
===================================
HAZ-03: Occluded pedestrian emergence
Scenario: Ego approaches intersection. Pedestrian hidden behind
parked vehicle, then walks into ego path at step 40.
SOTIF: T4 (pedestrian + degraded sensors)
Safety goal: SG2 (TTC scaling), SG4 (affordance override)
ASIL: D (H5 — undetected pedestrian at crossing under combined failure)

Key difference from HAZ-01:
  HAZ-01: pedestrian visible from start (stationary)
  HAZ-03: pedestrian emerges from occlusion (parked car)
  Tests late detection scenario — most safety-critical pedestrian case
  Pedestrian detection delayed by occlusion — ego has less reaction time

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

GLARE_SEVERITIES = [0.0, 0.25, 0.50, 0.75]
CONFIGS = {0: 'baseline', 1: 'loop1_only', 2: 'loop2_only', 3: 'combined'}

CAUTIOUS_THRESHOLD     = 0.20
CONSERVATIVE_THRESHOLD = 0.55

THROTTLE = {
    'NORMAL':       0.6,
    'CAUTIOUS':     0.4,
    'CONSERVATIVE': 0.15,
    'EMERGENCY':    0.0,
}

def compute_camera_trust(glare_severity, loop1_active):
    import math
    if loop1_active:
        return 1.0 / (1.0 + math.exp(6.0 * (glare_severity - 0.4)))
    return 0.58

def compute_mode(cam_trust, loop2_active):
    lidar_trust = 1.0 - cam_trust
    fused_unc = 1.0 - (0.6 * cam_trust + 0.4 * lidar_trust)
    if not loop2_active:
        return 'NORMAL', fused_unc
    if fused_unc >= CONSERVATIVE_THRESHOLD:
        return 'CONSERVATIVE', fused_unc
    elif fused_unc >= CAUTIOUS_THRESHOLD:
        return 'CAUTIOUS', fused_unc
    return 'NORMAL', fused_unc

def run_haz03(world, bp_lib, glare_severity, config_id,
              config_name, n_steps=150):
    loop1 = config_id in [1, 3]
    loop2 = config_id in [2, 3]

    spawn_points = world.get_map().get_spawn_points()
    vehicle_bp = bp_lib.find('vehicle.tesla.model3')
    ped_bp = bp_lib.find('walker.pedestrian.0001')
    parked_bp = bp_lib.find('vehicle.mercedes.sprinter')

    ego = world.spawn_actor(vehicle_bp, spawn_points[0])

    # Spawn parked vehicle 20m ahead (creates occlusion)
    parked_loc = carla.Location(
        x=spawn_points[0].location.x + 20,
        y=spawn_points[0].location.y + 2.5,
        z=spawn_points[0].location.z + 0.5
    )
    parked = world.spawn_actor(
        parked_bp, carla.Transform(parked_loc, spawn_points[0].rotation))

    # Spawn pedestrian behind parked vehicle (occluded)
    ped_start = carla.Location(
        x=spawn_points[0].location.x + 22,
        y=spawn_points[0].location.y + 5.0,
        z=spawn_points[0].location.z + 1.0
    )
    pedestrian = world.spawn_actor(ped_bp, carla.Transform(ped_start))

    # Walker controller
    ped_control_bp = world.get_blueprint_library().find('controller.ai.walker')
    ped_controller = world.spawn_actor(
        ped_control_bp, carla.Transform(), pedestrian)
    ped_controller.start()

    metrics = {
        'min_distance': 999.0,
        'min_ttc': 999.0,
        'collision': False,
        'mode_changes': 0,
        'final_mode': 'NORMAL',
        'mean_speed': 0.0,
        'glare_severity': glare_severity,
        'config': config_name,
        'scenario': 'HAZ-03_occlusion',
        'pedestrian_emerged': False,
        'detection_distance': None,
    }

    prev_mode = 'NORMAL'
    speeds = []
    ped_emerged = False

    for step in range(n_steps):
        world.tick()

        vel = ego.get_velocity()
        speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2) * 3.6
        dist = ego.get_location().distance(pedestrian.get_location())

        # Pedestrian emerges from behind parked car at step 40
        if step == 40 and not ped_emerged:
            ped_target = carla.Location(
                x=spawn_points[0].location.x + 22,
                y=spawn_points[0].location.y - 3.0,
                z=spawn_points[0].location.z + 1.0
            )
            ped_controller.go_to_location(ped_target)
            ped_controller.set_max_speed(1.4)
            ped_emerged = True
            metrics['pedestrian_emerged'] = True
            metrics['detection_distance'] = round(dist, 2)
            print(f"    [step={step}] Pedestrian emerges — ego distance={dist:.1f}m speed={speed:.1f}km/h")

        # Camera trust (occlusion: partial detection before emergence)
        if not ped_emerged:
            # Pedestrian not visible — trust based only on glare
            cam_trust = compute_camera_trust(glare_severity, loop1)
        else:
            # Pedestrian visible — full degradation model
            cam_trust = compute_camera_trust(glare_severity, loop1)
            # Additional uncertainty from late detection
            if loop1:
                cam_trust = max(0.0, cam_trust - 0.1)

        mode, fused_unc = compute_mode(cam_trust, loop2)

        if mode != prev_mode:
            metrics['mode_changes'] += 1
        prev_mode = mode

        throttle = THROTTLE[mode]
        ego.apply_control(carla.VehicleControl(throttle=throttle))

        if speed > 0.5:
            ttc = dist / (speed / 3.6)
            metrics['min_ttc'] = min(metrics['min_ttc'], ttc)

        metrics['min_distance'] = min(metrics['min_distance'], dist)
        speeds.append(speed)

        if step % 25 == 0:
            print(f"    step={step:3d} speed={speed:.1f}km/h "
                  f"dist={dist:.1f}m cam_t={cam_trust:.3f} "
                  f"mode={mode} emerged={ped_emerged}")

        if dist < 2.0:
            metrics['collision'] = True
            break

    metrics['final_mode'] = mode
    metrics['mean_speed'] = round(sum(speeds)/len(speeds), 2) if speeds else 0
    metrics['min_distance'] = round(metrics['min_distance'], 3)
    metrics['min_ttc'] = round(
        metrics['min_ttc'], 3) if metrics['min_ttc'] < 900 else None

    ped_controller.stop()
    ped_controller.destroy()
    pedestrian.destroy()
    parked.destroy()
    ego.destroy()
    return metrics

def compute_fpc(baseline, injected, severity):
    if severity == 0.0 or not baseline['min_ttc'] or not injected['min_ttc']:
        return 0.0
    delta = abs(baseline['min_ttc'] - injected['min_ttc']) / baseline['min_ttc']
    return round(delta / severity, 4)

def main():
    print("=" * 60)
    print("HAZ-03: Occluded pedestrian emergence")
    print("SOTIF T4 | ASIL D | SG2 TTC + SG4 Affordance")
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
    total = len(GLARE_SEVERITIES) * len(CONFIGS)
    print(f"Runs: {len(GLARE_SEVERITIES)} severities x {len(CONFIGS)} configs = {total}")

    all_results = []
    run_id = 0

    for sev in GLARE_SEVERITIES:
        print(f"\n=== Glare severity: {sev:.2f} ===")
        config_results = {}

        for cid, cname in CONFIGS.items():
            print(f"\n  Config: {cname}")
            try:
                m = run_haz03(world, bp_lib, sev, cid, cname)
                config_results[cname] = m
                run_id += 1
                print(f"  -> dist={m['min_distance']:.1f}m "
                      f"ttc={m['min_ttc']}s "
                      f"collision={m['collision']} "
                      f"mode={m['final_mode']} "
                      f"detection_dist={m['detection_distance']}m")
            except Exception as e:
                print(f"  ERROR {cname}: {e}")
                import traceback
                traceback.print_exc()
                config_results[cname] = None

        baseline = config_results.get('baseline')
        if baseline:
            for cname, m in config_results.items():
                if m and cname != 'baseline':
                    m['fpc'] = compute_fpc(baseline, m, sev)

        all_results.append({'severity': sev, 'configs': config_results})

    print("\n=== CAMPAIGN SUMMARY ===")
    print(f"{'Sev':5} {'Config':12} {'FPC':8} {'MinTTC':8} "
          f"{'Collision':10} {'Mode':12} {'DetDist':8}")
    for r in all_results:
        for cname, m in r['configs'].items():
            if m:
                print(f"{r['severity']:5.2f} {cname:12} "
                      f"{m.get('fpc',0):8.4f} "
                      f"{str(m['min_ttc']):8} "
                      f"{str(m['collision']):10} "
                      f"{m['final_mode']:12} "
                      f"{str(m.get('detection_distance','N/A')):8}")

    os.makedirs('/home/carla/results', exist_ok=True)
    out = {
        'timestamp': datetime.now().isoformat(),
        'scenario': 'HAZ-03_occlusion',
        'sotif_trigger': 'T4_pedestrian_degraded_sensors',
        'asil': 'D',
        'safety_goals': ['SG2_ttc_scaling', 'SG4_affordance_override'],
        'total_runs': run_id,
        'results': all_results
    }
    path = '/home/carla/results/haz03_occlusion.json'
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {path}")
    print(f"Total runs: {run_id}")

    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("CAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
