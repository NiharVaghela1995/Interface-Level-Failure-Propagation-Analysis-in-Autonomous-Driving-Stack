"""
scripts/stage3_haz06_night.py
===============================
HAZ-06: Night + low contrast — pedestrian crossing
Scenario: Ego approaches pedestrian at night. Low ambient light
reduces camera reliability. LiDAR unaffected.
SOTIF: T1 (sensor performance limits — darkness variant)
Safety goal: SG2 (TTC scaling), SG4 (affordance override)
ASIL: C (H1 — sensor performance limits under darkness)

Key difference:
  Night degrades camera significantly but NOT LiDAR
  Loop 1: camera trust drops, LiDAR trust stays high → compensation works
  This tests whether Loop 1 correctly identifies the reliable modality

Includes SG4 fix: pedestrian affordance override (distance-based)
Includes AEB assist: brake when VRU within 6m
"""

import sys, math, json, os
from datetime import datetime

sys.path.append('/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg')
sys.path.append('/home/carla/PythonAPI/carla')
sys.path.append('/home/carla')
import carla

try:
    from planning_utils import (compute_camera_trust_night, compute_lidar_trust,
                                  compute_mode, compute_control, compute_fpc)
except ImportError:
    import math
    def compute_camera_trust_night(dark, loop1):
        return max(0.1, 0.58*(1.0-dark*0.6)) if loop1 else 0.58
    def compute_lidar_trust(dropout, loop1):
        return max(0.0, 1.0-dropout) if loop1 else 0.42
    def compute_mode(ct, lt, loop2, dist=None, sg4=True):
        unc = 1.0-(0.6*ct+0.4*lt)
        if not loop2: return 'NORMAL', unc
        if sg4 and dist and dist <= 6.0: return 'EMERGENCY', unc
        if sg4 and dist and dist <= 15.0 and unc < 0.20: unc = 0.20
        if unc >= 0.75: return 'EMERGENCY', unc
        if unc >= 0.40: return 'CONSERVATIVE', unc
        if unc >= 0.20: return 'CAUTIOUS', unc
        return 'NORMAL', unc
    def compute_control(mode, dist=None):
        t = {'NORMAL':0.6,'CAUTIOUS':0.4,'CONSERVATIVE':0.15,'EMERGENCY':0.0}[mode]
        b = 0.8 if mode=='EMERGENCY' else 0.0
        if dist and dist<=6.0: t,b=0.0,0.6
        return t,b
    def compute_fpc(baseline, injected, severity):
        if severity==0.0 or not baseline.get('min_ttc') or not injected.get('min_ttc'): return 0.0
        return round(abs(baseline['min_ttc']-injected['min_ttc'])/baseline['min_ttc']/severity, 4)

DARKNESS_SEVERITIES = [0.0, 0.25, 0.50, 0.75]
CONFIGS = {0:'baseline', 1:'loop1_only', 2:'loop2_only', 3:'combined'}

def run_haz06(world, bp_lib, darkness, config_id, config_name, n_steps=120):
    loop1 = config_id in [1, 3]
    loop2 = config_id in [2, 3]

    # Night weather
    weather = carla.WeatherParameters(
        cloudiness=20.0,
        precipitation=0.0,
        sun_altitude_angle=-10.0 - darkness * 15.0,
        sun_azimuth_angle=0.0,
        fog_density=0.0,
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

    ped_ctrl_bp = world.get_blueprint_library().find('controller.ai.walker')
    ped_ctrl = world.spawn_actor(ped_ctrl_bp, carla.Transform(), pedestrian)
    ped_ctrl.start()
    ped_ctrl.go_to_location(carla.Location(
        x=spawn_points[0].location.x + 28,
        y=spawn_points[0].location.y - 3.0,
        z=spawn_points[0].location.z + 1.0
    ))
    ped_ctrl.set_max_speed(1.2)

    # Night: camera degrades, LiDAR unaffected
    cam_trust_fn = lambda: compute_camera_trust_night(darkness, loop1)
    lid_trust_fn = lambda: compute_lidar_trust(0.0, loop1)  # LiDAR unaffected by darkness

    metrics = {
        'min_distance': 999.0, 'min_ttc': 999.0,
        'collision': False, 'mode_changes': 0,
        'final_mode': 'NORMAL', 'mean_speed': 0.0,
        'darkness': darkness, 'config': config_name,
        'scenario': 'HAZ-06_night',
        'conservative_triggered': False, 'emergency_triggered': False,
        'sg4_override_triggered': False,
        'lidar_compensation_active': loop1,
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
    print("HAZ-06: Night + low contrast — pedestrian crossing")
    print("SOTIF T1 | ASIL C | LiDAR compensation test + SG4 fix")
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

    for dark in DARKNESS_SEVERITIES:
        print(f"\n=== Darkness: {dark:.2f} ===")
        config_results = {}

        for cid, cname in CONFIGS.items():
            print(f"  Config: {cname}")
            try:
                m = run_haz06(world, bp_lib, dark, cid, cname)
                config_results[cname] = m
                run_id += 1
                print(f"  -> dist={m['min_distance']:.1f}m ttc={m['min_ttc']}s "
                      f"coll={m['collision']} mode={m['final_mode']} "
                      f"SG4={m['sg4_override_triggered']}")
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback; traceback.print_exc()
                config_results[cname] = None

        baseline = config_results.get('baseline')
        if baseline:
            for cname, m in config_results.items():
                if m and cname != 'baseline':
                    m['fpc'] = compute_fpc(baseline, m, dark)

        all_results.append({'darkness': dark, 'configs': config_results})

    print("\n=== SUMMARY ===")
    print(f"{'Dark':5} {'Config':12} {'FPC':8} {'TTC':8} {'Coll':6} {'Mode':12} {'SG4':5}")
    for r in all_results:
        for cname, m in r['configs'].items():
            if m:
                print(f"{r['darkness']:5.2f} {cname:12} {m.get('fpc',0):8.4f} "
                      f"{str(m['min_ttc']):8} {str(m['collision']):6} "
                      f"{m['final_mode']:12} {str(m['sg4_override_triggered']):5}")

    os.makedirs('/home/carla/results', exist_ok=True)
    out = {
        'timestamp': datetime.now().isoformat(),
        'scenario': 'HAZ-06_night',
        'sotif_trigger': 'T1_darkness_sensor_limits',
        'asil': 'C', 'hazard': 'H1',
        'sg4_fix': 'pedestrian_affordance_override_15m',
        'aeb_assist': 'brake_at_6m',
        'lidar_unaffected_by_darkness': True,
        'total_runs': run_id,
        'results': all_results
    }
    with open('/home/carla/results/haz06_night.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: /home/carla/results/haz06_night.json | Runs: {run_id}")

    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("CAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
