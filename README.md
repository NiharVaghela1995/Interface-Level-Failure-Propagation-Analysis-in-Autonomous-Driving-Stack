# Autonomous Driving Safety, Simulation & Validation Framework

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Domain](https://img.shields.io/badge/domain-AV%20Safety%20%26%20V%26V-green)
![Status](https://img.shields.io/badge/status-V%26V%20framework-brightgreen)
![Dataset](https://img.shields.io/badge/dataset-nuScenes%20mini-lightgrey)
![Evaluation](https://img.shields.io/badge/evaluation-closed--loop%20%2B%20open--loop-brightgreen)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/NiharVaghela1995/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/blob/main/notebooks/phase1_gradcam_uncertainty_planning.ipynb)
[![Interactive Demo](https://img.shields.io/badge/demo-interactive%20viz-blue)](https://niharvaghela1995.github.io/Interface-Level-Failure-Propagation-Analysis-in-Autonomous-Driving-Stack/phase3_interactive.html)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20718531-blue)](https://doi.org/10.5281/zenodo.20718531)

## What this project is

A simulation-based safety validation program for autonomous driving systems, built on the standard automotive V-model — hazard analysis (HARA/SOTIF), scenario-based test design, closed-loop simulation in CARLA, KPI measurement, coverage analysis, and a GSN safety case.

On top of that foundation, the project instruments four interface points inside a modular AV perception-planning stack and measures how sensor failures at one boundary propagate downstream, how two mitigation loops reshape that propagation, and what safety outcomes and trade-offs each mitigation produces.

The V&V program (Stages 2-4, the 160-run closed-loop campaign) is the primary, validated contribution. A parallel exploratory track investigated whether a *learned* perception-uncertainty signal (rather than known injected severity) could drive the same trust-and-planning logic — that track surfaced real, documented signal-quality problems and is presented honestly as open work, not as a result. See "Implementation Notes" below and `vnv_program.md` Section 9 for the full account.

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
| **Specify** | ODD · HARA · SOTIF triggers · Safety goals · Scenarios (.xosc) | ✅ Complete |
| **Integrate** | CARLA closed-loop rig · Sensors · 4 interface injection points | ✅ Complete |
| **Execute** | 8-scenario campaign · 4 configurations · 160 runs | ✅ Complete |
| **Evaluate** | KPIs · GSN safety case · Trade-off ledger · Coverage | ✅ Complete |

**Traceability spine:** Requirement → Hazard → Safety Goal → Scenario (.xosc) → Closed-loop run (160 runs) → KPI result (JSON) → Failure analysis → Safety case (GSN) → Residual risks → New requirements → back to Requirement

---

## Closed-Loop Campaign — Stages 2–4

**Simulator:** CARLA 0.9.15 · Town10HD_Opt · RTX 4090 · synchronous mode 20 FPS

**Campaign:** 8 SOTIF scenarios × 4 mitigation configurations × variable severities = 160 runs total

**Note on signal source:** the trust-and-planning logic in this closed-loop campaign uses *known injected degradation severity* (glare intensity, LiDAR dropout rate) as its input — a deliberate simplification to validate the systems/control response independent of perception-model uncertainty estimation. See "Implementation Notes" below for why, and for the separate exploratory work on learned uncertainty signals.

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
- Loop 1 alone: zero standalone safety benefit confirmed across every run — an architectural finding (Loop 1 and Loop 2 are a coupled mechanism, not independent layers), not a calibration gap
- Combined loops required for CONSERVATIVE/EMERGENCY at extreme degradation (HAZ-08)
- Failure Propagation Coefficient (Loop 2 only, safety-outcome basis) stays at or below 1.0 in every measured scenario — no amplification anywhere. Attenuation is graduated: complete (FPC=0.0) in rain/night/construction; mild (FPC 0.87–0.92) in fog/occlusion; near-full transmission (FPC=0.99) in the most extreme combined-failure scenario, where Combined config is required

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

> **Two separate tracks in this repository — read this before citing any number below.**
>
> **Track 1 — the closed-loop campaign (Stages 2–4, 160 runs).** This is the
> validated contribution. Trust and planning mode are computed as a
> deterministic function of *known* injected degradation severity. This
> was a deliberate engineering choice: it isolates and validates the
> systems/control question (does the stack correctly reweight trust and
> escalate planning regime when degradation is known to be present) from
> the separate, harder question of whether a perception model can detect
> degradation reliably on its own.
>
> **Track 2 — exploratory perception-uncertainty work (Phases 1–7,
> open-loop, single/few-sample, nuScenes mini).** This track investigated
> whether MC Dropout or Evidential Deep Learning could produce a
> degradation-responsive uncertainty signal directly from a perception
> model, without externally-known severity. **This is presented as an
> open problem, not a validated finding.** Specifically:
> - Phase 1's single-sample MC Dropout result showed uncertainty
>   *decreasing* under glare — the wrong direction
> - Phase 4b's Evidential Deep Learning head was never trained (only the
>   pretrained backbone was loaded); its outputs are flat/near-constant
>   across the full glare sweep and should not be read as a measurement
> - Phase 3's broader 7×7 sweep shows real scatter in the uncertainty
>   signal, consistent with the above
>
> Phase 7 (real BEVFusion inference) is planned/exploratory and has not
> yet been validated against the real model checkpoint.
>
> **Perception backbone:** Phases 1–6 use SegFormer-B2 (pretrained on
> Cityscapes) as a camera perception proxy — not yet validated against a
> real multi-sensor fusion stack.
>
> **Sensor degradation:** Camera corruptions synthetically applied.
> LiDAR dropout simulated via random point removal.
>
> Full account, including what would be required to close the
> learned-uncertainty gap (trained + calibrated evidential head or
> ensemble, validated with a reliability diagram): see `vnv_program.md`
> Section 9.

---

## Phase 1 — Exploratory: GradCAM + MC Dropout + Planning Demo

![Summary](screenshots/phase1/07_summary.png)

**Status: exploratory single-scene demonstration, not a validated finding.**

- GradCAM attention shift under glare: 0.011 — attention does spatially redistribute under degradation, a real and reproducible measurement
- MC Dropout uncertainty on this specific scene/sample went from 0.0002455 (clean) to 0.0002349 (glare) — a **decrease**, the wrong direction for a degradation-tracking signal. Reported honestly rather than omitted: on this single sample, the stochastic MC Dropout signal did not reliably track degradation severity
- Loop 2 in this single-sample demo stayed in NORMAL mode, consistent with the uncertainty signal not crossing a mode-change threshold
- Dataset: nuScenes mini, CAM_FRONT, scene 0, single sample

**Why this is kept in the repository:** the attention-shift measurement is real and useful; the uncertainty-direction result is an honest negative finding that motivated the broader 7×7 sweep in Phase 3, and ultimately the decision to use known injected severity (rather than learned uncertainty) as the input to the closed-loop Stage 2-4 campaign.

---

## Phase 2 Results — Multi-Camera GradCAM + Sensor Trust

![Phase 2 GradCAM](screenshots/phase2/phase2_01_multicam.png)
![Phase 2 Trust](screenshots/phase2/phase2_02_trust.png)

**Key findings:**
- Camera confidence score remains stable under glare (0.939 → 0.939) while attention pattern shifts — on this multi-camera sample, uncertainty also showed a small increase (+3.8%), the expected direction (contrast with Phase 1's single-sample result, which went the other way — see Phase 1 for the honest discussion of signal scatter)
- CAM_FRONT_LEFT shows highest natural uncertainty (0.001667) — oblique viewing angle reduces model confidence
- This scatter across samples (Phase 1 vs Phase 2) motivated the systematic 7×7 sweep in Phase 3 to characterise the signal's reliability properly, rather than relying on single-sample demonstrations

---

## Phase 3 Results — 7×7 Sensitivity Matrix

![Phase 3 Sensitivity Matrix](screenshots/phase3/phase3_01_sensitivity_matrix.png)
![Phase 3 Cross Section](screenshots/phase3/phase3_02_cross_section.png)
![Phase 3 Mode Map](screenshots/phase3/phase3_03_mode_map.png)

**Key findings:**
- Camera trust drops 0.58 → 0.41 at maximum glare (zero dropout) — this trust value is computed from a deterministic sigmoid of glare severity, the same approach later used in the closed-loop Stage 2-4 campaign
- The underlying MC Dropout uncertainty values across the 7×7 grid show real scatter (range roughly 0.00026–0.00064) without a clean monotonic trend against glare alone — consistent with Phase 1's finding that the raw learned signal is noisy at this sample size
- System enters CAUTIOUS mode from LiDAR dropout ≥ 10% in this sweep
- This scatter is the direct motivation for using known severity (not raw uncertainty) as the closed-loop campaign's input — see Implementation Notes above

---

## Phase 4a Results — SOTIF & ISO 26262 Safety Analysis

![SOTIF Classification](screenshots/phase4a/phase4_01_sotif_classification.png)
![Risk Analysis](screenshots/phase4a/phase4_02_risk_analysis.png)
![Complete Summary](screenshots/phase4a/phase4_03_complete_summary.png)

**Verification & Validation Traceability:**

| Requirement | Hazard | Scenario | Result | Status | Gap |
|------------|---------|----------|-------------|--------|-----|
| SG1 Confidence threshold | H1,H2 | T1 | Loop 1 trust formula implemented | ⚠️ Partial | Loop 1 non-independent (closed-loop finding) |
| SG2 TTC scaling | H3 | T2,T4 | HAZ-01: 10.4× TTC, collision 100%→0% | ✅ Verified (closed-loop) | — |
| SG3 CONSERVATIVE regime | H4 | T3 | HAZ-03/05/06/07/08 triggered | ✅ Verified (closed-loop) | — |
| SG4 Affordance override | H5 | T4 | AEB + proximity override (15m) active | ⚠️ Partial | Classification layer pending |
| SG5 MRC trigger | H6 | T5 | HAZ-08: EMERGENCY at extreme failure | ✅ Verified (closed-loop) | — |
| ODD robustness coverage | H1–H6 | T1–T5 | 8 corruption families exercised | ⚠️ Exploratory | Perception-uncertainty signal not yet calibrated — see Phase 1/4b |

**Key findings:**
- 6 hazards identified (H1–H6): 2× ASIL D, 2× ASIL C, 2× ASIL B
- 5 SOTIF trigger conditions (T1–T5): glare, rain dropout, combined degradation, pedestrian with degraded sensors, and extreme combined failure
- Unknown unsafe scenario space reduced from 12 to 5 combinations (58.3% reduction) — this is a scenario-space classification result, independent of the perception-uncertainty signal questions discussed in Phase 1/4b
- Highest-criticality hazards: H2 and H5 (ASIL D)

**A note on this section's quantitative figures:** the HARA table — hazard
identification, severity/exposure/controllability classification, ASIL
derivation, SOTIF trigger definitions, and the hazard-to-mitigation
mapping — is genuine engineering classification work and is presented as
such. However, the "29.3% mean risk reduction" figure and the per-hazard
"achieved coverage" percentages shown in earlier versions of this
analysis were generated from illustrative/synthetic arrays rather than
measured from simulation output, and are **not cited here as validated
results**. The classification structure (which hazards exist, their ASIL
ratings, and which mitigation addresses which hazard) stands; the
specific risk-reduction percentage does not.

---

## Phase 4b — Exploratory: Evidential Deep Learning (Open Problem)

![EDL Comparison](screenshots/phase4b/phase4b_01_edl_comparison.png)
![Trust Comparison](screenshots/phase4b/phase4b_02_trust_comparison.png)

**Status: exploratory, not validated. Read this before the numbers below.**

This phase attempted to replace the MC Dropout uncertainty signal with an Evidential Deep Learning (EDL) head, following Sensoy et al. (2018). The EDL head was attached to a pretrained SegFormer-B2 backbone but **was never trained** — only the backbone weights are pretrained; the evidential head itself is randomly initialised. As a result:

- Epistemic and aleatoric outputs are effectively constant across the full glare sweep (epistemic: −2.347 to −2.345; aleatoric: 2.940 to 2.943) — consistent with an untrained head producing near-noise output, not a measured signal
- The "EDL velocity" column below is constant at exactly 50.0 km/h at every glare level — the planner never leaves NORMAL mode under this signal, which is a symptom of a flat, untrained uncertainty estimate, not a finding
- The MC Dropout comparison series in this experiment uses a closed-form formula as a stand-in baseline rather than measured dropout-pass variance — for an apples-to-apples comparison this needs to be replaced with real MC Dropout output

**What this section does NOT show:** that EDL outperforms MC Dropout, that the aleatoric/epistemic separation is calibrated, or that the trust formula produces correct planning behaviour from a learned signal. None of these claims are supported by the current data.

**What would close this gap:** train the evidential head with the evidential loss function (not just load pretrained backbone weights), calibrate it against a reliability diagram (ECE) on held-out degraded samples, and only then compare it against a real (not formula-based) MC Dropout baseline. Tracked as open work — see `vnv_program.md` Section 9.

| Glare Intensity | MC Trust (formula baseline) | EDL Trust (untrained head) | MC Velocity (km/h) | EDL Velocity (km/h) |
|-----------------|----------|-----------|--------------------|---------------------|
| 0.00 | 0.609 | 0.656 | 45.9 | 50.0 |
| 0.15 | 0.596 | 0.656 | 44.6 | 50.0 |
| 0.30 | 0.483 | 0.656 | 33.3 | 50.0 |
| 0.45 | 0.550 | 0.656 | 40.0 | 50.0 |
| 0.60 | 0.586 | 0.657 | 43.6 | 50.0 |
| 0.75 | 0.500 | 0.657 | 35.0 | 50.0 |
| 0.90 | 0.242 | 0.656 | 30.0 | 50.0 |

*The EDL columns are flat by construction (untrained head) — shown for transparency, not as evidence of a working uncertainty signal.*

---

## Phase 5 Results — Open-Loop Robustness Benchmark

![Phase 5 Benchmark](screenshots/phase5/phase5_01_corruption_benchmark.png)

**Status: exploratory, same uncertainty-signal caveats as Phase 1/3/4b apply.**

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

**Reported ranking (most to least impactful by mean uncertainty increase):** fog, rain, glare, motion blur, brightness, darkness, snow — with "clean" itself showing a 12.1% increase over its own baseline. That a clean-vs-clean comparison shows a double-digit increase is itself a sign of measurement noise in this benchmark, consistent with the uncertainty-signal issues documented in Phase 1/3/4b. These percentages should be treated as exploratory, not as calibrated robustness figures, until the underlying signal is validated.

---

## Phase 6 Results — Interface Injection Framework (Open-Loop)

![FPC Matrix](screenshots/phase6/phase6_01_fpc_matrix.png)
![FPC vs Severity](screenshots/phase6/phase6_02_fpc_vs_severity.png)
![Propagation Chain](screenshots/phase6/phase6_03_propagation_chain.png)

**Key findings:**
- 45 injection runs: 5 SOTIF scenarios × 3 injection points × 3 severities, open-loop
- This open-loop injection framework is a methodology precursor to the closed-loop Stage 2-4 campaign, which is where the validated FPC results are — see "Closed-Loop Campaign" section above for the safety-outcome-basis FPC values
- 17/45 injection runs caused planning mode changes

---

## Writing

- [Why modular AV stacks can't tilt their head](https://medium.com/@niharvaghela/why-modular-av-stacks-cant-tilt-their-head-17fa40497c13) — the systems thinking behind this project: technical choices, reasoning, honest limitations

- [I built the industry's AV safety V&V playbook from scratch — then read Foretellix's guide](https://medium.com/@niharvaghela/i-built-the-industrys-av-safety-v-v-playbook-from-scratch-then-read-foretellix-s-guide-e066723458ce) — how 160 closed-loop runs in CARLA mapped to the Safety-Driven V&V methodology

---

## Research Roadmap

| V&V Objective | Focus | Status |
|---|---|---|
| Phase 1 | GradCAM + MC Dropout + Loop 2 planning demo | ✅ Complete (exploratory — see notes) |
| Phase 2 | Multi-camera GradCAM + adaptive sensor trust | ✅ Complete (exploratory) |
| Phase 3 | 7×7 sensitivity matrix + planning mode distribution | ✅ Complete (exploratory) |
| Phase 4a | SOTIF & ISO 26262 — HARA table, risk boundaries | ✅ Complete |
| Phase 4b | Evidential Deep Learning — aleatoric vs epistemic | ⚠️ Exploratory — EDL head untrained, open problem |
| Phase 5 | Open-loop robustness benchmark — 8 corruptions × 5 severities | ⚠️ Exploratory — see signal caveats |
| Phase 6 | Interface injection framework — open-loop FPC precursor | ✅ Complete (open-loop methodology) |
| Stage 2 | CARLA closed-loop rig — ego + CAM_FRONT + LIDAR_TOP, 4 interface points | ✅ Complete |
| Stage 3 | 8-scenario campaign — 160 closed-loop runs · 4 configs each | ✅ Complete |
| Stage 4 | V&V report · GSN safety case · trade-off ledger · 3/5 SGs verified | ✅ Complete |
| Phase 7 | Real BEVFusion inference + multi-scenario campaign | 📋 Planned — not yet validated against real checkpoint |

---

## Tech Stack

PyTorch · SegFormer-B2 (camera backbone proxy) · nuScenes devkit ·
GradCAM · Captum · Conformal Prediction (MAPIE) ·
Evidential Deep Learning (exploratory) · CARLA 0.9.15 · OpenSCENARIO 1.0 · esmini ·
SOTIF (ISO 21448) · ISO 26262 · GSN safety case

## Dataset

nuScenes mini (10 scenes, 404 samples) — [nuscenes.org](https://nuscenes.org)
Registration required for download.
