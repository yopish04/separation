"""Output film positif (hitam = tinta) dengan register mark dan label."""

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .separate import Channel, Separation


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _reg_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, width: int) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, width=width)
    draw.line([cx - 2 * r, cy, cx + 2 * r, cy], fill=0, width=width)
    draw.line([cx, cy - 2 * r, cx, cy + 2 * r], fill=0, width=width)


def render_film(sep: Separation, ch: Channel, mirror: bool = False, label: str = "") -> Image.Image:
    w, h = sep.size
    mm = sep.dpi / 25.4
    margin = int(20 * mm)
    r = max(4, int(2.5 * mm))
    stroke = max(1, int(0.25 * mm))

    film = Image.new("L", (w + 2 * margin, h + 2 * margin), 255)
    art = Image.fromarray(np.where(ch.ink, 0, 255).astype(np.uint8), "L")
    film.paste(art, (margin, margin))

    draw = ImageDraw.Draw(film)
    W, H = film.size
    for cx, cy in [(W // 2, margin // 2), (W // 2, H - margin // 2), (margin // 2, H // 2), (W - margin // 2, H // 2)]:
        _reg_mark(draw, cx, cy, r, stroke)

    if mirror:
        film = ImageOps.mirror(film)
        draw = ImageDraw.Draw(film)

    font = _font(max(10, int(3 * mm)))
    text = label or f"{ch.meta.get('urutan', '?')}. {ch.name} {ch.hex}"
    if not label and ch.meta.get("info"):
        text += f" · {ch.meta['info']}"
    draw.text((margin, int(margin * 0.15)), text, fill=0, font=font)
    return film


def save_films(sep: Separation, labels: dict[int, str], out_dir, mirror: bool = False) -> list:
    out = []
    pages = []
    for i, ch in enumerate(sep.channels):
        film = render_film(sep, ch, mirror=mirror, label=labels.get(i, ""))
        path = out_dir / f"film_{ch.meta['urutan']:02d}_{ch.name.lower().replace(' ', '_')}.png"
        film.save(path, dpi=(sep.dpi, sep.dpi))
        out.append(path)
        pages.append(film.convert("1"))
        if ch.tone is not None:
            # Channel grayscale (hitam = tinta) untuk diedit di Photoshop/GIMP sebelum di-halftone ulang.
            tone = Image.fromarray((255 - np.clip(ch.tone, 0, 1) * 255).round().astype(np.uint8), "L")
            tpath = out_dir / f"tone_{ch.meta['urutan']:02d}_{ch.name.lower().replace(' ', '_')}.png"
            tone.save(tpath, dpi=(sep.dpi, sep.dpi))
            out.append(tpath)
    if pages:
        pdf = out_dir / "films.pdf"
        pages[0].save(pdf, save_all=True, append_images=pages[1:], resolution=sep.dpi)
        out.append(pdf)
    return out
