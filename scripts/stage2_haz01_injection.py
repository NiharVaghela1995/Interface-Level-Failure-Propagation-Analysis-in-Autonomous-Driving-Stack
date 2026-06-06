"""
scripts/stage2_haz01_injection.py
==================================
HAZ-01: Occluded pedestrian under degraded camera — closed-loop V&V
Stage 2 (Integrate) + Stage 3 (Execute) + Stage 4 (Evaluate)

Four-configuration mitigation campaign:
  Config 0: Baseline (no loops)
  Config 1: Loop 1 only (adaptive trust)
  Config 2: Loop 2 only (uncertainty planner)
  Config 3: Combined (both loops)

Interface injection points:
  IP1: sensor input (glare applied to raw camera)
  IP2: perception output (uncertainty scalar injected)
  IP3: trust weights (camera trust degraded)
  IP4: planning output (velocity perturbed)

Failure Propagation Coefficient (FPC):
  FPC = |downstream_delta_normalized| / |injected_delta_normalized|
  FPC < 1.0 = interface attenuates
  FPC > 1.0 = interface amplifies
"""

import sys, time, math, json, os
from datetime import datetime

sys.path.append('/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg')
sys.path.append('/home/carla/PythonAPI/carla')
import carla

# ── Configuration ─────────────────────────────────────────────────────────────

GLARE_SEVERITIES = [0.0, 0.25, 0.50, 0.75]   # IP1 injection levels
INJECTION_POINTS = ['IP1', 'IP2', 'IP3']       # IP4 is definitional, skip
CONFIGS = {
    0: 'baseline',
    1: 'loop1_only',
    2: 'loop2_only',
    3: 'combined'
}

# Planning thresholds (from Phase 3)
NORMAL_THRESHOLD     = 0.20
CAUTIOUS_THRESHOLD   = 0.45
CONSERVATIVE_THRESHOLD = 0.60

# K(t) rate controller per mode
K_T = {
    'NORMAL': 1.0,
    'CAUTIOUS': 0.5,
    'CONSERVATIVE': 0.15,
    'EMERGENCY': 0.0
}

# Velocity targets per mode (km/h)
V_TARGET = {
    'NORMAL': 50.0,
    'CAUTIOUS': 32.0,
    'CONSERVATIVE': 27.0,
    'EMERGENCY': 0.0
}

# ── Trust and Planning Logic ───────────────────────────────────────────────────

def apply_glare(uncertainty_base, glare_severity):
    """IP1: apply glare to camera uncertainty signal."""
    # Glare increases uncertainty (sigmoid response)
    import math
    cam_trust = 1.0 / (1.0 + math.exp(6.0 * (glare_severity - 0.4)))
    return cam_trust

def compute_camera_trust(uncertainty, glare_severity, loop1_active):
    """Loop 1: compute camera trust from uncertainty + glare."""
    if loop1_active:
        cam_trust = apply_glare(uncertainty, glare_severity)
    else:
        cam_trust = max(0.0, 1.0 - uncertainty * 2.0)
    lidar_trust = 1.0 - cam_trust
    return cam_trust, lidar_trust

def compute_planning_mode(cam_trust, lidar_trust, loop2_active):
    """Loop 2: compute planning mode from fused trust."""
    fused_uncertainty = 1.0 - (0.6 * cam_trust + 0.4 * lidar_trust)
    if not loop2_active:
        return 'NORMAL', fused_uncertainty
    if fused_uncertainty >= CONSERVATIVE_THRESHOLD:
        return 'CONSERVATIVE', fused_uncertainty
    elif fused_uncertainty >= CAUTIOUS_THRESHOLD:
        return 'CAUTIOUS', fused_uncertainty
    elif fused_uncertainty >= NORMAL_THRESHOLD:
        return 'CAUTIOUS', fused_uncertainty
    else:
        return 'NORMAL', fused_uncertainty

def compute_target_velocity(mode, current_speed):
    """Loop 2: compute target velocity from mode."""
    k = K_T[mode]
    v_target = V_TARGET[mode]
    return current_speed + k * (v_target - current_speed) * 0.05

def inject_ip2(uncertainty, severity):
    """IP2: inject noise at perception output (uncertainty scalar)."""
    return min(1.0, uncertainty + severity * 0.5)

def inject_ip3(cam_trust, severity):
    """IP3: inject noise at trust weights."""
    return max(0.0, cam_trust - severity * 0.4)

# ── Scenario Runner ────────────────────────────────────────────────────────────

