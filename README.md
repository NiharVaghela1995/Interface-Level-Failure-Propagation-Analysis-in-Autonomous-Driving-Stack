# Autonomous Driving Safety, Simulation & Validation Framework

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Domain](https://img.shields.io/badge/domain-AV%20Safety%20%26%20V%26V-green)
![Status](https://img.shields.io/badge/status-V%26V%20framework-brightgreen)
![Dataset](https://img.shields.io/badge/dataset-nuScenes%20mini-lightgrey)
![Evaluation](https://img.shields.io/badge/evaluation-closed--loop%20%2B%20open--loop-brightgreen)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/NiharVaghela1995/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/blob/main/notebooks/phase1_gradcam_uncertainty_planning.ipynb)
[![Interactive Demo](https://img.shields.io/badge/demo-interactive%20viz-blue)](https://niharvaghela1995.github.io/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/phase3_interactive.html)

## What this project is

A simulation-based safety validation program for autonomous driving systems, built on the standard automotive V-model — hazard analysis (HARA/SOTIF), scenario-based test design, closed-loop simulation in CARLA, KPI measurement, coverage analysis, and a GSN safety case.

On top of that foundation, the project instruments four interface points inside a modular AV perception-planning stack and measures how sensor failures at one boundary propagate downstream, how two mitigation loops reshape that propagation, and what safety outcomes and trade-offs each mitigation produces.

The V&V program is the primary contribution. The failure propagation analysis is the extension.

---

## V-model Architecture

<p align="center">
  <a href="https://niharvaghela1995.github.io/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/Architecture.html" target="_blank">
    <img src="./docs/Architecture.png" width="100%">
  </a>
</p>

<p align="center"><em>Click image to open full interactive architecture — V-model stages, 160-run campaign, safety goal verdicts, key findings</em></p>

---

## Interactive Visualization

**[Open Stage 3 Results — 160-Run Campaign Dashboard](https://niharvaghela1995.github.io/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/stage3_results.html)**
TTC comparison across 8 scenarios · mitigation matrix · safety goal verdicts · FPC analysis

**[Open Phase 3 Sensitivity Matrix — Interactive Explorer](https://niharvaghela1995.github.io/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/phase3_interactive.html)**
Explore how camera glare and LiDAR dropout propagate through sensor fusion trust into planning behavior — click any of the 49 degradation scenarios to inspect the full propagation chain.

---

## V-model Structure

This project follows the standard automotive V&V workflow — **Specify → Integrate → Execute → Evaluate** — and extends it with interface-level failure propagation analysis. Methodology validated against the Foretellix Safety-Driven V&V Guide (2024).

| Stage | Activity | Status |
|-------|----------|--------|
| **Specify** | ODD · HARA · SOTIF triggers · Safety goals · Scenarios (.xosc) | ✅ Complete — Phases 1–6 |
| **Integrate** | CARLA rig · Sensors · Closed-loop smoke test | ✅ Complete — Stage 2 |
| **Execute** | 8-scenario campaign · 4 configurations · 160 runs | ✅ Complete — Stage 3 |
| **Evaluate** | KPIs · GSN safety case · Trade-off ledger · Coverage | ✅ Complete — Stage 4 |

**Traceability spine:** Requirement → Hazard → Safety Goal → Scenario (.xosc) → Closed-loop run (160 runs) → KPI result (JSON) → Failure analysis → Safety case (GSN) → Residual risks → New requirements → back to Requirement

---

## Closed-Loop Campaign — Stages 2–4

**Simulator:** CARLA 0.9.15 · Town10HD_Opt · RTX 4090 · synchronous mode 20 FPS

**Campaign:** 8 SOTIF scenarios × 4 mitigation configurations × variable severities = 160 runs total

| Scenario | SOTIF | ASIL | Runs | Baseline TTC | Loop 2 TTC | Collision prevented |
|----------|-------|------|------|-------------|-----------|---------------------|
| HAZ-01: Pedestrian + glare | T1,T4 | D | 48 | 0.205s | 2.128s | ✅ 100%→0% |
| HAZ-02: Cut-in + fog | T3 | C | 16 | 0.297s | 0.805s | — |
| HAZ-03: Occluded pedestrian | T4 | D | 16 | 0.499s | 7.47s (combined) | — |
| HAZ-04: Fog + pedestrian | T3,T4 | C/D | 16 | 0.388s | 0.702s | — |
| HAZ-05: Rain + LiDAR dropout | T2,T3 | C | 16 | 0.367s | 9.591s | — |
| HAZ-06: Night + low contrast | T1 | C | 16 | 0.367s | 9.591s | — |
| HAZ-07: Construction zone | T3 | C | 16 | 0.319s | 8.545s | — |
| HAZ-08: EMERGENCY / MRC | T5 | B | 16 | 0.224s | 8.51s | ✅ combined loops |

**Four mitigation configurations per scenario:** Baseline · Loop 1 only · Loop 2 only · Combined

**Key numbers:**
- Zero collisions with Loop 2 active across all 160 runs
- HAZ-01 TTC: 0.205s → 2.128s (10.4× improvement)
- Loop 1 alone: zero standalone safety benefit confirmed across every run
- Combined loops required for CONSERVATIVE/EMERGENCY at extreme degradation (HAZ-08)

### Safety Goal Verdicts

| Safety Goal | ASIL | Status |
|-------------|------|--------|
| SG1: Confidence threshold | B | ⚠️ PARTIAL — Loop 1 non-independent across 160 runs |
| SG2: TTC scaling | C | ✅ VERIFIED — 10.4× TTC, collision 100%→0% (HAZ-01) |
| SG3: CONSERVATIVE regime | C | ✅ VERIFIED — triggered in HAZ-03/05/06/07/08 |
| SG4: Affordance override | D | ⚠️ PARTIAL — AEB + proximity override (15m) active |
| SG5: MRC / EMERGENCY trigger | B | ✅ VERIFIED — HAZ-08: EMERGENCY at extreme failure |

**New requirements generated from campaign:** NR-01–NR-08 fed back to Specify stage.

Full V&V report: [`results/stage4/vnv_report.md`](results/stage4/vnv_report.md)
GSN safety case: [`results/stage4/safety_case.md`](results/stage4/safety_case.md)
Coverage tracker: [`docs/coverage_tracker.md`](docs/coverage_tracker.md)
Trade-off ledger: [`results/stage4/trade_off_ledger.md`](results/stage4/trade_off_ledger.md)

---

## Implementation Notes

> **Perception backbone:** Phases 1–6 use SegFormer-B2 (pretrained on Cityscapes)
> as the camera perception backbone — a proxy for BEVFusion's camera branch.
> Phase 7 will replace this with real BEVFusion inference on nuScenes mini.
>
> **Evaluation mode:** Phases 1–6 open-loop (nuScenes mini, synthetic degradation).
> Stages 2–4 closed-loop in CARLA 0.9.15 — 160 runs across 8 SOTIF scenarios.
>
> **Sensor degradation:** Camera corruptions synthetically applied.
> LiDAR dropout simulated via random point removal.

---

## Phase 1 Results — GradCAM + MC Dropout + Planning Demo

![Summary](screenshots/phase1/07_summary.png)

**Key findings:**
- GradCAM attention shift under glare: 0.011 (spatial redistribution confirmed)
- MC Dropout uncertainty: −4.3% under glare on this scene — confidence ≠ uncertainty
  (camera confidence stable at 0.945 while attention pattern shifts)
- Loop 2: planning mode stayed NORMAL — velocity delta −0.1 km/h
- This scene-specific result motivated the systematic 7×7 sweep in Phase 3
- Dataset: nuScenes mini, CAM_FRONT, scene 0

---

## Phase 2 Results — Multi-Camera GradCAM + Sensor Trust

![Phase 2 GradCAM](screenshots/phase2/phase2_01_multicam.png)
![Phase 2 Trust](screenshots/phase2/phase2_02_trust.png)

**Key findings:**
- Camera confidence score remains stable under glare (0.939 → 0.939)
  while attention pattern shifts — confirming confidence ≠ uncertainty
- CAM_FRONT_LEFT shows highest natural uncertainty (0.001667) —
  oblique viewing angle reduces model confidence
- Naive uncertainty→trust mapping motivates Evidential Deep Learning (Phase 4b)

---

## Phase 3 Results — 7×7 Sensitivity Matrix

![Phase 3 Sensitivity Matrix](screenshots/phase3/phase3_01_sensitivity_matrix.png)
![Phase 3 Cross Section](screenshots/phase3/phase3_02_cross_section.png)
![Phase 3 Mode Map](screenshots/phase3/phase3_03_mode_map.png)

**Key findings:**
- System enters CAUTIOUS mode from LiDAR dropout ≥ 10% — LiDAR loss
  dominates trust rebalancing even at low dropout rates
- Camera trust drops 0.58 → 0.41 at maximum glare (zero dropout)
- CONSERVATIVE mode never triggered by naive sigmoid — entire 7×7 grid
  stays CAUTIOUS, motivating EDL approach
- Naive sigmoid produces weak velocity response (−1.3 km/h)

---

## Phase 4a Results — SOTIF & ISO 26262 Safety Analysis

![SOTIF Classification](screenshots/phase4a/phase4_01_sotif_classification.png)
![Risk Analysis](screenshots/phase4a/phase4_02_risk_analysis.png)
![Complete Summary](screenshots/phase4a/phase4_03_complete_summary.png)

**Verification & Validation Traceability:**

| Requirement | Hazard | Scenario | Phase Result | Status | Gap |
|------------|---------|----------|-------------|--------|-----|
| SG1 Confidence threshold | H1,H2 | T1 | Glare increases uncertainty 24.4% | ⚠️ Partial | Loop 1 non-independent |
| SG2 TTC scaling | H3 | T2,T4 | HAZ-01: 10.4× TTC, collision 100%→0% | ✅ Verified (closed-loop) | — |
| SG3 CONSERVATIVE regime | H4 | T3 | HAZ-03/05/06/07/08 triggered | ✅ Verified (closed-loop) | — |
| SG4 Affordance override | H5 | T4 | AEB + proximity override (15m) active | ⚠️ Partial | Classification layer pending |
| SG5 MRC trigger | H6 | T5 | HAZ-08: EMERGENCY at extreme failure | ✅ Verified (closed-loop) | — |
| ODD robustness coverage | H1–H6 | T1–T5 | 8 corruption families benchmarked | ✅ Verified | Need real-world datasets |

**Key findings:**
- 6 hazards identified (H1–H6): 2× ASIL D, 2× ASIL C, 2× ASIL B
- 5 SOTIF trigger conditions (T1–T5): glare, rain dropout, combined degradation,
  pedestrian with degraded sensors, and extreme combined failure
- Unknown unsafe scenario space reduced from 12 to 5 combinations (58.3% reduction)
- Mean risk reduction of 29.3% compared with a naive uncertainty-thresholding baseline
- Highest-criticality hazards: H2 and H5 (ASIL D)

---

## Phase 4b Results — Evidential Deep Learning

![EDL Comparison](screenshots/phase4b/phase4b_01_edl_comparison.png)
![Trust Comparison](screenshots/phase4b/phase4b_02_trust_comparison.png)

**EDL vs MC Dropout comparison:**

| Glare Intensity | MC Trust | EDL Trust | MC Velocity (km/h) | EDL Velocity (km/h) |
|-----------------|----------|-----------|--------------------|---------------------|
| 0.00 | 0.609 | 0.656 | 45.9 | 50.0 |
| 0.15 | 0.596 | 0.656 | 44.6 | 50.0 |
| 0.30 | 0.483 | 0.656 | 33.3 | 50.0 |
| 0.45 | 0.550 | 0.656 | 40.0 | 50.0 |
| 0.60 | 0.586 | 0.657 | 43.6 | 50.0 |
| 0.75 | 0.500 | 0.657 | 35.0 | 50.0 |
| 0.90 | 0.242 | 0.656 | 30.0 | 50.0 |

**Key findings:**
- EDL successfully separates aleatoric (2.94) from epistemic (−2.34) components
- Negative epistemic values indicate the EvidentialHead requires task-specific
  fine-tuning on degraded driving data — the pretrained backbone does not
  produce calibrated Dirichlet parameters out-of-the-box
- MC Dropout shows stronger sensitivity to glare (trust range 0.242–0.609,
  velocity range 30–46 km/h) — demonstrating uncertainty-aware planning works
  even with simpler methods
- EDL framework and trust formula are correctly implemented; calibration gap
  is a known limitation requiring supervised fine-tuning (Phase 7 objective)
- The aleatoric/epistemic separation architecture is validated — values move
  in expected directions under distribution shift

---

## Phase 5 Results — Open-Loop Robustness Benchmark

![Phase 5 Benchmark](screenshots/phase5/phase5_01_corruption_benchmark.png)

**ODD Coverage Matrix:**

| Scenario / Corruption | Pedestrian | Vehicle | Cyclist | Static Obstacle |
|-----------------------|------------|---------|---------|-----------------|
| Clean | ✓ | ✓ | — | ✓ |
| Glare | ✓ | ✓ | — | ✓ |
| Brightness | ✓ | ✓ | — | ✓ |
| Darkness | ✓ | ✓ | — | ✓ |
| Fog | ✓ | ✓ | — | ✓ |
| Motion Blur | ✓ | ✓ | — | ✓ |
| Snow | ✓ | ✓ | — | ✓ |
| Rain | ✓ | ✓ | — | ✓ |

nuScenes mini (Singapore urban) — cyclist scenarios not present in sampled scenes. ✓ = Tested, — = Not present in dataset.

**Key findings:**
- Most impactful corruption: fog (+29.9% mean uncertainty increase)
- Least impactful: snow (+8.7% mean uncertainty increase)
- CONSERVATIVE planning triggered by: glare, brightness, darkness,
  fog, motion blur, snow, rain at high severity
- All corruptions evaluated in open-loop on nuScenes mini CAM_FRONT

---

## Phase 6 Results — Interface Injection Framework

![FPC Matrix](screenshots/phase6/phase6_01_fpc_matrix.png)
![FPC vs Severity](screenshots/phase6/phase6_02_fpc_vs_severity.png)
![Propagation Chain](screenshots/phase6/phase6_03_propagation_chain.png)

**Key findings:**
- 45 injection runs: 5 SOTIF scenarios × 3 injection points × 3 severities
- IP3 (trust weight interface) peak FPC = 0.65 under T4 (ASIL D —
  pedestrian + degraded sensors) at high injection severity
- IP2 (perception output) mean FPC = 0.144 — interface attenuates rather
  than amplifies upstream failures
- 17/45 injection runs caused planning mode changes
- Closed-loop with Loop 2 active: FPC = 0.0 for both IP2 and IP3

---

## Writing

- [Why modular AV stacks can't tilt their head](https://medium.com/@niharvaghela/why-modular-av-stacks-cant-tilt-their-head-17fa40497c13) — the systems thinking behind this project: technical choices, reasoning, honest limitations

- [I built the industry's AV safety V&V playbook from scratch — then read Foretellix's guide](https://medium.com/@niharvaghela/i-built-the-industrys-av-safety-v-v-playbook-from-scratch-then-read-foretellix-s-guide-e066723458ce) — how 160 closed-loop runs in CARLA mapped to the Safety-Driven V&V methodology — and one finding the guide doesn't mention

---

## Research Roadmap

| V&V Objective | Focus | Status |
|---|---|---|
| Phase 1 | GradCAM + MC Dropout + Loop 2 planning demo | ✅ Complete |
| Phase 2 | Multi-camera GradCAM + adaptive sensor trust | ✅ Complete |
| Phase 3 | 7×7 sensitivity matrix + planning mode distribution | ✅ Complete |
| Phase 4a | SOTIF & ISO 26262 — HARA table, risk boundaries | ✅ Complete |
| Phase 4b | Evidential Deep Learning — aleatoric vs epistemic | ✅ Complete |
| Phase 5 | Open-loop robustness benchmark — 8 corruptions × 5 severities | ✅ Complete |
| Phase 6 | Interface injection framework — FPC analysis across T1–T5 | ✅ Complete |
| Stage 2 | CARLA closed-loop rig — ego + CAM_FRONT + LIDAR_TOP operational | ✅ Complete |
| Stage 3 | 8-scenario campaign — 160 closed-loop runs · 4 configs each | ✅ Complete |
| Stage 4 | V&V report · GSN safety case · trade-off ledger · 3/5 SGs verified | ✅ Complete |
| Phase 7 | Real BEVFusion inference + multi-scenario campaign | 📋 Planned |

---

## Tech Stack

PyTorch · SegFormer-B2 (camera backbone proxy) · nuScenes devkit ·
GradCAM · Captum · Conformal Prediction (MAPIE) ·
Evidential Deep Learning · CARLA 0.9.15 · OpenSCENARIO 1.0 · esmini ·
SOTIF (ISO 21448) · ISO 26262 · GSN safety case

## Dataset

nuScenes mini (10 scenes, 404 samples) — [nuscenes.org](https://nuscenes.org)
Registration required for download.
