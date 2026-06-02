"""
utils/planning.py
==================
Loop 2: Uncertainty-aware Frenet planner.

Extracted from: phase1, phase3 inline implementations.

The planner maps sensor trust + planning mode to concrete driving outputs:
  - Target velocity (km/h)
  - TTC safety margin (seconds)
  - Lateral safety margin (meters)
  - Rate-of-change controller K(t)

Key results from Phase 3 sensitivity matrix:
  NORMAL:       ~50 km/h, TTC 3.5s, lateral 2.5m
  CAUTIOUS:     ~30–35 km/h, TTC 3.5–3.6s, lateral 2.5–2.6m
  CONSERVATIVE: ~25–30 km/h, TTC 3.6–3.7s, lateral 2.6–2.8m
  EMERGENCY:    <20 km/h,    TTC 4.0+s,    lateral 3.0m
"""

from dataclasses import dataclass
from typing import Dict


# ── Planning mode parameters ──────────────────────────────────────────────────

@dataclass
class PlanningParams:
    """Target values for each planning regime."""
    velocity_kmh:       float   # target speed
    ttc_margin_s:       float   # time-to-collision safety buffer
    lateral_margin_m:   float   # lane-keeping clearance
    k_rate:             float   # K(t) rate controller gain


# Calibrated from Phase 1/3 results
PLANNING_PARAMS: Dict[str, PlanningParams] = {
    "NORMAL": PlanningParams(
        velocity_kmh     = 50.0,
        ttc_margin_s     = 3.5,
        lateral_margin_m = 2.5,
        k_rate           = 1.0
    ),
    "CAUTIOUS": PlanningParams(
        velocity_kmh     = 32.0,
        ttc_margin_s     = 3.55,
        lateral_margin_m = 2.53,
        k_rate           = 0.5
    ),
    "CONSERVATIVE": PlanningParams(
        velocity_kmh     = 27.0,
        ttc_margin_s     = 3.65,
        lateral_margin_m = 2.65,
        k_rate           = 0.15
    ),
    "EMERGENCY": PlanningParams(
        velocity_kmh     = 15.0,
        ttc_margin_s     = 4.0,
        lateral_margin_m = 3.0,
        k_rate           = 0.0
    ),
}


# ── Core planner ──────────────────────────────────────────────────────────────

def frenet_planner(
    mode: str,
    camera_trust: float,
    lidar_trust: float,
    current_velocity_kmh: float = 50.0
) -> Dict[str, float]:
    """
    Uncertainty-aware Frenet planner (Loop 2).

    Maps planning mode + sensor trust to target driving parameters.
    Interpolates between mode boundaries using trust weights to produce
    smooth transitions rather than hard mode switches.

    Args:
        mode:                  current planning mode (from trust_to_planning_mode)
        camera_trust:          normalized camera trust weight [0, 1]
        lidar_trust:           normalized LiDAR trust weight [0, 1]
        current_velocity_kmh:  ego vehicle speed (for rate limiting)

    Returns:
        dict with keys: velocity_kmh, ttc_margin_s, lateral_margin_m, k_rate, mode
    """
    params = PLANNING_PARAMS[mode]

    # Trust-weighted interpolation within mode boundaries
    # Higher combined trust → closer to mode upper bound
    combined_trust = 0.6 * camera_trust + 0.4 * lidar_trust

    # Soft velocity adjustment within ±3 km/h of mode target
    trust_adjustment = (combined_trust - 0.5) * 6.0   # ±3 km/h
    target_velocity  = params.velocity_kmh + trust_adjustment
    target_velocity  = max(params.velocity_kmh - 3.0,
                           min(params.velocity_kmh + 3.0, target_velocity))

    # Rate controller: limits how fast velocity can change
    # K(t) = 0.0 → hold current speed (EMERGENCY)
    # K(t) = 1.0 → jump to target immediately (NORMAL)
    rate = params.k_rate
    actual_velocity = current_velocity_kmh + rate * (target_velocity - current_velocity_kmh)

    return {
        "velocity_kmh":      round(actual_velocity, 2),
        "ttc_margin_s":      round(params.ttc_margin_s, 3),
        "lateral_margin_m":  round(params.lateral_margin_m, 3),
        "k_rate":            params.k_rate,
        "mode":              mode,
        "camera_trust":      round(camera_trust, 4),
        "lidar_trust":       round(lidar_trust, 4),
    }


# ── TTC and collision safety ──────────────────────────────────────────────────

def compute_ttc(
    ego_velocity_ms: float,
    lead_distance_m: float,
    lead_velocity_ms: float = 0.0
) -> float:
    """
    Time-to-collision (TTC) in seconds.

    Args:
        ego_velocity_ms:   ego speed (m/s)
        lead_distance_m:   distance to leading object (meters)
        lead_velocity_ms:  speed of leading object (m/s), positive = moving away

    Returns:
        TTC in seconds, or float('inf') if no collision course
    """
    relative_velocity = ego_velocity_ms - lead_velocity_ms
    if relative_velocity <= 0:
        return float('inf')
    return lead_distance_m / relative_velocity


def is_ttc_safe(ttc: float, mode: str) -> bool:
    """Check if TTC exceeds required margin for current planning mode."""
    required = PLANNING_PARAMS[mode].ttc_margin_s
    return ttc >= required or ttc == float('inf')


# ── Planning output delta (for propagation analysis) ─────────────────────────

def planning_delta(
    clean_output: Dict[str, float],
    degraded_output: Dict[str, float]
) -> Dict[str, float]:
    """
    Compute the change in planning outputs between clean and degraded conditions.
    Used in Phase B interface injection to measure downstream propagation.

    Args:
        clean_output:    frenet_planner() output under clean conditions
        degraded_output: frenet_planner() output under degraded conditions

    Returns:
        dict of deltas: Δvelocity, ΔTTC, Δlateral, mode_changed
    """
    return {
        "delta_velocity_kmh":    round(degraded_output["velocity_kmh"]     - clean_output["velocity_kmh"],     3),
        "delta_ttc_s":           round(degraded_output["ttc_margin_s"]      - clean_output["ttc_margin_s"],     3),
        "delta_lateral_m":       round(degraded_output["lateral_margin_m"]  - clean_output["lateral_margin_m"], 3),
        "delta_camera_trust":    round(degraded_output["camera_trust"]      - clean_output["camera_trust"],     4),
        "mode_changed":          degraded_output["mode"] != clean_output["mode"],
        "mode_clean":            clean_output["mode"],
        "mode_degraded":         degraded_output["mode"],
    }
