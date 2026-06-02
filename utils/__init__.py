"""
utils/ — Shared utilities for AV Interface Failure Propagation Framework
=========================================================================

Import pattern:
    from utils.sensor_degradation import apply_corruption, apply_lidar_dropout
    from utils.uncertainty import mc_dropout_passes, edl_decompose, EvidentialHead
    from utils.trust import edl_trust, mc_trust, rebalance_trust
    from utils.planning import frenet_planner, planning_delta
    from utils.metrics import propagation_coefficient, coverage_percentage

Quick test — run this file directly to verify all imports work:
    python scripts/utils/__init__.py
"""

from utils.sensor_degradation import (
    apply_glare,
    apply_corruption,
    apply_lidar_dropout,
    CORRUPTION_TYPES,
)

from utils.uncertainty import (
    enable_dropout,
    mc_dropout_passes,
    uncertainty_scalar,
    EvidentialHead,
    edl_decompose,
    aleatoric_fraction,
    uncertainty_to_mode,
    UNCERTAINTY_THRESHOLDS,
)

from utils.trust import (
    mc_trust,
    edl_trust,
    rebalance_trust,
    trust_to_planning_mode,
    CAMERA_TRUST_BASELINE,
    LIDAR_TRUST_BASELINE,
    GLARE_FRAGILITY_BOUNDARY,
    DROPOUT_FRAGILITY_BOUNDARY,
)

from utils.planning import (
    frenet_planner,
    compute_ttc,
    is_ttc_safe,
    planning_delta,
    PLANNING_PARAMS,
)

from utils.metrics import (
    safety_margin,
    collision_risk_score,
    risk_reduction_vs_baseline,
    coverage_percentage,
    coverage_gaps,
    propagation_coefficient,
    normalize_delta,
    interface_fragility_score,
    ODD_COVERAGE_MATRIX,
)

__all__ = [
    # sensor_degradation
    "apply_glare", "apply_corruption", "apply_lidar_dropout", "CORRUPTION_TYPES",
    # uncertainty
    "enable_dropout", "mc_dropout_passes", "uncertainty_scalar",
    "EvidentialHead", "edl_decompose", "aleatoric_fraction",
    "uncertainty_to_mode", "UNCERTAINTY_THRESHOLDS",
    # trust
    "mc_trust", "edl_trust", "rebalance_trust", "trust_to_planning_mode",
    "CAMERA_TRUST_BASELINE", "LIDAR_TRUST_BASELINE",
    "GLARE_FRAGILITY_BOUNDARY", "DROPOUT_FRAGILITY_BOUNDARY",
    # planning
    "frenet_planner", "compute_ttc", "is_ttc_safe", "planning_delta", "PLANNING_PARAMS",
    # metrics
    "safety_margin", "collision_risk_score", "risk_reduction_vs_baseline",
    "coverage_percentage", "coverage_gaps", "propagation_coefficient",
    "normalize_delta", "interface_fragility_score", "ODD_COVERAGE_MATRIX",
]


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import numpy as np
    from PIL import Image

    print("Testing utils/ imports...\n")

    # sensor_degradation
    img = Image.fromarray(np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8))
    degraded = apply_glare(img, intensity=0.5)
    print(f"  [✓] apply_glare:      PIL → PIL, size {degraded.size}")

    degraded2 = apply_corruption(img, "fog", severity=0.6)
    print(f"  [✓] apply_corruption: fog at 0.6 severity")

    pts = np.random.rand(34688, 4).astype(np.float32)
    reduced = apply_lidar_dropout(pts, dropout_rate=0.35)
    print(f"  [✓] apply_lidar_dropout: {len(pts)} → {len(reduced)} pts ({len(reduced)/len(pts)*100:.1f}% kept)")

    # trust
    trust_val = edl_trust(0.593, 2.940, ep_baseline=0.592, al_baseline=2.940)
    print(f"  [✓] edl_trust:        {trust_val:.4f}")

    cam_w, lid_w = rebalance_trust(camera_raw_trust=0.41, lidar_dropout_rate=0.35)
    print(f"  [✓] rebalance_trust:  camera={cam_w:.3f}, lidar={lid_w:.3f}, sum={cam_w+lid_w:.3f}")

    mode = trust_to_planning_mode(cam_w, lid_w, glare_intensity=0.5)
    print(f"  [✓] planning mode:    {mode}")

    # planning
    output = frenet_planner(mode, cam_w, lid_w, current_velocity_kmh=50.0)
    print(f"  [✓] frenet_planner:   {output['velocity_kmh']} km/h, TTC {output['ttc_margin_s']}s")

    clean  = frenet_planner("NORMAL",    0.58, 0.42)
    degrad = frenet_planner("CAUTIOUS",  0.41, 0.59)
    delta  = planning_delta(clean, degrad)
    print(f"  [✓] planning_delta:   Δv={delta['delta_velocity_kmh']} km/h, mode_changed={delta['mode_changed']}")

    # metrics
    cov = coverage_percentage()
    print(f"  [✓] ODD coverage:     {cov:.1f}%")

    gaps = coverage_gaps()
    print(f"  [✓] coverage gaps:    {len(gaps)} untested combinations")

    fpc = propagation_coefficient(injection_delta=0.15, downstream_delta=0.08)
    print(f"  [✓] FPC:              {fpc:.3f} (< 1.0 = attenuation, > 1.0 = amplification)")

    print("\nAll utils/ imports working correctly.")
