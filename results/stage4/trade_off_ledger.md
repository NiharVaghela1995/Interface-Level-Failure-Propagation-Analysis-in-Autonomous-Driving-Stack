# Trade-off Ledger — HAZ-01 Campaign
## Stage 4: Evaluate — Secondary Effects of Mitigation

**Generated:** 2026-06-06 17:18

This ledger records every mitigation that improves one metric while
introducing secondary costs. Per the V&V program specification, these
are not failures — they are the expected secondary effects of a systems
view, and documenting them is what makes the safety argument honest.

---

## Trade-off 1: Loop 2 speed reduction

**Mitigation:** Loop 2 switches to CAUTIOUS mode (throttle 0.6 → 0.4)
when uncertainty threshold is crossed.

| Metric | Baseline | Loop 2 | Delta |
|--------|----------|--------|-------|
| Collision rate | 100% | 0% | -100% (BENEFIT) |
| Min TTC | 0.205s | 2.128s | +10.4x (BENEFIT) |
| Mean speed | 22.3 km/h | 13.3 km/h | -40% (COST) |
| Throughput | High | Reduced | Degraded (COST) |

**Secondary risk introduced:** In dense following traffic, the 40% speed
reduction could increase rear-end collision risk from trailing vehicles.
This scenario was not tested in HAZ-01 (single actor, open intersection).

**New requirement:** NR-01 — rear-proximity monitor.

---

## Trade-off 2: IP3 trust corruption bypasses combined mitigation

**Observation:** At IP3 sev=0.25, the combined mitigation (Loop 1 + Loop 2)
fails — collision=True. At IP3 sev=0.50 and sev=0.75, combined succeeds.

**Explanation:** Low-severity trust corruption is sufficient to degrade the
Loop 1 output signal but insufficient to push uncertainty above the Loop 2
activation threshold. The system is in a "partially degraded" state where
neither loop functions correctly.

**This is the most safety-critical finding of the campaign.** The combined
mitigation has a non-monotonic response to injection severity at IP3 — worse
at low severity than at high severity.

**New requirement:** NR-02 — trust weight integrity check.

---

## Trade-off 3: Loop 1 independence assumption

**Observation:** Loop 1 alone provides zero safety benefit (100% collision).

**Implication:** The V&V program assumption that Loop 1 provides independent
safety coverage is incorrect. Loop 1 is an enabling mechanism for Loop 2,
not an independent safety layer.

**Architecture impact:** The safety case cannot claim Loop 1 as an
independent defense-in-depth layer. Both loops must be treated as a single
combined mechanism.

---

## Summary

| Trade-off | Type | Priority | New Requirement |
|-----------|------|----------|-----------------|
| Loop 2 speed reduction | Performance vs Safety | Medium | NR-01 |
| IP3 non-monotonic response | Safety vs Safety | High | NR-02 |
| Loop 1 non-independence | Architecture | High | Architecture revision |

---

*Source: `results/stage3/haz01_v2.json`*
