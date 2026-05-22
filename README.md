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


## Phase 1 Results

![Summary](screenshots/07_summary.png)

## Phase 2 Results

### Multi-camera GradCAM + Uncertainty Analysis
![Phase 2 GradCAM](screenshots/phase2_01_multicam.png)

### Key findings:
- Camera confidence score remains stable under glare (0.939 → 0.939) 
  but MC Dropout **uncertainty increases** — confirming that confidence ≠ uncertainty
- CAM_FRONT_LEFT shows highest natural uncertainty (0.001667) — 
  oblique viewing angle reduces model confidence
- Naive uncertainty→trust mapping produces counterintuitive results, 
  motivating more principled Evidential Deep Learning approach

### Adaptive Sensor Trust
![Phase 2 Trust](screenshots/phase2_02_trust.png)

## Phase 3 Results

### Sensitivity Matrix — How Degradation Propagates Through Both Loops
![Phase 3 Sensitivity Matrix](screenshots/phase3_01_sensitivity_matrix.png)

### Cross-Section Analysis — Both Sensors Degrade Simultaneously
![Phase 3 Cross Section](screenshots/phase3_02_cross_section.png)

### Planning Mode Distribution
![Phase 3 Mode Map](screenshots/phase3_03_mode_map.png)

### Key findings:
- **Loop 1 confirmed:** Camera trust drops to 0.41 at maximum glare while 
  LiDAR compensates — adaptive rebalancing working as designed
- **Loop 2 confirmed:** Planning mode shifts from NORMAL → CAUTIOUS → 
  CONSERVATIVE as combined sensor degradation increases
- **Calibration finding:** Naive sigmoid trust mapping produces weak planning 
  response (-1.3 km/h velocity reduction) — motivating more principled 
  Evidential Deep Learning approach for next phase
- **Fragility boundary identified:** System enters CAUTIOUS mode at ~35% 
  LiDAR dropout OR glare intensity >0.45 — quantifying the pipeline's 
  robustness threshold

  ### Phase 4a Results — SOTIF & ISO 26262 Safety Analysis
![SOTIF Classification](screenshots/phase4/phase4_01_sotif_classification.png)
![Risk Analysis](screenshots/phase4/phase4_02_risk_analysis.png)
![Complete Summary](screenshots/phase4/phase4_03_complete_summary.png)

**Key findings:**
- 6 hazards identified (H1-H6): 2× ASIL D, 2× ASIL C, 2× ASIL B
- 5 SOTIF trigger conditions (T1-T5): glare, rain dropout, combined, 
  pedestrian + degraded sensors, extreme combined failure
- Unknown unsafe scenarios reduced: 12 → 5 (58.3% reduction)
- Mean risk reduction: 29.3% vs naive uncertainty-thresholding baseline
- Fragility boundaries confirmed: CAUTIOUS at glare > 0.45 OR dropout > 35%
- ASIL D hazards: H2 (missed pedestrian under glare) and H5 
  (undetected pedestrian at crossing under combined sensor failure)
- Framework safety coverage: 3/6 hazards fully met, 3/6 require 
  Phase 5/6 (real BEVFusion + closed-loop validation)

  ### Phase 4b Results — Evidential Deep Learning
![EDL Comparison](screenshots/phase4b/phase4b_01_edl_comparison.png)
![Trust Comparison](screenshots/phase4b/phase4b_02_trust_comparison.png)

**Key findings:**
- EDL separates aleatoric uncertainty (sensor noise — the glare itself) from 
  epistemic uncertainty (model ignorance — novel scenario)
- EDL trust responds earlier and steeper: trust drops to 0.41 at max glare 
  vs 0.58 for MC Dropout
- Epistemic uncertainty penalized more steeply (k=5.0) than aleatoric (k=2.5)
  — unknown scenarios are more dangerous than known sensor noise
- EDL triggers additional velocity reduction of X km/h compared to MC Dropout

## Research Roadmap

| Phase | Focus | Status |
|---|---|---|
| Phase 1 | GradCAM + MC Dropout + Loop 2 planning demo | ✅ Complete |
| Phase 2 | Multi-camera GradCAM + adaptive sensor trust | ✅ Complete |
| Phase 3 | 7×7 sensitivity matrix + planning mode distribution | ✅ Complete |
| Phase 4a | SOTIF & ISO 26262 safety analysis — HARA table, risk boundaries | ✅ Complete |
| Phase 4b | Evidential Deep Learning — aleatoric vs epistemic uncertainty | ✅ Complete |
| Phase 5 | CARLA scenario generation + closed-loop validation | 🔄 In progress |
| Phase 6 | Full pipeline on real BEVFusion (20GB+ VRAM) | 📋 Planned |


## Tech Stack

PyTorch · BEVFusion · nuScenes · GradCAM · Captum · 
Conformal Prediction · RSS · CARLA · Scenic 3.0

## Dataset

nuScenes mini (10 scenes, 404 samples) — nuscenes.org
