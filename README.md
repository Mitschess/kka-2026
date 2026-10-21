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

## Metode: pendekatan dua tingkat

Untuk penugasan sekolah -> SPPG yang tetap, rute tiap SPPG saling bebas. Karena itu masalah
dipecah menjadi dua tingkat yang sesuai dengan materi kuliah (dekomposisi ini eksak: penugasan
terbaik + rute optimal per SPPG = optimum masalah penuh).

**Bagian A: rute di dalam satu SPPG** (pencarian, Kuliah 2 & 3), `src/mbgvrp/search.py`.
Keadaan = (sekolah tersisa, posisi, muatan Granmax, waktu, Granmax terpakai). Aksi = antar ke
sekolah / pulang ke SPPG. Biaya langkah = kontribusi langkah itu ke fitness.

| # | Algoritma | Kegunaan | Optimal? |
|---|---|---|---|
| 1 | Uniform-Cost Search | f = g (biaya bensin + waktu tiba), pangkas keadaan > 3 jam | ya |
| 2 | A* | f = g + h, h admissible: **h2** = relaksasi penugasan slot (Hungaria); pembanding **h1** = jalan masuk termurah | ya |
| 3 | DFS + Branch and Bound | telusuri dalam-dulu, pangkas bila g >= solusi terbaik | ya |
| 4 | Breadth-First Search | solusi dengan langkah paling sedikit = Granmax paling sedikit | tidak |
| 5 | Iterative Deepening | sama dengan BFS, memori seperti DFS | tidak |
| 6 | Greedy Best-First | f = h saja, cepat | tidak |

**Bagian B: pembagian sekolah ke SPPG** (pencarian lokal, Kuliah 6), `src/mbgvrp/local_search.py`.
Representasi x[s] = SPPG untuk sekolah s. Fitness = jumlah biaya rute optimal tiap SPPG
(`src/mbgvrp/router.py`, hasilnya identik dengan UCS/A*) + penalti. Tetangga = pindah satu
sekolah atau tukar dua sekolah antar-SPPG.

| # | Algoritma | Keterangan |
|---|---|---|
| 7 | Hill Climbing | steepest-ascent, berhenti di optimum lokal |
| 8 | HC + sideways moves | boleh langkah datar, maks. 100 berturut-turut |
| 9 | Stochastic HC | pilih acak di antara langkah yang memperbaiki |
| 10 | Random-Walk HC | peluang 0,05 langkah acak, selain itu langkah terbaik |
| 11 | Random-Restart HC | HC diulang dari penugasan acak sampai anggaran habis |
| 12 | Enforced HC | BFS dari optimum lokal sampai ketemu keadaan yang lebih baik |
| 13 | Simulated Annealing | terima langkah lebih buruk dengan peluang e^(−ΔF/T) |
| 14 | Genetic Algorithm | kromosom = SPPG tiap sekolah, fitness = 1/F, turnamen, crossover uniform |

Semua algoritma Bagian B diberi anggaran 200.000 evaluasi per run, 30 seed, dan mulai dari
penugasan acak yang sama untuk seed yang sama.

**Pembanding (`run_experiments.py`)**: Greedy dan metaheuristik *terintegrasi* yang mencari
langsung di ruang rute penuh, semuanya dari materi kuliah: Random-Restart Hill Climbing
(permutasi + pemisah kendaraan, 50 tetangga acak swap/insert/inversion per langkah, restart saat
optimum lokal), Simulated Annealing (representasi sama, pendinginan geometrik, T0 adaptif), dan
Genetic Algorithm (urutan sekolah + decoder greedy, OX crossover). Masing-masing 20.000 evaluasi
per run, 30 seed.

Semua metode meminimalkan *weighted sum* ternormalisasi
`F = w·f1/ref1 + (1−w)·f2/ref2 + penalti·pelanggaran` (bobot utama w = 0,5).
Trade-off biaya vs waktu didapat dengan menyapu w ∈ {0, 0.25, 0.5, 0.75, 1}.

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
  search.py              Bagian A: BFS, IDS, DFS-B&B, UCS, A* (h1, h2), Greedy Best-First
  router.py              rute optimal per SPPG (cepat, untuk fitness Bagian B)
  local_search.py        Bagian B: 6 varian Hill Climbing, SA, GA
  encoding.py            representasi permutasi + operator (pembanding terintegrasi)
  construct.py           konstruksi Greedy + decoder GA (pembanding terintegrasi)
  algorithms.py          Greedy, HC, SA, GA terintegrasi (pembanding)
  viz.py                 grafik & peta rute
  animation_template.html tampilan animasi (Leaflet)
