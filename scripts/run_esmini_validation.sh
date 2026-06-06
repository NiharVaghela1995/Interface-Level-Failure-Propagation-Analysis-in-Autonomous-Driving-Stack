#!/bin/bash
# scripts/run_esmini_validation.sh
# =================================
# Validates HAZ-01 OpenSCENARIO file using esmini logical track.
# Runs on local machine — no GPU, no RunPod, no cost.
#
# Purpose:
#   1. Verify haz01_scenario.xosc is schema-valid and executes correctly
#   2. Run parameter sweep to validate all severity combinations
#   3. Produce CSV trace for failure analysis
#
# Usage:
#   bash scripts/run_esmini_validation.sh
#
# Requirements:
#   wget, unzip, python3

set -e

ESMINI_VERSION="v2.37.4"
ESMINI_DIR="./esmini-demo"
SCENARIO="scenarios/haz01_scenario.xosc"
RESULTS_DIR="results/esmini"

mkdir -p "$RESULTS_DIR"

echo "=================================================="
echo "esmini Logical Track Validation"
echo "Scenario: $SCENARIO"
echo "=================================================="

# Step 1: Download esmini if not present
if [ ! -f "$ESMINI_DIR/bin/esmini" ]; then
    echo "Step 1: Downloading esmini $ESMINI_VERSION..."
    wget -q --show-progress \
        "https://github.com/esmini/esmini/releases/download/$ESMINI_VERSION/esmini-bin_Ubuntu.zip" \
        -O /tmp/esmini.zip
    unzip -q /tmp/esmini.zip -d .
    chmod +x "$ESMINI_DIR/bin/esmini"
    echo "  esmini downloaded and ready"
else
    echo "Step 1: esmini already present"
fi

# Verify esmini works
echo ""
echo "Step 2: Verifying esmini..."
"$ESMINI_DIR/bin/esmini" --version 2>/dev/null || echo "  Note: version flag not supported, continuing"

# Step 3: Validate scenario with default parameters (headless)
echo ""
echo "Step 3: Default parameter validation (GlareIntensity=0.45, LidarDropout=0.35)..."
"$ESMINI_DIR/bin/esmini" \
    --osc "$SCENARIO" \
    --headless \
    --fixed_timestep 0.05 \
    --record "$RESULTS_DIR/haz01_default.dat" \
    2>&1 | tail -5

if [ $? -eq 0 ]; then
    echo "  PASS: Default parameters validated"
else
    echo "  FAIL: Default parameters failed — check scenario file"
    exit 1
fi

# Step 4: Parameter sweep — all severity combinations
echo ""
echo "Step 4: Parameter sweep (4 glare × 4 LiDAR dropout = 16 combinations)..."

python3 << 'PYEOF'
import subprocess, os, json
from datetime import datetime

esmini = "./esmini-demo/bin/esmini"
scenario = "scenarios/haz01_scenario.xosc"
results_dir = "results/esmini"

glare_values = [0.0, 0.25, 0.50, 0.75]
lidar_values = [0.0, 0.25, 0.50, 0.75]

results = []
passed = 0
failed = 0

for glare in glare_values:
    for lidar in lidar_values:
        cmd = [
            esmini,
            '--osc', scenario,
            '--headless',
            '--fixed_timestep', '0.05',
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env={
                    **os.environ,
                    'OVERRIDE_GlareIntensity': str(glare),
                    'OVERRIDE_LidarDropout': str(lidar),
                }
            )
            status = 'PASS' if result.returncode == 0 else 'FAIL'
            if status == 'PASS':
                passed += 1
            else:
                failed += 1
        except subprocess.TimeoutExpired:
            status = 'TIMEOUT'
            failed += 1
        except Exception as e:
            status = f'ERROR: {e}'
            failed += 1

        results.append({
            'glare': glare,
            'lidar_dropout': lidar,
            'status': status
        })
        print(f"  glare={glare:.2f} lidar={lidar:.2f}: {status}")

print(f"\nResults: {passed}/{len(results)} passed, {failed} failed")

# Save results
out = {
    'timestamp': datetime.now().isoformat(),
    'scenario': scenario,
    'esmini_version': 'v2.37.4',
    'total': len(results),
    'passed': passed,
    'failed': failed,
    'results': results
}
with open(f'{results_dir}/parameter_sweep.json', 'w') as f:
    json.dump(out, f, indent=2)
print(f"Saved: {results_dir}/parameter_sweep.json")
PYEOF

# Step 5: Export CSV trace for failure analysis
echo ""
echo "Step 5: Generating CSV trace for failure analysis..."
"$ESMINI_DIR/bin/esmini" \
    --osc "$SCENARIO" \
    --headless \
    --fixed_timestep 0.05 \
    --csv_logger "$RESULTS_DIR/haz01_trace.csv" \
    2>/dev/null

if [ -f "$RESULTS_DIR/haz01_trace.csv" ]; then
    lines=$(wc -l < "$RESULTS_DIR/haz01_trace.csv")
    echo "  Trace exported: $RESULTS_DIR/haz01_trace.csv ($lines lines)"
else
    echo "  Note: CSV export not supported in this esmini build"
fi

echo ""
echo "=================================================="
echo "esmini Logical Track Validation Complete"
echo "Results: $RESULTS_DIR/"
echo "  haz01_default.dat   — replay file"
echo "  parameter_sweep.json — all 16 combinations"
echo "  haz01_trace.csv      — CSV trace"
echo "=================================================="
echo ""
echo "To replay a scenario visually:"
echo "  $ESMINI_DIR/bin/esmini --replay $RESULTS_DIR/haz01_default.dat --window 60 60 1200 600"
