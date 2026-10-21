# Komparasi Algoritma Pencarian

Rute di dalam satu SPPG; sekolah dibagi ke SPPG terdekat (Kuliah 2–3). Optimum acuan = biaya UCS.

| Algoritma | Jenis | Frontier | Optimal? | Memori | Optimal (sub-masalah nyata) | Selisih rata-rata | Node diekspansi (total) | Memori maks. (node) | Waktu total |
|---|---|---|---|---|---|---|---|---|---|
| BFS | buta | antrian FIFO | tidak (hanya bila biaya langkah sama) | O(b^d) | 0/9 | 65.8% | 128,325 | 80,948 | 0.70 s |
| IDS | buta | DFS berbatas kedalaman 0, 1, 2, ... | tidak (sama dengan BFS) | O(b·d) | 0/9 | 78.4% | 4,056,125 | 61 | 12.81 s |
| DFS-B&B | buta + batas | tumpukan LIFO, pangkas g >= solusi terbaik | ya | O(b·d) | 8/9 | 0.0% | 7,260,876 | 60 | 20.31 s |
| UCS | buta (biaya) | antrian prioritas g(n) | ya | O(b^(C*/ε)) | 9/9 | 0.0% | 126,558 | 80,951 | 1.12 s |
| A* (h1) | berinformasi | antrian prioritas g(n) + h1(n) | ya (h1 admissible) | eksponensial, < UCS | 9/9 | 0.0% | 122,659 | 80,580 | 3.12 s |
| A* | berinformasi | antrian prioritas g(n) + h2(n) | ya (h2 admissible) | eksponensial, << UCS | 9/9 | 0.0% | 13,357 | 25,731 | 1.79 s |
| GBFS | berinformasi | antrian prioritas h2(n) saja | tidak | bergantung h | 0/9 | 73.4% | 983 | 472 | 0.04 s |

Skalabilitas (median node diekspansi; `batas` = ada sub-masalah yang melewati batas node):

| k | BFS | IDS | DFS-B&B | UCS | A* (h1) | A* | GBFS |
|---|---|---|---|---|---|---|---|
| 3 | 17 | 26 | 21 | 16 | 14 | 14 | 4 |
| 4 | 105 | 217 | 100 | 78 | 46 | 34 | 8 |
| 5 | 369 | 1,033 | 400 | 246 | 149 | 60 | 7 |
| 6 | 1,016 | 4,742 | 2,178 | 840 | 467 | 74 | 8 |
| 7 | 2,515 | 39,856 | 12,580 | 2,314 | 1,838 | 151 | 14 |
| 8 | 4,600 | 145,749 | 55,538 | 4,602 | 3,902 | 232 | 16 |
| 9 | 6,083 | 387,833 | 148,234 | 6,088 | 5,630 | 500 | 14 |
| 10 | 39,716 | batas | batas | 39,045 | 36,938 | 1,470 | 34 |
| 11 | 66,134 | batas | batas | 66,090 | 63,229 | 3,071 | 283 |
| 12 | 80,853 | batas | batas | 80,856 | 79,684 | 5,224 | 176 |
