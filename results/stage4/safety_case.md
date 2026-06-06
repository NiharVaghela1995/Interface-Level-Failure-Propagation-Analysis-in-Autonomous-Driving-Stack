# GSN Safety Case — Multi-Scenario Closed-Loop Evidence
## Interface-Level Failure Propagation Analysis in Autonomous Driving Stacks

**Version:** 2.0 (updated after HAZ-02 and HAZ-04 campaigns)
**Generated:** 2026-06-06 20:00
**Total evidence runs:** 80

---

## Top Safety Claim

**G1:** The uncertainty-aware perception-planning stack maintains acceptable
safety under the defined sensor-degradation ODD across pedestrian approach,
cut-in, and fog scenarios in Town10HD urban environment.

---

## Evidence Structure

### G1.1: Loop 2 is a necessary mitigation — verified across 3 scenarios

**E1.1a (HAZ-01):** Collision rate 100%→0%, TTC 0.205s→2.128s (10.4×)
**E1.1b (HAZ-02):** TTC 0.297s→0.805s (2.7×), no collision
**E1.1c (HAZ-04):** TTC 0.388s→0.702s (1.8×), no collision
**Conclusion:** Loop 2 consistently improves safety — robust across scenario types

### G1.2: Loop 1 alone is architecturally insufficient — confirmed across 80 runs

**E1.2:** Loop 1 only = baseline in every run across all 3 scenarios (80 runs)
**Conclusion:** Trust reweighting requires planning adaptation. Cannot be claimed as independent safety layer.

### G1.3: SG2 TTC scaling VERIFIED in closed-loop (HAZ-01)

**E1.3:** HAZ-01 Loop 2 TTC = 2.128s ≥ 1.5s threshold
**Conclusion:** SG2 verified for ASIL D pedestrian scenario

### G1.4: SG2 PARTIAL for HAZ-02 and HAZ-04

**E1.4:** HAZ-02 Loop2 TTC=0.805s, HAZ-04 Loop2 TTC=0.702s — both below 1.5s
**Conclusion:** CAUTIOUS mode insufficient — CONSERVATIVE needed. Threshold tuning required (NR-06).

### G1.5: IP3 fragility — residual risk at trust weight interface

**E1.5:** HAZ-01 IP3 sev=0.25 combined: collision=True
**Conclusion:** Low-severity trust corruption bypasses combined mitigation. Residual risk RR-01.

---

## Residual Risks (updated)

| ID | Risk | ASIL | Closure |
|----|------|------|---------|
| RR-01 | IP3 trust corruption sev=0.25 bypasses combined | C | NR-02 integrity check |
| RR-02 | Loop 1 non-independence | B | Architecture documented |
| RR-03 | Speed reduction trade-off in dense traffic | B | NR-01 rear monitor |
| RR-04 | HAZ-02/04 TTC below 1.5s threshold with Loop 2 | C | NR-06 threshold tuning |
| RR-05 | CONSERVATIVE regime never triggered | C | Higher severity campaign |
| RR-06 | SG3/SG5 not verified | B/C | HAZ-08 extreme scenario |
| RR-07 | Fog over-conservatism at low severity | B | NR-05 fog floor |
| RR-08 | Single map coverage | B | Multi-map campaign |
| RR-09 | Sim-to-real gap | D | Real-world validation debt |

---

## Safety Goal Verdicts (updated)

| SG | ASIL | Verdict | Evidence |
|----|------|---------|----------|
| SG1: Confidence threshold | B | ⚠️ PARTIAL | Loop 1 non-independent across 80 runs |
| SG2: TTC scaling | C | ✅ VERIFIED (HAZ-01) / ⚠️ PARTIAL (HAZ-02/04) | 10.4× TTC, 0% collision HAZ-01 |
| SG3: CONSERVATIVE regime | C | ⚠️ NEVER TRIGGERED | Threshold never reached in 80 runs |
| SG4: Affordance override | D | ⚠️ PARTIAL | Pedestrian avoided, no explicit layer |
| SG5: MRC trigger | B | ❌ NOT TESTED | Requires extreme combined failure |

---

## New Requirements (fed back to Specify)

NR-01: Rear-proximity monitor
NR-02: IP3 trust integrity check
NR-03: Uncertainty floor for IP2
NR-04: Campaign expansion to 8 scenarios
NR-05: Fog uncertainty floor
NR-06: CONSERVATIVE threshold tuning

---

*Evidence: results/stage3/ | V&V report: results/stage4/vnv_report.md*
