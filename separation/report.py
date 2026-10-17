"""Rekomendasi mesh, estimasi tinta, dan laporan job separasi."""

from .separate import Channel, Separation

MESHES = [110, 125, 156, 180, 200, 230, 305]  # T/inch yang umum di pasaran

# Perkiraan deposit tinta plastisol per cm² area tinta, per mesh (gram).
# Angka kasar dari praktik lapangan; kalibrasi dengan menimbang tinta di studio sendiri.
_DEPOSIT_G_PER_CM2 = {110: 0.0060, 125: 0.0052, 156: 0.0042, 180: 0.0036, 200: 0.0032, 230: 0.0028, 305: 0.0020}


def recommend_mesh(ch: Channel, halftone: bool, lpi: float) -> int:
    if ch.is_underbase:
        return 156 if halftone else 110
    if halftone:
        # Patokan: mesh minimal ~4,5x LPI supaya titik halftone tidak hilang di benang.
        need = lpi * 4.5
        return next((m for m in MESHES if m >= need), MESHES[-1])
    return 156


def build_report(sep: Separation, prints: int = 1) -> dict:
    o = sep.options
    w_cm = sep.size[0] / sep.dpi * 2.54
    h_cm = sep.size[1] / sep.dpi * 2.54
    rows = []
    for ch in sep.channels:
        mesh = recommend_mesh(ch, o.halftone, o.lpi)
        area = sep.area_cm2(ch)
        grams = area * _DEPOSIT_G_PER_CM2[mesh]
        rows.append(
            {
                "urutan": ch.meta["urutan"],
                "nama": ch.name,
                "hex": ch.hex,
                "underbase": ch.is_underbase,
                "coverage_persen": round(ch.coverage * 100, 1),
                "area_cm2": round(area, 1),
                "mesh_T_per_inch": mesh,
                "sudut_halftone": ch.angle,
                "tinta_gram_per_pcs": round(grams, 2),
                "tinta_gram_total": round(grams * prints * 1.15, 1),  # +15% sisa di screen/rakel
                "flash_sesudahnya": ch.is_underbase,
            }
        )
    return {
        "ukuran_cetak_cm": [round(w_cm, 1), round(h_cm, 1)],
        "dpi": sep.dpi,
        "warna_kaos": None if sep.garment is None else "#%02x%02x%02x" % sep.garment,
        "mode": f"halftone {o.lpi:g} LPI" if o.halftone else "spot solid",
        "jumlah_screen": len(sep.channels),
        "jumlah_cetak": prints,
        "channel": rows,
    }


def report_markdown(rep: dict) -> str:
    lines = [
        "# Lembar Kerja Separasi",
        "",
        f"- Ukuran cetak: **{rep['ukuran_cetak_cm'][0]} x {rep['ukuran_cetak_cm'][1]} cm** @ {rep['dpi']:g} dpi",
        f"- Warna kaos: {rep['warna_kaos'] or '-'}",
        f"- Mode: {rep['mode']}",
        f"- Jumlah screen: **{rep['jumlah_screen']}**, jumlah cetak: {rep['jumlah_cetak']} pcs",
        "",
        "| # | Channel | Hex | Mesh | Sudut | Coverage | Area cm² | Tinta g/pcs | Tinta total g |",
        "|---|---------|-----|------|-------|----------|----------|-------------|---------------|",
    ]
    for r in rep["channel"]:
        name = r["nama"] + (" → FLASH" if r["flash_sesudahnya"] else "")
        angle = "-" if r["sudut_halftone"] is None else f"{r['sudut_halftone']:g}°"
        lines.append(
            f"| {r['urutan']} | {name} | `{r['hex']}` | {r['mesh_T_per_inch']}T | {angle} | "
            f"{r['coverage_persen']}% | {r['area_cm2']} | {r['tinta_gram_per_pcs']} | {r['tinta_gram_total']} |"
        )
    lines += [
        "",
        "Catatan:",
        "- Estimasi tinta untuk plastisol, sudah termasuk +15% sisa di screen. Kalibrasi dengan data studio.",
        "- Cek register mark di keempat sisi film sebelum exposure.",
        "- Urutan cetak adalah saran; sesuaikan dengan tinta (wet-on-wet) dan mesin.",
    ]
    return "\n".join(lines) + "\n"
