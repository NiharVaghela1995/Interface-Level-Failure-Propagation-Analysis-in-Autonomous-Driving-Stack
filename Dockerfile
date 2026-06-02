# Dockerfile
# av-perception-planning-research
# ─────────────────────────────────────────────────────────────────────────────
# Base: PyTorch 2.1 + CUDA 11.8 (matches RunPod default GPU images)
# Purpose: reproducible environment for all phase scripts
#
# Build:  docker build -t av-failure-propagation .
# Run:    docker run --gpus all -v /path/to/nuscenes:/data/nuscenes \
#                   -v $(pwd)/reports:/app/reports \
#                   av-failure-propagation ./run_phase.sh 5
# ─────────────────────────────────────────────────────────────────────────────

FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first for Docker layer caching
# (rebuild only if requirements change, not on every code change)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Copy project files ────────────────────────────────────────────────────────
COPY scripts/ ./scripts/
COPY notebooks/ ./notebooks/
COPY reports/ ./reports/

# Create output directories
RUN mkdir -p reports screenshots/phase1 screenshots/phase2 screenshots/phase3 \
             screenshots/phase4a screenshots/phase4b screenshots/phase5

# ── nuScenes data mount point ─────────────────────────────────────────────────
# Mount your nuScenes mini dataset here at runtime:
# docker run -v /local/nuscenes:/data/nuscenes ...
RUN mkdir -p /data/nuscenes

# ── Environment ───────────────────────────────────────────────────────────────
ENV PYTHONPATH=/app
ENV NUSCENES_DATAROOT=/data/nuscenes

# ── Default command ───────────────────────────────────────────────────────────
# Override with: docker run ... ./run_phase.sh [phase_number]
CMD ["python", "scripts/utils/__init__.py"]