def run_scenario(client, world, bp_lib, glare_severity, injection_point,
                 config_id, config_name, n_steps=80):
    """Run one HAZ-01 scenario and return metrics."""

    loop1_active = config_id in [1, 3]
    loop2_active = config_id in [2, 3]

    spawn_points = world.get_map().get_spawn_points()

    # Spawn ego
    vehicle_bp = bp_lib.find('vehicle.tesla.model3')
    ego = world.spawn_actor(vehicle_bp, spawn_points[0])
    ego.set_autopilot(False)

    # Spawn pedestrian 30m ahead
    ped_bp = bp_lib.find('walker.pedestrian.0001')
    ped_loc = carla.Location(
        x=spawn_points[0].location.x + 30,
        y=spawn_points[0].location.y,
        z=spawn_points[0].location.z + 1.0
    )
    pedestrian = world.spawn_actor(ped_bp, carla.Transform(ped_loc))

    # Attach sensors
    cam_bp = bp_lib.find('sensor.camera.rgb')
    cam_bp.set_attribute('image_size_x', '640')
    cam_bp.set_attribute('image_size_y', '480')
    camera = world.spawn_actor(cam_bp,
        carla.Transform(carla.Location(x=2.0, z=1.4)), attach_to=ego)

    lid_bp = bp_lib.find('sensor.lidar.ray_cast')
    lid_bp.set_attribute('channels', '32')
    lid_bp.set_attribute('range', '50')
    lid_bp.set_attribute('points_per_second', '200000')
    lidar = world.spawn_actor(lid_bp,
        carla.Transform(carla.Location(x=0.0, z=2.4)), attach_to=ego)

    sensor_data = {'cam': None, 'lidar': None}
    camera.listen(lambda img: sensor_data.update({'cam': img}))
    lidar.listen(lambda pts: sensor_data.update({'lidar': pts}))

    # Metrics tracking
    metrics = {
        'steps': [],
        'min_distance': 999.0,
        'collision': False,
        'min_ttc': 999.0,
        'mode_changes': 0,
        'final_mode': 'NORMAL',
        'mean_speed': 0.0,
        'fpc_ip': injection_point,
        'glare_severity': glare_severity,
        'config': config_name,
    }

    prev_mode = 'NORMAL'
    speeds = []

    # Base uncertainty (clean)
    base_uncertainty = 0.15

    for step in range(n_steps):
        world.tick()

        vel = ego.get_velocity()
        speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2) * 3.6
        dist = ego.get_location().distance(pedestrian.get_location())
        lidar_pts = len(sensor_data['lidar']) if sensor_data['lidar'] else 0

        # Compute uncertainty based on injection point
        uncertainty = base_uncertainty

        if injection_point == 'IP1':
            # Glare applied at sensor input
            cam_trust, lidar_trust = compute_camera_trust(
                uncertainty, glare_severity, loop1_active)
        elif injection_point == 'IP2':
            # Inject at perception output
            uncertainty = inject_ip2(base_uncertainty, glare_severity)
            cam_trust, lidar_trust = compute_camera_trust(
                uncertainty, 0.0, loop1_active)
        elif injection_point == 'IP3':
            # Inject at trust weights
            cam_trust, lidar_trust = compute_camera_trust(
                uncertainty, 0.0, loop1_active)
            cam_trust = inject_ip3(cam_trust, glare_severity)
            lidar_trust = 1.0 - cam_trust

        # Planning mode
        mode, fused_unc = compute_planning_mode(
            cam_trust, lidar_trust, loop2_active)

        # Mode change tracking
        if mode != prev_mode:
            metrics['mode_changes'] += 1
        prev_mode = mode

        # Target velocity
        v_target = compute_target_velocity(mode, speed)
        throttle = max(0.0, min(1.0, (v_target - speed) / 20.0))
        if mode == 'EMERGENCY':
            throttle = 0.0
        ego.apply_control(carla.VehicleControl(throttle=throttle))

        # TTC calculation
        if speed > 0.5:
            ttc = dist / (speed / 3.6)
        else:
            ttc = 999.0

        speeds.append(speed)
        metrics['min_distance'] = min(metrics['min_distance'], dist)
        metrics['min_ttc'] = min(metrics['min_ttc'], ttc)
        metrics['final_mode'] = mode

        if dist < 2.0:
            metrics['collision'] = True
            break

        if step % 20 == 0:
            print(f"  step={step:3d} speed={speed:5.1f}km/h dist={dist:5.1f}m "
                  f"cam_t={cam_trust:.3f} mode={mode:12s} ttc={ttc:.1f}s")

    metrics['mean_speed'] = sum(speeds) / len(speeds) if speeds else 0.0

    # Cleanup
    camera.stop()
    lidar.stop()
    camera.destroy()
    lidar.destroy()
    pedestrian.destroy()
    ego.destroy()

    return metrics

# ── FPC Calculation ────────────────────────────────────────────────────────────

