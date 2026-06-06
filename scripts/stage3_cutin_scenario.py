"""
scripts/stage3_cutin_scenario.py
=================================
HAZ-02: Cut-in vehicle under fog degradation
Scenario: Ego driving on straight road, NPC vehicle cuts in from
adjacent lane under fog degradation.
SOTIF: T3 (combined degradation) — camera uncertainty under fog
Safety goal: SG2 (TTC scaling), SG3 (CONSERVATIVE regime)
ASIL: C (H4 — combined degradation → unreliable scene understanding)

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
    """Fog increases camera uncertainty — from Phase 5: fog +29.9%"""
    base_unc = 0.15
    return min(1.0, base_unc + fog_severity * 0.299)

def compute_trust(uncertainty, loop1_active):
    if loop1_active:
        cam_trust = max(0.0, 1.0 - uncertainty * 1.5)
    else:
        cam_trust = 0.58
    lidar_trust = 1.0 - cam_trust
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

def run_cutin(world, bp_lib, fog_severity, config_id, config_name, n_steps=120):
    loop1 = config_id in [1, 3]
    loop2 = config_id in [2, 3]

    # Set weather — fog
    weather = carla.WeatherParameters(
        cloudiness=80.0,
        precipitation=0.0,
        fog_density=fog_severity * 80.0,
        fog_distance=max(5.0, 50.0 * (1.0 - fog_severity)),
        sun_altitude_angle=45.0
    )
    world.set_weather(weather)

    spawn_points = world.get_map().get_spawn_points()
    vehicle_bp = bp_lib.find('vehicle.tesla.model3')
    npc_bp = bp_lib.find('vehicle.audi.a2')

    # Spawn ego
    ego_sp = spawn_points[0]
    ego = world.spawn_actor(vehicle_bp, ego_sp)

    # Spawn NPC 25m ahead in adjacent lane (offset 3.5m laterally)
    npc_location = carla.Location(
        x=ego_sp.location.x + 25,
        y=ego_sp.location.y + 3.5,
        z=ego_sp.location.z + 0.5
    )
    npc_transform = carla.Transform(npc_location, ego_sp.rotation)
    npc = world.spawn_actor(npc_bp, npc_transform)

    metrics = {
        'min_distance': 999.0,
        'min_ttc': 999.0,
        'collision': False,
        'mode_changes': 0,
        'final_mode': 'NORMAL',
        'mean_speed': 0.0,
        'fog_severity': fog_severity,
        'config': config_name,
        'scenario': 'HAZ-02_cutin'
    }

    prev_mode = 'NORMAL'
    speeds = []
    uncertainty = fog_to_uncertainty(fog_severity)

    for step in range(n_steps):
        world.tick()

        vel = ego.get_velocity()
        speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2) * 3.6
        dist = ego.get_location().distance(npc.get_location())

        # NPC cuts in after 30 steps
        if step == 30:
            npc.apply_control(carla.VehicleControl(
                throttle=0.3, steer=-0.3))
        elif step > 30 and step < 50:
            npc.apply_control(carla.VehicleControl(
                throttle=0.3, steer=-0.1))
        else:
            npc.apply_control(carla.VehicleControl(
                throttle=0.3, steer=0.0))

        cam_trust, lidar_trust = compute_trust(uncertainty, loop1)
        mode, _ = compute_mode(cam_trust, lidar_trust, loop2)

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

        if dist < 1.5:
            metrics['collision'] = True
            break

    metrics['final_mode'] = mode
    metrics['mean_speed'] = round(sum(speeds)/len(speeds), 2) if speeds else 0
    metrics['min_distance'] = round(metrics['min_distance'], 3)
    metrics['min_ttc'] = round(metrics['min_ttc'], 3) if metrics['min_ttc'] < 900 else None

    npc.destroy()
    ego.destroy()
    return metrics

def compute_fpc(baseline, injected, severity):
    if severity == 0.0 or not baseline['min_ttc'] or not injected['min_ttc']:
        return 0.0
    delta = abs(baseline['min_ttc'] - injected['min_ttc']) / baseline['min_ttc']
    return round(delta / severity, 4)

def main():
    print("=" * 60)
    print("HAZ-02: Cut-in vehicle under fog — closed-loop campaign")
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
            try:
                m = run_cutin(world, bp_lib, sev, cid, cname)
                config_results[cname] = m
                run_id += 1
                print(f"  {cname:12}: dist={m['min_distance']:.1f}m "
                      f"ttc={m['min_ttc']}s collision={m['collision']} "
                      f"mode={m['final_mode']}")
            except Exception as e:
                print(f"  ERROR {cname}: {e}")
                config_results[cname] = None

        baseline = config_results.get('baseline')
        if baseline:
            for cname, m in config_results.items():
                if m and cname != 'baseline':
                    m['fpc'] = compute_fpc(baseline, m, sev)

        all_results.append({'severity': sev, 'configs': config_results})

    print("\n=== SUMMARY ===")
    print(f"{'Sev':5} {'Config':12} {'FPC':8} {'MinTTC':8} {'Collision':10} {'Mode':12}")
    for r in all_results:
        for cname, m in r['configs'].items():
            if m:
                print(f"{r['severity']:5.2f} {cname:12} "
                      f"{m.get('fpc',0):8.4f} {str(m['min_ttc']):8} "
                      f"{str(m['collision']):10} {m['final_mode']:12}")

    os.makedirs('/home/carla/results', exist_ok=True)
    out = {
        'timestamp': datetime.now().isoformat(),
        'scenario': 'HAZ-02_cutin',
        'sotif_trigger': 'T3_combined_degradation',
        'asil': 'C',
        'total_runs': run_id,
        'results': all_results
    }
    with open('/home/carla/results/haz02_cutin.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: /home/carla/results/haz02_cutin.json")

    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("CAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
