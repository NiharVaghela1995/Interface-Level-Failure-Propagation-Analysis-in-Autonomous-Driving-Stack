# V&V Program: Interface-Level Failure Propagation in Autonomous Driving Stacks

*A closed-loop V&V program following the standard Specify → Integrate → Execute → Evaluate model, extended with interface-centric failure-propagation and mitigation analysis.*

---

## 1. Positioning

This is a verification-and-validation program built on the standard automotive V-model. Requirements and a defined ODD drive hazard analysis; hazards become safety goals; safety goals become parameterised scenarios; scenarios execute against the system under test in closed-loop simulation; results become KPIs, coverage, and a safety case; the engineering verdict generates new requirements.

The differentiator is narrow and stated plainly. In a modular AV stack — perception, fusion, prediction, planning, control — dangerous behaviour rarely originates where it becomes visible. A camera insufficiency surfaces as a planning error two interfaces downstream. Standard V&V evaluates the *vehicle-level outcome*; this program additionally instruments the *interfaces between elements* and measures how a fault injected at one boundary propagates, attenuates, or amplifies on its way to vehicle behaviour.

This is not a new idea so much as a quantitative, simulation-based treatment of properties the standards already name but seldom measure directly: **freedom from interference between software elements** (ISO 26262), **fault propagation** (FMEA / fault-tree reasoning), and **triggering conditions acting on functional insufficiencies** (ISO 21448 / SOTIF).

The second strand is mitigation. A human driver who loses confidence in one sense leans on the others and reduces speed and commitment until confidence returns. That observation motivates two safety mechanisms that this program *specifies as requirements* and then *measures*: an adaptive sensor-trust loop (lean on the reliable modality) and an uncertainty-aware planning loop (slow down, widen margins, escalate regime). Treating these as specified, testable safety functions keeps the contribution inside the engineering process rather than beside it.

**Posture: the standard process, executed properly, with a deeper treatment of interface behaviour and mitigation where a systems view earns it.**

---

## 2. Scope and ODD

- **ODD slice:** urban intersection and arterial; daylight to low-light; dry to moderate rain and glare; 0–50 km/h; mixed traffic including vulnerable road users
- **Lead hazard (vertical slice first):** ego fails to yield to a pedestrian crossing from behind an occlusion under a degraded front camera — HAZ-01 in the traceability matrix
- **Sensor scope:** front camera (perception backbone) + top LiDAR (cross-modal compensation)

---

## 3. Program at a Glance

| V-stage | Standard activity | Status | Evidence |
|---|---|---|---|
| **Specify** | ODD, HARA, SOTIF triggers, safety goals, logical → concrete scenarios | ✅ Complete | HARA (H1–H6, ASIL A–D), SG1–SG5, SOTIF T1–T5 |
| **Integrate** | CARLA world + ego sensors, closed-loop rig, four interface injection points | ✅ Complete | CARLA 0.9.15 closed-loop rig, IP1–IP4 instrumented |
| **Execute** | Four-configuration mitigation campaign across 8 scenarios | ✅ Complete | 160 closed-loop runs (8 scenarios × 4 configs × severities) |
| **Evaluate** | KPIs, failure analysis, coverage, GSN safety case, new requirements | ✅ Complete | V&V report, safety case, FPC recalibration, 8 new requirements (NR-01–08) |

**Current status: all four stages complete for the closed-loop campaign (160 runs, 8 scenarios).**

A separate, earlier exploratory track (open-loop perception-uncertainty work — GradCAM, MC Dropout, Evidential Deep Learning on single-frame samples) ran in parallel and is **not part of the closed-loop campaign above**. See Section 9 — this exploratory track has known, documented signal-quality issues and its results are not used as evidence in the safety case.

---

## 4. Stage 1 — Specify ✅ Complete

**What was built:**

