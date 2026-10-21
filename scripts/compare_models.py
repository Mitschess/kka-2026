"""Tabel komparasi algoritma pencarian (dipakai di laporan & presentasi).

Jalankan setelah run_search.py:
  python scripts/compare_models.py
Hasil: results/komparasi_model.md  (karakteristik, hasil sub-masalah nyata, skalabilitas)
"""
import csv
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ["BFS", "IDS", "DFS-B&B", "UCS", "A* (h1)", "A*", "GBFS"]

SEARCH_TRAITS = {
    "BFS": ("buta", "antrian FIFO", "tidak (hanya bila biaya langkah sama)", "O(b^d)"),
    "IDS": ("buta", "DFS berbatas kedalaman 0, 1, 2, ...", "tidak (sama dengan BFS)", "O(b·d)"),
    "DFS-B&B": ("buta + batas", "tumpukan LIFO, pangkas g >= solusi terbaik", "ya", "O(b·d)"),
    "UCS": ("buta (biaya)", "antrian prioritas g(n)", "ya", "O(b^(C*/ε))"),
    "A* (h1)": ("berinformasi", "antrian prioritas g(n) + h1(n)", "ya (h1 admissible)", "eksponensial, < UCS"),
    "A*": ("berinformasi", "antrian prioritas g(n) + h2(n)", "ya (h2 admissible)", "eksponensial, << UCS"),
    "GBFS": ("berinformasi", "antrian prioritas h2(n) saja", "tidak", "bergantung h"),
}
LOCAL_TRAITS = {
    "HC": ("langkah terbaik (steepest)", "tidak", "tidak - berhenti di optimum lokal"),
    "HC-Sideways": ("langkah terbaik, boleh datar", "tidak (hanya ΔF = 0)", "plateau saja (maks. 100 langkah datar)"),
    "Stochastic HC": ("acak di antara langkah yang memperbaiki", "tidak", "tidak - berhenti di optimum lokal"),
    "Random-Walk HC": ("terbaik, peluang 0,05 langkah acak", "ya (langkah acak)", "ya, langkah acak"),
    "RR-HC": ("HC berulang dari titik acak", "tidak", "ya, mulai ulang"),
    "EHC": ("BFS sampai ketemu yang lebih baik", "ya (di dalam BFS)", "ya, lompatan 2 langkah"),
    "SA": ("tetangga acak", "ya, peluang e^(−ΔF/T)", "ya, suhu menurun"),
    "GA": ("populasi 100, crossover uniform", "ya (seleksi)", "ya, populasi beragam"),
}


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    out = ROOT / "results"
    real = read_csv(out / "search_real.csv")
    summ = read_csv(out / "search_summary.csv")
    md = ["# Komparasi Algoritma Pencarian\n",
          "Rute di dalam satu SPPG; sekolah dibagi ke SPPG terdekat (Kuliah 2–3). "
          "Optimum acuan = biaya UCS.\n",
          "| Algoritma | Jenis | Frontier | Optimal? | Memori | Optimal (sub-masalah nyata) | "
          "Selisih rata-rata | Node diekspansi (total) | Memori maks. (node) | Waktu total |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for a in SEARCH:
        rs = [r for r in real if r["algorithm"] == a]
        kind, frontier, opt, mem = SEARCH_TRAITS[a]
        n_opt = sum(r["optimal"] == "True" for r in rs)
        gap = abs(np.nanmean([float(r["gap_pct"]) for r in rs]))
        md.append(f"| {a} | {kind} | {frontier} | {opt} | {mem} | {n_opt}/{len(rs)} | {gap:.1f}% | "
                  f"{sum(int(r['expanded']) for r in rs):,} | {max(int(r['max_stored']) for r in rs):,} | "
                  f"{sum(float(r['runtime_s']) for r in rs):.2f} s |")
    md += ["\nSkalabilitas (median node diekspansi; `batas` = ada sub-masalah yang melewati batas node):\n",
           "| k | " + " | ".join(SEARCH) + " |", "|---" * (len(SEARCH) + 1) + "|"]
    for k in sorted({int(r["k"]) for r in summ}):
        cells = []
        for a in SEARCH:
            s = next(r for r in summ if int(r["k"]) == k and r["algorithm"] == a)
            cells.append("batas" if float(s["solved_rate"]) < 1 else f"{float(s['expanded_median']):,.0f}")
        md.append(f"| {k} | " + " | ".join(cells) + " |")
    (out / "komparasi_model.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"-> {out / 'komparasi_model.md'}")


if __name__ == "__main__":
    main()
