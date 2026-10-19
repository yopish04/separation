import numpy as np
import pytest
from PIL import Image

from separation.cli import main
from separation.color import parse_hex, srgb_to_lab
from separation.halftone import am_halftone, angles_for, fm_halftone, index_halftone
from separation.simprocess import (
    DEFAULT_PALETTE, WHITE, SimOptions, reconstruct, simulate, solve_coverage, tone_preview,
)


def _gradient(w=240, h=120):
    """Hitam -> merah -> kuning -> putih secara horizontal, di atas kaos hitam."""
    stops = np.array([[0, 0, 0], [208, 32, 46], [246, 199, 0], [255, 255, 255]], dtype=np.float64)
    x = np.linspace(0, len(stops) - 1, w)
    i = np.minimum(x.astype(int), len(stops) - 2)
    f = (x - i)[:, None]
    row = stops[i] * (1 - f) + stops[i + 1] * f
    return Image.fromarray(np.broadcast_to(row, (h, w, 3)).round().astype(np.uint8), "RGB")


def _inks():
    return np.array([parse_hex(h) for _, h in DEFAULT_PALETTE] + [WHITE], dtype=np.float32)


def test_solver_constraints_and_accuracy():
    rng = np.random.default_rng(1)
    inks = _inks()
    # Target dibuat dari campuran tinta yang valid, jadi solver harus bisa menemukannya kembali.
    true = rng.dirichlet(np.ones(len(inks) + 1), size=500)[:, :-1].astype(np.float32)
    target = reconstruct(true, (0, 0, 0), inks)
    d = solve_coverage(target, (0, 0, 0), inks, iters=200)
    assert d.min() >= 0 and d.max() <= 1 + 1e-6
    assert (d.sum(1) <= 1 + 1e-5).all()
    de = np.linalg.norm(srgb_to_lab(reconstruct(d, (0, 0, 0), inks)) - srgb_to_lab(target), axis=-1)
    assert de.mean() < 1.5


def test_gradient_tone_preview_is_close():
    img = _gradient()
    sep = simulate(img, SimOptions(dpi=150, lpi=30))
    de = np.linalg.norm(srgb_to_lab(np.array(img)) - srgb_to_lab(np.array(tone_preview(sep))), axis=-1)
    assert de.mean() < 10
    names = [c.name for c in sep.channels]
    assert names[0] == "Underbase" and names[-1] == "Highlight Putih"
    assert "Hitam" not in names  # tinta hampir sama dengan kaos hitam dibuang


def test_garment_area_gets_no_ink():
    img = Image.new("RGB", (80, 40), (0, 0, 0))
    img.paste((255, 255, 255), (40, 0, 80, 40))
    sep = simulate(img, SimOptions(dpi=150, lpi=30))
    for ch in sep.channels:
        assert not ch.ink[:, :38].any(), ch.name
    hl = next(c for c in sep.channels if c.name == "Highlight Putih")
    base = sep.channels[0]
    assert hl.tone[:, 45:75].mean() > 0.8 and base.tone[:, 45:75].mean() > 0.8
    for ch in sep.channels[1:-1]:  # warna di bawah highlight di-knockout
        assert ch.tone[:, 45:75].max() < 0.3


def test_underbase_choked_and_fringe_removed():
    img = Image.new("RGB", (100, 60), (0, 0, 0))
    img.paste((240, 220, 180), (30, 15, 70, 45))
    sep = simulate(img, SimOptions(dpi=150, lpi=30, choke_px=2))
    base = sep.channels[0].tone
    assert base[:, :29].max() == 0 and base[:, 72:].max() == 0
    nz = base[base > 0]
    assert nz.min() >= 0.05


def test_alpha_is_no_ink():
    img = _gradient().convert("RGBA")
    a = np.array(img)
    a[:, :120, 3] = 0
    sep = simulate(Image.fromarray(a), SimOptions(dpi=150, lpi=30))
    assert all(not ch.ink[:, :118].any() for ch in sep.channels)


def test_angles():
    assert angles_for(5, "bertingkat", 23) == [23, 53, 83, 113, 143]
    assert angles_for(3, "sama", 22.5) == [22.5] * 3
    with pytest.raises(ValueError):
        angles_for(2, "acak")


@pytest.mark.parametrize("dot", ["bulat", "elips"])
def test_am_and_fm_coverage_linear(dot):
    for tone in (0.1, 0.5, 0.9):
        flat = np.full((240, 240), tone)
        assert am_halftone(flat, 300, 55, 22.5, dot).mean() == pytest.approx(tone, abs=0.03)
        assert fm_halftone(flat).mean() == pytest.approx(tone, abs=0.03)


def test_index_channels_do_not_overlap():
    a, b = np.full((128, 128), 0.3), np.full((128, 128), 0.5)
    ia, ib = index_halftone([a, b])
    assert not (ia & ib).any()
    assert ia.mean() == pytest.approx(0.3, abs=0.03) and ib.mean() == pytest.approx(0.5, abs=0.03)


def test_auto_palette():
    sep = simulate(_gradient(), SimOptions(n_colors=2, dpi=150, lpi=30))
    assert sum(not c.is_underbase and c.name.startswith("Warna") for c in sep.channels) >= 1


def test_cli_simulasi(tmp_path):
    src = tmp_path / "foto.png"
    _gradient().save(src)
    out = tmp_path / "out"
    args = ["simulasi", str(src), "--dpi", "150", "--lpi", "30", "--sudut", "bertingkat", "-o", str(out)]
    assert main(args) == 0
    films = sorted(out.glob("film_*.png"))
    assert len(films) == len(list(out.glob("tone_*.png"))) >= 4
    for name in ("films.pdf", "preview.png", "preview_tone.png", "laporan.md"):
        assert (out / name).exists()
    assert "simulated process" in (out / "laporan.md").read_text()

    out2 = tmp_path / "idx"
    assert main(["simulasi", str(src), "--dpi", "150", "--metode", "index",
                 "--palet", "Merah=#d0202e,#f6c700", "-o", str(out2)]) == 0
    assert (out2 / "film_02_kuning.png").exists() or (out2 / "film_02_warna_2.png").exists()


def test_index_base_is_union_of_light_inks():
    img = _gradient(480, 240)
    sep = simulate(img, SimOptions(method="index", dpi=300))
    base = sep.channels[0]
    assert base.is_underbase
    tops = [c for c in sep.channels[1:]]
    for i, a in enumerate(tops):  # titik warna atas tidak bertumpuk
        for b in tops[i + 1:]:
            assert not (a.ink & b.ink).any()
    light = np.zeros_like(base.ink)
    for c in tops:
        light |= c.ink
    assert not (light & ~base.ink).any()  # semua tinta terang punya base di bawahnya
    # Dilihat dari jauh (rata-rata blok 12 px) hasil cetak mendekati aslinya.
    f = 12
    a = np.asarray(sep.preview(), np.float32).reshape(20, f, 40, f, 3).mean((1, 3))
    o = np.asarray(img, np.float32).reshape(20, f, 40, f, 3).mean((1, 3))
    assert np.linalg.norm(srgb_to_lab(a) - srgb_to_lab(o), axis=-1).mean() < 6
