# Komparasi Model

Pendekatan dua tingkat: **Bagian A** = rute di dalam satu SPPG (algoritma pencarian, Kuliah 2–3); **Bagian B** = pembagian sekolah ke SPPG (pencarian lokal, Kuliah 6) dengan rute tiap SPPG dihitung optimal. Pembanding: Greedy dan metaheuristik terintegrasi (HC, SA, GA pada representasi rute penuh, run_experiments.py).

## Bagian A — rute di dalam satu SPPG

| Algoritma | Jenis | Frontier | Optimal? | Memori | Optimal (sub-masalah nyata) | Selisih rata-rata | Node diekspansi (total) | Memori maks. (node) | Waktu total |
|---|---|---|---|---|---|---|---|---|---|
| BFS | buta | antrian FIFO | tidak (hanya bila biaya langkah sama) | O(b^d) | 0/9 | 53.9% | 19,310 | 4,679 | 0.09 s |
| IDS | buta | DFS berbatas kedalaman 0, 1, 2, ... | tidak (sama dengan BFS) | O(b·d) | 0/9 | 53.9% | 394,920 | 35 | 0.79 s |
| DFS-B&B | buta + batas | tumpukan LIFO, pangkas g >= solusi terbaik | ya | O(b·d) | 9/9 | 0.0% | 136,558 | 31 | 0.33 s |
| UCS | buta (biaya) | antrian prioritas g(n) | ya | O(b^(C*/ε)) | 9/9 | 0.0% | 17,703 | 4,678 | 0.08 s |
| A* (h1) | berinformasi | antrian prioritas g(n) + h1(n) | ya (h1 admissible) | eksponensial, < UCS | 9/9 | 0.0% | 14,033 | 4,505 | 0.25 s |
| A* | berinformasi | antrian prioritas g(n) + h2(n) | ya (h2 admissible) | eksponensial, << UCS | 9/9 | 0.0% | 926 | 1,026 | 0.10 s |
| GBFS | berinformasi | antrian prioritas h2(n) saja | tidak | bergantung h | 0/9 | 51.5% | 149 | 67 | 0.01 s |

Skalabilitas (median node diekspansi; `batas` = ada sub-masalah yang melewati batas node):

| k | BFS | IDS | DFS-B&B | UCS | A* (h1) | A* | GBFS |
|---|---|---|---|---|---|---|---|
| 3 | 17 | 26 | 21 | 16 | 14 | 14 | 4 |
| 4 | 105 | 217 | 104 | 78 | 47 | 36 | 8 |
| 5 | 369 | 1,033 | 400 | 249 | 149 | 52 | 7 |
| 6 | 1,016 | 4,742 | 2,174 | 840 | 472 | 72 | 8 |
| 7 | 2,515 | 39,856 | 12,694 | 2,313 | 1,957 | 118 | 12 |
| 8 | 4,600 | 145,749 | 55,538 | 4,601 | 3,902 | 220 | 16 |
| 9 | 6,083 | 387,833 | 148,234 | 6,087 | 5,630 | 416 | 18 |
| 10 | 39,716 | batas | batas | 39,045 | 36,938 | 1,470 | 34 |
| 11 | 66,134 | batas | batas | 66,090 | 63,229 | 3,071 | 283 |
| 12 | 80,853 | batas | batas | 80,856 | 79,684 | 5,224 | 176 |

## Bagian B — pembagian sekolah ke SPPG

| Algoritma | Cara melangkah | Menerima langkah lebih buruk? | Keluar dari optimum lokal |
|---|---|---|---|
| HC | langkah terbaik (steepest) | tidak | tidak - berhenti di optimum lokal |
| HC-Sideways | langkah terbaik, boleh datar | tidak (hanya ΔF = 0) | plateau saja (maks. 100 langkah datar) |
| Stochastic HC | acak di antara langkah yang memperbaiki | tidak | tidak - berhenti di optimum lokal |
| Random-Walk HC | terbaik, peluang 0,05 langkah acak | ya (langkah acak) | ya, langkah acak |
| RR-HC | HC berulang dari titik acak | tidak | ya, mulai ulang |
| EHC | BFS sampai ketemu yang lebih baik | ya (di dalam BFS) | ya, lompatan 2 langkah |
| SA | tetangga acak | ya, peluang e^(−ΔF/T) | ya, suhu menurun |
| GA | populasi 100, crossover uniform | ya (seleksi) | ya, populasi beragam |

Hasil (w = 0.5, 30 seed, 200,000 evaluasi/run). Sukses = mencapai solusi terbaik yang diketahui.

### surabaya_utara (terbaik diketahui F = 1.9951; Greedy 2.1621)

| Algoritma | Fitness mean ± std | Terbaik | Sukses | Selisih rata-rata | Biaya bensin | Evaluasi dipakai | Evaluasi s.d. terbaik (median) | Waktu/run |
|---|---|---|---|---|---|---|---|---|
| HC | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 1,350 | 1,122 | 0.1 s |
| HC-Sideways | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 1,350 | 1,122 | 0.1 s |
| Stochastic HC | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 3,216 | 2,738 | 0.1 s |
| Random-Walk HC | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 200,000 | 1,096 | 0.6 s |
| RR-HC | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 200,000 | 1,122 | 3.3 s |
| EHC | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 21,102 | 256 | 0.2 s |
| SA | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 200,000 | 61,145 | 7.4 s |
| GA | 1.9951 ± 0.0000 | 1.9951 | 100% | 0.00% | Rp59,973 | 200,000 | 2,690 | 10.4 s |

