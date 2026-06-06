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

| V-stage | Standard activity | Already built | Net-new work |
|---|---|---|---|
| **Specify** | ODD, HARA, SOTIF triggers, safety goals, logical → concrete scenarios, OpenSCENARIO | HARA (H1–H6, ASIL A–D), SG1–SG5, SOTIF T1–T5, corruption-impact ranking | Interface provenance per hazard; loops as safety requirements; `.xosc` authoring |
| **Integrate** | CARLA world + ego sensors, AD stack via ROS2 + bridge, esmini logical track, closed-loop smoke test | Sensor-degradation and interface-injection code (becomes rig instrumentation) | The closed-loop rig — **essentially all new** |
| **Execute** | Scenario Runner criteria, batch runs, data recording, dataset QA | Degradation/corruption stimulus library, injection points IP1–IP4, sensitivity-sweep method | In-loop injection runs; four-configuration mitigation campaign |
| **Evaluate** | KPIs, failure analysis, coverage, report, engineering decision → new requirements | FPC metric, sensitivity/coverage maps, traceability skeleton | FPC against safety outcomes; trade-off ledger; GSN safety case |

**Current status:** Stage 1 (Specify) complete across 6 phases. Stage 2 (Integrate) in progress on `dev` branch.

---

## 4. Stage 1 — Specify ✅ Complete

**What was built across Phases 1–6:**

- **HARA (ISO 26262):** 6 hazards (H1–H6), ASIL A–D, 2× ASIL D (H2: missed pedestrian under glare; H5: pedestrian at crossing under combined failure)
- **Safety goals:** SG1–SG5 covering confidence threshold, TTC scaling, CONSERVATIVE regime, affordance override, MRC trigger
- **SOTIF triggers (ISO 21448):** T1 direct sunlight/glare (Cl. 8.3), T2 rain/LiDAR dropout (Cl. 8.3), T3 combined degradation (Cl. 8.4), T4 pedestrian + degraded sensors (Cl. 8.4), T5 extreme combined failure (Cl. 8.4)
- **Sensitivity matrix:** 7×7 sweep (glare 0–0.9 × LiDAR dropout 0–80%), camera trust 0.58→0.41 at max glare
- **Corruption benchmark:** 8 types × 5 severities — fog most impactful (+29.9%), snow least (+8.7%)
- **Interface injection (open-loop):** 45 runs across T1–T5 × IP2/IP3/IP4 × 3 severities — FPC < 1.0 for IP2 and IP3

**Interface provenance (systems extension):** Each hazard carries the interface where its functional insufficiency originates and the boundary it crosses to reach behaviour — e.g. *camera branch → fusion-trust interface → planning input* for H2. This makes the later closed-loop propagation measurement traceable to a hazard rather than free-floating.

**Mitigations as safety requirements:** The two adaptation loops are specified as compensatory safety functions on controllability grounds: degraded perception shall reweight modality trust toward the reliable sensor (SG-trust), and elevated uncertainty shall trigger a conservative planning regime with increased margins and reduced speed (SG-regime).

---

## 5. Stage 2 — Integrate 🔄 In Progress

**Objective:** Stand up the closed-loop simulation rig and wire the system under test into it.

**Components:**
- CARLA 0.9.15 world matching the ODD (urban intersection, configurable weather)
- Ego sensor suite: CAM_FRONT + LIDAR_TOP matching stack input spec
- AD stack integration via ROS2 + CARLA–Autoware bridge
- Time synchronisation verification
- esmini logical track for cheap scenario validation before CARLA runs
- Closed-loop smoke test: trivial route, no scenario actors, perception → planning → control → actuation loop stable

**Instrumentation (systems extension):** The rig is not stood up clean — it is instrumented at four interface points so that a fault can be both injected and measured mid-loop:

```
IP1 — sensor input (raw camera/LiDAR)
IP2 — perception output (corrupted logits / feature map)
IP3 — fusion-trust weights (Loop 1 output, pre-planning)
IP4 — planning output (pre-control)
```

