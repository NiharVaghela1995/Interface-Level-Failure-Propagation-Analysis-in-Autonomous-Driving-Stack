#!/bin/bash
# SETUP_RUNPOD.sh
# ================
# Run this at the start of every new RunPod session to restore
# the CARLA environment. Works with carlasim/carla:0.9.15 image
# on RTX 4090 (confirmed working configuration).
#
# Usage:
#   bash scripts/SETUP_RUNPOD.sh
#
# Or fetch directly from GitHub on a new pod:
#   python3 -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/NiharVaghela1995/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/dev/scripts/SETUP_RUNPOD.sh', '/tmp/setup.sh')"
#   bash /tmp/setup.sh

set -e

echo "=================================================="
echo "CARLA RunPod Environment Setup"
echo "Image: carlasim/carla:0.9.15"
echo "=================================================="

# ── Environment variables ─────────────────────────────
export LD_LIBRARY_PATH=/home/carla:$LD_LIBRARY_PATH
export DISPLAY=:99
export VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
export PYTHONPATH=/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg:/home/carla/PythonAPI/carla
export PYTHONIOENCODING=utf-8

echo "Step 1: Installing missing libraries..."
python3 << 'PYEOF'
import urllib.request, tarfile, shutil, glob, os

def extract_deb(deb, outname):
    with open(deb, 'rb') as f:
        c = f.read()
    pos = 8
    while pos < len(c):
        name = c[pos:pos+16].decode('ascii', errors='replace').strip()
        size = int(c[pos+48:pos+58].decode('ascii').strip())
        ds = pos + 60
        if name.startswith('data.tar'):
            with open(f'/tmp/{outname}', 'wb') as o:
                o.write(c[ds:ds+size])
            return True
        pos = ds + size + (size % 2)

base = 'https://mirrors.edge.kernel.org/ubuntu/pool/main'
pkgs = [
    ('jpeg', f'{base}/libj/libjpeg-turbo/libjpeg-turbo8_1.5.2-0ubuntu5_amd64.deb'),
    ('tiff', f'{base}/t/tiff/libtiff5_4.0.9-5ubuntu0.10_amd64.deb'),
    ('png',  f'{base}/libp/libpng1.6/libpng16-16_1.6.34-1ubuntu0.18.04.2_amd64.deb'),
    ('jbig', f'{base}/j/jbigkit/libjbig0_2.1-3.1build1_amd64.deb'),
    ('zstd', f'{base}/libz/libzstd/libzstd1_1.3.3+dfsg-2ubuntu1.2_amd64.deb'),
]

for name, url in pkgs:
    try:
        urllib.request.urlretrieve(url, f'/tmp/{name}.deb')
        extract_deb(f'/tmp/{name}.deb', f'{name}.tar.xz')
        with tarfile.open(f'/tmp/{name}.tar.xz') as t:
            t.extractall('/tmp')
        print(f'  OK: {name}')
    except Exception as e:
        print(f'  FAIL {name}: {e}')

copied = 0
for so in glob.glob('/tmp/usr/lib/x86_64-linux-gnu/lib*.so*'):
    shutil.copy(so, '/home/carla/')
    copied += 1
print(f'  Copied {copied} library files to /home/carla/')
PYEOF

echo "Step 2: Starting virtual display..."
Xvfb :99 -screen 0 1280x720x24 &>/dev/null &
sleep 2
echo "  Display :99 ready"

echo "Step 3: Fixing Vulkan ICD..."
cat > /etc/vulkan/icd.d/nvidia_icd.json << 'VEOF'
{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3.194"}}
VEOF
echo "  nvidia_icd.json written"

echo "Step 4: Starting CARLA server..."
cd /home/carla
./CarlaUE4.sh -prefernvidia -RenderOffScreen -nosound -carla-server -fps=10 -quality-level=Low &
echo "  Waiting 60 seconds for initialization..."
sleep 60

echo "Step 5: Verifying connection..."
python3 -c "
import sys
sys.path.append('/home/carla/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg')
import carla
client = carla.Client('localhost', 2000)
client.set_timeout(15.0)
version = client.get_server_version()
world = client.get_world()
map_name = world.get_map().name
spawn_pts = len(world.get_map().get_spawn_points())
blueprints = len(world.get_blueprint_library())
print(f'CARLA version: {version}')
print(f'Map: {map_name}')
print(f'Spawn points: {spawn_pts}')
print(f'Blueprints: {blueprints}')
print('READY')
"

echo ""
echo "=================================================="
echo "Setup complete. CARLA is running."
echo ""
echo "To run the HAZ-01 campaign:"
echo "  python3 /home/carla/stage2_haz01_injection.py"
echo ""
echo "To fetch latest scripts from GitHub:"
echo "  python3 -c \"import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/NiharVaghela1995/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/dev/scripts/stage2_haz01_injection.py', '/home/carla/stage2_haz01_injection.py')\""
echo "=================================================="
