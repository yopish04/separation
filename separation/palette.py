"""Penentuan palet warna spot: k-means di ruang Lab, atau palet manual."""

import numpy as np

from .color import srgb_to_lab


def kmeans_palette(
    rgb: np.ndarray, k: int, max_samples: int = 40000, iters: int = 25, seed: int = 0
) -> np.ndarray:
    """Cari k warna dominan dari piksel (N, 3). Mengembalikan array (k, 3) RGB."""
    pixels = np.asarray(rgb, dtype=np.float64).reshape(-1, 3)
    if len(pixels) == 0:
        raise ValueError("Tidak ada piksel untuk dianalisis (gambar transparan semua?)")
    rng = np.random.default_rng(seed)
    if len(pixels) > max_samples:
        pixels = pixels[rng.choice(len(pixels), max_samples, replace=False)]
    unique = np.unique(pixels, axis=0)
    k = min(k, len(unique))
    lab = srgb_to_lab(pixels)

    # Inisialisasi k-means++ supaya hasil stabil.
    centers = [lab[rng.integers(len(lab))]]
    for _ in range(1, k):
        d2 = np.min(((lab[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
        if d2.sum() == 0:
            break
        centers.append(lab[rng.choice(len(lab), p=d2 / d2.sum())])
    centers = np.array(centers)

    labels = np.zeros(len(lab), dtype=int)
    for _ in range(iters):
        labels = np.argmin(((lab[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        new = np.array(
            [lab[labels == i].mean(0) if np.any(labels == i) else centers[i] for i in range(len(centers))]
        )
        if np.allclose(new, centers, atol=1e-3):
            break
        centers = new

    # Warna wakil diambil sebagai rata-rata RGB anggota cluster (tanpa konversi balik Lab->RGB).
    palette = [pixels[labels == i].mean(0) for i in range(len(centers)) if np.any(labels == i)]
    return np.round(np.array(palette)).clip(0, 255)


def assign(rgb: np.ndarray, palette: np.ndarray, softness: float = 0.0) -> np.ndarray:
    """Bobot keanggotaan tiap piksel ke tiap warna palet.

    rgb: (H, W, 3); palette: (K, 3). Hasil (H, W, K) bernilai 0..1.
    softness = 0 -> hard assignment (warna solid); > 0 -> bobot lembut (sigma dalam
    satuan Delta-E) agar gradasi antarwarna bisa dijadikan halftone.
    """
    lab = srgb_to_lab(rgb)
    pal = srgb_to_lab(palette)
    d2 = ((lab[..., None, :] - pal[None, None]) ** 2).sum(-1)
    if softness <= 0:
        idx = np.argmin(d2, axis=-1)
        return (idx[..., None] == np.arange(len(palette))).astype(np.float64)
    logits = -d2 / (2 * softness**2)
    logits -= logits.max(-1, keepdims=True)
    w = np.exp(logits)
    return w / w.sum(-1, keepdims=True)
