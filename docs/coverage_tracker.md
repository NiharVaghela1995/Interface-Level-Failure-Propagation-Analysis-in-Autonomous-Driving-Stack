# Coverage Tracker
## Interface-Level Failure Propagation Analysis in Autonomous Driving Stacks

*Updated: June 2026 — after Stage 3 HAZ-01 closed-loop campaign*

---

## Safety Goal Coverage

| Safety Goal | ASIL | Test Scenario | Phase Evidence | Closed-Loop Evidence | Verdict | Gap |
|-------------|------|--------------|----------------|----------------------|---------|-----|
| SG1: Confidence threshold — perception confidence shall not drive planning when camera reliability < 0.5 | B | T1 glare | Phase 2: confidence flat (0.939) while uncertainty rises | HAZ-01: Loop 1 alone insufficient — trust reweighting requires Loop 2 | ⚠️ PARTIAL | Loop 1 non-independence confirmed — needs combined activation |
| SG2: TTC margin scaling — TTC shall increase proportionally to sensor uncertainty | C | T2 LiDAR dropout | Phase 3: velocity −1.3 km/h at max degradation (open-loop proxy) | HAZ-01: TTC 0.205s → 2.128s (10.4×) with Loop 2 | ✅ VERIFIED | Verified in closed-loop HAZ-01 |
| SG3: CONSERVATIVE regime — system shall enter CONSERVATIVE when combined reliability < 0.35 | C | T3 combined | Phase 3: entire 7×7 grid CAUTIOUS — naive sigmoid never triggers CONSERVATIVE | HAZ-01: CAUTIOUS triggered, CONSERVATIVE not reached | ⚠️ PARTIAL | Higher severity scenario needed to trigger CONSERVATIVE |
| SG4: Affordance override — pedestrian presence shall trigger stricter regime regardless of threshold | D | T4 pedestrian | Phase 4a: ASIL D mitigation path defined | HAZ-01: pedestrian avoided by Loop 2 — no explicit affordance classification | ⚠️ PARTIAL | Explicit pedestrian affordance layer not implemented |
| SG5: MRC trigger — system shall request MRC when both sensors below minimum | B | T5 extreme | Phase 4a: EMERGENCY mode defined (K(t)=0.0) | NOT TESTED in closed-loop | ❌ NOT TESTED | Requires extreme combined failure scenario |

---

## Hazard Coverage

| Hazard | ASIL | Triggering Condition | Open-Loop Evidence | Closed-Loop Evidence | Coverage |
|--------|------|---------------------|--------------------|----------------------|----------|
| H1: False positive under glare → unnecessary braking | B | T1 | Phase 4a: risk reduction 29.3% | HAZ-01 IP1/IP2/IP3 runs | ✅ Covered |
| H2: Missed pedestrian under glare → collision | D | T1 | Phase 6: IP3 peak FPC=0.65 | HAZ-01: baseline 100% collision → Loop2 0% collision | ✅ Covered |
| H3: LiDAR range error in rain → incorrect distance | C | T2 | Phase 3: LiDAR trust compensates | NOT TESTED in closed-loop | ⚠️ Open-loop only |
| H4: Combined degradation → unreliable scene understanding | C | T3 | Phase 4a: 58.3% unknown unsafe reduction | HAZ-01 combined: IP3 sev=0.25 breaks mitigation | ⚠️ Partially covered |
| H5: Undetected pedestrian at crossing under combined failure | D | T4 | Phase 6: T4 peak FPC=0.65 | HAZ-01: pedestrian avoided, combined fragility at IP3 sev=0.25 | ⚠️ Partially covered |
| H6: Complete perception failure → MRC required | B | T5 | Phase 4a: EMERGENCY mode defined | NOT TESTED | ❌ Not covered |

---

## Scenario Coverage

| Scenario | Type | SOTIF Trigger | Status | Runs | Key Finding |
|----------|------|--------------|--------|------|-------------|
| HAZ-01: Pedestrian approach, stationary | Closed-loop | T1, T4 | ✅ Complete | 48 | Loop 2 prevents collision (0% vs 100% baseline) |
| HAZ-02: Cut-in vehicle | Closed-loop | T3 | 📋 Planned | 0 | — |
| HAZ-03: Occluded pedestrian emergence | Closed-loop | T4 | 📋 Planned | 0 | — |
| HAZ-04: Fog + glare combined | Closed-loop | T3, T5 | 📋 Planned | 0 | — |
| HAZ-05: Rain + LiDAR dropout | Closed-loop | T2, T3 | 📋 Planned | 0 | — |
| HAZ-06: Night + low contrast | Closed-loop | T1 | 📋 Planned | 0 | — |
| HAZ-07: Construction zone | Closed-loop | T3 | 📋 Planned | 0 | — |
| HAZ-08: EMERGENCY / MRC trigger | Closed-loop | T5 | 📋 Planned | 0 | — |

