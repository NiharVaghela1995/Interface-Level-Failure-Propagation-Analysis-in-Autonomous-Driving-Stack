# Autoware Integration — Research Notes and Dockerfile
## Stage 2 Production-Grade AD Stack Integration

*Status: Research complete, Dockerfile ready, execution pending*
*Priority: Thesis positioning (2027) — not required for internship applications*

---

## Why Autoware

The current closed-loop rig uses simplified Python vehicle control (direct throttle).
Autoware replaces this with a production-grade AD stack:

```
Current rig:
  CARLA sensors → Python trust/planning → direct throttle control

Autoware rig:
  CARLA sensors → ROS2 topics → Autoware perception → Autoware planning
               → Autoware control → CARLA vehicle actuation
```

The difference: Autoware runs real BEV perception, real prediction, real planning,
and real control. The interface injection points (IP1–IP4) become real ROS2 topic
intercepts rather than Python variable overrides.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CARLA 0.9.15 (simulation)                                  │
│  Town10HD_Opt · ego sensors · actor spawning                │
└──────────────┬──────────────────────────────────────────────┘
               │ ROS2 topics (via carla-ros-bridge)
               │ /carla/ego_vehicle/camera/image_raw
               │ /carla/ego_vehicle/lidar/point_cloud
               ▼
┌─────────────────────────────────────────────────────────────┐
│  carla-ros-bridge (ROS2 Humble)                             │
│  Converts CARLA sensor data to ROS2 message types           │
└──────────────┬──────────────────────────────────────────────┘
               │ sensor_msgs/Image, sensor_msgs/PointCloud2
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Autoware Universe (ROS2 Humble)                            │
│  perception → prediction → planning → control               │
│                                                              │
│  Injection points:                                           │
│  IP2: /perception/object_recognition/objects (intercept)    │
│  IP3: custom trust_weights topic (inject)                   │
│  IP4: /planning/trajectory (intercept)                      │
└──────────────┬──────────────────────────────────────────────┘
               │ /control/command/control_cmd
               ▼
┌─────────────────────────────────────────────────────────────┐
│  carla-ros-bridge (reverse)                                 │
│  Converts control commands back to CARLA vehicle actuation  │
└─────────────────────────────────────────────────────────────┘
```

---

## Dockerfile

```dockerfile
# Autoware + CARLA integration environment
# Base: Autoware Universe (ROS2 Humble, Ubuntu 22.04)
# CARLA: 0.9.15 Python API
# Bridge: carla-ros-bridge for ROS2

FROM ghcr.io/autowarefoundation/autoware:latest-prebuilt-cuda

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=humble

# Install CARLA Python API dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    wget \
    xvfb \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/*

# Install CARLA Python client
RUN pip3 install carla==0.9.15 --break-system-packages 2>/dev/null || \
    pip3 install carla==0.9.15

# Install carla-ros-bridge
WORKDIR /workspace
RUN git clone --recurse-submodules \
    https://github.com/carla-simulator/ros-bridge.git \
    /workspace/ros-bridge

# Build ros-bridge
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    cd /workspace/ros-bridge && \
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release"

# Install project scripts
COPY scripts/ /workspace/scripts/
COPY scenarios/ /workspace/scenarios/

# Environment setup script
RUN cat > /workspace/setup.sh << 'EOF'
#!/bin/bash
source /opt/ros/humble/setup.bash
source /workspace/ros-bridge/install/setup.bash
export CARLA_ROOT=/home/carla
export PYTHONPATH=$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.15-cp38-cp38-linux_x86_64.egg:$PYTHONPATH
export PYTHONPATH=$CARLA_ROOT/PythonAPI/carla:$PYTHONPATH
echo "Autoware + CARLA environment ready"
echo "ROS_DISTRO: $ROS_DISTRO"
EOF
RUN chmod +x /workspace/setup.sh

WORKDIR /workspace
CMD ["/bin/bash"]
```

---

## ROS2 Topic Contract

The interface injection system intercepts and modifies these topics:

| Interface | ROS2 Topic | Message Type | Injection Method |
|-----------|-----------|--------------|-----------------|
| IP1 | `/carla/ego_vehicle/camera/image_raw` | `sensor_msgs/Image` | Pre-bridge corruption |
| IP2 | `/perception/object_recognition/objects` | `autoware_auto_perception_msgs/DetectedObjects` | Topic relay with noise |
| IP3 | `/sensing/lidar/top/pointcloud_raw` | `sensor_msgs/PointCloud2` | Point dropout filter |
| IP4 | `/planning/scenario_planning/trajectory` | `autoware_auto_planning_msgs/Trajectory` | Velocity perturbation |

---

## Integration Steps (for future execution)

```bash
# Terminal 1: Start CARLA
./CarlaUE4.sh -prefernvidia -RenderOffScreen -nosound -carla-server

# Terminal 2: Start carla-ros-bridge
source /workspace/setup.sh
ros2 launch carla_ros_bridge carla_ros_bridge_with_example_ego_vehicle.launch.py \
    host:=localhost port:=2000 town:=Town10HD_Opt

# Terminal 3: Start Autoware
source /workspace/setup.sh
ros2 launch autoware_launch autoware.launch.xml \
    map_path:=/workspace/maps/Town10HD_Opt \
    vehicle_model:=sample_vehicle \
    sensor_model:=sample_sensor_kit

# Terminal 4: Run injection campaign
source /workspace/setup.sh
python3 /workspace/scripts/stage3_autoware_injection.py
```

---

## Known challenges

1. **CARLA-Autoware map alignment** — Autoware requires Lanelet2 format (.osm).
   CARLA Town10HD_Opt map needs conversion via `carla-to-lanelet2` tool.

2. **Sensor calibration** — Autoware requires precise extrinsic calibration between
   camera and LiDAR. CARLA spawn coordinates must match Autoware sensor_kit config.

3. **Time synchronisation** — CARLA runs at 20 FPS synchronous; Autoware expects
   real-time ROS clock. The bridge handles this but requires careful configuration.

4. **Autoware image size** — full Autoware Docker image is ~20GB. Requires RunPod
   with 40GB+ container disk and high-memory GPU (RTX 4090 or A40).

---

## Validation debt this closes

- VD-01: Real BEVFusion perception backbone (Autoware uses CenterPoint + BEVFusion)
- VD-02: Real planning stack (Autoware path planner replaces Python proxy)
- VD-03: Real control (Autoware MPC controller replaces direct throttle)

---

## Timeline estimate

- Dockerfile build + CARLA bridge setup: 4–6 hours
- Map conversion (Town10HD → Lanelet2): 2–3 hours
- Sensor calibration: 2–3 hours
- First closed-loop smoke test: 2–4 hours
- Injection campaign adaptation: 3–4 hours
- **Total: ~20 hours of focused engineering work**

Recommended: one dedicated weekend session after Pflichtpraktikum starts,
when access to better hardware may be available through the internship.
