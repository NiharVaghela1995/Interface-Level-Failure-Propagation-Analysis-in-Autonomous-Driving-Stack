"""
scripts/stage3_haz05_rain.py
==============================
HAZ-05: Rain + LiDAR dropout — pedestrian crossing
Scenario: Ego approaches pedestrian in rain. Rain affects both
camera (visibility) and LiDAR (point dropout from water returns).
SOTIF: T2 (rain/LiDAR dropout) + T3 (combined degradation)
Safety goal: SG2 (TTC scaling), SG3 (CONSERVATIVE)
ASIL: C (H3 — LiDAR range error in rain)

Key difference from previous scenarios:
  HAZ-01/03: glare degrades camera only
  HAZ-05: rain degrades BOTH camera AND LiDAR simultaneously
  This is the scenario where Loop 1's LiDAR compensation fails —
  when both sensors degrade, there is no reliable fallback modality.

Includes SG4 fix: pedestrian affordance override (distance-based)
Includes AEB assist: brake when VRU within 6m
"""

import sys, math, json, os
from datetime import datetime

sys.path.append('/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg')
sys.path.append('/home/carla/PythonAPI/carla')
sys.path.append('/home/carla')
import carla

# Import shared utilities
try:
    from planning_utils import (compute_camera_trust_fog, compute_lidar_trust,
                                  compute_mode, compute_control, compute_fpc,
                                  CONSERVATIVE_THRESHOLD)
except ImportError:
    # Inline fallback if planning_utils not available
    import math
    CONSERVATIVE_THRESHOLD = 0.40
    def compute_camera_trust_fog(sev, loop1):
        if loop1: return max(0.0, 1.0 - min(1.0, 0.15 + sev*0.299)*1.5)
        return 0.58
    def compute_lidar_trust(dropout, loop1):
        return max(0.0, 1.0-dropout) if loop1 else 0.42
    def compute_mode(ct, lt, loop2, dist=None, sg4=True):
        unc = 1.0 - (0.6*ct + 0.4*lt)
        if not loop2: return 'NORMAL', unc
        if sg4 and dist and dist <= 6.0: return 'EMERGENCY', unc
        if sg4 and dist and dist <= 15.0 and unc < 0.20: unc = 0.20
        if unc >= 0.75: return 'EMERGENCY', unc
        if unc >= 0.40: return 'CONSERVATIVE', unc
        if unc >= 0.20: return 'CAUTIOUS', unc
        return 'NORMAL', unc
    def compute_control(mode, dist=None):
        t = {'NORMAL':0.6,'CAUTIOUS':0.4,'CONSERVATIVE':0.15,'EMERGENCY':0.0}[mode]
        b = 0.8 if mode == 'EMERGENCY' else 0.0
        if dist and dist <= 6.0: t, b = 0.0, 0.6
        return t, b
    def compute_fpc(baseline, injected, severity):
        if severity == 0.0 or not baseline.get('min_ttc') or not injected.get('min_ttc'): return 0.0
        return round(abs(baseline['min_ttc']-injected['min_ttc'])/baseline['min_ttc']/severity, 4)

RAIN_SEVERITIES = [0.0, 0.25, 0.50, 0.75]
CONFIGS = {0:'baseline', 1:'loop1_only', 2:'loop2_only', 3:'combined'}

