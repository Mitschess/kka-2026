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
| Constraint | maks **3 sekolah per Granmax**, armada per SPPG terbatas (default 3, dinaikkan bila sekolah terdekatnya kelebihan), drop **15 menit**/sekolah, tiba ≤ **180 menit** setelah masak |
| Asumsi | tidak macet, lampu hijau, semua makanan selesai & berangkat bersamaan, Granmax kembali ke SPPG |

Catatan: "maks 3 sekolah" dimodelkan **per kendaraan**.

## Metode

1. **Penugasan**: tiap sekolah dilayani **SPPG terdekat** (jarak jalan OSRM), `assign_nearest` di
   `src/mbgvrp/problem.py`. Setelah penugasan tetap, rute tiap SPPG saling bebas.
2. **Rute di dalam satu SPPG** (pencarian, Kuliah 2 & 3), `src/mbgvrp/search.py`.
   Keadaan = (sekolah tersisa, posisi, muatan Granmax, waktu, Granmax terpakai). Aksi = antar ke
   sekolah / pulang ke SPPG. Biaya langkah = kontribusi langkah itu ke fungsi objektif
   `F = w·f1/ref1 + (1−w)·f2/ref2` (w = 0,5).

| # | Algoritma | Kegunaan | Optimal? |
|---|---|---|---|
| 1 | Breadth-First Search | solusi dengan langkah paling sedikit = Granmax paling sedikit | tidak |
| 2 | Iterative Deepening | sama dengan BFS, memori seperti DFS | tidak |
| 3 | DFS + Branch and Bound | telusuri dalam-dulu, pangkas bila g >= solusi terbaik | ya |
| 4 | Uniform-Cost Search | f = g (biaya bensin + waktu tiba), pangkas keadaan > 3 jam | ya |
| 5 | A* (h1) | h1 = jalan masuk termurah (admissible) | ya |
| 6 | A* (h2) | h2 = relaksasi penugasan slot (Hungaria), admissible | ya |
| 7 | Greedy Best-First | f = h saja, cepat | tidak |

Optimum acuan untuk menghitung selisih (gap) = biaya UCS. A*, A* (h1), dan DFS-B&B diperiksa
(`assert`) menghasilkan biaya yang sama dengan UCS.

## Struktur

```
config.json              parameter masalah, instance, eksperimen pencarian
data/raw/sppg.csv        lokasi SPPG + sumber berita
data/raw/schools_osm.csv sekolah Surabaya dari OpenStreetMap
data/instances/<nama>/   titik terpilih + matriks jarak (km) & waktu (menit)
scripts/fetch_schools.py ambil data sekolah (Overpass API)
scripts/build_instance.py pilih sekolah + hitung matriks OSRM
scripts/compare_models.py tabel komparasi algoritma -> results/komparasi_model.md
scripts/build_site.py    kumpulkan hasil ke site/ untuk Vercel
src/mbgvrp/
  problem.py             model masalah, evaluasi, penugasan SPPG terdekat
  search.py              BFS, IDS, DFS-B&B, UCS, A* (h1, h2), Greedy Best-First
  viz.py                 grafik & peta rute
  animation_template.html tampilan animasi (Leaflet)
  site_template.html     tampilan halaman depan situs (peta, grafik, tabel interaktif)
run_search.py            eksperimen: sub-masalah nyata + skalabilitas k = 3..12
make_animation.py        animasi gaya VisuAlgo (pencarian rute + pengiriman)
results/<instance>/      rute_terbaik.json|txt, fig_rute_terbaik.png, peta_rute_terbaik.html, animasi.html
report/                  generator Final Report (DOCX) dan Presentation Deck (PPTX)
```

## Cara menjalankan

```bash
pip install -r requirements.txt

# (opsional) bangun ulang data: butuh internet
python scripts/fetch_schools.py
python scripts/build_instance.py

python run_search.py --workers 4         # eksperimen pencarian + rute terbaik
python make_animation.py                 # animasi (butuh rute_terbaik.json dari run_search.py)
python scripts/compare_models.py         # tabel komparasi algoritma

# laporan & presentasi (butuh Node.js; Microsoft Word opsional untuk mengisi daftar isi otomatis)
python report/build_report.py            # -> report/Laporan_Final_MBG_VRP.docx (Word)
cd report && npm install && node build_deck.js   # -> report/Presentasi_MBG_VRP.pptx
```

Identitas tim di sampul laporan dan slide judul diisi di bagian atas `report/build_report.py`
(`TEAM`, `LECTURER`, `INSTITUTION`) dan `report/build_deck.js` (`TEAM`).

Buka `results/<instance>/peta_rute_terbaik.html` di browser untuk melihat peta rute interaktif.

### Animasi (`results/<instance>/animasi.html`)

Dua tahap:
1. **Rute terbaik**: langkah demi langkah BFS / UCS / A* / GBFS / DFS-B&B mencari rute di satu
   sub-masalah nyata (SPPG dengan sekolah terbanyak, dibatasi k <= 9). Baris pseudocode yang
   sedang dijalankan di-highlight.
2. **Pengiriman**: Granmax bergerak di jalan asli dari SPPG ke sekolah dengan jam berjalan,
   memakai rute terbaik (A*) seluruh instance.

Tombol *Sembunyikan kode* menyembunyikan panel pseudocode. Kontrol: spasi = putar/jeda,
panah kiri/kanan = langkah. Tautan langsung juga bisa, misalnya
`animasi.html#stage=1&algoRoute=A*&frame=30`. Setelah mengubah template, cukup
`python make_animation.py --html-only`.

## Deploy hasil ke web (Vercel)

Halaman depan (`site/index.html`, template `src/mbgvrp/site_template.html`) interaktif: peta rute
tiap algoritma di jalan asli (bisa disorot per Granmax dan dibandingkan dengan rute optimal), grafik
perbandingan, tabel yang bisa diurutkan, grafik skalabilitas, serta mode terang/gelap. Angkanya dibaca
dari `results/search_real.csv`, `results/search_summary.csv`, dan `results/<instance>/rute_algoritma.json`;
tidak ada pencarian yang dijalankan ulang. Skrip ini juga memasang Vercel Web Analytics di setiap
halaman. Semua hasil adalah file statis, jadi cukup dihosting tanpa server:

```bash
python scripts/build_site.py      # kumpulkan animasi, peta, grafik + halaman depan ke site/
vercel login                      # sekali saja
vercel deploy site --prod
```

## Sumber data
- Sekolah dan jaringan jalan: © kontributor OpenStreetMap (ODbL), routing via OSRM.
- Lokasi SPPG: lihat kolom `reference` di `data/raw/sppg.csv`. Koordinatnya **perkiraan**
  (geocoding nama jalan/kelurahan), jadi sebaiknya diverifikasi dengan Google Maps.
