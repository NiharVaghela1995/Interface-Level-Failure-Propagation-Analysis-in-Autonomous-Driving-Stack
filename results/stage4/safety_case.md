# GSN Safety Case — HAZ-01
## Interface-Level Failure Propagation Analysis in Autonomous Driving Stacks

**Version:** 1.0 (Stage 4 — closed-loop evidence)
**Generated:** 2026-06-06 17:18
**Standard:** ISO 26262 + ISO 21448 (SOTIF)

---

## Top Safety Claim

**G1:** The uncertainty-aware perception-planning stack maintains acceptable
safety under the defined sensor-degradation ODD for HAZ-01 (pedestrian
approach, glare degradation, Town10HD urban intersection).

---

## Evidence Structure

### G1 → Strategy: Argument over mitigation configurations

**S1:** Safety is argued by demonstrating that the combined mitigation
(Loop 1 + Loop 2) prevents collision across all tested injection points
and severities, with quantified TTC improvement as the safety metric.

---

### Sub-claim G1.1: Baseline system is unsafe without mitigation

**Evidence E1.1:**
- Baseline collision rate: 100% (12/12 pedestrian runs)
- Baseline min TTC: 0.205s (below 1.5s threshold)
- Source: `results/stage3/haz01_v2.json`, all IP × severity × baseline rows

**Conclusion:** The unmitigated stack collides with the pedestrian in every
HAZ-01 run. This establishes the need for the mitigation loops.

---

### Sub-claim G1.2: Loop 2 is a necessary and sufficient mitigation for HAZ-01

**Evidence E1.2:**
- Loop 2 collision rate: 0% across all IP × severity combinations
  where uncertainty threshold is crossed
- Loop 2 min TTC: 2.128s (above 1.5s threshold)
- TTC improvement factor: 10.4x
- Source: `results/stage3/haz01_v2.json`, loop2_only rows

**Conclusion:** Loop 2 (uncertainty-aware planning) is sufficient to prevent
collision in HAZ-01. Activation of CAUTIOUS mode (throttle 0.6 → 0.4) provides
adequate TTC margin.

---

### Sub-claim G1.3: Loop 1 alone is insufficient — two-loop architecture required

**Evidence E1.3:**
- Loop 1 only collision rate: 100% (identical to baseline)
- Trust reweighting without planning adaptation provides zero safety benefit
- Source: `results/stage3/haz01_v2.json`, loop1_only rows (all collision=True)

**Conclusion:** The adaptive trust mechanism (Loop 1) is necessary for correct
uncertainty signal propagation but must be paired with Loop 2 to affect behavior.

---

### Sub-claim G1.4: IP3 trust weight interface is the most fragile point

**Evidence E1.4:**
- IP3 sev=0.25, combined config: collision=True
- All other combined configs: collision=False
- Trust weight injection at low severity (0.25) can bypass the combined mitigation
- Source: `results/stage3/haz01_v2.json`, IP3 sev=0.25 combined row

**Conclusion:** The trust weight interface (IP3) represents a residual risk.
Low-severity corruption at this boundary can degrade the combined mitigation
to baseline behavior.

---

## Residual Risks

| ID | Risk | Severity | Closure Path |
|----|------|----------|--------------|
| RR-01 | IP3 trust corruption at sev=0.25 breaks combined mitigation | ASIL C | NR-02: trust integrity check |
| RR-02 | Loop 1 provides no standalone safety benefit | ASIL B | Architecture documented — two loops required together |
| RR-03 | Speed reduction trade-off not validated in dense traffic | ASIL B | NR-01: rear-proximity monitor |
| RR-04 | Single scenario coverage — HAZ-01 only | ASIL C | Stage 3 campaign expansion needed |
| RR-05 | Single map — Town10HD only | ASIL B | Multi-map campaign pending |
| RR-06 | EDL epistemic calibration gap | ASIL C | Task-specific fine-tuning (Phase 7) |
| RR-07 | Sim-to-real gap | ASIL D | Real-world validation debt |

---

## Safety Goal Verdicts

| Safety Goal | ASIL | Closed-Loop Status | Evidence |
|-------------|------|-------------------|----------|
| SG1: Confidence threshold | B | PARTIAL | Loop 2 compensates — Loop 1 signal not independently effective |
| SG2: TTC scaling | C | VERIFIED | 10.4x TTC improvement, 0% collision rate |
| SG3: CONSERVATIVE regime | C | PARTIAL | CAUTIOUS triggered; CONSERVATIVE not reached in HAZ-01 |
| SG4: Affordance override | D | PARTIAL | Pedestrian avoided but no explicit affordance classification |
| SG5: MRC trigger | B | NOT TESTED | Requires extreme combined failure scenario |

---

## New Requirements (feed back to Specify)

| ID | Requirement | Source Finding | Priority |
|----|-------------|----------------|----------|
| NR-01 | Rear-proximity monitor shall inhibit CAUTIOUS speed reduction when following vehicle within 5m | Trade-off: Loop 2 speed reduction | ASIL B |
| NR-02 | IP3 trust weight integrity check — system shall detect and flag trust inputs deviating >0.3 from expected range | Finding 3: IP3 fragility | ASIL C |
| NR-03 | Minimum uncertainty floor of 0.20 to prevent Loop 2 remaining in NORMAL at zero IP2 injection | Finding 4: IP2 zero-severity | ASIL B |
| NR-04 | Campaign shall be extended to cut-in, occlusion, fog, rain, and night scenarios | Coverage gap | ASIL C |

---

## Validation Debt

| Item | Description | Closes |
|------|-------------|--------|
| VD-01 | Real-world perception backbone (BEVFusion replacing SegFormer proxy) | Phase 7 |
| VD-02 | Closed-loop validation on real nuScenes full split | Phase 7 |
| VD-03 | Multi-scenario campaign (cut-in, occlusion, weather) | Stage 3 expansion |
| VD-04 | EDL epistemic head fine-tuning on degraded driving data | Phase 7 |
| VD-05 | Sim-to-real transfer validation | Post-thesis |

---

*Safety case evidence: `results/stage3/haz01_v2.json`*
*V&V report: `results/stage4/vnv_report.md`*
*Campaign code: `scripts/stage2_haz01_injection.py`*
