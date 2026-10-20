"""Komparasi semua model di semua instance (dipakai di laporan & presentasi).

Jalankan setelah run_search.py, run_assignment.py, dan run_experiments.py:
  python scripts/compare_models.py
Hasil:
  results/komparasi_model.csv   satu baris per (instance, pendekatan, algoritma)
  results/komparasi_model.md    tabel Bagian A, Bagian B, dan pembanding terintegrasi
  results/fig_komparasi.png     selisih rata-rata terhadap solusi terbaik yang diketahui
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SEARCH = ["BFS", "IDS", "DFS-B&B", "UCS", "A* (h1)", "A*", "GBFS"]
LOCAL = ["HC", "HC-Sideways", "Stochastic HC", "Random-Walk HC", "RR-HC", "EHC", "SA", "GA"]
INTEGRATED = ["HC", "SA", "GA", "ACO"]

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
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    names = list(config["instances"])
    out = ROOT / "results"
    rows, md = [], ["# Komparasi Model\n",
                    "Pendekatan dua tingkat: **Bagian A** = rute di dalam satu SPPG (algoritma pencarian, "
                    "Kuliah 2–3); **Bagian B** = pembagian sekolah ke SPPG (pencarian lokal, Kuliah 6) "
                    "dengan rute tiap SPPG dihitung optimal. Pembanding: Greedy dan metaheuristik "
                    "terintegrasi (representasi rute penuh) dari eksperimen awal.\n"]

    # ------------------------------------------------------------- Bagian A
    real = read_csv(out / "search_real.csv")
    summ = read_csv(out / "search_summary.csv")
    md += ["## Bagian A — rute di dalam satu SPPG\n",
           "| Algoritma | Jenis | Frontier | Optimal? | Memori | Optimal (sub-masalah nyata) | "
           "Selisih rata-rata | Node diekspansi (total) | Memori maks. (node) | Waktu total |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for a in SEARCH:
        rs = [r for r in real if r["algorithm"] == a]
        kind, frontier, opt, mem = SEARCH_TRAITS[a]
        n_opt = sum(r["optimal"] == "True" for r in rs)
        gap = abs(np.nanmean([float(r["gap_pct"]) for r in rs]))
        exp_ = sum(int(r["expanded"]) for r in rs)
        stored = max(int(r["max_stored"]) for r in rs)
        rt = sum(float(r["runtime_s"]) for r in rs)
        md.append(f"| {a} | {kind} | {frontier} | {opt} | {mem} | {n_opt}/{len(rs)} | {gap:.1f}% | "
                  f"{exp_:,} | {stored:,} | {rt:.2f} s |")
        rows.append({"instance": "sub-masalah nyata", "approach": "A: pencarian", "algorithm": a,
                     "optimal_rate": n_opt / len(rs), "gap_mean_pct": gap, "expanded_total": exp_,
                     "max_stored": stored, "runtime_s": rt})
    ks = sorted({int(r["k"]) for r in summ})
    md += ["\nSkalabilitas (median node diekspansi; `batas` = ada sub-masalah yang melewati batas node):\n",
           "| k | " + " | ".join(SEARCH) + " |", "|---" * (len(SEARCH) + 1) + "|"]
    for k in ks:
        cells = []
        for a in SEARCH:
            s = next(r for r in summ if int(r["k"]) == k and r["algorithm"] == a)
            cells.append("batas" if float(s["solved_rate"]) < 1 else f"{float(s['expanded_median']):,.0f}")
        md.append(f"| {k} | " + " | ".join(cells) + " |")

    # ------------------------------------------------------------- Bagian B
    md += ["\n## Bagian B — pembagian sekolah ke SPPG\n",
           "| Algoritma | Cara melangkah | Menerima langkah lebih buruk? | Keluar dari optimum lokal |",
           "|---|---|---|---|"]
    for a in LOCAL:
        md.append(f"| {a} | " + " | ".join(LOCAL_TRAITS[a]) + " |")
    asg = config["assignment"]
    md.append(f"\nHasil (w = {config['experiment']['main_weight']}, {asg['n_seeds']} seed, "
              f"{asg['budget_evals']:,} evaluasi/run). Sukses = mencapai solusi terbaik yang diketahui.\n")
    for name in names:
        res = out / name
        ls = {r["algorithm"]: r for r in read_csv(res / "ls_summary.csv")}
        best = json.loads((res / "ls_best.json").read_text(encoding="utf-8"))
        bk, g = float(best["best_known_fitness"]), best["Greedy"]
        md += [f"### {name} (terbaik diketahui F = {bk:.4f}; Greedy {g['fitness']:.4f})\n",
               "| Algoritma | Fitness mean ± std | Terbaik | Sukses | Selisih rata-rata | Biaya bensin | "
               "Evaluasi dipakai | Evaluasi s.d. terbaik (median) | Waktu/run |",
               "|---|---|---|---|---|---|---|---|---|"]
        for a in LOCAL:
            s = ls[a]
            md.append(f"| {a} | {float(s['fitness_mean']):.4f} ± {float(s['fitness_std']):.4f} | "
                      f"{float(s['fitness_best']):.4f} | {float(s['success_rate']):.0%} | "
                      f"{float(s['gap_mean_pct']):.2f}% | Rp{float(s['cost_rp_mean']):,.0f} | "
                      f"{float(s['n_evals_mean']):,.0f} | {float(s['evals_to_best_median']):,.0f} | "
                      f"{float(s['runtime_s_mean']):.1f} s |")
            rows.append({"instance": name, "approach": "B: dua tingkat", "algorithm": a,
                         "fitness_mean": float(s["fitness_mean"]), "fitness_std": float(s["fitness_std"]),
                         "fitness_best": float(s["fitness_best"]), "success_rate": float(s["success_rate"]),
                         "gap_mean_pct": float(s["gap_mean_pct"]), "cost_rp_mean": float(s["cost_rp_mean"]),
                         "runtime_s": float(s["runtime_s_mean"])})
        tests = read_csv(res / "ls_stat_tests.csv")
        sig = [t for t in tests if t["significant_5pct"] == "True"]
        md.append(f"\nUji Mann-Whitney U + Holm: {len(sig)}/{len(tests)} pasangan berbeda signifikan.")
        for t in sig:
            md.append(f"- {t['pair']}: p(Holm) = {float(t['p_holm']):.3g}, rata-rata lebih baik: {t['better_mean']}")
        md.append("")

        # pembanding terintegrasi (eksperimen awal)
        integ = {r["algorithm"]: r for r in read_csv(res / "summary_main_w.csv")}
        md += [f"Pembanding terintegrasi ({name}, {config['experiment']['budget_evals']:,} evaluasi/run, "
               f"{config['experiment']['n_seeds']} seed):\n",
               "| Model | Fitness mean ± std | Terbaik | Selisih rata-rata thd terbaik diketahui | Biaya bensin |",
               "|---|---|---|---|---|"]
        for a in ["Greedy"] + INTEGRATED:
            s = integ[a]
            f = float(s["fitness_mean"])
            md.append(f"| {a} | {f:.4f} ± {float(s['fitness_std']):.4f} | {float(s['fitness_best']):.4f} | "
                      f"{(f - bk) / bk * 100:.2f}% | Rp{float(s['cost_rp_mean']):,.0f} |")
            rows.append({"instance": name, "approach": "baseline" if a == "Greedy" else "terintegrasi",
                         "algorithm": a, "fitness_mean": f, "fitness_std": float(s["fitness_std"]),
                         "fitness_best": float(s["fitness_best"]), "gap_mean_pct": (f - bk) / bk * 100,
                         "cost_rp_mean": float(s["cost_rp_mean"]), "runtime_s": float(s["runtime_s_mean"])})
        md.append("")

    keys = ["instance", "approach", "algorithm", "fitness_mean", "fitness_std", "fitness_best",
            "success_rate", "gap_mean_pct", "cost_rp_mean", "runtime_s", "optimal_rate",
            "expanded_total", "max_stored"]
    with open(out / "komparasi_model.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})
    (out / "komparasi_model.md").write_text("\n".join(md), encoding="utf-8")

    # ---- grafik: selisih rata-rata terhadap solusi terbaik yang diketahui (small multiples)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mbgvrp.viz import INK2, _style

    groups = [("Greedy", "baseline", "#52514e"), ("terintegrasi", "terintegrasi", "#eb6834"),
              ("dua tingkat", "B: dua tingkat", "#2a78d6")]
    fig, axes = plt.subplots(1, len(names), figsize=(11, 5.2), sharey=True)
    for ax, name in zip(np.atleast_1d(axes), names):
        items = [(f"{a} (terintegrasi)" if ap == "terintegrasi" else a, r["gap_mean_pct"], col)
                 for label, ap, col in groups for r in rows
                 if r["instance"] == name and r["approach"] == ap for a in [r["algorithm"]]]
        y = np.arange(len(items))[::-1]
        ax.barh(y, [v for _, v, _ in items], height=0.62, color=[c for *_, c in items])
        top = max(v for _, v, _ in items)
        for yi, (_, v, _) in zip(y, items):
            ax.text(v + top * 0.015, yi, f"{v:.2f}%", va="center", fontsize=8.5, color=INK2)
        ax.set_yticks(y, [lab for lab, *_ in items])
        ax.set_xlim(0, top * 1.22)
        spec = config["instances"][name]
        _style(ax, f"{name} ({len(spec['sppg_ids'])} SPPG, {spec['n_schools']} sekolah)",
               "Selisih rata-rata terhadap terbaik diketahui (%)", "")
        ax.grid(axis="y", visible=False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for *_, c in groups]
    fig.legend(handles, ["Greedy (baseline)", "Metaheuristik terintegrasi (eksperimen awal)",
                         "Dua tingkat: pencarian lokal + rute optimal"],
               loc="lower center", ncol=3, frameon=False, fontsize=9.5)
    fig.suptitle(f"Kualitas rata-rata {config['assignment']['n_seeds']} seed (w = "
                 f"{config['experiment']['main_weight']}); makin kecil makin baik",
                 x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out / "fig_komparasi.png", dpi=160, facecolor="white")
    plt.close(fig)
    print(f"-> {out / 'komparasi_model.md'}\n-> {out / 'komparasi_model.csv'}\n-> {out / 'fig_komparasi.png'}")


if __name__ == "__main__":
    main()
