# Reproducing Results

This document explains how to reproduce every phase result from scratch.

---

## Requirements

- Docker (recommended) **or** Python 3.10+ with pip
- NVIDIA GPU with 8GB+ VRAM (RunPod RTX 3090 recommended for phases 1–5)
- nuScenes mini dataset (~4GB) — [register and download here](https://nuscenes.org)
- ~30 minutes total runtime for all phases

---

## Option A: Docker (recommended)

### 1. Clone the repository

```bash
git clone https://github.com/NiharVaghela1995/av-perception-planning-research.git
cd av-perception-planning-research
```

### 2. Build the Docker image

```bash
docker build -t av-failure-propagation .
```

Build time: ~5–10 minutes (downloads PyTorch base + installs dependencies).

### 3. Mount nuScenes and run a phase

```bash
docker run --gpus all \
  -v /path/to/nuscenes:/data/nuscenes \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/screenshots:/app/screenshots \
  av-failure-propagation \
  ./run_phase.sh 5
```

Replace `/path/to/nuscenes` with your local nuScenes mini path.

### 4. Run all phases

```bash
docker run --gpus all \
  -v /path/to/nuscenes:/data/nuscenes \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/screenshots:/app/screenshots \
  av-failure-propagation \
  ./run_phase.sh all
```

Results appear in `reports/` and `screenshots/` on your host machine.

---

## Option B: Local Python

### 1. Clone and install

```bash
git clone https://github.com/NiharVaghela1995/av-perception-planning-research.git
cd av-perception-planning-research
pip install -r requirements.txt
```

### 2. Set nuScenes path

```bash
export NUSCENES_DATAROOT=/path/to/nuscenes
```

### 3. Verify utils/ imports work

```bash
PYTHONPATH=. python scripts/utils/__init__.py
```

Expected output: all `[✓]` lines, no errors.

### 4. Run a phase

```bash
chmod +x run_phase.sh
./run_phase.sh 4b    # Phase 4b: Evidential Deep Learning
```

### 5. Run all phases

```bash
./run_phase.sh all
```

---

## Option C: Google Colab (Phase 4b only — no GPU needed)

Phase 4b (Evidential Deep Learning) runs on Colab free tier.

1. Open a new Colab notebook
2. Upload `scripts/phase4b_edl.py`
3. Run: `exec(open('phase4b_edl.py').read())`

Output files saved to `/content/` — download with the Colab file browser.

---

## Expected Outputs per Phase

| Phase | Script | Output figures | JSON results |
|-------|--------|----------------|--------------|
| 1 | phase1_gradcam.py | screenshots/phase1/ | reports/phase1_results.json |
| 2 | phase2_multicam.py | screenshots/phase2/ | reports/phase2_results.json |
| 3 | phase3_sensitivity.py | screenshots/phase3/ | reports/phase3_results.json |
| 4a | phase4a_sotif.py | screenshots/phase4a/ | reports/phase4a_results.json |
| 4b | phase4b_edl.py | screenshots/phase4b/ | reports/phase4b_results.json |
| 5 | phase5_benchmark.py | screenshots/phase5/ | reports/phase5_results.json |

---

## Verifying Results

Key quantitative results to verify against published values:

```
Phase 2:  Camera trust clean=0.58, degraded=0.65 (with LiDAR rain dropout)
Phase 3:  Camera trust at max glare = 0.41
          CONSERVATIVE mode covers 23% of 7×7 matrix
Phase 4a: Mean risk reduction = 29.3% vs naive baseline
          Unknown unsafe scenarios: 12 → 5 (58.3% reduction)
Phase 4b: Mean EDL trust across glare sweep ≈ 0.65 (flat, conservative)
          Mean MC Dropout trust ≈ 0.68 (noisy, variable)
Phase 5:  Fog = most impactful corruption (29.9% uncertainty increase)
          Snow = least impactful (8.7%)
```

If any result differs significantly, check:
1. nuScenes mini version (should be v1.0)
2. SegFormer-B2 checkpoint (`nvidia/segformer-b2-finetuned-cityscapes-1024-1024`)
3. Random seed — MC Dropout is stochastic; run 3× and take mean

---

## Hardware Notes

- Phases 1–5 tested on: NVIDIA A100 40GB (RunPod) — total runtime ~45 min
- Phase 4b also tested on: Colab T4 16GB — runtime ~8 min
- Minimum: RTX 3060 12GB — phases run but slower
- CPU-only: Phase 4b only (~3 min), other phases impractically slow

---

## Questions

Open a GitHub Issue or contact via the repository profile.
