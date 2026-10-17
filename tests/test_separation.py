import numpy as np
import pytest
from PIL import Image, ImageDraw

from separation.cli import main
from separation.color import parse_hex, srgb_to_lab, to_hex
from separation.halftone import am_halftone
from separation.quote import Costs, quote
from separation.report import build_report
from separation.separate import Options, separate


def _design():
    img = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 90, 90], fill=(220, 30, 30, 255))
    d.rectangle([110, 10, 190, 90], fill=(20, 40, 200, 255))
    return img


def test_hex_roundtrip():
    assert parse_hex("#f80") == (255, 136, 0)
    assert to_hex(parse_hex("1a2b3c")) == "#1a2b3c"
    with pytest.raises(ValueError):
        parse_hex("#12345")


def test_lab_white_black():
    lab = srgb_to_lab(np.array([[255, 255, 255], [0, 0, 0]]))
    assert lab[0, 0] == pytest.approx(100, abs=0.1)
    assert lab[1, 0] == pytest.approx(0, abs=0.1)


def test_spot_separation_light_garment():
    sep = separate(_design(), Options(n_colors=2, garment="#ffffff"))
    assert len(sep.channels) == 2
    assert not any(c.is_underbase for c in sep.channels)
    for ch in sep.channels:
        assert ch.coverage == pytest.approx(81 * 81 / (200 * 100), rel=0.02)
    # Tidak ada tumpang tindih antar warna spot solid.
    assert not (sep.channels[0].ink & sep.channels[1].ink).any()


def test_underbase_auto_on_dark_garment_is_choked():
    sep = separate(_design(), Options(n_colors=2, garment="#101010", choke_px=2))
    base = sep.channels[0]
    assert base.is_underbase and base.meta["urutan"] == 1
    colors = sep.channels[1].ink | sep.channels[2].ink
    assert not (base.ink & ~colors).any()  # underbase tidak keluar dari area warna
    assert base.ink.sum() < colors.sum()


def test_manual_palette_and_garment_knockout():
    img = _design()
    sep = separate(img, Options(colors=["#dc1e1e"], garment="#1428c8", underbase=False))
    assert len(sep.channels) == 1
    assert sep.channels[0].ink[:, 100:].sum() == 0  # biru = warna kaos, tidak dicetak


def test_halftone_coverage_tracks_tone():
    for tone in (0.25, 0.5, 0.75):
        ink = am_halftone(np.full((300, 300), tone), dpi=300, lpi=30, angle_deg=22.5)
        assert ink.mean() == pytest.approx(tone, abs=0.08)


def test_report_and_quote():
    sep = separate(_design(), Options(n_colors=2, garment="#000000", dpi=100))
    rep = build_report(sep, prints=10)
    assert rep["jumlah_screen"] == 3
    assert rep["channel"][0]["mesh_T_per_inch"] == 110

    small, big = quote(12, [2], True), quote(500, [2], True)
    assert small["jumlah_screen"] == 3
    assert big["hpp_per_pcs"] < small["hpp_per_pcs"]
    assert small["harga_jual_per_pcs"] % 500 == 0
    assert quote(12, [2], costs=Costs(kaos=0), include_garment=False)["biaya_variabel_per_pcs"]["kaos"] == 0


def test_cli_end_to_end(tmp_path):
    src = tmp_path / "d.png"
    _design().save(src)
    out = tmp_path / "out"
    assert main(["pisah", str(src), "-n", "2", "--kaos", "#000000", "--halftone", "-o", str(out)]) == 0
    assert (out / "films.pdf").exists() and (out / "preview.png").exists()
    assert len(list(out.glob("film_*.png"))) == 3
    assert main(["harga", "--warna", "2,1", "--qty", "24"]) == 0
