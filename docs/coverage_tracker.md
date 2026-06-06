# Coverage Tracker
## Interface-Level Failure Propagation Analysis in Autonomous Driving Stacks

*Updated: June 2026 — after 5-scenario closed-loop campaign (112 runs)*

---

## Safety Goal Coverage

| Safety Goal | ASIL | Evidence | Verdict | Gap |
|-------------|------|----------|---------|-----|
| SG1: Confidence threshold | B | Loop 1 zero standalone benefit — 112 runs across 5 scenarios | ⚠️ PARTIAL | Loop 1 non-independent — requires Loop 2 |
| SG2: TTC scaling | C | HAZ-01: 10.4× TTC · HAZ-03 combined: 7.47s >> 1.5s | ✅ VERIFIED | — |
| SG3: CONSERVATIVE regime | C | HAZ-08 glare=0.50+lidar=0.50 combined: CONSERVATIVE triggered | ✅ VERIFIED | — |
| SG4: Affordance override | D | HAZ-03: detection distance +29% with combined loops | ⚠️ PARTIAL | No explicit pedestrian affordance layer |
| SG5: MRC/EMERGENCY trigger | B | HAZ-08 glare=0.90+lidar=0.80 combined: EMERGENCY triggered | ✅ VERIFIED | — |

**3/5 verified · 2/5 partial · 0/5 not tested**

---

## Hazard Coverage

| Hazard | ASIL | Scenario | Status | Evidence |
|--------|------|----------|--------|----------|
| H1: False positive under glare | B | HAZ-01 | ✅ Covered | IP1/IP2/IP3 injection runs |
| H2: Missed pedestrian under glare | D | HAZ-01 | ✅ Covered | Baseline 100% collision → Loop2 0% |
| H3: LiDAR range error in rain | C | — | ❌ Not covered | Rain scenario pending |
| H4: Combined degradation | C | HAZ-02, HAZ-04 | ✅ Covered | Cut-in + fog campaigns |
| H5: Pedestrian at crossing combined failure | D | HAZ-03, HAZ-08 | ✅ Covered | Occlusion + extreme combined |
| H6: Complete perception failure | B | HAZ-08 | ✅ Covered | EMERGENCY triggered at extreme degradation |

**5/6 hazards covered · H3 pending**

---

## Scenario Coverage

| Scenario | Type | SOTIF | Status | Runs | Key Finding |
|----------|------|-------|--------|------|-------------|
| HAZ-01: Pedestrian+glare | Closed-loop | T1, T4 | ✅ Complete | 48 | Loop2: 100%→0% collision, 10.4× TTC |
| HAZ-02: Cut-in+fog | Closed-loop | T3 | ✅ Complete | 16 | TTC below threshold — CONSERVATIVE needed |
| HAZ-03: Occluded pedestrian | Closed-loop | T4 | ✅ Complete | 16 | First Loop1 benefit — detection +29% |
| HAZ-04: Fog+pedestrian | Closed-loop | T3, T4 | ✅ Complete | 16 | Fog triggers CAUTIOUS at zero severity |
| HAZ-05: Rain+LiDAR | Closed-loop | T2, T3 | 📋 Planned | 0 | — |
| HAZ-06: Night+low contrast | Closed-loop | T1 | 📋 Planned | 0 | — |
| HAZ-07: Construction zone | Closed-loop | T3 | 📋 Planned | 0 | — |
| HAZ-08: EMERGENCY/MRC | Closed-loop | T5 | ✅ Complete | 16 | SG3+SG5 verified — combined required |

**5/8 scenarios complete · 3 pending**

---

## Interface Injection Coverage

| Interface | Open-Loop FPC | Closed-Loop Finding | Status |
|-----------|--------------|---------------------|--------|
| IP1: Sensor input | N/A | Loop2 compensates | ✅ Covered |
| IP2: Perception output | 0.144 mean | Loop2 compensates | ✅ Covered |
| IP3: Trust weights | 0.65 peak T4 | Sev=0.25 breaks combined — fragility confirmed | ✅ Covered |
| IP4: Planning output | 1.000 def | Not tested closed-loop | ⚠️ Open-loop only |

---

## Mitigation Configuration Coverage

| Config | HAZ-01 | HAZ-02 | HAZ-03 | HAZ-04 | HAZ-08 | Pattern |
|--------|--------|--------|--------|--------|--------|---------|
| Baseline | COLLISION | safe | safe | safe | COLLISION | Unsafe at moderate + extreme |
| Loop 1 only | COLLISION | safe | safe | safe | COLLISION | Zero standalone benefit — 112 runs |
| Loop 2 only | safe | safe | safe | safe | COLLISION | Sufficient moderate, fails extreme |
| Combined | safe* | safe | safe | safe | safe | Required for extreme degradation |

*IP3 sev=0.25 breaks combined in HAZ-01

---

## Parameter Space Coverage

| Space | Coverage | Runs |
|-------|----------|------|
| Glare × LiDAR dropout (Phase 3) | 7×7 = 49 cells | 49 open-loop |
| Glare × IP × config (HAZ-01) | 4×3×4 = 48 | 48 closed-loop |
| Fog × config (HAZ-02/04) | 4×4×2 = 32 | 32 closed-loop |
| Occlusion × glare × config (HAZ-03) | 4×4 = 16 | 16 closed-loop |
| Extreme combined × config (HAZ-08) | 4×4 = 16 | 16 closed-loop |
| **Total closed-loop** | | **112** |

---

## Coverage Gaps

| Gap ID | Description | Priority | Closure |
|--------|-------------|----------|---------|
| COV-01 | H3 LiDAR rain not tested closed-loop | ASIL C | HAZ-05 scenario |
| COV-02 | IP4 closed-loop injection not tested | ASIL B | Add to campaign |
| COV-03 | 3/8 scenarios pending | ASIL C | HAZ-05/06/07 |
| COV-04 | Single map (Town10HD) | ASIL B | Multi-map campaign |
| COV-05 | SG4 explicit affordance layer missing | ASIL D | NR-07 |
| COV-06 | CONSERVATIVE threshold gap HAZ-02/04 | ASIL C | NR-06 |

---

## Traceability Spine

```
Requirement
  └─ Hazard (HARA + interface provenance)
       └─ Safety goal (SG1–SG5)
            └─ Scenario (.xosc — scenarios/haz01_scenario.xosc)
                 └─ Closed-loop runs (scripts/stage2_haz01_injection.py etc.)
                      └─ KPI results (results/stage3/*.json — 112 runs)
                           └─ Failure analysis (results/stage4/vnv_report.md)
                                └─ Coverage (docs/coverage_tracker.md)
                                     └─ Safety case (results/stage4/safety_case.md)
                                          └─ Residual risks + NEW requirements
                                               └─ feeds back to Requirement ↑
```

---

*Last updated: June 2026 — 5 scenarios, 112 closed-loop runs*
*Safety goals verified: SG2, SG3, SG5 · Partial: SG1, SG4*
