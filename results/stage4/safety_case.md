# GSN Safety Case — Full Closed-Loop Evidence
## Interface-Level Failure Propagation Analysis in Autonomous Driving Stacks

**Version:** 3.0 — after 5-scenario campaign
**Generated:** 2026-06-06 20:15
**Total evidence runs:** 112

---

## Top Safety Claim

**G1:** The uncertainty-aware perception-planning stack maintains acceptable safety
under the defined sensor-degradation ODD across 5 SOTIF trigger scenarios in
Town10HD urban environment, with combined mitigation loops active.

---

## Evidence

### G1.1: SG2 TTC scaling — VERIFIED
- HAZ-01: TTC 0.205s → 2.128s (10.4×), collision 100%→0%
- HAZ-03 combined sev=0.75: TTC 7.47s >> 1.5s threshold

### G1.2: SG3 CONSERVATIVE regime — VERIFIED
- HAZ-08 glare=0.50+lidar=0.50 combined: CONSERVATIVE triggered, TTC 8.51s

### G1.3: SG5 EMERGENCY/MRC trigger — VERIFIED
- HAZ-08 glare=0.90+lidar=0.80 combined: EMERGENCY triggered, brake applied

### G1.4: SG1 confidence threshold — PARTIAL
- Loop 1 alone: zero benefit across 112 runs
- Combined loops: detection distance improves in HAZ-03
- Gap: Loop 1 not independently effective

### G1.5: SG4 affordance override — PARTIAL
- HAZ-03: detection distance +29% with combined loops
- Gap: no explicit pedestrian affordance classification layer

---

## Residual Risks

| ID | Risk | ASIL | Closure |
|----|------|------|---------|
| RR-01 | IP3 sev=0.25 bypasses combined (HAZ-01) | C | NR-02 |
| RR-02 | Loop 1 non-independent | B | Architecture documented |
| RR-03 | HAZ-02/04 TTC below threshold | C | NR-06 |
| RR-04 | SG1/SG4 partial | B/D | NR-07 + Phase 7 |
| RR-05 | Single map coverage | B | Multi-map campaign |
| RR-06 | Sim-to-real gap | D | Real-world validation |

---

## New Requirements → Specify

NR-01 through NR-07 defined in vnv_report.md — fed back to Stage 1.

---

*Evidence: results/stage3/ | Report: results/stage4/vnv_report.md*