Uji Mann-Whitney U + Holm: 0/28 pasangan berbeda signifikan.

Pembanding terintegrasi (surabaya_utara, 20,000 evaluasi/run, 30 seed):

| Model | Fitness mean ± std | Terbaik | Selisih rata-rata thd terbaik diketahui | Biaya bensin |
|---|---|---|---|---|
| Greedy | 2.1621 ± 0.0000 | 2.1621 | 8.37% | Rp74,562 |
| HC | 2.0937 ± 0.0387 | 2.0066 | 4.94% | Rp66,979 |
| SA | 2.0031 ± 0.0178 | 1.9951 | 0.40% | Rp60,893 |
| GA | 1.9986 ± 0.0050 | 1.9951 | 0.18% | Rp60,548 |

### surabaya_6sppg (terbaik diketahui F = 2.0574; Greedy 2.2417)

| Algoritma | Fitness mean ± std | Terbaik | Sukses | Selisih rata-rata | Biaya bensin | Evaluasi dipakai | Evaluasi s.d. terbaik (median) | Waktu/run |
|---|---|---|---|---|---|---|---|---|
| HC | 2.0818 ± 0.0355 | 2.0574 | 3% | 1.19% | Rp135,278 | 27,304 | 25,606 | 1.1 s |
| HC-Sideways | 2.0818 ± 0.0355 | 2.0574 | 3% | 1.19% | Rp135,278 | 27,304 | 25,606 | 1.1 s |
| Stochastic HC | 2.0645 ± 0.0164 | 2.0574 | 37% | 0.35% | Rp131,339 | 70,759 | 69,453 | 2.3 s |
| Random-Walk HC | 2.0609 ± 0.0103 | 2.0574 | 30% | 0.17% | Rp130,581 | 200,000 | 29,402 | 3.3 s |
| RR-HC | 2.0578 ± 0.0007 | 2.0574 | 57% | 0.02% | Rp129,179 | 200,000 | 86,476 | 7.9 s |
| EHC | 2.0576 ± 0.0003 | 2.0574 | 53% | 0.01% | Rp129,259 | 200,000 | 3,915 | 7.6 s |
| SA | 2.0575 ± 0.0003 | 2.0574 | 70% | 0.01% | Rp129,187 | 200,000 | 181,404 | 58.1 s |
| GA | 2.0581 ± 0.0008 | 2.0574 | 30% | 0.03% | Rp130,022 | 200,000 | 15,245 | 19.8 s |

Uji Mann-Whitney U + Holm: 16/28 pasangan berbeda signifikan.
- HC vs Stochastic HC: p(Holm) = 0.0266, rata-rata lebih baik: Stochastic HC
- HC vs Random-Walk HC: p(Holm) = 0.00259, rata-rata lebih baik: Random-Walk HC
- HC vs RR-HC: p(Holm) = 3.31e-06, rata-rata lebih baik: RR-HC
- HC vs EHC: p(Holm) = 2.22e-07, rata-rata lebih baik: EHC
- HC vs SA: p(Holm) = 4.48e-08, rata-rata lebih baik: SA
- HC vs GA: p(Holm) = 0.00249, rata-rata lebih baik: GA
- HC-Sideways vs Stochastic HC: p(Holm) = 0.0266, rata-rata lebih baik: Stochastic HC
- HC-Sideways vs Random-Walk HC: p(Holm) = 0.00259, rata-rata lebih baik: Random-Walk HC
- HC-Sideways vs RR-HC: p(Holm) = 3.31e-06, rata-rata lebih baik: RR-HC
- HC-Sideways vs EHC: p(Holm) = 2.22e-07, rata-rata lebih baik: EHC
- HC-Sideways vs SA: p(Holm) = 4.48e-08, rata-rata lebih baik: SA
- HC-Sideways vs GA: p(Holm) = 0.00249, rata-rata lebih baik: GA
- Stochastic HC vs SA: p(Holm) = 0.0137, rata-rata lebih baik: SA
- Random-Walk HC vs SA: p(Holm) = 0.0137, rata-rata lebih baik: SA
- EHC vs GA: p(Holm) = 0.0137, rata-rata lebih baik: EHC
- SA vs GA: p(Holm) = 0.00434, rata-rata lebih baik: SA

Pembanding terintegrasi (surabaya_6sppg, 20,000 evaluasi/run, 30 seed):

| Model | Fitness mean ± std | Terbaik | Selisih rata-rata thd terbaik diketahui | Biaya bensin |
|---|---|---|---|---|
| Greedy | 2.2417 ± 0.0000 | 2.2417 | 8.96% | Rp163,086 |
| HC | 2.6465 ± 0.0852 | 2.4315 | 28.63% | Rp230,914 |
| SA | 2.1385 ± 0.0246 | 2.1070 | 3.95% | Rp145,778 |
| GA | 2.0906 ± 0.0160 | 2.0698 | 1.62% | Rp134,323 |