run_assignment.py        eksperimen Bagian B (paralel, checkpoint) + sweep bobot
run_search.py            eksperimen Bagian A (sub-masalah nyata + skalabilitas)
run_experiments.py       eksperimen pembanding terintegrasi (Greedy, HC, SA, GA)
run_sensitivity.py       analisis sensitivitas (kapasitas, kemacetan, km/L)
make_animation.py        animasi gaya VisuAlgo (alokasi SPPG + rute terbaik + pengiriman)
scripts/compare_models.py komparasi semua model di semua instance
results/<instance>/      hasil: CSV, grafik PNG, peta_rute.html, animasi.html, best_routes.txt
results/komparasi_model.md  tabel perbandingan model (karakteristik + hasil + uji statistik)
report/                  generator Final Report (DOCX) dan Presentation Deck (PPTX)
```

## Cara menjalankan

```bash
pip install -r requirements.txt

# (opsional) bangun ulang data: butuh internet
python scripts/fetch_schools.py
python scripts/build_instance.py

python run_assignment.py --quick         # uji cepat Bagian B (~1 menit)
python run_assignment.py --workers 4     # Bagian B penuh (30 seed, ~20 menit)
python run_assignment.py --sweep RR-HC --seeds 10   # trade-off biaya vs waktu
python run_search.py --workers 4         # Bagian A (butuh ls_best.json dari Bagian B)
python run_experiments.py                # pembanding terintegrasi (30 seed)
python run_sensitivity.py --instance surabaya_6sppg
python make_animation.py                 # animasi (~2-5 menit per instance)
python scripts/compare_models.py         # tabel & grafik komparasi model

# laporan & presentasi (butuh Node.js; Microsoft Word opsional untuk mengisi daftar isi otomatis)
python report/build_report.py            # -> report/Laporan_Final_MBG_VRP.docx (Word)
cd report && npm install && node build_deck.js   # -> report/Presentasi_MBG_VRP.pptx
```

Identitas tim di sampul laporan dan slide judul diisi di bagian atas `report/build_report.py`
(`TEAM`, `LECTURER`, `INSTITUTION`) dan `report/build_deck.js` (`TEAM`).

Setiap run yang selesai disimpan ke `results/<instance>/.checkpoint_*.pkl`. Kalau eksperimen
terhenti (misalnya RAM habis), jalankan ulang perintah yang sama dan eksperimen akan lanjut dari
run terakhir. Kalau RAM terbatas, kurangi jumlah proses paralel, misalnya `--workers 4`.

Buka `results/<instance>/peta_rute.html` di browser untuk melihat peta rute interaktif.
Di peta, rute tiap algoritma bisa dinyalakan/dimatikan lewat panel layer.

### Animasi (`results/<instance>/animasi.html`)

Tiga tahap, pilih algoritma di kanan atas:
1. **Alokasi SPPG** (Bagian B): langkah demi langkah HC / SA / GA menugaskan sekolah ke SPPG.
   Rute tiap SPPG dihitung optimal (Router) di setiap langkah, jadi peta selalu solusi lengkap.
2. **Rute terbaik** (Bagian A): langkah demi langkah BFS / UCS / A* / GBFS / DFS-B&B mencari rute
   di satu sub-masalah nyata (SPPG dengan sekolah terbanyak dari penugasan terbaik tahap 1,
   dibatasi k <= 9). Baris pseudocode yang sedang dijalankan di-highlight.
3. **Pengiriman**: Granmax bergerak di jalan asli dari SPPG ke sekolah dengan jam berjalan,
   memakai solusi terbaik tahap 1 (HC/SA/GA).

Tombol *Sembunyikan kode* menyembunyikan panel pseudocode. Kontrol: spasi = putar/jeda,
panah kiri/kanan = langkah. Tautan langsung juga bisa, misalnya
`animasi.html#stage=2&algoRoute=A*&frame=30`. Run HC/SA/GA/BFS/UCS/A*/GBFS/DFS-B&B di animasi
sama persis dengan run seed 1 di eksperimen (`trace` tidak memakai rng).
Setelah mengubah template, cukup `python make_animation.py --html-only`.

## Deploy hasil ke web (Vercel)

Halaman depan (`site/index.html`) menampilkan dua case: Alokasi SPPG (HC/SA/GA, dari
`run_assignment.py`) dan Rute terbaik (BFS/UCS/A*/GBFS/DFS-B&B, diagregasi dari
`results/search_real.csv`, dari `run_search.py`). Pembanding terintegrasi
(`run_experiments.py`) tetap jalan standalone tapi tidak ditampilkan di web.

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
