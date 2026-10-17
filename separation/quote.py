"""Kalkulator HPP dan harga jual order sablon (Rupiah)."""

import json
from dataclasses import asdict, dataclass, fields


@dataclass
class Costs:
    """Biaya dasar studio. Ubah lewat file JSON sesuai harga lokal."""

    kaos: float = 45000  # harga kaos polos per pcs
    screen_per_warna: float = 60000  # afdruk: emulsi, exposure, cuci (per screen per job)
    film_per_warna: float = 15000
    setup_per_warna: float = 25000  # registrasi, tes cetak
    tinta_per_kg: float = 220000
    gram_tinta_per_warna: float = 4.0  # per pcs per lokasi cetak
    upah_per_tarikan: float = 1200  # upah operator per pcs per warna
    flash_per_pcs: float = 500  # listrik flash/curing untuk underbase
    curing_per_pcs: float = 700
    packing_per_pcs: float = 1500
    overhead_persen: float = 10.0  # sewa, listrik, penyusutan alat
    margin_persen: float = 30.0
    reject_persen: float = 3.0  # cadangan kaos gagal cetak

    @classmethod
    def load(cls, path) -> "Costs":
        with open(path) as f:
            data = json.load(f)
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Field tidak dikenal di {path}: {', '.join(sorted(unknown))}")
        return cls(**data)


def quote(qty: int, colors: list[int], dark_garment: bool = False, costs: Costs | None = None, include_garment: bool = True) -> dict:
    """colors: jumlah warna per lokasi cetak, mis. [4, 1] = depan 4 warna, belakang 1 warna."""
    if qty <= 0:
        raise ValueError("qty harus > 0")
    c = costs or Costs()
    screens = sum(n + (1 if dark_garment else 0) for n in colors)
    pulls = screens  # tarikan per pcs (underbase dihitung satu tarikan)

    setup = screens * (c.screen_per_warna + c.film_per_warna + c.setup_per_warna)
    per_pcs = {
        "kaos": c.kaos * (1 + c.reject_persen / 100) if include_garment else 0.0,
        "tinta": pulls * c.gram_tinta_per_warna * c.tinta_per_kg / 1000,
        "upah": pulls * c.upah_per_tarikan,
        "flash": c.flash_per_pcs * len(colors) if dark_garment else 0.0,
        "curing": c.curing_per_pcs,
        "packing": c.packing_per_pcs,
    }
    variable = sum(per_pcs.values())
    hpp = (variable + setup / qty) * (1 + c.overhead_persen / 100)
    price = hpp * (1 + c.margin_persen / 100)
    price = -(-price // 500) * 500  # bulatkan ke atas kelipatan Rp500
    return {
        "qty": qty,
        "jumlah_screen": screens,
        "biaya_setup": round(setup),
        "biaya_variabel_per_pcs": {k: round(v) for k, v in per_pcs.items()},
        "hpp_per_pcs": round(hpp),
        "harga_jual_per_pcs": int(price),
        "total_harga": int(price * qty),
        "laba_kotor": round((price - hpp) * qty),
        "asumsi": asdict(c),
    }


def price_breaks(colors: list[int], dark_garment: bool = False, costs: Costs | None = None,
                 tiers=(12, 24, 48, 72, 100, 250, 500), include_garment: bool = True) -> list[dict]:
    return [quote(q, colors, dark_garment, costs, include_garment) for q in tiers]


def format_rp(x: float) -> str:
    return "Rp" + f"{x:,.0f}".replace(",", ".")