A standard SIL rig answers "does the stack pass the scenario." This rig additionally answers "where did the fault enter, and how far did it travel."

**Gating dependency:** Every behavioural and safety-outcome claim downstream depends on this stage. This is the single highest-value engineering action in the program.

---

## 6. Stage 3 — Execute 📋 Planned

**Standard runs:**
- Criteria-instrumented scenarios (Scenario Runner pass/fail + trigger conditions)
- Batch execution via Leaderboard route/suite
- Per-run logging: rosbag, sensor streams, telemetry, scenario outcome

**Four-configuration mitigation campaign:**

Every scenario is run under four configurations:

| Config | Description |
|---|---|
| Baseline | Both loops disabled |
| Loop 1 only | Adaptive sensor trust active, planning unchanged |
| Loop 2 only | Uncertainty-aware planner active, trust fixed |
| Combined | Both loops active |

Scenarios: cut-in, pedestrian emergence, occlusion, fog, rain, night, glare, construction zone.

This converts execution from a verdict check into a controlled intervention experiment — the difference between configurations *is* the measured mitigation effect.

---

## 7. Stage 4 — Evaluate 📋 Planned

**KPI set:**

| Metric | Category | Threshold |
|---|---|---|
| Collision count / collision-with-VRU | Safety | 0 |
| Minimum TTC | Safety | ≥ 1.5s |
| Minimum clearance to VRU | Safety | ≥ 1.0m |
| Lane-departure / red-light infractions | Compliance | 0 |
| Max longitudinal accel / jerk | Comfort | ≤ 3.0 / ≤ 2.0 m/s² |
| **Failure Propagation Coefficient (to behaviour)** | Propagation | < 1.0 target |
| **Loop-attributable risk reduction** | Mitigation efficacy | Δ baseline → each config |
| **Residual risk per hazard** | Mitigation efficacy | Input to safety case |
| **Planner oscillation / intervention rate** | Trade-off | Secondary cost metric |

**Trade-off ledger (systems extension):** Every mitigation that improves one metric while regressing another is logged explicitly — e.g. conservative planning reduces collision risk at an occluded crossing but increases dwell time and rear-end exposure in dense following traffic. These secondary effects are not failures; they are what a systems view expects, and documenting them is what makes the safety argument honest.

**GSN safety case:** Top claim → evidence (diagnostics, propagation runs, mitigation campaign, coverage) → residual risks → per-safety-goal conclusions. Every residual risk and trade-off is written as a new requirement feeding back to Specify.

---

## 8. Traceability Spine

```
Requirement → Hazard (HARA + interface provenance) → Safety goal → Scenario (.xosc)
  → Closed-loop run → KPI result → Failure analysis (FPC) → Coverage
  → Evidence → Safety claim → Residual risk / trade-off → NEW requirement ──┐
       ▲                                                                     │
       └─────────────────────────────────────────────────────────────────────┘
```

---

## 9. Known Limitations and Validation Debt

| Limitation | Status | Closure path |
|---|---|---|
| Perception backbone fidelity | SegFormer-B2 proxy; real stack in Stage 2 | Replace at Integrate |
| Open-loop to closed-loop | All Phase 1–6 results are open-loop | Stage 2 gating |
| Uncertainty calibration | EDL epistemic head uncalibrated on degraded data | Supervised fine-tuning (Stage 3) |
| Dataset scale | nuScenes-mini (10 scenes, 404 samples) | Scale at Execute |
| Sim-to-real gap | Simulation evidence only | Real-world validation debt |

---

## 10. Build Sequence

1. **Vertical slice first** — HAZ-01 end-to-end through all 4 stages before breadth
2. **Stage 2** — CARLA + esmini + ROS2 rig (gating dependency)
3. **Stage 3** — Four-configuration campaign across full scenario set
4. **Stage 4** — GSN safety case, trade-off ledger, feedback to Specify
5. **Traceability live throughout** — fill as runs happen, not retrofitted

---

*All phase results (Phases 1–6), code, and figures are in the repository root. This document describes the full program scope including planned stages.*