- **HARA (ISO 26262):** 6 hazards (H1–H6), ASIL A–D, 2× ASIL D (H2: missed pedestrian under glare; H5: pedestrian at crossing under combined failure)
- **Safety goals:** SG1–SG5 covering confidence threshold, TTC scaling, CONSERVATIVE regime, affordance override, MRC trigger
- **SOTIF triggers (ISO 21448):** T1 direct sunlight/glare (Cl. 8.3), T2 rain/LiDAR dropout (Cl. 8.3), T3 combined degradation (Cl. 8.4), T4 pedestrian + degraded sensors (Cl. 8.4), T5 extreme combined failure (Cl. 8.4)

**Interface provenance (systems extension):** Each hazard carries the interface where its functional insufficiency originates and the boundary it crosses to reach behaviour — e.g. *camera branch → fusion-trust interface → planning input* for H2.

**Mitigations as safety requirements:** Two adaptation loops specified as compensatory safety functions: degraded perception shall reweight modality trust toward the reliable sensor (SG-trust / "Loop 1"), and elevated uncertainty shall trigger a conservative planning regime with increased margins and reduced speed (SG-regime / "Loop 2").

---

## 5. Stage 2 — Integrate ✅ Complete

**What was built:**
- CARLA 0.9.15 closed-loop world (Town10HD_Opt), synchronous mode, 20 FPS, RTX 4090
- Ego sensor suite: CAM_FRONT (1280×720) + LIDAR_TOP (64-channel, ~14,600 pts/frame)
- Deterministic Loop 1 / Loop 2 trust-and-planning logic (`planning_utils.py`) — camera/LiDAR trust and planning mode computed as a function of **injected, known degradation severity** (glare intensity, LiDAR dropout rate), not from a learned perception-uncertainty signal
- Four interface injection points instrumented: IP1 (sensor input), IP2 (perception output), IP3 (trust weights), IP4 (planning output)

**Design choice, stated plainly:** the closed-loop rig uses *known* injected severity as the trust-and-planning input, rather than a model-estimated uncertainty signal. This was a deliberate simplification to validate the systems/control response — does the stack correctly reweight trust and escalate planning regime when degradation is known to be present — independent of whether a perception model can detect that degradation on its own. The second question (can a learned signal detect degradation reliably) was explored separately; see Section 9.

---

## 6. Stage 3 — Execute ✅ Complete

**Four-configuration mitigation campaign, executed across 8 scenarios:**

| Config | Description |
|---|---|
| Baseline | Both loops disabled |
| Loop 1 only | Adaptive sensor trust active, planning unchanged |
| Loop 2 only | Uncertainty-aware planner active, trust fixed |
| Combined | Both loops active |

**Scenarios executed (160 runs total):**

| Scenario | Hazard | SOTIF | ASIL | Runs |
|---|---|---|---|---|
| HAZ-01: Pedestrian + glare | H2 | T1, T4 | D | 48 |
| HAZ-02: Cut-in + fog | H4 | T3 | C | 16 |
| HAZ-03: Occluded pedestrian | H5 | T4 | D | 16 |
| HAZ-04: Fog + pedestrian | H4, H5 | T3, T4 | C/D | 16 |
| HAZ-05: Rain + LiDAR dropout | H3 | T2, T3 | C | 16 |
| HAZ-06: Night + low contrast | H1 | T1 | C | 16 |
| HAZ-07: Construction zone | H4 | T3 | C | 16 |
| HAZ-08: EMERGENCY / MRC | H6 | T5 | B | 16 |
| **Total** | | | | **160** |

---

## 7. Stage 4 — Evaluate ✅ Complete

**Results summary:**
- **Zero collisions with Loop 2 active across all 160 runs**
- Loop 1 alone provides zero standalone safety benefit in every run — an architectural finding, not a calibration gap: Loop 1 and Loop 2 are a coupled mechanism, not independent layers
- 3/5 safety goals fully verified (SG2 TTC scaling, SG3 CONSERVATIVE regime, SG5 MRC/EMERGENCY); 2/5 partial (SG1, SG4)

**KPI set instrumented:**