---

## Interface Injection Coverage

| Interface | Description | Open-Loop FPC | Closed-Loop FPC | Closed-Loop Collision | Status |
|-----------|-------------|--------------|-----------------|----------------------|--------|
| IP1: Sensor input | Glare applied to raw camera | N/A (not injected in P6) | 0.0 (Loop2 compensates) | Baseline: True, Loop2: False | ✅ Covered |
| IP2: Perception output | Uncertainty scalar injected | 0.144 mean, 0.18 peak | 0.0 (Loop2 compensates) | Baseline: True, Loop2: False | ✅ Covered |
| IP3: Trust weights | Camera trust degraded | 0.191 mean, 0.65 peak | 0.0 (except sev=0.25 combined) | IP3 sev=0.25 breaks combined | ✅ Covered — fragility confirmed |
| IP4: Planning output | Velocity perturbed | 1.000 (definitional) | Not tested in closed-loop | — | ⚠️ Open-loop only |

---

## Mitigation Configuration Coverage

| Config | Description | HAZ-01 Collision | HAZ-01 Min TTC | Verdict |
|--------|-------------|-----------------|----------------|---------|
| Baseline | No loops | 100% | 0.205s | FAIL — unsafe without mitigation |
| Loop 1 only | Adaptive trust, fixed planning | 100% | 0.205s | FAIL — trust reweighting insufficient alone |
| Loop 2 only | Fixed trust, uncertainty planner | 0% | 2.128s | PASS — planning adaptation sufficient |
| Combined | Both loops | ~92% safe | 2.128s | PASS with residual risk at IP3 sev=0.25 |

---

## Parameter Space Coverage

### Glare intensity × LiDAR dropout (Phase 3 open-loop)
- Covered: 7×7 grid (0.0–0.9 glare × 0%–80% dropout) = 49 cells ✅

### Glare severity × injection point × mitigation config (Stage 3 closed-loop)
- Covered: 4 severities × 3 IPs × 4 configs = 48 runs ✅

### Corruption types (Phase 5 open-loop)
- Covered: 8 types × 5 severities = 40 cells ✅

### Scenario × configuration (Stage 3)
- Covered: 1 scenario × 4 configs = 4 (HAZ-01 only)
- Planned: 8 scenarios × 4 configs = 32 ⚠️ 7 scenarios pending

---

## Coverage Gaps (New Requirements)

| Gap ID | Description | Priority | Closure Path |
|--------|-------------|----------|--------------|
| COV-01 | SG5 / H6 not tested — EMERGENCY/MRC scenario missing | ASIL B | Add HAZ-08 extreme combined failure scenario |
| COV-02 | H3 LiDAR range error not tested in closed-loop | ASIL C | Add HAZ-05 rain + LiDAR dropout scenario |
| COV-03 | IP4 closed-loop injection not tested | ASIL B | Add IP4 in-loop injection to campaign script |
| COV-04 | CONSERVATIVE regime never triggered | ASIL C | Run higher-severity campaign or add HAZ-04 |
| COV-05 | Only 1/8 planned scenarios executed | ASIL C | Phase 8 campaign expansion |
| COV-06 | Single map (Town10HD_Opt) only | ASIL B | Add Town05 or Town03 for ODD breadth |
| COV-07 | Pedestrian affordance layer not implemented | ASIL D | Explicit VRU detection and regime override |

---

## Traceability Spine

```
Requirement
  └─ Hazard (HARA + interface provenance)
       └─ Safety goal (SG1–SG5)
            └─ Scenario (.xosc — scenarios/haz01_scenario.xosc)
                 └─ Closed-loop run (scripts/stage2_haz01_injection.py)
                      └─ KPI result (results/stage3/haz01_v2.json)
                           └─ Failure analysis (results/stage4/vnv_report.md)
                                └─ Coverage (docs/coverage_tracker.md ← this file)
                                     └─ Safety claim (results/stage4/safety_case.md)
                                          └─ Residual risk + NEW requirement
                                               └─ feeds back to Requirement ↑
```

---

*Last updated: June 2026 after HAZ-01 Stage 3 campaign*
*Next update: after Phase 8 scenario campaign expansion*
