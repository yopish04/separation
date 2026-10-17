"""Halftone AM (titik bulat) dengan LPI dan sudut screen."""

import numpy as np

# Sudut umum untuk separasi spot/simulated process agar tidak moire.
DEFAULT_ANGLES = [22.5, 52.5, 82.5, 7.5, 37.5, 67.5]


def am_halftone(coverage: np.ndarray, dpi: float, lpi: float, angle_deg: float) -> np.ndarray:
    """coverage (H, W) 0..1 -> bitmap bool (True = tinta).

    Memakai spot function Euclidean (cosinus) pada grid yang diputar.
    """
    h, w = coverage.shape
    cell = dpi / lpi
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    t = np.deg2rad(angle_deg)
    u = (xx * np.cos(t) + yy * np.sin(t)) / cell
    v = (-xx * np.sin(t) + yy * np.cos(t)) / cell
    # Nilai 0..1; titik tumbuh dari tengah sel.
    spot = (np.cos(2 * np.pi * u) + np.cos(2 * np.pi * v)) / 4 + 0.5
    threshold = 1.0 - spot
    ink = coverage > threshold
    # Pastikan 0% bersih dan 100% solid.
    ink[coverage <= 0.02] = False
    ink[coverage >= 0.98] = True
    return ink