| Metric | Category | Threshold | Status |
|---|---|---|---|
| Collision count / collision-with-VRU | Safety | 0 | Instrumented |
| Minimum TTC | Safety | ≥ 1.5s | Instrumented |
| Minimum clearance to VRU | Safety | ≥ 1.0m | Instrumented |
| Failure Propagation Coefficient (to safety outcome) | Propagation | ≤ 1.0 | Instrumented — recalibrated to collision-probability basis |
| Intervention rate | Trade-off | report | Instrumented |
| Max accel / jerk | Comfort | ≤ 3.0 / ≤ 2.0 m/s² | Proxy only — speed reduction used; exact instrumentation pending |
| Lane departure | Compliance | 0 | Not instrumented — not applicable to current straight-approach scenario design |

**Trade-off ledger and GSN safety case:** complete, with 8 new requirements (NR-01–NR-08) fed back to Specify, and 6 residual risks documented with closure paths.

---

## 8. Traceability Spine

```
Requirement → Hazard (HARA + interface provenance) → Safety goal → Scenario (.xosc / Python)
  → Closed-loop run → KPI result → Failure analysis (FPC) → Coverage
  → Evidence → Safety claim → Residual risk / trade-off → NEW requirement ──┐
       ▲                                                                     │
       └─────────────────────────────────────────────────────────────────────┘
```

---

## 9. Known Limitations and Validation Debt

**On the closed-loop campaign (160 runs) — what to know:**

| Limitation | Status | Closure path |
|---|---|---|
| Trust/planning input is known severity, not learned uncertainty | By design — see Stage 2 | See "Exploratory perception-uncertainty track" below |
| Dataset / map scale | Single CARLA map (Town10HD_Opt) | Multi-map campaign (NR-04) |
| Sim-to-real gap | Simulation evidence only | Real-world validation debt |
| Lane departure, exact accel/jerk | Not instrumented / proxy only | Velocity logging + lane-keeping planner (Phase 7 / Autoware integration) |

**On the separate, exploratory perception-uncertainty track — read this before citing any of the following:**

A parallel, earlier exploratory effort attempted to derive the trust/planning input directly from a learned perception-uncertainty signal (MC Dropout and Evidential Deep Learning on a SegFormer-B2 backbone, single-frame nuScenes-mini samples) rather than from known injected severity. **This track has real, identified problems and its numerical results should not be cited as validated findings:**

- The MC Dropout uncertainty signal did not respond reliably to degradation severity on the tested samples — in one measured case, uncertainty *decreased* under glare, the wrong direction
- The Evidential Deep Learning head was not trained (pretrained backbone weights loaded; evidential head randomly initialised) — its outputs are not a measurement, and any comparison built on it should be disregarded
- The single-image, single-pass nature of this exploration means dynamic range is small and likely dominated by stochastic noise rather than a genuine degradation-tracking signal

**This track is retained in the repository as an honestly-documented open problem, not as a result.** The actual research question — can a perception model produce a calibrated, degradation-responsive uncertainty estimate that a safety-critical planner can act on directly, without externally-known ground-truth severity — remains open. Closing it requires: a trained and calibrated evidential or ensemble-based uncertainty head, validated against a reliability diagram (ECE) on held-out degraded samples, before any trust/planning logic is built on top of it.

---

## 10. Build Sequence (historical)

1. **Vertical slice first** — HAZ-01 end-to-end through all 4 stages before breadth ✅
2. **Stage 2** — CARLA closed-loop rig ✅
3. **Stage 3** — Four-configuration campaign across full scenario set ✅
4. **Stage 4** — GSN safety case, trade-off ledger, feedback to Specify ✅
5. **Next** — replace known-severity trust input with a calibrated learned uncertainty signal (see Section 9); multi-map campaign; real-hardware/Autoware integration

---

*Closed-loop campaign code: `scripts/stage2_*.py` through `scripts/stage4_*.py`. Exploratory perception-uncertainty code: `scripts/phase1_*.py` through `scripts/phase7_*.py` — see Section 9 for status. Results: `results/stage3/`, `results/stage4/`.*
