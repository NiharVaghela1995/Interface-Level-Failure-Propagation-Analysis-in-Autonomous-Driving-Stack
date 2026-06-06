"""
scripts/stage3_fog_scenario.py
================================
HAZ-04: Pedestrian crossing under heavy fog
Scenario: Ego approaches intersection in heavy fog. Pedestrian
crosses from the side — reduced visibility delays detection.
SOTIF: T3 (combined degradation) + T4 (pedestrian + degraded sensors)
Safety goal: SG2 (TTC scaling), SG3 (CONSERVATIVE regime)
ASIL: C/D (H4/H5)

Four-configuration mitigation campaign:
  Config 0: Baseline (no loops)
  Config 1: Loop 1 only (adaptive trust)
  Config 2: Loop 2 only (uncertainty planner)
  Config 3: Combined (both loops)

Key difference from HAZ-01:
  HAZ-01 uses glare as degradation signal
  HAZ-04 uses fog — from Phase 5, fog is most impactful (+29.9%)
  Pedestrian crosses laterally (not stationary ahead)
"""

import sys, time, math, json, os
from datetime import datetime

sys.path.append('/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg')
sys.path.append('/home/carla/PythonAPI/carla')
import carla

# ── Configuration ─────────────────────────────────────────────────────────────

FOG_SEVERITIES = [0.0, 0.25, 0.50, 0.75]
CONFIGS = {0: 'baseline', 1: 'loop1_only', 2: 'loop2_only', 3: 'combined'}

CAUTIOUS_THRESHOLD = 0.45
CONSERVATIVE_THRESHOLD = 0.60

THROTTLE = {
    'NORMAL': 0.6,
    'CAUTIOUS': 0.4,
    'CONSERVATIVE': 0.2,
    'EMERGENCY': 0.0
}

def fog_to_uncertainty(fog_severity):
    """
    Fog uncertainty model from Phase 5 benchmark:
    fog = most impactful corruption (+29.9% mean uncertainty increase)
    Additionally affects LiDAR (fog_dropout proxy)
    """
    base_cam_unc = 0.15
    base_lid_unc = 0.10
    cam_unc = min(1.0, base_cam_unc + fog_severity * 0.299)
    lid_unc = min(1.0, base_lid_unc + fog_severity * 0.15)
    return cam_unc, lid_unc

def compute_trust(cam_unc, lid_unc, loop1_active):
    if loop1_active:
        cam_trust = max(0.0, 1.0 - cam_unc * 1.5)
        lidar_trust = max(0.0, 1.0 - lid_unc * 1.2)
        # Normalize
        total = cam_trust + lidar_trust
        if total > 0:
            cam_trust /= total
            lidar_trust /= total
    else:
        cam_trust = 0.58
        lidar_trust = 0.42
    return cam_trust, lidar_trust

def compute_mode(cam_trust, lidar_trust, loop2_active):
    fused_unc = 1.0 - (0.6 * cam_trust + 0.4 * lidar_trust)
    if not loop2_active:
        return 'NORMAL', fused_unc
    if fused_unc >= CONSERVATIVE_THRESHOLD:
        return 'CONSERVATIVE', fused_unc
    elif fused_unc >= CAUTIOUS_THRESHOLD:
        return 'CAUTIOUS', fused_unc
    return 'NORMAL', fused_unc

