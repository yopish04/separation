# separation

Alat bantu studio sablon kaos (screenprinting): **separasi warna → film per screen**, underbase otomatis
untuk kaos gelap, halftone, lembar kerja (mesh, urutan cetak, estimasi tinta), dan **kalkulator HPP/harga jual**.

## Instalasi

```bash
pip install -e .[dev]
```

Butuh Python 3.10+, numpy, Pillow.

## 1. Separasi warna (`pisah`)

```bash
# Desain 3 warna untuk kaos hitam, lebar cetak 28 cm
separation pisah desain.png -n 3 --kaos "#111111" --lebar-cm 28 -o job_001

# Palet manual (warna tinta yang sudah ada di rak)
separation pisah desain.png --palet "#ffffff,#d62828,#fcbf49" --kaos "#000000"

# Desain bergradasi -> halftone 45 LPI
separation pisah desain.png -n 4 --kaos "#1a1a1a" --halftone --lpi 45
```

Output di folder `-o`:

| File | Isi |
|------|-----|
| `film_01_underbase.png`, `film_02_...png` | Film positif per screen (hitam = tinta), 300 dpi, dengan register mark di 4 sisi dan label urutan/warna |
| `films.pdf` | Semua film dalam satu PDF, siap cetak di printer film/inkjet transparan |
| `preview.png` | Simulasi hasil cetak di atas warna kaos |
| `laporan.md` / `laporan.json` | Lembar kerja: urutan cetak, mesh, sudut halftone, coverage, area, estimasi tinta |

Cara kerja singkat:

- **Palet**: k-means di ruang warna CIELAB (lebih mirip persepsi mata) atau palet manual `--palet`.
- **Warna kaos** (`--kaos`): area yang warnanya senada dengan kaos tidak dicetak (hemat tinta & screen).
- **Underbase**: otomatis aktif kalau kaos gelap; di-*choke* (`--choke`, piksel) supaya putih tidak keluar dari tepi warna. Paksa dengan `--underbase ya|tidak`.
- **Halftone**: titik bulat AM, sudut screen berbeda per warna untuk menghindari moiré.
- **Mesh**: underbase 110T (156T kalau halftone), warna solid 156T, halftone ≥ 4,5 × LPI.
- **Transparansi PNG** = tanpa tinta. Gunakan desain di resolusi cetak, atau `--lebar-cm` untuk resize.
- `--mirror` untuk film emulsi-down, `--despeckle 3` untuk membersihkan noise JPEG.

## 2. Kalkulator harga (`harga`)

```bash
# Tabel harga bertingkat: depan 3 warna + belakang 1 warna, kaos gelap
separation harga --warna 3,1 --gelap

# Satu order 48 pcs, rincian HPP
separation harga --warna 3 --gelap --qty 48

# Jasa sablon saja (kaos dari customer), biaya studio sendiri
separation harga --warna 2 --qty 100 --tanpa-kaos --biaya contoh/biaya.json
```

Edit `contoh/biaya.json` dengan harga lokal Anda (kaos, afdruk screen, film, tinta/kg, upah per tarikan,
overhead, margin, persentase reject). Harga jual dibulatkan ke atas kelipatan Rp500.

## Tes

```bash
pytest
```

## Catatan

Estimasi tinta dan deposit per mesh adalah angka awal. Kalibrasi dengan menimbang tinta sebelum/sesudah
satu run produksi di studio Anda, lalu sesuaikan `_DEPOSIT_G_PER_CM2` di `separation/report.py`.
