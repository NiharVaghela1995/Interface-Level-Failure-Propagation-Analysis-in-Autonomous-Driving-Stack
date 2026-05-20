# av-perception-planning-research
Active perception &amp; uncertainty-aware planning for AV systems — sensor fusion validation, GradCAM diagnostics, Loop 1 &amp; Loop 2 

# Active Perception & Uncertainty-Aware Planning for Autonomous Vehicles

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Domain](https://img.shields.io/badge/domain-AV%20Safety%20%26%20Validation-green)
![Status](https://img.shields.io/badge/status-active%20research-orange)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/NiharVaghela1995/av-perception-planning-research/blob/main/notebooks/phase1_gradcam_uncertainty_planning.ipynb)

## Research Question

When camera and LiDAR disagree — camera detects a pedestrian, 
LiDAR and radar register nothing — how should an autonomous vehicle 
reason about which sensor to trust, and how should that uncertainty 
propagate into planning behavior?

## Framework: Two Recursive Feedback Loops

Sensors (Camera + LiDAR + Radar)

↓

Adaptive Fusion ↔ Perception (Loop 1: sensor trust adaptation)

↓

Perception ↔ Planning (Loop 2: uncertainty-aware behavior)

↓

Safety-constrained behavior (RSS / CBF)

**Loop 1** — When a modality degrades (camera glare, LiDAR rain dropout), 
fusion adapts sensor weighting dynamically.

**Loop 2** — When belief confidence is low, planning adapts: 
reduced speed, wider TTC margins, conservative maneuver profile.

## Results

![Summary](screenshots/07_summary.png)

## Phases

| Phase | Focus | Status |
|-------|-------|--------|
| Phase 1 | GradCAM + MC Dropout + Planning adaptation on nuScenes | ✅ Done |
| Phase 2 | Real BEVFusion cross-modal attention + Evidential Deep Learning | 🔄 In progress |
| Phase 3 | Sensitivity matrix + CARLA scenario generation | 📋 Planned |

## Tech Stack

PyTorch · BEVFusion · nuScenes · GradCAM · Captum · 
Conformal Prediction · RSS · CARLA · Scenic 3.0

## Dataset

nuScenes mini (10 scenes, 404 samples) — nuscenes.org
