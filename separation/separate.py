"""Pipeline separasi: gambar desain -> channel tinta per warna spot (+ underbase)."""

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter

from .color import lightness, parse_hex, to_hex
from .halftone import DEFAULT_ANGLES, am_halftone
from .palette import assign, kmeans_palette


@dataclass
class Options:
    n_colors: int = 4
    colors: list[str] | None = None  # palet manual (hex); kalau None pakai k-means
    garment: str | None = None  # warna kaos; area senada tidak diberi tinta
    dpi: float = 300.0
    width_cm: float | None = None  # resample desain ke lebar cetak ini
    halftone: bool = False
    lpi: float = 45.0
    softness: float = 12.0  # Delta-E; hanya dipakai saat halftone
    underbase: bool | None = None  # None = otomatis (kaos gelap)
    choke_px: int = 2
    despeckle: int = 0  # ukuran median filter (ganjil), 0 = mati
    alpha_threshold: int = 128


@dataclass
class Channel:
    name: str
    rgb: tuple[int, int, int]
    ink: np.ndarray  # bool (H, W), True = area tinta
    angle: float | None = None
    is_underbase: bool = False
    meta: dict = field(default_factory=dict)
    tone: np.ndarray | None = None  # float (H, W) 0..1 sebelum halftone (simulated process)

    @property
    def hex(self) -> str:
        return to_hex(self.rgb)

    @property
    def coverage(self) -> float:
        return float(self.ink.mean())


@dataclass
class Separation:
    channels: list[Channel]
    size: tuple[int, int]  # (W, H) piksel
    dpi: float
    garment: tuple[int, int, int] | None
    options: Options

    def area_cm2(self, ch: Channel) -> float:
        px_cm = self.dpi / 2.54
        return float(ch.ink.sum()) / (px_cm**2)

    def preview(self) -> Image.Image:
        """Simulasi hasil cetak di atas kaos."""
        w, h = self.size
        base = np.array(self.garment if self.garment else (255, 255, 255), dtype=np.uint8)
        out = np.broadcast_to(base, (h, w, 3)).copy()
        # Dicat sesuai urutan cetak; underbase yang tidak tertutup warna lain ikut terlihat putih.
        for ch in self.channels:
            out[ch.ink] = ch.rgb
        return Image.fromarray(out, "RGB")


def _load(path_or_image, opts: Options) -> tuple[np.ndarray, np.ndarray]:
    img = path_or_image if isinstance(path_or_image, Image.Image) else Image.open(path_or_image)
    img = img.convert("RGBA")
    if opts.width_cm:
        target_w = max(1, round(opts.width_cm / 2.54 * opts.dpi))
        target_h = max(1, round(img.height * target_w / img.width))
        img = img.resize((target_w, target_h), Image.LANCZOS)
    if opts.despeckle and opts.despeckle >= 3:
        size = opts.despeckle | 1
        rgb = img.convert("RGB").filter(ImageFilter.MedianFilter(size))
        img = Image.merge("RGBA", (*rgb.split(), img.getchannel("A")))
    arr = np.array(img)
    return arr[..., :3], arr[..., 3] >= opts.alpha_threshold


def _choke(mask: np.ndarray, px: int) -> np.ndarray:
    """Kecilkan area tinta sebanyak px piksel (biar underbase tidak 'nongol')."""
    if px <= 0:
        return mask
    img = Image.fromarray(mask.astype(np.uint8) * 255, "L")
    return np.array(img.filter(ImageFilter.MinFilter(2 * px + 1))) > 127


def _name(rgb, n: int) -> str:
    L = lightness(rgb)
    if L > 95:
        return "Highlight Putih"
    if L < 12:
        return "Hitam"
    return f"Warna {n}"


def is_dark(rgb) -> bool:
    return lightness(rgb) < 55


def separate(source, opts: Options | None = None) -> Separation:
    opts = opts or Options()
    rgb, opaque = _load(source, opts)
    h, w = opaque.shape
    garment = parse_hex(opts.garment) if opts.garment else None

    if opts.colors:
        palette = np.array([parse_hex(c) for c in opts.colors], dtype=np.float64)
    else:
        palette = kmeans_palette(rgb[opaque], opts.n_colors)

    # Warna kaos ikut jadi kandidat, tapi artinya "tanpa tinta" (kaos terlihat).
    full = np.vstack([palette, [garment]]) if garment else palette
    weights = assign(rgb, full, opts.softness if opts.halftone else 0.0)
    weights[~opaque] = 0.0

    angles = iter(DEFAULT_ANGLES * 4)
    channels = []
    for i, color in enumerate(palette):
        cov = weights[..., i]
        angle = next(angles) if opts.halftone else None
        ink = am_halftone(cov, opts.dpi, opts.lpi, angle) if opts.halftone else cov > 0.5
        if not ink.any():
            continue
        rgb_t = tuple(int(c) for c in color)
        channels.append(Channel(name=_name(rgb_t, len(channels) + 1), rgb=rgb_t, ink=ink, angle=angle))

    want_base = opts.underbase if opts.underbase is not None else bool(garment and is_dark(garment))
    if want_base and channels:
        ink_cov = weights[..., : len(palette)].sum(-1).clip(0, 1)
        if opts.halftone:
            base = am_halftone(ink_cov, opts.dpi, opts.lpi, 0.0) | (ink_cov > 0.5)
        else:
            base = ink_cov > 0.5
        base = _choke(base, opts.choke_px)
        channels.insert(0, Channel("Underbase", (255, 255, 255), base, is_underbase=True))

    _order(channels)
    return Separation(channels, (w, h), opts.dpi, garment, opts)


def _order(channels: list[Channel]) -> None:
    """Urutan cetak saran: underbase -> warna terang ke gelap.

    Putih (highlight) yang bukan underbase ditaruh paling akhir agar tajam.
    """
    def key(ch: Channel):
        if ch.is_underbase:
            return (0, 0)
        L = lightness(ch.rgb)
        if L > 95:
            return (2, 0)
        return (1, -L)

    channels.sort(key=key)
    for n, ch in enumerate(channels, 1):
        ch.meta["urutan"] = n
