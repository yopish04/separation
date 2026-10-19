"""Halftone AM (titik bulat/elips) dengan LPI dan sudut screen, plus FM blue-noise untuk index."""

import numpy as np

# Sudut umum untuk separasi spot/simulated process agar tidak moire.
DEFAULT_ANGLES = [22.5, 52.5, 82.5, 7.5, 37.5, 67.5]


def angles_for(n: int, mode: str = "bertingkat", start: float = 22.5, step: float = 30.0) -> list[float]:
    """Sudut per channel.

    "sama"       : semua film satu sudut (gaya UltraSeps, sim process 55 LPI).
    "bertingkat" : start + k*step (gaya plugin Photoshop: 23/53/83/113/143°).
    """
    if mode == "sama":
        return [start] * n
    if mode != "bertingkat":
        raise ValueError(f"Mode sudut tidak dikenal: {mode!r}")
    return [round((start + k * step) % 180, 2) for k in range(n)]


def _spot(u: np.ndarray, v: np.ndarray, dot: str) -> np.ndarray:
    cu, cv = np.cos(2 * np.pi * u), np.cos(2 * np.pi * v)
    if dot == "bulat":
        return cu + cv
    if dot == "elips":
        # Titik memanjang ke satu sumbu dan menyambung (chain) di midtone: transisi lebih halus di kain.
        return 1.2 * cu + 0.8 * cv
    raise ValueError(f"Bentuk titik tidak dikenal: {dot!r}")


def _equalizer(dot: str, n: int = 256):
    """Peta nilai spot -> ambang 0..1 supaya luas titik linear terhadap tone."""
    g = (np.arange(n) + 0.5) / n
    u, v = np.meshgrid(g, g)
    s = np.sort(_spot(u, v, dot).ravel())[::-1]
    return s, np.linspace(0, 1, s.size)


def am_halftone(coverage: np.ndarray, dpi: float, lpi: float, angle_deg: float, dot: str = "bulat") -> np.ndarray:
    """coverage (H, W) 0..1 -> bitmap bool (True = tinta)."""
    h, w = coverage.shape
    cell = dpi / lpi
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = np.deg2rad(angle_deg)
    u = (xx * np.cos(t) + yy * np.sin(t)) / cell
    v = (-xx * np.sin(t) + yy * np.cos(t)) / cell
    del xx, yy
    s = _spot(u, v, dot)
    del u, v
    # Titik tumbuh dari nilai spot tertinggi (tengah sel); ranking membuat coverage linear.
    s_sorted, rank = _equalizer(dot)
    # Tabel 4096 entri lebih cepat daripada np.interp per piksel.
    lo, hi = float(s_sorted[-1]), float(s_sorted[0])
    grid = np.linspace(lo, hi, 4096)
    table = np.interp(-grid, -s_sorted, rank).astype(np.float32)
    threshold = table[np.clip(((s - lo) * (4095 / (hi - lo))).astype(np.int32), 0, 4095)]
    ink = coverage > threshold
    # Pastikan 0% bersih dan 100% solid.
    ink[coverage <= 0.02] = False
    ink[coverage >= 0.98] = True
    return ink


def blue_noise(size: int = 64, seed: int = 0, rounds: int = 8) -> np.ndarray:
    """Mask ambang blue-noise (size x size, nilai 0..1 merata) dari white noise yang di-high-pass berulang."""
    rng = np.random.default_rng(seed)
    m = rng.random((size, size))
    f = np.fft.fftfreq(size)
    r2 = f[:, None] ** 2 + f[None, :] ** 2
    lowpass = np.exp(-r2 / (2 * 0.08**2))
    for _ in range(rounds):
        m = m - np.real(np.fft.ifft2(np.fft.fft2(m) * lowpass))
        m = np.argsort(np.argsort(m.ravel())).reshape(size, size) / (size * size - 1)
    return m


def _tile(mask: np.ndarray, shape, grain_px: int, offset: int = 0) -> np.ndarray:
    big = np.kron(np.roll(mask, offset, axis=(0, 1)), np.ones((grain_px, grain_px)))
    reps = (-(-shape[0] // big.shape[0]), -(-shape[1] // big.shape[1]))
    return np.tile(big, reps)[: shape[0], : shape[1]]


def fm_halftone(coverage: np.ndarray, grain_px: int = 2, offset: int = 0) -> np.ndarray:
    """Dither FM (titik persegi ukuran sama, jarak acak) untuk satu channel."""
    th = _tile(blue_noise(), coverage.shape, max(1, grain_px), offset)
    return coverage > th


def index_halftone(tones: list[np.ndarray], grain_px: int = 2) -> list[np.ndarray]:
    """Index separation: tiap piksel film hanya mendapat satu tinta (titik tidak bertumpuk).

    Tone ditumpuk kumulatif dan dibandingkan dengan satu mask blue-noise yang sama, sehingga
    proporsi tiap tinta sesuai coverage-nya.
    """
    if not tones:
        return []
    th = _tile(blue_noise(), tones[0].shape, max(1, grain_px))
    lo = np.zeros_like(tones[0])
    out = []
    for t in tones:
        hi = lo + t
        out.append((th >= lo) & (th < hi) & (t > 0))
        lo = hi
    return out
