"""
scripts/planning_utils.py
==========================
Shared planning utilities for closed-loop campaign scripts.
Implements:
  - Camera/LiDAR trust computation (Phase 3 formulas)
  - Planning mode with CONSERVATIVE threshold fix
  - SG4: Pedestrian affordance override (distance-based)
  - AEB assist: brake when VRU within proximity threshold
  - FPC computation

Used by: stage3_haz05_rain.py, stage3_haz06_night.py, stage3_haz07_construction.py
"""

import math

# ── Thresholds (updated — lower CONSERVATIVE threshold) ───────────────────────

CAUTIOUS_THRESHOLD      = 0.20   # unchanged
CONSERVATIVE_THRESHOLD  = 0.40   # LOWERED from 0.55 — closes HAZ-02/04 TTC gap
EMERGENCY_THRESHOLD     = 0.75   # unchanged

# SG4: pedestrian affordance override distance (meters)
PEDESTRIAN_OVERRIDE_DIST = 15.0  # force CAUTIOUS minimum within 15m of VRU
AEB_DIST                 = 6.0   # apply partial brake within 6m

# Throttle per mode
THROTTLE = {
    'NORMAL':       0.6,
    'CAUTIOUS':     0.4,
    'CONSERVATIVE': 0.15,
    'EMERGENCY':    0.0,
}

BRAKE = {
    'NORMAL':       0.0,
    'CAUTIOUS':     0.0,
    'CONSERVATIVE': 0.0,
    'EMERGENCY':    0.8,
}

# ── Trust computation ──────────────────────────────────────────────────────────

def compute_camera_trust_glare(glare_severity, loop1_active):
    """Phase 3 sigmoid formula for glare."""
    if loop1_active:
        return 1.0 / (1.0 + math.exp(6.0 * (glare_severity - 0.4)))
    return 0.58

def compute_camera_trust_fog(fog_severity, loop1_active):
    """Phase 5: fog +29.9% uncertainty."""
    if loop1_active:
        unc = min(1.0, 0.15 + fog_severity * 0.299)
        return max(0.0, 1.0 - unc * 1.5)
    return 0.58

def compute_camera_trust_night(darkness, loop1_active):
    """Night: darkness reduces camera reliability linearly."""
    if loop1_active:
        return max(0.1, 0.58 * (1.0 - darkness * 0.6))
    return 0.58

def compute_lidar_trust(dropout, loop1_active):
    """LiDAR trust degrades with dropout (rain/construction debris)."""
    if loop1_active:
        return max(0.0, 1.0 - dropout)
    return 0.42

# ── Mode computation with SG4 fix ─────────────────────────────────────────────

def compute_mode(cam_trust, lidar_trust, loop2_active,
                 dist_to_vru=None, sg4_active=True):
    """
    Compute planning mode from trust weights.
    
    sg4_active: if True, applies pedestrian affordance override (SG4 fix)
                Forces CAUTIOUS minimum when VRU within PEDESTRIAN_OVERRIDE_DIST
    """
    fused_unc = 1.0 - (0.6 * cam_trust + 0.4 * lidar_trust)

    if not loop2_active:
        return 'NORMAL', fused_unc

    # SG4: pedestrian affordance override
    if sg4_active and dist_to_vru is not None:
        if dist_to_vru <= AEB_DIST:
            return 'EMERGENCY', fused_unc
        elif dist_to_vru <= PEDESTRIAN_OVERRIDE_DIST:
            # Force minimum CAUTIOUS regardless of uncertainty
            if fused_unc < CAUTIOUS_THRESHOLD:
                fused_unc = CAUTIOUS_THRESHOLD

    if fused_unc >= EMERGENCY_THRESHOLD:
        return 'EMERGENCY', fused_unc
    elif fused_unc >= CONSERVATIVE_THRESHOLD:
        return 'CONSERVATIVE', fused_unc
    elif fused_unc >= CAUTIOUS_THRESHOLD:
        return 'CAUTIOUS', fused_unc
    return 'NORMAL', fused_unc

def compute_control(mode, dist_to_vru=None):
    """Compute throttle and brake from mode + AEB assist."""
    throttle = THROTTLE[mode]
    brake = BRAKE[mode]

    # AEB assist: partial brake when close to VRU
    if dist_to_vru is not None and dist_to_vru <= AEB_DIST:
        throttle = 0.0
        brake = max(brake, 0.6)

    return throttle, brake

def compute_fpc(baseline, injected, severity):
    """FPC = |delta_TTC_normalized| / severity"""
    if severity == 0.0:
        return 0.0
    if not baseline.get('min_ttc') or not injected.get('min_ttc'):
        return 0.0
    if baseline['min_ttc'] > 900 or injected['min_ttc'] > 900:
        return 0.0
    delta = abs(baseline['min_ttc'] - injected['min_ttc']) / baseline['min_ttc']
    return round(delta / severity, 4)
