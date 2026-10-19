"""Separasi simulated process untuk kaos gelap.

Ringkasan metode (lihat README untuk referensi):
1. Coverage tiap tinta per piksel dicari dengan least squares terbatas: warna tercetak dimodelkan sebagai
   campuran luas (Murray-Davies) antara warna kaos dan tinta-tinta, ``(1 - Σd)·kaos + Σ dᵢ·tintaᵢ``,
   dengan ``dᵢ ≥ 0`` dan ``Σd ≤ 1`` (titik sim process idealnya tidak bertumpuk).
2. Underbase = luas semua tinta terang (+ putih yang terlihat), diberi kurva S, dipertebal di bawah
   merah/biru, fringe < 6% dibuang, lalu di-choke (metode Fresener/UltraSeps).
3. Highlight white = putih di area paling terang dan netral (L* > 85, chroma < 25), warna di bawahnya
   di-knockout supaya highlight bersih.
4. Tiap channel di-halftone (AM bulat/elips, sudut sama atau bertingkat) atau index (FM blue-noise).
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from .color import lightness, parse_hex, srgb_to_lab
from .halftone import am_halftone, angles_for, fm_halftone, index_halftone
from .palette import kmeans_palette
from .separate import Channel, Separation, _load

# Palet default mengikuti setup umum sim process kaos gelap (seperti plugin di Photoshop):
# base putih + merah, kuning, cyan, hitam bayangan, highlight putih.
DEFAULT_PALETTE = [
    ("Merah", "#d0202e"),
    ("Kuning", "#f6c700"),
    ("Cyan", "#0a86c0"),
    ("Hitam", "#1c1c1c"),
]
WHITE = (255, 255, 255)


@dataclass
class SimOptions:
    garment: str = "#000000"
    palette: list[tuple[str, str]] | None = None  # [(nama, hex)]; None = DEFAULT_PALETTE
    n_colors: int | None = None  # isi untuk memilih warna otomatis (k-means pada warna jenuh)
    dpi: float = 300.0
    width_cm: float | None = None
    lpi: float = 55.0
    angle_mode: str = "bertingkat"  # "bertingkat" (23/53/83/..., seperti plugin) | "sama" (UltraSeps)
    angle_start: float = 22.5
    dot: str = "elips"  # "bulat" | "elips"
    method: str = "halftone"  # "halftone" (AM) | "index" (FM, titik persegi)
    grain_px: int = 2  # ukuran titik index (piksel)
    choke_px: int = 2
    min_density: float = 0.05
    fringe: float = 0.06
    red_blue_boost: float = 0.15
    highlight: bool = True
    despeckle: int = 0
    alpha_threshold: int = 128
    iters: int = 60
    space: str = "gamma"  # "gamma" (seperti channel Photoshop) | "linear"

    # Atribut yang dibaca report.build_report.
    halftone: bool = True

    @property
    def label(self) -> str:
        if self.method == "index":
            return f"simulated process · index {self.grain_px}px"
        return f"simulated process · {self.lpi:g} LPI · titik {self.dot} · sudut {self.angle_mode}"


def _linear(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, dtype=np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _encode(rgb: np.ndarray, space: str) -> np.ndarray:
    """Ruang hitung campuran. "gamma" = nilai sRGB apa adanya, seperti channel Photoshop: % titik
    mengikuti persepsi dan otomatis mengompensasi dot gain di kain. "linear" = Murray-Davies murni."""
    if space == "gamma":
        return np.asarray(rgb, dtype=np.float32) / 255.0
    if space == "linear":
        return _linear(rgb)
    raise ValueError(f"Ruang warna tidak dikenal: {space!r}")


def _decode(x: np.ndarray, space: str) -> np.ndarray:
    x = np.clip(x, 0, 1)
    if space == "linear":
        x = np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)
    return x * 255


def _project(d: np.ndarray) -> np.ndarray:
    """Proyeksi tiap baris ke {d ≥ 0, Σd ≤ 1}."""
    x = np.maximum(d, 0)
    over = x.sum(1) > 1
    if over.any():
        v = d[over]
        u = -np.sort(-v, axis=1)
        css = np.cumsum(u, axis=1) - 1
        k = np.arange(1, v.shape[1] + 1)
        rho = (u - css / k > 0).sum(1)
        theta = css[np.arange(len(v)), rho - 1] / rho
        x[over] = np.maximum(v - theta[:, None], 0)
    return x


def solve_coverage(target_rgb: np.ndarray, garment_rgb, inks_rgb: np.ndarray, iters: int = 60,
                   space: str = "gamma", block: int = 1 << 20) -> np.ndarray:
    """Least squares terbatas (FISTA). target (N, 3) -> coverage (N, K)."""
    g = _encode(np.array(garment_rgb), space)
    A = _encode(inks_rgb, space) - g  # (K, 3)
    AtA = A @ A.T
    step = 1.0 / max(float(np.linalg.eigvalsh(AtA).max()), 1e-6)
    out = np.empty((len(target_rgb), len(inks_rgb)), dtype=np.float32)
    for s in range(0, len(target_rgb), block):
        t = _encode(target_rgb[s : s + block], space) - g
        Atb = t @ A.T
        # Inisialisasi: tinta tunggal terbaik per piksel.
        single = np.clip(Atb / np.maximum(np.diag(AtA), 1e-6), 0, 1)
        err = (single**2) * np.diag(AtA) - 2 * single * Atb
        d = np.zeros_like(Atb)
        best = np.argmin(err, axis=1)
        d[np.arange(len(d)), best] = single[np.arange(len(d)), best]
        y, tk = d.copy(), 1.0
        for _ in range(iters):
            d_new = _project(y - step * (y @ AtA - Atb))
            tk_new = (1 + np.sqrt(1 + 4 * tk * tk)) / 2
            y = d_new + ((tk - 1) / tk_new) * (d_new - d)
            d, tk = d_new, tk_new
        out[s : s + block] = d
    return out


def coverage_lut(garment_rgb, inks_rgb: np.ndarray, iters: int = 60, space: str = "gamma") -> np.ndarray:
    """Tabel coverage untuk grid warna 64^3 (indeks = nilai >> 2). Solver jadi tidak bergantung ukuran gambar."""
    g = np.arange(64, dtype=np.float32) * 4 + 1.5
    grid = np.stack(np.meshgrid(g, g, g, indexing="ij"), axis=-1).reshape(-1, 3)
    return solve_coverage(grid, garment_rgb, inks_rgb, iters, space).reshape(64, 64, 64, -1)


def reconstruct(cov: np.ndarray, garment_rgb, inks_rgb: np.ndarray, space: str = "gamma") -> np.ndarray:
    """Kebalikan model: coverage (..., K) -> sRGB 0..255 (untuk tes)."""
    g = _encode(np.array(garment_rgb), space)
    return _decode(g + cov @ (_encode(inks_rgb, space) - g), space)


def _blur3(x: np.ndarray) -> np.ndarray:
    """Gaussian 3x3 (1-2-1) dengan tepi direplikasi."""
    p = np.pad(x, 1, mode="edge")
    rows = p[:-2] + 2 * p[1:-1] + p[2:]
    return (rows[:, :-2] + 2 * rows[:, 1:-1] + rows[:, 2:]) / 16


def _erode(x: np.ndarray, px: int) -> np.ndarray:
    if px <= 0:
        return x
    img = Image.fromarray(np.clip(x * 255, 0, 255).astype(np.uint8), "L")
    return np.asarray(img.filter(ImageFilter.MinFilter(2 * px + 1)), dtype=np.float32) / 255


def _s_curve(x: np.ndarray) -> np.ndarray:
    return x * x * (3 - 2 * x)


def _palette(opts: SimOptions, rgb: np.ndarray, opaque: np.ndarray, garment) -> list[tuple[str, tuple]]:
    if opts.n_colors:
        lab = srgb_to_lab(rgb[opaque])
        chroma = np.hypot(lab[:, 1], lab[:, 2])
        vivid = rgb[opaque][chroma > 20]
        cols = kmeans_palette(vivid if len(vivid) else rgb[opaque], opts.n_colors)
        pal = [(f"Warna {i + 1}", tuple(int(c) for c in col)) for i, col in enumerate(cols)]
    else:
        pal = [(n, parse_hex(h)) for n, h in (opts.palette or DEFAULT_PALETTE)]
    # Tinta yang hampir sama dengan warna kaos tidak berguna (mis. hitam di kaos hitam).
    g_lab = srgb_to_lab(np.array(garment, dtype=np.float64))
    keep = []
    for name, col in pal:
        if np.linalg.norm(srgb_to_lab(np.array(col, dtype=np.float64)) - g_lab) >= 10:
            keep.append((name, col))
    return keep


def simulate(source, opts: SimOptions | None = None) -> Separation:
    opts = opts or SimOptions()
    if opts.method not in ("halftone", "index"):
        raise ValueError(f"Metode tidak dikenal: {opts.method!r}")
    rgb, opaque = _load(source, opts)
    h, w = opaque.shape
    garment = parse_hex(opts.garment)
    named = _palette(opts, rgb, opaque, garment)
    if not named:
        raise ValueError("Palet kosong setelah membuang tinta yang sama dengan warna kaos")

    # Putih ikut sebagai tinta di solver: putih yang terlihat = underbase terbuka + highlight.
    inks = np.array([c for _, c in named] + [WHITE], dtype=np.float32)
    lut = coverage_lut(garment, inks, opts.iters, opts.space)
    q = (rgb >> 2).astype(np.intp)
    cov = lut[q[..., 0], q[..., 1], q[..., 2]]
    cov[~opaque] = 0

    # Pixel yang hampir sama dengan kaos -> tanpa tinta.
    g64 = np.arange(64) * 4 + 1.5
    lab_lut = srgb_to_lab(np.stack(np.meshgrid(g64, g64, g64, indexing="ij"), axis=-1)).astype(np.float32)
    lab = lab_lut[q[..., 0], q[..., 1], q[..., 2]]
    near_garment = np.linalg.norm(lab - srgb_to_lab(np.array(garment, dtype=np.float64)), axis=-1) < 8
    cov[near_garment] = 0

    tones = [_blur3(cov[..., i]) for i in range(cov.shape[-1])]
    white = tones.pop()

    # Highlight white: area terang & netral; knockout warna di bawahnya.
    hl = np.zeros_like(white)
    if opts.highlight:
        chroma = np.hypot(lab[..., 1], lab[..., 2])
        # Hanya putih netral; makin berwarna makin kecil supaya warna pucat (krem, kuning muda) tidak hilang.
        hl = white * np.clip((lab[..., 0] - 85) / 15, 0, 1) * np.clip(1 - chroma / 15, 0, 1)
        hl = _erode(hl, 1)
        tones = [t * (1 - 0.8 * hl) for t in tones]

    # Underbase: di bawah semua tinta terang + putih yang terlihat.
    lights = [t for t, (_, c) in zip(tones, named) if lightness(c) > 25]
    base = np.clip(sum(lights, np.zeros_like(white)) + white, 0, 1)
    base = _s_curve(base)
    for t, (_, c) in zip(tones, named):
        if _needs_boost(c):
            base = np.clip(base + opts.red_blue_boost * t, 0, 1)
    base[base < opts.fringe] = 0
    base = _erode(base, opts.choke_px)

    def clean(t):
        t = np.where(opaque, t, 0).astype(np.float32)
        t[t < opts.min_density] = 0
        return t

    layers = [("Underbase", WHITE, clean(base), True, 156)]
    for (name, col), t in sorted(zip(named, tones), key=lambda nt: -lightness(nt[0][1])):
        layers.append((name, col, clean(t), False, None))
    if opts.highlight:
        layers.append(("Highlight Putih", WHITE, clean(hl), False, 230))
    layers = [l for l in layers if l[2].any()]

    angles = angles_for(len(layers), opts.angle_mode, opts.angle_start)
    if opts.method == "index":
        # Semua tinta atas + putih terbuka berbagi satu mask, jadi titik tidak bertumpuk. Underbase =
        # gabungan titik tinta terang + putih, sehingga putih tidak "bocor" di sela titik warna.
        has_base = bool(layers) and layers[0][3]
        top = layers[has_base:]
        open_white = clean(np.clip(white - hl, 0, 1))
        bits = index_halftone([l[2] for l in top] + [open_white], opts.grain_px)
        base_bits = bits.pop()
        for l, b in zip(top, bits):
            if lightness(l[1]) > 25:
                base_bits = base_bits | b
        if has_base:
            bits.insert(0, base_bits)
    else:
        bits = [am_halftone(l[2], opts.dpi, opts.lpi, a, opts.dot) for l, a in zip(layers, angles)]

    top_mesh = 305 if opts.method == "index" else _mesh_for_lpi(opts.lpi)
    channels = []
    for n, ((name, col, tone, is_base, mesh), ink, angle) in enumerate(zip(layers, bits, angles), 1):
        info = f"SIMULASI · index {opts.grain_px}px" if opts.method == "index" else f"SIMULASI · {opts.lpi:g} LPI · {angle:g}°"
        ch = Channel(
            name=name, rgb=tuple(int(c) for c in col), ink=ink,
            angle=None if opts.method == "index" else angle, is_underbase=is_base, tone=tone,
            meta={"urutan": n, "info": info, "mesh": mesh or top_mesh},
        )
        channels.append(ch)
    return Separation(channels, (w, h), opts.dpi, garment, opts)


def _needs_boost(rgb) -> bool:
    """Merah dan biru paling 'tenggelam' di kaos gelap -> butuh underbase lebih tebal."""
    L, a, b = srgb_to_lab(np.array(rgb, dtype=np.float64))
    hue = np.degrees(np.arctan2(b, a)) % 360
    chroma = np.hypot(a, b)
    return chroma > 30 and (hue < 50 or hue > 330 or 220 < hue < 320)


def _mesh_for_lpi(lpi: float) -> int:
    from .report import MESHES

    need = lpi * 4.5
    return next((m for m in MESHES if m >= need), MESHES[-1])


def tone_preview(sep: Separation) -> Image.Image:
    """Preview target model (sebelum halftone): tinta berdampingan, underbase terlihat hanya di luar warna.

    Hasil cetak sebenarnya (termasuk putih base yang mengintip di sela titik AM) ada di ``Separation.preview``.
    """
    w, h = sep.size
    space = getattr(sep.options, "space", "gamma")
    g = _encode(np.array(sep.garment), space)
    out = np.broadcast_to(g, (h, w, 3)).copy()
    tops = [ch for ch in sep.channels if ch.tone is not None and not ch.is_underbase]
    base = next((ch.tone for ch in sep.channels if ch.is_underbase and ch.tone is not None), np.zeros((h, w)))
    lights = sum((ch.tone for ch in tops if lightness(ch.rgb) > 25), np.zeros((h, w)))
    vis = [ch.tone for ch in tops] + [np.clip(base - lights, 0, 1)]
    cols = [ch.rgb for ch in tops] + [WHITE]
    total = np.maximum(sum(vis), 1)
    for t, c in zip(vis, cols):
        out += (t / total)[..., None] * (_encode(np.array(c), space) - g)
    return Image.fromarray(_decode(out, space).round().astype(np.uint8), "RGB")
