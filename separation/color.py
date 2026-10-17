"""Konversi warna sRGB <-> CIELAB dan parsing hex."""

import numpy as np

_D65 = np.array([0.95047, 1.0, 1.08883])
_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)


def parse_hex(value: str) -> tuple[int, int, int]:
    """'#ff8800' / 'ff8800' / '#f80' -> (255, 136, 0)."""
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Warna hex tidak valid: {value!r}")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def to_hex(rgb) -> str:
    r, g, b = (int(round(float(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Array (..., 3) uint8/float 0-255 -> Lab (..., 3)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _RGB_TO_XYZ.T / _D65
    eps = 216 / 24389
    kappa = 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lightness(rgb) -> float:
    return float(srgb_to_lab(np.array(rgb, dtype=np.float64))[0])
