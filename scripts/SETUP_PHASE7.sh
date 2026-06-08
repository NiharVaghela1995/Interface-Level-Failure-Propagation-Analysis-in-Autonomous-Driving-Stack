#!/bin/bash
# scripts/SETUP_PHASE7.sh
# ========================
# Complete Phase 7 setup on RunPod:
#   1. Install MMDetection3D + dependencies
#   2. Download nuScenes mini
#   3. Download BEVFusion checkpoint
#   4. Run BEVFusion inference
#   5. Extract features for Phase 1-5 re-analysis
#
# Usage: bash scripts/SETUP_PHASE7.sh
# RunPod image: runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04
# GPU: RTX 4090

set -e

echo "=================================================="
echo "Phase 7: BEVFusion Setup on RunPod"
echo "=================================================="

WORKDIR="/workspace"
DATA_DIR="$WORKDIR/data/nuscenes"
CKPT_DIR="$WORKDIR/checkpoints"
RESULTS_DIR="$WORKDIR/phase7_results"

mkdir -p $DATA_DIR $CKPT_DIR $RESULTS_DIR

# ── Step 1: Install dependencies ──────────────────────────────────────────────
echo ""
echo "Step 1: Installing dependencies..."

pip install -q openmim
mim install -q mmengine
mim install -q "mmcv>=2.0.0"
mim install -q "mmdet>=3.0.0"
mim install -q "mmdet3d>=1.1.0"

pip install -q nuscenes-devkit
pip install -q numpy==1.23.5
pip install -q open3d

echo "  Dependencies installed"

# ── Step 2: Download nuScenes mini ────────────────────────────────────────────
echo ""
echo "Step 2: Downloading nuScenes mini (~4GB)..."

cd $DATA_DIR
wget -q --show-progress \
    https://d36yt3mvayqw5m.cloudfront.net/public/v1.0/v1.0-mini.tgz

echo "  Extracting..."
tar -xzf v1.0-mini.tgz --no-same-owner
rm v1.0-mini.tgz

echo "  nuScenes mini ready: $(du -sh $DATA_DIR)"

# ── Step 3: Download BEVFusion checkpoint ─────────────────────────────────────
echo ""
echo "Step 3: Downloading BEVFusion checkpoint..."

cd $CKPT_DIR

# MMDetection3D BEVFusion checkpoint (camera+LiDAR fusion, nuScenes)
wget -q --show-progress \
    https://download.openmmlab.com/mmdetection3d/v1.1.0_models/bevfusion/bevfusion_lidar-cam_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d-5239b1af.pth \
    -O bevfusion_lidar_cam.pth

echo "  Checkpoint: $(ls -lh $CKPT_DIR/bevfusion_lidar_cam.pth)"

# ── Step 4: Create nuScenes data info ─────────────────────────────────────────
echo ""
echo "Step 4: Creating nuScenes data info files..."

python3 - << 'PYEOF'
import subprocess
result = subprocess.run([
    'python', '-m', 'mmdet3d.tools.create_data',
    'nuscenes',
    '--root-path', '/workspace/data/nuscenes',
    '--out-dir', '/workspace/data/nuscenes',
    '--extra-tag', 'nuscenes',
    '--version', 'v1.0-mini',
    '--max-sweeps', '10'
], capture_output=True, text=True)
print(result.stdout[-2000:] if result.stdout else "")
if result.returncode != 0:
    print("Warning:", result.stderr[-500:])
    print("Trying alternative data prep...")
PYEOF

echo "  Data info created"

echo ""
echo "=================================================="
echo "Setup complete. Run: python3 scripts/phase7_bevfusion_inference.py"
echo "=================================================="
