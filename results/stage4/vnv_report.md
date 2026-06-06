# V&V Report — Full Scenario Campaign
## Interface-Level Failure Propagation Analysis in Autonomous Driving Stacks

**Generated:** 2026-06-06 20:15
**Total runs:** 112
**Scenarios:** 5
**Simulator:** CARLA 0.9.15, Town10HD_Opt, RTX 4090, synchronous 20 FPS

---

## 1. Campaign Overview

| Scenario | Description | SOTIF | ASIL | Hazard | Runs |
|----------|-------------|-------|------|--------|------|
| HAZ-01 | Pedestrian approach under glare | T1, T4 | D | H2 | 48 |
| HAZ-02 | Cut-in vehicle under fog | T3 | C | H4 | 16 |
| HAZ-03 | Occluded pedestrian emergence | T4 | D | H5 | 16 |
| HAZ-04 | Pedestrian crossing under fog | T3, T4 | C/D | H4, H5 | 16 |
| HAZ-08 | EMERGENCY/MRC extreme combined failure | T5 | B | H6 | 16 |
| **Total** | | | | | **112** |

---

## 2. Cross-Scenario KPI Results

### Primary Safety KPI: Collision (threshold: 0)

| Scenario | ASIL | Baseline | Loop 1 | Loop 2 | Combined |
|----------|------|----------|--------|--------|----------|
| HAZ-01 pedestrian+glare | D | **COLLISION** | **COLLISION** | safe | safe* |
| HAZ-02 cut-in+fog | C | safe | safe | safe | safe |
| HAZ-03 occlusion | D | safe | safe | safe | safe |
| HAZ-04 fog+pedestrian | C/D | safe | safe | safe | safe |
| HAZ-08 emergency | B | **COLLISION** | **COLLISION** | **COLLISION** | safe |

*HAZ-01 combined fails at IP3 sev=0.25

### Secondary Safety KPI: Minimum TTC (threshold: ≥ 1.5s)

| Scenario | Baseline TTC | Loop 2 TTC | Combined TTC | Threshold Met |
|----------|-------------|-----------|--------------|---------------|
| HAZ-01 | 0.205s | 2.128s ✅ | 2.128s ✅ | Loop 2 + Combined |
| HAZ-02 | 0.297s | 0.805s ❌ | 0.805s ❌ | Neither |
| HAZ-03 | 0.499s | 0.835s ❌ | 7.47s ✅ | Combined only |
| HAZ-04 | 0.388s | 0.702s ❌ | 0.702s ❌ | Neither |
| HAZ-08 | 0.224s | 0.393s ❌ | 8.51s ✅ | Combined only |

---

## 3. Failure Analysis

### Finding 1: Loop 2 necessary but not always sufficient — Combined loops required for extreme scenarios

HAZ-08 is the decisive evidence: Loop 2 alone cannot prevent collision at extreme
degradation (glare=0.90 + lidar=0.80). Only the combined configuration prevents
collision. Loop 1 provides the correct trust signal; Loop 2 acts on it.

This upgrades the architectural finding from HAZ-01:
- HAZ-01: Loop 2 alone sufficient for moderate degradation
- HAZ-08: Combined loops required for extreme degradation
- Pattern: the more severe the degradation, the more the two loops need each other

### Finding 2: Loop 1 zero standalone benefit — confirmed across ALL 112 runs

Loop 1 only = baseline in every run across all 5 scenarios. Zero exceptions.
This is now the most statistically robust finding in the campaign.

### Finding 3: First positive Loop 1 finding — detection distance (HAZ-03)

HAZ-03 combined sev=0.75: detection distance 17.56m → 22.62m (+29%).
Loop 1 trust reweighting, when combined with Loop 2, causes earlier
conservative response — the system slows down before the pedestrian
is as close as in the baseline case. Loop 1 is not useless; it is
architecturally dependent on Loop 2 to produce observable behavior.

### Finding 4: SG3 CONSERVATIVE verified (HAZ-08)

CONSERVATIVE triggered at glare=0.50 + lidar_dropout=0.50 with combined config.
TTC: 0.224s → 8.51s. This closes the coverage gap identified after HAZ-01/02/04.

### Finding 5: SG5 EMERGENCY verified (HAZ-08)

EMERGENCY triggered at glare=0.90 + lidar_dropout=0.80 with combined config.
EMERGENCY mode applies brake=0.8 + throttle=0.0. TTC: 0.224s → 8.51s.

### Finding 6: TTC threshold gap in HAZ-02/04