def compute_fpc(baseline_metrics, injected_metrics, severity):
    """Compute Failure Propagation Coefficient."""
    if severity == 0.0:
        return 0.0

    # Downstream delta: change in minimum TTC (safety outcome)
    baseline_ttc = baseline_metrics['min_ttc']
    injected_ttc = injected_metrics['min_ttc']

    if baseline_ttc > 900:
        return 0.0

    downstream_delta = abs(baseline_ttc - injected_ttc) / max(baseline_ttc, 0.1)

    # Injected delta: normalized severity
    injected_delta = severity

    fpc = downstream_delta / injected_delta if injected_delta > 0 else 0.0
    return round(fpc, 4)

# ── Main Campaign ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("HAZ-01 CLOSED-LOOP INJECTION CAMPAIGN")
    print("Stage 3: Four-configuration mitigation experiment")
    print("=" * 60)

    client = carla.Client('localhost', 2000)
    client.set_timeout(20.0)
    world = client.get_world()
    bp_lib = world.get_blueprint_library()

    # Synchronous mode
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05
    world.apply_settings(settings)

    print(f"Map: {world.get_map().name}")
    print(f"Running: {len(GLARE_SEVERITIES)} severities × "
          f"{len(INJECTION_POINTS)} IPs × {len(CONFIGS)} configs")
    print(f"Total runs: "
          f"{len(GLARE_SEVERITIES) * len(INJECTION_POINTS) * len(CONFIGS)}")
    print()

    all_results = []
    run_id = 0

    for ip in INJECTION_POINTS:
        print(f"\n{'='*60}")
        print(f"Injection Point: {ip}")
        print(f"{'='*60}")

        for severity in GLARE_SEVERITIES:
            print(f"\n  Severity: {severity}")

            # Run all four configs
            config_results = {}
            for config_id, config_name in CONFIGS.items():
                print(f"\n  Config {config_id}: {config_name}")
                try:
                    metrics = run_scenario(
                        client, world, bp_lib,
                        glare_severity=severity,
                        injection_point=ip,
                        config_id=config_id,
                        config_name=config_name,
                        n_steps=80
                    )
                    config_results[config_name] = metrics
                    run_id += 1
                    print(f"  → min_dist={metrics['min_distance']:.1f}m "
                          f"min_ttc={metrics['min_ttc']:.2f}s "
                          f"collision={metrics['collision']} "
                          f"mode_changes={metrics['mode_changes']}")
                    time.sleep(1)  # Brief pause between runs
                except Exception as e:
                    print(f"  ERROR: {e}")
                    config_results[config_name] = None

            # Compute FPC for each config vs baseline
            baseline = config_results.get('baseline')
            if baseline:
                for config_name, metrics in config_results.items():
                    if metrics and config_name != 'baseline':
                        fpc = compute_fpc(baseline, metrics, severity)
                        metrics['fpc'] = fpc
                        print(f"  FPC [{config_name}]: {fpc:.4f}")

            all_results.append({
                'injection_point': ip,
                'severity': severity,
                'configs': {
                    name: m for name, m in config_results.items() if m
                }
            })

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("CAMPAIGN SUMMARY — FPC vs Safety Outcome")
    print("=" * 60)
    print(f"{'IP':4} {'Sev':5} {'Config':15} {'FPC':8} "
          f"{'Min TTC':8} {'Collision':10} {'Modes':6}")
    print("-" * 60)

    for result in all_results:
        ip = result['injection_point']
        sev = result['severity']
        for config_name, metrics in result['configs'].items():
            if metrics:
                fpc = metrics.get('fpc', 0.0)
                print(f"{ip:4} {sev:5.2f} {config_name:15} "
                      f"{fpc:8.4f} {metrics['min_ttc']:8.2f} "
                      f"{str(metrics['collision']):10} "
                      f"{metrics['mode_changes']:6}")

    # ── Save Results ───────────────────────────────────────────────────────────
    output = {
        'timestamp': datetime.now().isoformat(),
        'map': world.get_map().name,
        'scenario': 'HAZ-01',
        'total_runs': run_id,
        'results': all_results,
        'key_findings': {
            'description': 'Closed-loop FPC measurement across four mitigation configs',
            'injection_points': INJECTION_POINTS,
            'severities': GLARE_SEVERITIES,
            'configs': list(CONFIGS.values()),
        }
    }

    os.makedirs('/home/carla/results', exist_ok=True)
    out_path = '/home/carla/results/haz01_campaign.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")
    print(f"Total runs completed: {run_id}")

    # Restore async
    settings.synchronous_mode = False
    world.apply_settings(settings)
    print("\nCAMPAIGN COMPLETE")

if __name__ == '__main__':
    main()
