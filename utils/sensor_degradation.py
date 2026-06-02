"""
utils/sensor_degradation.py
============================
Synthetic sensor degradation functions used across all phases.

Extracted from: phase1, phase2, phase3, phase5 inline implementations.
Single source of truth — import this instead of redefining per phase.

Degradation types:
  Camera:  glare, brightness, darkness, fog, motion_blur, snow, rain
  LiDAR:   random point dropout (density reduction)

All functions:
  - Accept PIL.Image or np.ndarray (auto-detected)
  - Return same type as input
  - Are deterministic given a seed (pass rng for reproducibility)
"""

import numpy as np
from PIL import Image, ImageFilter
from typing import Union, Optional

ImageLike = Union[Image.Image, np.ndarray]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _to_array(img: ImageLike) -> np.ndarray:
    if isinstance(img, Image.Image):
        return np.array(img, dtype=np.float32)
    return img.astype(np.float32)


def _to_pil(arr: np.ndarray, original: ImageLike) -> ImageLike:
    clipped = np.clip(arr, 0, 255).astype(np.uint8)
    if isinstance(original, Image.Image):
        return Image.fromarray(clipped)
    return clipped


# ── Camera corruptions ────────────────────────────────────────────────────────

def apply_glare(image: ImageLike, intensity: float) -> ImageLike:
    """
    Additive white overlay simulating direct sunlight / headlight glare.

    Args:
        image:     input image (PIL or ndarray)
        intensity: glare strength in [0.0, 1.0]
                   0.0 = no effect, 1.0 = fully white

    Used in: Phase 1, 2, 3, 4b, 5
    """
    arr = _to_array(image)
    arr = arr + intensity * 255.0
    return _to_pil(arr, image)


def apply_brightness(image: ImageLike, intensity: float) -> ImageLike:
    """
    Multiplicative brightness increase (overexposure simulation).

    Args:
        intensity: scale factor offset, e.g. 0.5 → multiply by 1.5

    Used in: Phase 5
    """
    arr = _to_array(image)
    arr = arr * (1.0 + intensity)
    return _to_pil(arr, image)


def apply_darkness(image: ImageLike, intensity: float) -> ImageLike:
    """
    Multiplicative darkness (underexposure / night driving simulation).

    Args:
        intensity: darkness strength in [0.0, 1.0]
                   1.0 = fully black

    Used in: Phase 5
    """
    arr = _to_array(image)
    arr = arr * (1.0 - intensity)
    return _to_pil(arr, image)


def apply_fog(image: ImageLike, intensity: float) -> ImageLike:
    """
    Fog simulation: linear blend toward white with contrast reduction.

    Args:
        intensity: fog density in [0.0, 1.0]

    Used in: Phase 5
    Note: Most impactful corruption — 29.9% mean uncertainty increase at max severity.
    """
    arr = _to_array(image)
    fog_layer = np.ones_like(arr) * 230.0   # slightly off-white fog color
    arr = arr * (1.0 - intensity * 0.85) + fog_layer * (intensity * 0.85)
    return _to_pil(arr, image)


