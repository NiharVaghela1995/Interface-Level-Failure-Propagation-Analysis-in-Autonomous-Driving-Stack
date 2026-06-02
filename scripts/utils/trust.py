"""
utils/trust.py
===============
Loop 1: Sensor trust reweighting formulas.

Extracted from: phase2, phase3, phase4b inline implementations.

Two trust models:
  MC Dropout trust  — naive sigmoid on total uncertainty (phases 2/3)
  EDL trust         — principled formula separating aleatoric/epistemic (phase 4b)

Key result from Phase 3:
  Camera trust drops 0.58 → 0.41 at max glare.
  LiDAR compensates: trust rises as camera degrades.
"""

import numpy as np
import torch
from typing import Tuple


# ── Constants (calibrated from Phase 2/3 results) ────────────────────────────

# Baseline camera trust under clean conditions
CAMERA_TRUST_BASELINE = 0.58
LIDAR_TRUST_BASELINE  = 0.42

# Fragility boundaries (from Phase 3 sensitivity matrix)
GLARE_FRAGILITY_BOUNDARY   = 0.45   # system enters CAUTIOUS above this
DROPOUT_FRAGILITY_BOUNDARY = 0.35   # 35% LiDAR dropout → CAUTIOUS

# EDL trust formula hyperparameters (Phase 4b)
EDL_EPISTEMIC_WEIGHT = 0.4
EDL_ALEATORIC_WEIGHT = 0.6
EDL_EPISTEMIC_K      = 5.0   # steeper penalty for unknown scenarios
EDL_ALEATORIC_K      = 2.5   # softer penalty for known sensor noise


# ── MC Dropout trust (naive sigmoid) ─────────────────────────────────────────

def mc_trust(
    uncertainty: float,
    baseline_uncertainty: float,
    k: float = 3.0,
    threshold_ratio: float = 1.2
) -> float:
    """
    MC Dropout camera trust: sigmoid on normalized uncertainty.
    Used in Phases 2 and 3.

    Trust = sigmoid(−k × (u/u_baseline − threshold_ratio))

    Args:
        uncertainty:          current MC Dropout scalar uncertainty
        baseline_uncertainty: clean-scene uncertainty (u_baseline)
        k:                    sigmoid steepness (3.0 calibrated in phase 3)
        threshold_ratio:      ratio at which trust = 0.5 (default 1.2×baseline)

    Returns:
        trust in [0, 1]

    Weakness: total uncertainty is undifferentiated — glare and novel scenarios
              get the same trust penalty → motivates EDL (Phase 4b).
    """
    ratio = uncertainty / (baseline_uncertainty + 1e-10)
    trust = torch.sigmoid(torch.tensor(-k * (ratio - threshold_ratio)))
    return float(trust.item())


# ── EDL trust (principled aleatoric/epistemic separation) ────────────────────

def edl_trust(
    epistemic: float,
    aleatoric: float,
    ep_baseline: float,
    al_baseline: float,
    ep_weight: float  = EDL_EPISTEMIC_WEIGHT,
    al_weight: float  = EDL_ALEATORIC_WEIGHT,
    ep_k: float       = EDL_EPISTEMIC_K,
    al_k: float       = EDL_ALEATORIC_K,
    ep_threshold: float = 1.1,
    al_threshold: float = 1.3
) -> float:
    """
    EDL camera trust formula from Phase 4b.

    Trust = ep_weight × sigmoid(−ep_k × (ep/ep_b − ep_thresh))
          + al_weight × sigmoid(−al_k × (al/al_b − al_thresh))

    Design rationale:
      ep_k=5.0 > al_k=2.5 — epistemic uncertainty (model ignorance about
      a novel scenario) is penalized more steeply than aleatoric uncertainty
      (known sensor noise like glare). Known noise is manageable;
      unknown scenarios are more dangerous.

    Args:
        epistemic:    current EDL epistemic uncertainty
        aleatoric:    current EDL aleatoric uncertainty
        ep_baseline:  clean-scene epistemic baseline
        al_baseline:  clean-scene aleatoric baseline

    Returns:
        trust in [0, 1]
    """
    ep_term = ep_weight * torch.sigmoid(
        torch.tensor(-ep_k * (epistemic / (ep_baseline + 1e-10) - ep_threshold))
    )
    al_term = al_weight * torch.sigmoid(
        torch.tensor(-al_k * (aleatoric / (al_baseline + 1e-10) - al_threshold))
    )
    return float((ep_term + al_term).item())


# ── Cross-modal trust rebalancing (Loop 1) ────────────────────────────────────

def rebalance_trust(
    camera_raw_trust: float,
    lidar_dropout_rate: float,
    camera_baseline: float = CAMERA_TRUST_BASELINE,
    lidar_baseline: float  = LIDAR_TRUST_BASELINE
) -> Tuple[float, float]:
    """
    Loop 1: Normalize camera + LiDAR trust weights so they sum to 1.
    When camera degrades → LiDAR trust increases to compensate.
    When LiDAR degrades → camera trust increases to compensate.

    Args:
        camera_raw_trust:   raw camera trust score from mc_trust() or edl_trust()
        lidar_dropout_rate: fraction of LiDAR points dropped [0.0, 1.0]
        camera_baseline:    clean-scene camera trust (default 0.58)
        lidar_baseline:     clean-scene LiDAR trust  (default 0.42)

    Returns:
        (camera_weight, lidar_weight) — normalized, sum to 1.0

    Calibrated results from Phase 2/3:
        Clean:    camera=0.58, LiDAR=0.42
        Max glare: camera=0.41, LiDAR=0.59  (camera degrades, LiDAR compensates)
        Max rain:  camera=0.65, LiDAR=0.35  (LiDAR degrades, camera compensates)
    """
    # LiDAR trust degrades with dropout
    lidar_raw_trust = lidar_baseline * (1.0 - lidar_dropout_rate * 0.8)
    lidar_raw_trust = max(lidar_raw_trust, 0.05)   # floor — never fully zero

    # Normalize to sum = 1.0
    total = camera_raw_trust + lidar_raw_trust
    camera_weight = camera_raw_trust / total
    lidar_weight  = lidar_raw_trust  / total

    return camera_weight, lidar_weight


# ── Trust → planning mode ─────────────────────────────────────────────────────

def trust_to_planning_mode(
    camera_trust: float,
    lidar_trust: float,
    glare_intensity: float = 0.0,
    lidar_dropout: float   = 0.0
) -> str:
    """
    Determine planning mode from sensor trust state.
    Boundaries calibrated from Phase 3 sensitivity matrix.

    NORMAL:       both sensors healthy
    CAUTIOUS:     one sensor degraded — increase margins
    CONSERVATIVE: both sensors degraded or primary failure
    EMERGENCY:    critical failure — max deceleration

    Returns: "NORMAL" | "CAUTIOUS" | "CONSERVATIVE" | "EMERGENCY"
    """
    if glare_intensity > 0.75 and lidar_dropout > 0.65:
        return "EMERGENCY"
    if glare_intensity > GLARE_FRAGILITY_BOUNDARY or lidar_dropout > DROPOUT_FRAGILITY_BOUNDARY:
        if camera_trust < 0.40 and lidar_trust < 0.35:
            return "CONSERVATIVE"
        return "CAUTIOUS"
    if camera_trust > 0.52 and lidar_trust > 0.38:
        return "NORMAL"
    return "CAUTIOUS"
