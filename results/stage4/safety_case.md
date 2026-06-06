# GSN Safety Case — Complete Campaign Evidence
## Interface-Level Failure Propagation Analysis

**Version:** 4.0 — all 8 scenarios complete
**Generated:** 2026-06-07 00:46
**Total evidence:** 160 closed-loop runs

---

## Top Claim: G1

The uncertainty-aware perception-planning stack maintains acceptable safety
under the defined sensor-degradation ODD across all 8 SOTIF trigger scenarios
in Town10HD urban environment, with Loop 2 active.

---

## Evidence

**G1.1: Zero collisions with Loop 2 — 160 runs**
All 8 scenarios, all severities, all injection points: no collision when Loop 2 active.

**G1.2: SG2 VERIFIED — TTC scaling**
HAZ-01: 10.4× improvement. 6/8 scenarios meet ≥1.5s threshold.

**G1.3: SG3 VERIFIED — CONSERVATIVE regime**
Triggered in HAZ-03, HAZ-05, HAZ-06, HAZ-07, HAZ-08.

**G1.4: SG5 VERIFIED — EMERGENCY / MRC**
HAZ-08: EMERGENCY at glare=0.90 + lidar=0.80 combined.

**G1.5: SG1 PARTIAL — confidence threshold**
Loop 1 non-independent — 160 run confirmation.

**G1.6: SG4 PARTIAL — affordance override**
AEB + proximity override active. Explicit classification layer pending (NR-07).

---

## Residual Risks

| ID | Risk | ASIL | Closure |
|----|------|------|---------|
| RR-01 | IP3 sev=0.25 bypasses combined | C | NR-02 |
| RR-02 | Loop1 non-independence | B | Architecture documented |
| RR-03 | HAZ-02/04 TTC gap | C | NR-06 |
| RR-04 | SG4 explicit classification pending | D | NR-07 |
| RR-05 | Single map | B | Multi-map campaign |
| RR-06 | Sim-to-real | D | Real-world validation |

---

## New Requirements → Specify

NR-01 through NR-08 defined in vnv_report.md.

---

*Evidence: results/stage3/ | Report: results/stage4/vnv_report.md*
