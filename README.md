# Optimasi Rute Distribusi Makan Bergizi Gratis (MBG) di Surabaya

Proyek KKA ETS. Studi kasus pengiriman makanan MBG dari **SPPG** (dapur) ke **sekolah**
di Surabaya memakai **Granmax**. Tujuannya meminimalkan **biaya bensin** sekaligus
**waktu tiba makanan**. Masalah ini dimodelkan sebagai
**Multi-Depot Vehicle Routing Problem (MDVRP) bi-objektif** dengan batas kapasitas dan batas waktu.

## Formulasi

| | |
|---|---|
| Depot | SPPG (lokasi dari berita resmi, koordinat hasil geocoding) |
| Pelanggan | SD/MI/SMP/MTs dari OpenStreetMap, dalam radius 3 km dari SPPG |
| Jarak & waktu | Jalan asli (OSRM / OpenStreetMap), kondisi lancar |
| **f1** (min) | Biaya bensin = total km / 14 km·L⁻¹ × Rp10.000 (Pertalite) |
| **f2** (min) | Rata-rata waktu tiba makanan di sekolah (menit sejak berangkat) |
| Constraint | maks **3 sekolah per Granmax**, armada per SPPG terbatas (default 3), drop **15 menit**/sekolah, tiba ≤ **180 menit** setelah masak |
| Asumsi | tidak macet, lampu hijau, semua makanan selesai & berangkat bersamaan, Granmax kembali ke SPPG |

Catatan: "maks 3 sekolah" dimodelkan **per kendaraan**. Untuk interpretasi "maks 3 sekolah per SPPG",
set `vehicles_per_sppg` = 1 di `config.json`.

## Metode yang dibandingkan

| Model | Representasi | Keterangan |
|---|---|---|
| Greedy (baseline) | konstruktif | pilih penambahan dengan biaya inkremental terkecil |
| Simulated Annealing | permutasi + pemisah kendaraan | swap / insert / inversion, pendinginan geometrik, T0 adaptif |
| Genetic Algorithm | urutan sekolah + **decoder greedy** | OX crossover, tournament, elitisme |
| Ant Colony Optimization | konstruktif probabilistik | **MAX-MIN Ant System**, heuristik = biaya inkremental |
| **NSGA-II** | urutan sekolah + **gen bobot decoder** | multi-objective langsung, constrained domination (Deb) |

SA, GA, dan ACO meminimalkan *weighted sum* ternormalisasi
`F = w·f1/ref1 + (1−w)·f2/ref2 + penalti·pelanggaran`, dengan w ∈ {0, 0.25, 0.5, 0.75, 1}.
NSGA-II langsung menghasilkan Pareto front, dengan anggaran evaluasi yang sama dengan total 5 run weighted sum.
Semua metaheuristik diberi **anggaran evaluasi yang sama** (20.000 evaluasi per run).

## Struktur

```
config.json              parameter masalah, instance, eksperimen, algoritma
data/raw/sppg.csv        lokasi SPPG + sumber berita
data/raw/schools_osm.csv sekolah Surabaya dari OpenStreetMap
data/instances/<nama>/   titik terpilih + matriks jarak (km) & waktu (menit)
scripts/fetch_schools.py ambil data sekolah (Overpass API)
scripts/build_instance.py pilih sekolah + hitung matriks OSRM
src/mbgvrp/
  problem.py             model masalah & fungsi evaluasi
  encoding.py            representasi permutasi + operator
  construct.py           konstruksi Greedy/ACO + decoder GA
  algorithms.py          SA, GA, ACO, NSGA-II
  metrics.py             hypervolume
  viz.py                 grafik & peta rute
  animation_template.html tampilan animasi (Leaflet)
run_experiments.py       eksperimen utama (paralel)
run_sensitivity.py       analisis sensitivitas (kapasitas, kemacetan, km/L)
make_animation.py        animasi gaya VisuAlgo (pencarian rute + pengiriman)
results/<instance>/      hasil: CSV, grafik PNG, peta_rute.html, animasi.html, best_routes.txt
```

## Cara menjalankan

```bash
pip install -r requirements.txt

# (opsional) bangun ulang data: butuh internet
python scripts/fetch_schools.py
python scripts/build_instance.py

python run_experiments.py --quick        # uji cepat (~1 menit)
python run_experiments.py                # eksperimen penuh (30 seed)
python run_sensitivity.py --instance surabaya_6sppg
python make_animation.py                 # animasi (~2-5 menit per instance)
```

Setiap run yang selesai disimpan ke `results/<instance>/.checkpoint_*.pkl`. Kalau eksperimen
terhenti (misalnya RAM habis), jalankan ulang perintah yang sama dan eksperimen akan lanjut dari
run terakhir. Kalau RAM terbatas, kurangi jumlah proses paralel, misalnya `--workers 4`.

Buka `results/<instance>/peta_rute.html` di browser untuk melihat peta rute interaktif.
Di peta, rute tiap algoritma bisa dinyalakan/dimatikan lewat panel layer.

### Animasi (`results/<instance>/animasi.html`)

Dua tahap, pilih algoritma di kanan atas:
1. **Pencarian rute**: langkah demi langkah Greedy / SA / GA / ACO / NSGA-II. Baris pseudocode
   yang sedang dijalankan di-highlight, rute di peta berubah mengikuti solusi saat itu
   (ACO: garis cokelat = feromon; NSGA-II: grafik sebaran populasi biaya vs waktu).
2. **Pengiriman**: Granmax bergerak di jalan asli dari SPPG ke sekolah dengan jam berjalan.

Tombol *Sembunyikan kode* menyembunyikan panel pseudocode. Kontrol: spasi = putar/jeda,
panah kiri/kanan = langkah. Tautan langsung juga bisa, misalnya `animasi.html#stage=2&algo=GA&t=30`.
Run SA/GA/ACO di animasi sama persis dengan run seed 1 di eksperimen (`trace` tidak memakai rng).
Setelah mengubah template, cukup `python make_animation.py --html-only`.

## Deploy hasil ke web (Vercel)

Semua hasil adalah file statis, jadi cukup dihosting tanpa server:

```bash
python scripts/build_site.py      # kumpulkan animasi, peta, grafik + halaman depan ke site/
vercel login                      # sekali saja
vercel deploy site --prod
```

## Sumber data
- Sekolah dan jaringan jalan: © kontributor OpenStreetMap (ODbL), routing via OSRM.
- Lokasi SPPG: lihat kolom `reference` di `data/raw/sppg.csv`. Koordinatnya **perkiraan**
  (geocoding nama jalan/kelurahan), jadi sebaiknya diverifikasi dengan Google Maps.
