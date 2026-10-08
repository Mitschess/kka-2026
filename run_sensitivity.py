"""Analisis sensitivitas (pakai GA, bobot utama) terhadap asumsi/constraint:

1. Kapasitas: maksimal 1, 2, 3, 4 sekolah per Granmax
2. Kemacetan: waktu tempuh dikali faktor 1-10 (melonggarkan asumsi "tidak macet")
   -> kapan batas 3 jam (selesai masak -> sampai sekolah) mulai mengikat?
3. Efisiensi bensin Granmax 10 vs 14 km/liter

Contoh:  python run_sensitivity.py --instance surabaya_6sppg --seeds 5
Hasil:   results/<instance>/sensitivity.csv, fig_sens_kapasitas.png, fig_sens_macet.png
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mbgvrp import algorithms as A  # noqa: E402
from mbgvrp.problem import load_instance  # noqa: E402

TRAFFIC_FACTORS = [1, 2, 4, 6, 8, 10]


def run_case(name, config, scenario, value, overrides, seed, budget):
    inst = load_instance(ROOT, name, config, overrides=dict(overrides))
    exp = config["experiment"]
    res = A.run_ga(inst, exp["main_weight"], exp["penalty"], budget=budget,
                   rng=np.random.default_rng(seed), **config["algorithms"]["ga"])
    ev = res.evaluation
    return {"scenario": scenario, "value": value, "seed": seed, "fitness": res.fitness,
            "cost_rp": ev.cost, "km": ev.km, "mean_arrival_min": ev.mean_arrival,
            "makespan_min": ev.makespan, "n_vehicles": ev.n_vehicles, "feasible": ev.feasible,
            "late_min": ev.late_min}


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default="surabaya_6sppg")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--budget", type=int, default=config["experiment"]["budget_evals"])
    ap.add_argument("--workers", type=int, default=min(8, max(1, (os.cpu_count() or 2) - 1)))
    args = ap.parse_args()
    name = args.instance
    n_vehicles = config["instances"][name]["vehicles_per_sppg"]
    n_schools = config["instances"][name]["n_schools"]
    n_sppg = len(config["instances"][name]["sppg_ids"])

    cases = []
    for q in [1, 2, 3, 4]:
        # armada ditambah bila kapasitas total tidak cukup melayani semua sekolah
        veh = max(n_vehicles, -(-n_schools // (q * n_sppg)))
        cases.append(("kapasitas", q, {"max_schools_per_vehicle": q, "vehicles_per_sppg": veh}))
    for tf in TRAFFIC_FACTORS:
        cases.append(("macet", tf, {"traffic_factor": tf}))
    for kmpl in [10, 14]:
        cases.append(("km_per_liter", kmpl, {"km_per_liter": kmpl}))

    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_case, name, config, sc, v, ov, seed, args.budget)
                for sc, v, ov in cases for seed in range(1, args.seeds + 1)]
        for k, f in enumerate(futs, start=1):
            rows.append(f.result())
            print(f"\r  {k}/{len(futs)} run selesai", end="", flush=True)
    print()

    from run_experiments import write_csv
    from mbgvrp import viz

    out = ROOT / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "sensitivity.csv", rows)

    # ambil solusi terbaik (fitness) per skenario-nilai
    best = {}
    for r in rows:
        key = (r["scenario"], r["value"])
        if key not in best or r["fitness"] < best[key]["fitness"]:
            best[key] = r
    print(f"\n{'skenario':14}{'nilai':>6}{'biaya Rp':>12}{'tiba mnt':>10}{'terakhir':>10}"
          f"{'Granmax':>9}{'feasible':>10}")
    for (sc, v), r in sorted(best.items()):
        print(f"{sc:14}{v:>6}{r['cost_rp']:>12,.0f}{r['mean_arrival_min']:>10.1f}"
              f"{r['makespan_min']:>10.1f}{r['n_vehicles']:>9}{str(r['feasible']):>10}")

    qs = [1, 2, 3, 4]
    viz.plot_sensitivity(qs, {"Biaya bensin (ribu Rp)": [best[("kapasitas", q)]["cost_rp"] / 1000 for q in qs]},
                         out / "fig_sens_kapasitas_biaya.png",
                         "Pengaruh kapasitas Granmax pada biaya bensin",
                         "Maksimal sekolah per Granmax", "Biaya bensin total (ribu Rp)")
    viz.plot_sensitivity(qs, {"Rata-rata tiba": [best[("kapasitas", q)]["mean_arrival_min"] for q in qs],
                              "Sekolah terakhir": [best[("kapasitas", q)]["makespan_min"] for q in qs]},
                         out / "fig_sens_kapasitas_waktu.png",
                         "Pengaruh kapasitas Granmax pada waktu tiba",
                         "Maksimal sekolah per Granmax", "Menit sejak makanan berangkat")
    tfs = TRAFFIC_FACTORS
    viz.plot_sensitivity(tfs, {"Sekolah terakhir": [best[("macet", t)]["makespan_min"] for t in tfs],
                               "Rata-rata tiba": [best[("macet", t)]["mean_arrival_min"] for t in tfs]},
                         out / "fig_sens_macet.png",
                         "Pengaruh kemacetan (batas 180 menit)",
                         "Faktor kemacetan (waktu tempuh x)", "Menit sejak makanan berangkat",
                         hline=(180, "Batas 3 jam"))


if __name__ == "__main__":
    main()