def run_fog_scenario(world, bp_lib, fog_severity, config_id,
                     config_name, n_steps=120):
    loop1 = config_id in [1, 3]
    loop2 = config_id in [2, 3]

    # Set fog weather
    weather = carla.WeatherParameters(
        cloudiness=90.0,
        precipitation=0.0,
        fog_density=fog_severity * 100.0,
        fog_distance=max(2.0, 30.0 * (1.0 - fog_severity)),
        fog_falloff=0.9,
        sun_altitude_angle=30.0,
        sun_azimuth_angle=180.0
    )
    world.set_weather(weather)

    spawn_points = world.get_map().get_spawn_points()
    vehicle_bp = bp_lib.find('vehicle.tesla.model3')
    ped_bp = bp_lib.find('walker.pedestrian.0001')

    # Spawn ego
    ego_sp = spawn_points[0]
    ego = world.spawn_actor(vehicle_bp, ego_sp)

    # Spawn pedestrian 25m ahead, 4m to the side (crossing path)
    ped_location = carla.Location(
        x=ego_sp.location.x + 25,
        y=ego_sp.location.y + 4.0,
        z=ego_sp.location.z + 1.0
    )
    pedestrian = world.spawn_actor(ped_bp, carla.Transform(ped_location))

    # Pedestrian walk controller
    ped_control = world.get_blueprint_library().find(
        'controller.ai.walker')
    ped_controller = world.spawn_actor(
        ped_control, carla.Transform(), pedestrian)
    ped_controller.start()

    # Walk pedestrian across road (toward ego path)
    ped_target = carla.Location(
        x=ego_sp.location.x + 25,
        y=ego_sp.location.y - 4.0,
        z=ego_sp.location.z + 1.0
    )
    ped_controller.go_to_location(ped_target)
    ped_controller.set_max_speed(1.4)

    metrics = {
        'min_distance': 999.0,
        'min_ttc': 999.0,
        'collision': False,
        'mode_changes': 0,
        'final_mode': 'NORMAL',
        'mean_speed': 0.0,
        'fog_severity': fog_severity,
        'config': config_name,
        'scenario': 'HAZ-04_fog_pedestrian'
    }

    prev_mode = 'NORMAL'
    speeds = []

    cam_unc, lid_unc = fog_to_uncertainty(fog_severity)

    for step in range(n_steps):
        world.tick()

        vel = ego.get_velocity()
        speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2) * 3.6
        dist = ego.get_location().distance(pedestrian.get_location())

        cam_trust, lidar_trust = compute_trust(cam_unc, lid_unc, loop1)
        mode, fused_unc = compute_mode(cam_trust, lidar_trust, loop2)

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

        if step % 20 == 0:
            print(f"    step={step:3d} speed={speed:.1f}km/h "
                  f"dist={dist:.1f}m cam_t={cam_trust:.3f} "
                  f"fused_unc={fused_unc:.3f} mode={mode}")

        if dist < 2.0:
            metrics['collision'] = True
            break

    metrics['final_mode'] = mode
    metrics['mean_speed'] = round(sum(speeds)/len(speeds), 2) if speeds else 0
    metrics['min_distance'] = round(metrics['min_distance'], 3)
    metrics['min_ttc'] = round(
        metrics['min_ttc'], 3) if metrics['min_ttc'] < 900 else None

    # Cleanup
    ped_controller.stop()
    ped_controller.destroy()
    pedestrian.destroy()
    ego.destroy()

    return metrics

def compute_fpc(baseline, injected, severity):
    if severity == 0.0 or not baseline['min_ttc'] or not injected['min_ttc']:
        return 0.0
    delta = abs(baseline['min_ttc'] - injected['min_ttc']) / baseline['min_ttc']
    return round(delta / severity, 4)

def main():
    print("=" * 60)
    print("HAZ-04: Pedestrian crossing under fog — closed-loop campaign")
    print("SOTIF T3/T4 | ASIL C/D")
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
    total = len(FOG_SEVERITIES) * len(CONFIGS)
    print(f"Runs: {len(FOG_SEVERITIES)} severities x {len(CONFIGS)} configs = {total}")

    all_results = []
    run_id = 0

    for sev in FOG_SEVERITIES:
        print(f"\n=== Fog severity: {sev:.2f} ===")
        config_results = {}

        for cid, cname in CONFIGS.items():
            print(f"\n  Config: {cname}")
            try:
                m = run_fog_scenario(world, bp_lib, sev, cid, cname)
                config_results[cname] = m
                run_id += 1
                print(f"  -> dist={m['min_distance']:.1f}m "
                      f"ttc={m['min_ttc']}s "
                      f"collision={m['collision']} "
                      f"mode={m['final_mode']} "
                      f"mode_changes={m['mode_changes']}")
            except Exception as e:
                print(f"  ERROR {cname}: {e}")
                import traceback
                traceback.print_exc()
                config_results[cname] = None

        # Compute FPC
        baseline = config_results.get('baseline')
        if baseline:
            for cname, m in config_results.items():
                if m and cname != 'baseline':
                    m['fpc'] = compute_fpc(baseline, m, sev)

        all_results.append({'severity': sev, 'configs': config_results})

    print("\n=== CAMPAIGN SUMMARY ===")
    print(f"{'Sev':5} {'Config':12} {'FPC':8} {'MinTTC':8} "
          f"{'Collision':10} {'FinalMode':12} {'ModeChanges':12}")
    for r in all_results:
        for cname, m in r['configs'].items():
            if m:
                print(f"{r['severity']:5.2f} {cname:12} "
                      f"{m.get('fpc',0):8.4f} "
                      f"{str(m['min_ttc']):8} "
                      f"{str(m['collision']):10} "
                      f"{m['final_mode']:12} "
                      f"{m['mode_changes']:12}")

    # Save results
    os.makedirs('/home/carla/results', exist_ok=True)
    out = {
        'timestamp': datetime.now().isoformat(),
        'scenario': 'HAZ-04_fog_pedestrian',
        'sotif_trigger': 'T3_T4_fog_combined_pedestrian',
        'asil': 'C_D',
        'fog_model': 'Phase5_benchmark_29.9pct_uncertainty_increase',
        'total_runs': run_id,
        'results': all_results
    }
    path = '/home/carla/results/haz04_fog.json'
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {path}")
    print(f"Total runs: {run_id}")

    # Restore async mode
    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("CAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