def run_haz05(world, bp_lib, rain_severity, config_id, config_name, n_steps=120):
    loop1 = config_id in [1, 3]
    loop2 = config_id in [2, 3]

    # Rain weather
    weather = carla.WeatherParameters(
        cloudiness=85.0,
        precipitation=rain_severity * 80.0,
        precipitation_deposits=rain_severity * 50.0,
        wind_intensity=rain_severity * 30.0,
        fog_density=rain_severity * 20.0,
        sun_altitude_angle=40.0,
        wetness=rain_severity * 100.0
    )
    world.set_weather(weather)

    spawn_points = world.get_map().get_spawn_points()
    ego = world.spawn_actor(
        bp_lib.find('vehicle.tesla.model3'), spawn_points[0])

    ped_loc = carla.Location(
        x=spawn_points[0].location.x + 28,
        y=spawn_points[0].location.y + 3.0,
        z=spawn_points[0].location.z + 1.0
    )
    pedestrian = world.spawn_actor(
        bp_lib.find('walker.pedestrian.0001'), carla.Transform(ped_loc))

    # Pedestrian crosses road
    ped_ctrl_bp = world.get_blueprint_library().find('controller.ai.walker')
    ped_ctrl = world.spawn_actor(ped_ctrl_bp, carla.Transform(), pedestrian)
    ped_ctrl.start()
    ped_target = carla.Location(
        x=spawn_points[0].location.x + 28,
        y=spawn_points[0].location.y - 3.0,
        z=spawn_points[0].location.z + 1.0
    )
    ped_ctrl.go_to_location(ped_target)
    ped_ctrl.set_max_speed(1.2)

    # Rain affects BOTH camera AND LiDAR
    cam_trust_fn = lambda: compute_camera_trust_fog(rain_severity, loop1)
    # LiDAR rain dropout — rain_severity maps to dropout fraction
    lidar_dropout = rain_severity * 0.6  # max 60% dropout at severity=1.0
    lid_trust_fn = lambda: compute_lidar_trust(lidar_dropout, loop1)

    metrics = {
        'min_distance': 999.0, 'min_ttc': 999.0,
        'collision': False, 'mode_changes': 0,
        'final_mode': 'NORMAL', 'mean_speed': 0.0,
        'rain_severity': rain_severity, 'lidar_dropout': lidar_dropout,
        'config': config_name, 'scenario': 'HAZ-05_rain',
        'conservative_triggered': False, 'emergency_triggered': False,
        'sg4_override_triggered': False,
    }

    prev_mode = 'NORMAL'
    speeds = []

    for step in range(n_steps):
        world.tick()
        vel = ego.get_velocity()
        speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2) * 3.6
        dist = ego.get_location().distance(pedestrian.get_location())

        cam_trust = cam_trust_fn()
        lid_trust = lid_trust_fn()
        mode, fused_unc = compute_mode(
            cam_trust, lid_trust, loop2, dist_to_vru=dist, sg4_active=loop2)

        if mode != prev_mode:
            metrics['mode_changes'] += 1
        prev_mode = mode
        if mode == 'CONSERVATIVE': metrics['conservative_triggered'] = True
        if mode == 'EMERGENCY': metrics['emergency_triggered'] = True
        if loop2 and dist <= 15.0: metrics['sg4_override_triggered'] = True

        throttle, brake = compute_control(mode, dist_to_vru=dist)
        ego.apply_control(carla.VehicleControl(throttle=throttle, brake=brake))

        if speed > 0.5:
            ttc = dist / (speed / 3.6)
            metrics['min_ttc'] = min(metrics['min_ttc'], ttc)
        metrics['min_distance'] = min(metrics['min_distance'], dist)
        speeds.append(speed)

        if step % 25 == 0:
            print(f"    step={step:3d} spd={speed:.1f}km/h dist={dist:.1f}m "
                  f"cam={cam_trust:.3f} lid={lid_trust:.3f} "
                  f"unc={fused_unc:.3f} mode={mode}")

        if dist < 2.0:
            metrics['collision'] = True
            break

    metrics['final_mode'] = mode
    metrics['mean_speed'] = round(sum(speeds)/len(speeds), 2) if speeds else 0
    metrics['min_distance'] = round(metrics['min_distance'], 3)
    metrics['min_ttc'] = round(metrics['min_ttc'], 3) if metrics['min_ttc'] < 900 else None

    ped_ctrl.stop()
    ped_ctrl.destroy()
    pedestrian.destroy()
    ego.destroy()
    return metrics

def main():
    print("=" * 60)
    print("HAZ-05: Rain + LiDAR dropout — pedestrian crossing")
    print("SOTIF T2/T3 | ASIL C | H3 coverage + SG4 fix")
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
    all_results = []
    run_id = 0

    for sev in RAIN_SEVERITIES:
        print(f"\n=== Rain severity: {sev:.2f} ===")
        config_results = {}

        for cid, cname in CONFIGS.items():
            print(f"  Config: {cname}")
            try:
                m = run_haz05(world, bp_lib, sev, cid, cname)
                config_results[cname] = m
                run_id += 1
                print(f"  -> dist={m['min_distance']:.1f}m ttc={m['min_ttc']}s "
                      f"coll={m['collision']} mode={m['final_mode']} "
                      f"CONS={m['conservative_triggered']} SG4={m['sg4_override_triggered']}")
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback; traceback.print_exc()
                config_results[cname] = None

        baseline = config_results.get('baseline')
        if baseline:
            for cname, m in config_results.items():
                if m and cname != 'baseline':
                    m['fpc'] = compute_fpc(baseline, m, sev)

        all_results.append({'severity': sev, 'configs': config_results})

    print("\n=== SUMMARY ===")
    print(f"{'Sev':5} {'Config':12} {'FPC':8} {'TTC':8} {'Coll':6} {'Mode':12} {'CONS':5} {'SG4':5}")
    for r in all_results:
        for cname, m in r['configs'].items():
            if m:
                print(f"{r['severity']:5.2f} {cname:12} {m.get('fpc',0):8.4f} "
                      f"{str(m['min_ttc']):8} {str(m['collision']):6} "
                      f"{m['final_mode']:12} {str(m['conservative_triggered']):5} "
                      f"{str(m['sg4_override_triggered']):5}")

    os.makedirs('/home/carla/results', exist_ok=True)
    out = {
        'timestamp': datetime.now().isoformat(),
        'scenario': 'HAZ-05_rain_lidar_dropout',
        'sotif_trigger': 'T2_T3_rain_combined',
        'asil': 'C', 'hazard': 'H3',
        'sg4_fix': 'pedestrian_affordance_override_15m',
        'aeb_assist': 'brake_at_6m',
        'conservative_threshold_updated': 0.40,
        'total_runs': run_id,
        'results': all_results
    }
    with open('/home/carla/results/haz05_rain.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: /home/carla/results/haz05_rain.json | Runs: {run_id}")

    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("CAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
