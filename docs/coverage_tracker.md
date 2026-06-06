# Coverage Tracker — Final
## Interface-Level Failure Propagation Analysis in Autonomous Driving Stacks

*Updated: June 2026 — Complete campaign: 8 scenarios, 160 closed-loop runs*

---

## Safety Goal Coverage — Final

| Safety Goal | ASIL | Evidence | Verdict |
|-------------|------|----------|---------|
| SG1: Confidence threshold | B | Loop 1 zero standalone benefit — **160 runs, 8 scenarios** | ⚠️ PARTIAL |
| SG2: TTC scaling | C | HAZ-01: 10.4× · HAZ-03/05/06/07/08: all meet ≥1.5s | ✅ VERIFIED |
| SG3: CONSERVATIVE regime | C | HAZ-03/05/06/07/08 all trigger CONSERVATIVE | ✅ VERIFIED |
| SG4: Affordance override | D | AEB + proximity override active · explicit classification pending | ⚠️ PARTIAL |
| SG5: MRC / EMERGENCY | B | HAZ-08: EMERGENCY at glare=0.90 + lidar=0.80 | ✅ VERIFIED |

**3/5 verified · 2/5 partial · 0/5 not tested**

---

## Hazard Coverage — Final

| Hazard | ASIL | Scenario | Status |
|--------|------|----------|--------|
| H1: False positive under glare | B | HAZ-01, HAZ-06 | ✅ Covered |
| H2: Missed pedestrian under glare | D | HAZ-01 | ✅ Covered |
| H3: LiDAR range error in rain | C | HAZ-05 | ✅ Covered |
| H4: Combined degradation | C | HAZ-02, HAZ-04, HAZ-07 | ✅ Covered |
| H5: Pedestrian at crossing combined failure | D | HAZ-03, HAZ-08 | ✅ Covered |
| H6: Complete perception failure | B | HAZ-08 | ✅ Covered |

**6/6 hazards covered**

---

## Scenario Coverage — Final

| Scenario | SOTIF | Status | Runs | Key Finding |
|----------|-------|--------|------|-------------|
| HAZ-01: Pedestrian + glare | T1, T4 | ✅ | 48 | Only collision scenario — Loop2 prevents all |
| HAZ-02: Cut-in + fog | T3 | ✅ | 16 | TTC gap — SG4 fix addresses |
| HAZ-03: Occluded pedestrian | T4 | ✅ | 16 | First Loop1 benefit — detection +29% |
| HAZ-04: Fog + pedestrian | T3, T4 | ✅ | 16 | Fog triggers CAUTIOUS at zero severity |
| HAZ-05: Rain + LiDAR dropout | T2, T3 | ✅ | 16 | H3 closed — SG3 in rain verified |
| HAZ-06: Night | T1 | ✅ | 16 | Loop1 modality identification validated |
| HAZ-07: Construction | T3 | ✅ | 16 | Symmetric degradation reveals Loop1 limit |
| HAZ-08: EMERGENCY / MRC | T5 | ✅ | 16 | SG3 + SG5 verified — combined required |

**8/8 scenarios complete · 160 total runs**

---

## Mitigation Coverage — Final

| Config | Pattern across 160 runs |
|--------|------------------------|
| Baseline | Collides in HAZ-01 (ASIL D) and HAZ-08 (ASIL B) |
| Loop 1 only | **Identical to baseline — zero benefit in every run** |
| Loop 2 only | Zero collisions except HAZ-08 extreme |
| Combined | **Zero collisions across all 160 runs** |

---

## Interface Injection Coverage

| Interface | Open-loop FPC | Closed-loop | Status |
|-----------|--------------|-------------|--------|
| IP1: Sensor input | N/A | Loop2 compensates | ✅ |
| IP2: Perception output | 0.144 mean | Loop2 compensates | ✅ |
| IP3: Trust weights | 0.65 peak | Sev=0.25 fragility confirmed | ✅ |
| IP4: Planning output | 1.000 def | Open-loop only | ⚠️ |

---

## Residual Gaps

| Gap | Priority | Closure |
|-----|----------|---------|
| SG4 explicit pedestrian classification | ASIL D | NR-07 |
| SG1 Loop1 independence | ASIL B | Architecture — documented |
| IP4 closed-loop injection | ASIL B | NR add to campaign |
| Single map (Town10HD only) | ASIL B | Multi-map campaign |
| Sim-to-real | ASIL D | Post-thesis |

---

## Traceability Spine

```
Requirement → Hazard → Safety Goal → Scenario (.xosc)
  → Closed-loop run (160 runs across 8 scenarios)
    → KPI results (results/stage3/*.json)
      → Failure analysis (results/stage4/vnv_report.md)
        → Coverage (docs/coverage_tracker.md)
          → Safety case (results/stage4/safety_case.md)
            → Residual risks + NR-01 to NR-08
              → feeds back to Requirement ↑
```

---

*Last updated: June 2026 — Campaign complete*
*SG2 ✅ SG3 ✅ SG5 ✅ · SG1 ⚠️ SG4 ⚠️ · 160 runs · 8 scenarios · 6 hazards*
