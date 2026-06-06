"""
scripts/stage3_haz07_construction.py
=======================================
HAZ-07: Construction zone — narrow lane + debris
Scenario: Ego navigates construction zone. Debris causes LiDAR
false returns. Narrow lane reduces lateral margin.
SOTIF: T3 (combined degradation — debris + reduced ODD)
Safety goal: SG2 (TTC scaling), SG3 (CONSERVATIVE)
ASIL: C (H4 — combined degradation)

Key difference:
  Construction = LiDAR false returns (debris) + camera distraction
  Both sensors partially degraded but in different ways:
  LiDAR: false returns from debris → inflated point cloud → trust drops
  Camera: dust/distraction → mild uncertainty increase
  Tests Loop 1 cross-modal compensation in symmetric degradation

Includes SG4 fix + AEB assist
"""

import sys, math, json, os
from datetime import datetime

sys.path.append('/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg')
sys.path.append('/home/carla/PythonAPI/carla')
sys.path.append('/home/carla')
import carla

try:
    from planning_utils import compute_mode, compute_control, compute_fpc
except ImportError:
    def compute_mode(ct, lt, loop2, dist=None, sg4=True):
        unc = 1.0-(0.6*ct+0.4*lt)
        if not loop2: return 'NORMAL', unc
        if sg4 and dist and dist<=6.0: return 'EMERGENCY', unc
        if sg4 and dist and dist<=15.0 and unc<0.20: unc=0.20
        if unc>=0.75: return 'EMERGENCY', unc
        if unc>=0.40: return 'CONSERVATIVE', unc
        if unc>=0.20: return 'CAUTIOUS', unc
        return 'NORMAL', unc
    def compute_control(mode, dist=None):
        t={'NORMAL':0.6,'CAUTIOUS':0.4,'CONSERVATIVE':0.15,'EMERGENCY':0.0}[mode]
        b=0.8 if mode=='EMERGENCY' else 0.0
        if dist and dist<=6.0: t,b=0.0,0.6
        return t,b
    def compute_fpc(baseline, injected, severity):
        if severity==0.0 or not baseline.get('min_ttc') or not injected.get('min_ttc'): return 0.0
        return round(abs(baseline['min_ttc']-injected['min_ttc'])/baseline['min_ttc']/severity, 4)

DEBRIS_SEVERITIES = [0.0, 0.25, 0.50, 0.75]
CONFIGS = {0:'baseline', 1:'loop1_only', 2:'loop2_only', 3:'combined'}

def debris_to_trust(debris_severity, loop1):
    """
    Construction debris model:
    LiDAR: debris causes false returns → trust drops (inverse of dropout)
    Camera: dust/visual clutter → mild uncertainty
    """
    if loop1:
        # LiDAR false returns reduce effective trust
        lid_trust = max(0.2, 0.42 * (1.0 - debris_severity * 0.5))
        # Camera: mild dust effect
        cam_trust = max(0.3, 0.58 * (1.0 - debris_severity * 0.25))
    else:
        lid_trust = 0.42
        cam_trust = 0.58
    return cam_trust, lid_trust

def run_haz07(world, bp_lib, debris_severity, config_id, config_name, n_steps=120):
    loop1 = config_id in [1, 3]
    loop2 = config_id in [2, 3]

    # Construction zone: overcast, some dust
    weather = carla.WeatherParameters(
        cloudiness=60.0,
        precipitation=0.0,
        fog_density=debris_severity * 15.0,
        dust_storm=debris_severity * 30.0 if hasattr(carla.WeatherParameters, 'dust_storm') else 0.0,
        sun_altitude_angle=35.0,
    )
    world.set_weather(weather)

    spawn_points = world.get_map().get_spawn_points()
    ego = world.spawn_actor(
        bp_lib.find('vehicle.tesla.model3'), spawn_points[0])

    # Spawn construction worker (pedestrian) ahead
    ped_loc = carla.Location(
        x=spawn_points[0].location.x + 25,
        y=spawn_points[0].location.y + 2.0,
        z=spawn_points[0].location.z + 1.0
    )
    pedestrian = world.spawn_actor(
        bp_lib.find('walker.pedestrian.0001'), carla.Transform(ped_loc))

    # Worker moves slowly across zone
    ped_ctrl_bp = world.get_blueprint_library().find('controller.ai.walker')
    ped_ctrl = world.spawn_actor(ped_ctrl_bp, carla.Transform(), pedestrian)
    ped_ctrl.start()
    ped_ctrl.go_to_location(carla.Location(
        x=spawn_points[0].location.x + 25,
        y=spawn_points[0].location.y - 2.0,
        z=spawn_points[0].location.z + 1.0
    ))
    ped_ctrl.set_max_speed(0.8)  # slow worker

    metrics = {
        'min_distance': 999.0, 'min_ttc': 999.0,
        'collision': False, 'mode_changes': 0,
        'final_mode': 'NORMAL', 'mean_speed': 0.0,
        'debris_severity': debris_severity,
        'config': config_name, 'scenario': 'HAZ-07_construction',
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

        cam_trust, lid_trust = debris_to_trust(debris_severity, loop1)
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
    print("HAZ-07: Construction zone — debris + worker")
    print("SOTIF T3 | ASIL C | H4 + SG4 fix + AEB assist")
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

    for sev in DEBRIS_SEVERITIES:
        print(f"\n=== Debris severity: {sev:.2f} ===")
        config_results = {}

        for cid, cname in CONFIGS.items():
            print(f"  Config: {cname}")
            try:
                m = run_haz07(world, bp_lib, sev, cid, cname)
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
    print(f"{'Sev':5} {'Config':12} {'FPC':8} {'TTC':8} {'Coll':6} {'Mode':12} {'CONS':5}")
    for r in all_results:
        for cname, m in r['configs'].items():
            if m:
                print(f"{r['severity']:5.2f} {cname:12} {m.get('fpc',0):8.4f} "
                      f"{str(m['min_ttc']):8} {str(m['collision']):6} "
                      f"{m['final_mode']:12} {str(m['conservative_triggered']):5}")

    os.makedirs('/home/carla/results', exist_ok=True)
    out = {
        'timestamp': datetime.now().isoformat(),
        'scenario': 'HAZ-07_construction',
        'sotif_trigger': 'T3_combined_degradation',
        'asil': 'C', 'hazard': 'H4',
        'sg4_fix': 'pedestrian_affordance_override_15m',
        'aeb_assist': 'brake_at_6m',
        'debris_model': 'LiDAR_false_returns_camera_dust',
        'total_runs': run_id,
        'results': all_results
    }
    with open('/home/carla/results/haz07_construction.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: /home/carla/results/haz07_construction.json | Runs: {run_id}")

    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("CAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
