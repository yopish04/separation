"""CLI: `separation pisah ...` untuk separasi film, `separation harga ...` untuk kalkulasi harga."""

import argparse
import json
import sys
from pathlib import Path

from .film import save_films
from .quote import Costs, format_rp, price_breaks, quote
from .report import build_report, report_markdown
from .separate import Options, separate


def _cmd_pisah(a) -> int:
    opts = Options(
        n_colors=a.warna,
        colors=[c for c in a.palet.split(",") if c] if a.palet else None,
        garment=a.kaos,
        dpi=a.dpi,
        width_cm=a.lebar_cm,
        halftone=a.halftone,
        lpi=a.lpi,
        softness=a.softness,
        underbase={"auto": None, "ya": True, "tidak": False}[a.underbase],
        choke_px=a.choke,
        despeckle=a.despeckle,
    )
    sep = separate(a.input, opts)
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)

    files = save_films(sep, {}, out, mirror=a.mirror)
    preview = out / "preview.png"
    sep.preview().save(preview)
    rep = build_report(sep, prints=a.qty)
    (out / "laporan.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    md = report_markdown(rep)
    (out / "laporan.md").write_text(md)

    print(md)
    print("File:")
    for f in [*files, preview, out / "laporan.json", out / "laporan.md"]:
        print(f"  {f}")
    return 0


def _cmd_harga(a) -> int:
    costs = Costs.load(a.biaya) if a.biaya else Costs()
    colors = [int(x) for x in a.warna.split(",")]
    if a.json:
        data = quote(a.qty, colors, a.gelap, costs, not a.tanpa_kaos) if a.qty else price_breaks(colors, a.gelap, costs, include_garment=not a.tanpa_kaos)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    if a.qty:
        q = quote(a.qty, colors, a.gelap, costs, not a.tanpa_kaos)
        print(f"Order {q['qty']} pcs, {q['jumlah_screen']} screen")
        print(f"  Biaya setup      : {format_rp(q['biaya_setup'])}")
        for k, v in q["biaya_variabel_per_pcs"].items():
            print(f"  {k:<17}: {format_rp(v)}/pcs")
        print(f"  HPP              : {format_rp(q['hpp_per_pcs'])}/pcs")
        print(f"  Harga jual       : {format_rp(q['harga_jual_per_pcs'])}/pcs")
        print(f"  Total            : {format_rp(q['total_harga'])}")
        print(f"  Laba kotor       : {format_rp(q['laba_kotor'])}")
        return 0
    print(f"Daftar harga — {'+'.join(map(str, colors))} warna, kaos {'gelap' if a.gelap else 'terang'}")
    print(f"{'Qty':>6} | {'HPP/pcs':>12} | {'Harga/pcs':>12} | {'Total':>14}")
    for q in price_breaks(colors, a.gelap, costs, include_garment=not a.tanpa_kaos):
        print(f"{q['qty']:>6} | {format_rp(q['hpp_per_pcs']):>12} | {format_rp(q['harga_jual_per_pcs']):>12} | {format_rp(q['total_harga']):>14}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="separation", description="Alat bantu studio sablon kaos.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("pisah", help="Separasi warna desain menjadi film per screen")
    s.add_argument("input", help="File desain (PNG disarankan, transparan = tanpa tinta)")
    s.add_argument("-o", "--output", default="hasil_separasi")
    s.add_argument("-n", "--warna", type=int, default=4, help="Jumlah warna spot (k-means)")
    s.add_argument("--palet", help="Palet manual, mis. '#ffffff,#d62828,#003049'")
    s.add_argument("--kaos", help="Warna kaos hex, mis. '#111111'")
    s.add_argument("--dpi", type=float, default=300)
    s.add_argument("--lebar-cm", type=float, help="Resize desain ke lebar cetak (cm)")
    s.add_argument("--halftone", action="store_true", help="Pakai halftone untuk gradasi")
    s.add_argument("--lpi", type=float, default=45)
    s.add_argument("--softness", type=float, default=12, help="Kelembutan transisi warna (Delta-E)")
    s.add_argument("--underbase", choices=["auto", "ya", "tidak"], default="auto")
    s.add_argument("--choke", type=int, default=2, help="Choke underbase (piksel)")
    s.add_argument("--despeckle", type=int, default=0, help="Median filter untuk bersihkan noise (3/5/7)")
    s.add_argument("--mirror", action="store_true", help="Cetak film terbalik (emulsi-down)")
    s.add_argument("--qty", type=int, default=1, help="Jumlah cetak untuk estimasi tinta")
    s.set_defaults(func=_cmd_pisah)

    h = sub.add_parser("harga", help="Hitung HPP dan harga jual")
    h.add_argument("--warna", default="1", help="Warna per lokasi, mis. '4,1' (depan 4, belakang 1)")
    h.add_argument("--qty", type=int, help="Jumlah order; kosongkan untuk tabel harga bertingkat")
    h.add_argument("--gelap", action="store_true", help="Kaos gelap (tambah underbase + flash)")
    h.add_argument("--tanpa-kaos", action="store_true", help="Kaos dari customer (jasa sablon saja)")
    h.add_argument("--biaya", help="File JSON biaya studio (lihat contoh/biaya.json)")
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=_cmd_harga)

    a = p.parse_args(argv)
    try:
        return a.func(a)
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