def apply_motion_blur(image: ImageLike, intensity: float) -> ImageLike:
    """
    Horizontal motion blur simulating camera shake or fast movement.

    Args:
        intensity: blur strength in [0.0, 1.0]
                   maps to kernel size 1–21 pixels

    Used in: Phase 5
    """
    pil_img = image if isinstance(image, Image.Image) else Image.fromarray(
        np.clip(image, 0, 255).astype(np.uint8)
    )
    kernel_size = max(1, int(intensity * 20) | 1)   # odd number
    blurred = pil_img.filter(ImageFilter.BoxBlur(kernel_size // 2))
    if isinstance(image, np.ndarray):
        return np.array(blurred, dtype=np.float32)
    return blurred


def apply_snow(image: ImageLike, intensity: float,
               rng: Optional[np.random.Generator] = None) -> ImageLike:
    """
    Sparse white pixel noise simulating snow.

    Args:
        intensity: snow density in [0.0, 1.0]
        rng:       numpy Generator for reproducibility

    Used in: Phase 5
    Note: Least impactful corruption — 8.7% mean uncertainty increase.
    """
    if rng is None:
        rng = np.random.default_rng()
    arr = _to_array(image)
    mask = rng.random(arr.shape[:2]) < (intensity * 0.15)
    arr[mask] = 255.0
    return _to_pil(arr, image)


def apply_rain(image: ImageLike, intensity: float,
               rng: Optional[np.random.Generator] = None) -> ImageLike:
    """
    Diagonal streak noise simulating rain on camera lens.

    Args:
        intensity: rain density in [0.0, 1.0]
        rng:       numpy Generator for reproducibility

    Used in: Phase 5
    """
    if rng is None:
        rng = np.random.default_rng()
    arr = _to_array(image)
    h, w = arr.shape[:2]
    n_streaks = int(intensity * w * 0.3)
    for _ in range(n_streaks):
        x = rng.integers(0, w)
        length = rng.integers(10, 40)
        brightness = rng.uniform(0.6, 1.0) * 255
        for dy in range(length):
            y = rng.integers(0, h)
            dx = int(dy * 0.3)
            if 0 <= y < h and 0 <= x + dx < w:
                arr[y, x + dx] = brightness
    return _to_pil(arr, image)


# ── Corruption dispatcher ─────────────────────────────────────────────────────

CORRUPTION_TYPES = [
    "clean", "glare", "brightness", "darkness",
    "fog", "motion_blur", "snow", "rain"
]

_CORRUPTION_FNS = {
    "glare":       apply_glare,
    "brightness":  apply_brightness,
    "darkness":    apply_darkness,
    "fog":         apply_fog,
    "motion_blur": apply_motion_blur,
    "snow":        apply_snow,
    "rain":        apply_rain,
}


def apply_corruption(image: ImageLike, corruption_type: str,
                     severity: float,
                     rng: Optional[np.random.Generator] = None) -> ImageLike:
    """
    Unified corruption dispatcher used in Phase 5 benchmark sweep.

    Args:
        image:           input image
        corruption_type: one of CORRUPTION_TYPES
        severity:        strength in [0.0, 1.0]
        rng:             optional Generator for stochastic corruptions

    Returns:
        Corrupted image (same type as input)

    Example:
        img = apply_corruption(frame, "fog", severity=0.8)
    """
    if corruption_type == "clean":
        return image
    if corruption_type not in _CORRUPTION_FNS:
        raise ValueError(
            f"Unknown corruption '{corruption_type}'. "
            f"Choose from: {CORRUPTION_TYPES}"
        )
    fn = _CORRUPTION_FNS[corruption_type]
    if corruption_type in ("snow", "rain"):
        return fn(image, severity, rng=rng)
    return fn(image, severity)


# ── LiDAR degradation ─────────────────────────────────────────────────────────

def apply_lidar_dropout(points: np.ndarray, dropout_rate: float,
                        rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """
    Random LiDAR point removal simulating rain scatter, dust, interference.

    Args:
        points:       LiDAR point cloud [N, 4] (x, y, z, intensity)
        dropout_rate: fraction of points to remove, in [0.0, 1.0]
                      0.0 = no dropout, 1.0 = all points removed
        rng:          numpy Generator for reproducibility

    Returns:
        Reduced point cloud [M, 4] where M = N * (1 - dropout_rate)

    Used in: Phase 2, 3
    Example:
        clean_pts = load_lidar(sample)          # 34,688 points
        rain_pts  = apply_lidar_dropout(clean_pts, dropout_rate=0.35)
        # → ~22,547 points (35% removed)
    """
    if rng is None:
        rng = np.random.default_rng()
    n = len(points)
    keep = rng.random(n) > dropout_rate
    return points[keep]


def lidar_point_count(points: np.ndarray) -> int:
    """Return number of points in a LiDAR cloud."""
    return len(points)


def lidar_density_ratio(degraded: np.ndarray,
                        clean: np.ndarray) -> float:
    """
    Fraction of LiDAR points remaining after degradation.
    1.0 = no dropout, 0.0 = all points removed.
    """
    if len(clean) == 0:
        return 0.0
    return len(degraded) / len(clean)