HAZ-02 Loop2 TTC=0.805s, HAZ-04 Loop2 TTC=0.702s — below 1.5s threshold.
CAUTIOUS mode (throttle=0.4) insufficient for cut-in and fog crossing.
CONSERVATIVE (throttle=0.15) needed but not triggered in these scenarios.
Root cause: uncertainty signal doesn't reach CONSERVATIVE_THRESHOLD (0.55)
in fog/cut-in scenarios — requires threshold tuning (NR-06).

---

## 4. Safety Goal Verdicts (final)

| SG | ASIL | Verdict | Evidence |
|----|------|---------|----------|
| SG1: Confidence threshold | B | ⚠️ PARTIAL | Loop 1 non-independent — 112 runs |
| SG2: TTC scaling | C | ✅ VERIFIED | HAZ-01: 10.4×, HAZ-03 combined: 7.47s |
| SG3: CONSERVATIVE regime | C | ✅ VERIFIED | HAZ-08: triggered at glare=0.50+lidar=0.50 |
| SG4: Affordance override | D | ⚠️ PARTIAL | HAZ-03: detection distance improves, no explicit layer |
| SG5: MRC/EMERGENCY trigger | B | ✅ VERIFIED | HAZ-08: triggered at glare=0.90+lidar=0.80 |

**3/5 safety goals verified in closed-loop. 2/5 partial.**

---

## 5. Trade-off Ledger (complete)

| Mitigation | Benefit | Cost | Scenario | Evidence |
|------------|---------|------|----------|----------|
| Loop 2 CAUTIOUS | Collision 100%→0%, TTC 10.4× | Speed −40% (22.3→13.3 km/h) | HAZ-01 | haz01_v2.json |
| Loop 2 CAUTIOUS | TTC 2.7× improvement | TTC still below 1.5s threshold | HAZ-02 | haz02_cutin.json |
| Combined CONSERVATIVE | TTC 7.47s, no collision | Speed further reduced, rear exposure | HAZ-03 | haz03_occlusion.json |
| Fog uncertainty model | Proactive CAUTIOUS in fog | Over-conservative at low fog | HAZ-04 | haz04_fog.json |
| Combined EMERGENCY | Collision prevented at extreme degradation | Full stop — throughput = 0 | HAZ-08 | haz08_emergency.json |
| Loop 1 + Loop 2 coupling | Earlier detection in occlusion (+29% distance) | Loop 1 useless without Loop 2 | HAZ-03 | haz03_occlusion.json |
| IP3 trust injection sev=0.25 | Reveals fragility | Breaks combined mitigation | HAZ-01 | haz01_v2.json |

---

## 6. New Requirements (complete set)

| ID | Requirement | Source | ASIL |
|----|-------------|--------|------|
| NR-01 | Rear-proximity monitor — inhibit CAUTIOUS when follower within 5m | HAZ-01 speed cost | B |
| NR-02 | IP3 trust integrity check — flag trust deviation >0.3 | HAZ-01 IP3 fragility | C |
| NR-03 | Uncertainty floor for IP2 zero-injection | HAZ-01 IP2 | B |
| NR-04 | Campaign expansion to remaining 3 scenarios | Coverage gap | C |
| NR-05 | Fog uncertainty floor — NORMAL below fog threshold | HAZ-04 | B |
| NR-06 | CONSERVATIVE threshold tuning for cut-in/fog scenarios | HAZ-02/04 TTC gap | C |
| NR-07 | Explicit pedestrian affordance classification layer | HAZ-03 SG4 partial | D |

---

## 7. Validation Debt

| Item | Description | Closes |
|------|-------------|--------|
| VD-01 | Real BEVFusion perception backbone | Phase 7 |
| VD-02 | Multi-map campaign (Town05, Town03) | Stage 3 expansion |
| VD-03 | Remaining 3 scenarios (rain, night, construction) | Stage 3 expansion |
| VD-04 | EDL epistemic calibration | Phase 7 |
| VD-05 | Sim-to-real transfer | Post-thesis |

---

## 8. Engineering Verdict

**Full campaign verdict: PASS with documented residual risks**

3/5 safety goals verified (SG2, SG3, SG5). 2/5 partially verified (SG1, SG4).
112 closed-loop runs across 5 scenarios. Most critical finding: combined loops
required for CONSERVATIVE/EMERGENCY — neither loop alone is sufficient at
extreme degradation.

**Total closed-loop runs:** {total_runs}
**Scenarios:** {len(scenarios)}/8 planned
**Safety goals verified:** 3/5
**Safety goals partial:** 2/5

---

*Results: `results/stage3/` | Code: `scripts/` | Generated: `scripts/stage4_evaluate.py`*
