# separation

Alat bantu studio sablon kaos (screenprinting): **separasi warna → film per screen**, **simulated process** untuk foto di kaos gelap, underbase otomatis
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

## 2. Simulated process (`simulasi`) — foto/gradasi di kaos gelap

```bash
# Default: base putih + merah, kuning, cyan, hitam bayangan, highlight putih; 55 LPI, sudut bertingkat 30°
separation simulasi foto.png --kaos "#000000" --lebar-cm 30 -o job_joker

# Sudut sama untuk semua film (gaya UltraSeps), titik bulat
separation simulasi foto.png --sudut sama --sudut-awal 22.5 --dot bulat

# Index separation (titik persegi FM, tidak bertumpuk, tanpa moiré)
separation simulasi foto.png --metode index --grain 2

# Palet tinta sendiri, atau pilih otomatis N warna dari gambar
separation simulasi foto.png --palet "Merah=#c8102e,Kuning=#ffcd00,Biru=#0057b8,Krem=#f1d6b8"
separation simulasi foto.png -n 5
```

Output: `film_XX_*.png` dan `films.pdf` (halftone siap cetak), `tone_XX_*.png` (channel grayscale untuk
diedit dulu di Photoshop/GIMP, hitam = tinta), `preview.png` (simulasi titik di kaos), `preview_tone.png`
(target warna sebelum halftone), dan `laporan.md`/`.json`.

Cara kerja:

1. **Coverage tinta per piksel** dicari dengan *least squares* terbatas (FISTA): warna cetak = campuran luas
   kaos dan tinta, `(1 − Σd)·kaos + Σ dᵢ·tintaᵢ`, dengan `dᵢ ≥ 0` dan `Σd ≤ 1`. Putih ikut jadi "tinta".
   Default-nya dihitung di ruang gamma (seperti channel Photoshop), karena di ruang linear detail bayangan
   hilang. Solver dijalankan sekali untuk tabel 64³ warna, jadi film 30×45 cm @ 300 dpi selesai < 1 menit.
2. **Underbase** = luas tinta terang + putih terbuka, kurva S, dipertebal di bawah merah/biru, fringe < 6%
   dibuang, lalu di-choke. Di mode index, base = gabungan titik tinta terang + putih (tidak bocor).
3. **Highlight putih** hanya di area paling terang dan netral (L* > 85, makin berwarna makin tipis);
   warna di bawahnya di-knockout.
4. **Halftone**: AM bulat/elips dengan luas titik linear terhadap tone (10% tone = 10% tinta), sudut sama
   atau bertingkat. Mode index memakai satu mask blue-noise untuk semua warna.
5. Tinta yang hampir sama dengan warna kaos dibuang otomatis (mis. hitam di kaos hitam).

Mesh otomatis: warna atas ≥ 4,5 × LPI (55 LPI → 305T), underbase 156T, highlight 230T, index 305T.

**AM vs index.** Di AM, titik base dan titik warna tidak sejajar, jadi putih base ikut terlihat di sela
titik warna dan midtone gelap jadi lebih pucat. `preview.png` menampilkan efek ini apa adanya. Pada gambar
uji, rata-rata ΔE preview terhadap asli: AM ≈ 6–11, index ≈ 4–5. Untuk foto dengan banyak midtone gelap,
coba mode index atau turunkan channel base di `tone_01_underbase.png` dengan Curves.

### Referensi yang dipakai

- Metode underbase dan simulated process Scott Fresener (T-Biz Network, *Simulated Process Color
  Separations – Part One/Two*), dan T-Seps.
- UltraSeps: *film positive output settings* (55 LPI, titik elips, sudut sama, mesh per channel) dan
  *Deleting Fringe Pixels From White Underbase*.
- Diskusi praktisi TheShirtBoard tentang index vs stochastic vs halftone.
- [serigraphie-toolkit](https://github.com/ultimatethemedev-bit/serigraphie-toolkit) (MIT): ide solver
  coverage di Lab, highlight white + knockout, densitas minimum. Diimplementasikan ulang di numpy.
- [reveal](https://github.com/electrosaur-labs/reveal) (Apache-2.0): pemilihan palet di Lab, arsitektur
  mesin inti terpisah dari adapter Photoshop.
- [bwLabSP](https://github.com/souheyell/bwLabSP): ramp highlight kontinu, AM elips + FM.
- [InkSplit](https://github.com/otacon239/inksplit) (GPL-3): hanya dibaca sebagai referensi, kodenya tidak dipakai.

## 3. Kalkulator harga (`harga`)

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
