# esmini Logical Track — HAZ-01 Scenario Validation
## Dual-Fidelity Setup for OpenSCENARIO Scenario Validation

esmini validates that a scenario is **logically correct** before spending
RunPod compute on sensor-realistic CARLA runs. It runs on CPU, takes seconds,
and serves as the deterministic replay tool during failure analysis.

---

## Installation (Ubuntu/local machine)

```bash
# Download esmini binary release
wget https://github.com/esmini/esmini/releases/download/v2.37.4/esmini-bin_Ubuntu.zip
unzip esmini-bin_Ubuntu.zip
cd esmini-demo

# Verify
./bin/esmini --version
```

---

## Validate HAZ-01 scenario

```bash
# Run HAZ-01 with default parameters (headless)
./bin/esmini \
    --osc ../scenarios/haz01_scenario.xosc \
    --headless \
    --fixed_timestep 0.05 \
    --record haz01_replay.dat

echo "Scenario completed — check for errors above"
```

### With window (visual validation)
```bash
./bin/esmini \
    --osc ../scenarios/haz01_scenario.xosc \
    --window 60 60 1200 600 \
    --fixed_timestep 0.05
```

---

## Parameter sweep — logical validation

Run all severity combinations before spending RunPod credits:

```bash
python3 << 'PYEOF'
import subprocess, os

# Parameter combinations to validate
severities = [0.0, 0.25, 0.50, 0.75]
distances = [20.0, 30.0, 40.0]

results = []
for sev in severities:
    for dist in distances:
        cmd = [
            './bin/esmini',
            '--osc', '../scenarios/haz01_scenario.xosc',
            '--headless',
            '--fixed_timestep', '0.05',
            '--override_parameter', f'GlareIntensity={sev}',
            '--override_parameter', f'PedestrianDistance={dist}',
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        status = 'PASS' if result.returncode == 0 else 'FAIL'
        results.append((sev, dist, status))
        print(f"sev={sev:.2f} dist={dist:.0f}m: {status}")

print(f"\n{sum(1 for r in results if r[2]=='PASS')}/{len(results)} scenarios valid")
PYEOF
```

---

## Deterministic replay (failure analysis)

After a CARLA run that fails, replay the exact scenario for root-cause:

```bash
# Replay recorded scenario
./bin/esmini \
    --replay haz01_replay.dat \
    --window 60 60 1200 600

# Export to CSV for analysis
./bin/esmini \
    --replay haz01_replay.dat \
    --headless \
    --csv_logger haz01_trace.csv
```

---

## Integration with CARLA campaign

**Workflow:**
1. Author scenario as `.xosc` (already done: `scenarios/haz01_scenario.xosc`)
2. Run esmini logical validation — catches broken scenarios in seconds
3. If esmini passes → run CARLA closed-loop (RunPod)
4. If CARLA run fails → replay in esmini for root-cause
5. Fix scenario → repeat from step 2

This dual-fidelity track prevents wasting RunPod credits on broken scenarios.

---

## Known esmini limitations for this project

- esmini does **not** simulate sensors (no camera/LiDAR data)
- esmini validates scenario **logic** only — timing, positions, triggers, collisions
- For sensor-realistic validation, CARLA is required
- esmini's collision detection is bounding-box based — less precise than CARLA physics

---

## Files

```
scenarios/
  haz01_scenario.xosc     HAZ-01 parameterised OpenSCENARIO file
  
docs/
  esmini_setup.md         This file
  coverage_tracker.md     Coverage tracker

scripts/
  stage2_haz01_injection.py   CARLA closed-loop campaign
  SETUP_RUNPOD.sh             RunPod environment restore
```
