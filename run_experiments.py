"""Eksperimen utama: Greedy vs SA vs GA vs ACO (weighted sum) dan NSGA-II (Pareto).

Contoh:
  python run_experiments.py                          # semua instance, setting config.json
  python run_experiments.py --instances surabaya_utara --seeds 30
  python run_experiments.py --quick                  # uji cepat (budget & seed kecil)

Hasil per instance di results/<instance>/ :
  runs.csv               semua run (algoritma, bobot, seed, objektif, waktu komputasi)
  summary_main_w.csv     ringkasan mean/std/best pada bobot utama
  summary_all_w.csv      ringkasan untuk setiap bobot
  stat_tests.csv         uji Mann-Whitney U antar algoritma (bobot utama)
  hypervolume.csv        hypervolume weighted-sum (SA/GA/ACO) vs NSGA-II per seed
  nsga2_front.csv        Pareto front gabungan NSGA-II
  best_routes.txt        rute terbaik tiap algoritma dalam bahasa manusia
  fig_*.png, peta_rute.html
"""
import argparse
import csv
import json
import os
import pickle
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mbgvrp import algorithms as A  # noqa: E402
from mbgvrp.metrics import hypervolume_2d, nondominated  # noqa: E402
from mbgvrp.problem import load_instance  # noqa: E402

SINGLE = {"SA": A.run_sa, "GA": A.run_ga, "ACO": A.run_aco}
_CACHE = {}


def _instance(name, config):
    if name not in _CACHE:
        _CACHE[name] = load_instance(ROOT, name, config)
    return _CACHE[name]


def _row(inst, algorithm, w, seed, ev, fitness, runtime, n_evals):
    return {"instance": inst.name, "algorithm": algorithm, "w": w, "seed": seed,
            "fitness": fitness, "cost_rp": ev.cost, "mean_arrival_min": ev.mean_arrival,
            "makespan_min": ev.makespan, "km": ev.km, "liter": ev.km / inst.km_per_liter,
            "n_vehicles": ev.n_vehicles, "feasible": ev.feasible,
            "runtime_s": runtime, "n_evals": n_evals}


def task_single(name, config, algo, w, seed, budget):
    inst = _instance(name, config)
    penalty = config["experiment"]["penalty"]
    params = config["algorithms"].get(algo.lower(), {})
    if algo == "Greedy":
        res = A.run_greedy(inst, w, penalty)
    else:
        rng = np.random.default_rng(seed * 1000 + int(w * 100))
        res = SINGLE[algo](inst, w, penalty, budget=budget, rng=rng, **params)
    assert inst.check_complete(res.routes), f"{algo} tidak melayani semua sekolah"
    row = _row(inst, algo, w, seed, res.evaluation, res.fitness, res.runtime_s, res.n_evals)
    return row, res.routes, res.history


def task_nsga2(name, config, seed, budget):
    inst = _instance(name, config)
    rng = np.random.default_rng(seed * 1000 + 999)
    res = A.run_nsga2(inst, budget, rng, snapshot_every=10, **config["algorithms"]["nsga2"])
    front = [(routes, ev) for routes, ev in res.front]
    return seed, front, res.runtime_s, res.n_evals, res.snapshots


# ---------------------------------------------------------------------- pelaporan
def describe_routes(inst, routes):
    lines = []
    for v, (d, seq) in enumerate(routes, start=1):
        t, prev, km = 0.0, d, 0.0
        parts = [inst.nodes[d]["id"]]
        for s in seq:
            i = inst.m + s
            t += inst.T[prev, i]
            km += inst.D[prev, i]
            parts.append(f"{inst.school_name(s)} (tiba {t:.1f} mnt)")
            t += inst.service
            prev = i
        if inst.return_to_depot:
            km += inst.D[prev, d]
            parts.append("kembali")
        lines.append(f"  Granmax {v:>2}: " + " -> ".join(parts) +
                     f"  [{km:.2f} km, Rp{km * inst.cost_per_km:,.0f}]")
    return "\n".join(lines)


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows, keys):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    out = []
    for key, rs in groups.items():
        f = np.array([r["fitness"] for r in rs])
        entry = dict(zip(keys, key))
        entry.update({
            "runs": len(rs),
            "fitness_mean": f.mean(), "fitness_std": f.std(ddof=1) if len(rs) > 1 else 0.0,
            "fitness_best": f.min(), "fitness_worst": f.max(),
            "cost_rp_mean": np.mean([r["cost_rp"] for r in rs]),
            "mean_arrival_min_mean": np.mean([r["mean_arrival_min"] for r in rs]),
            "makespan_min_mean": np.mean([r["makespan_min"] for r in rs]),
            "km_mean": np.mean([r["km"] for r in rs]),
            "n_vehicles_mean": np.mean([r["n_vehicles"] for r in rs]),
            "feasible_rate": np.mean([r["feasible"] for r in rs]),
            "runtime_s_mean": np.mean([r["runtime_s"] for r in rs]),
        })
        out.append(entry)
    return out


def report(name, config, rows, routes_of, histories, nsga, out):
    # import berat hanya di proses utama (worker cukup numpy -> hemat RAM)
    from scipy.stats import mannwhitneyu

    from mbgvrp import viz

    inst = _instance(name, config)
    exp = config["experiment"]
    w0 = exp["main_weight"]
    algos = ["SA", "GA", "ACO"]
    fmt = lambda x: f"{x:.4f}"  # noqa: E731

    write_csv(out / "runs.csv", rows)
    main_rows = [r for r in rows if r["w"] == w0]
    write_csv(out / "summary_main_w.csv", summarize(main_rows, ["algorithm"]))
    write_csv(out / "summary_all_w.csv", summarize(rows, ["w", "algorithm"]))

    # uji statistik Mann-Whitney U (dua sisi) antar metaheuristik, bobot utama
    tests = []
    for i, a in enumerate(algos):
        for b in algos[i + 1:]:
            fa = [r["fitness"] for r in main_rows if r["algorithm"] == a]
            fb = [r["fitness"] for r in main_rows if r["algorithm"] == b]
            stat, p = mannwhitneyu(fa, fb, alternative="two-sided")
            better = a if np.median(fa) < np.median(fb) else b
            tests.append({"pair": f"{a} vs {b}", "U": stat, "p_value": p,
                          "median_a": np.median(fa), "median_b": np.median(fb),
                          "significant_5pct": p < 0.05, "better_median": better})
    write_csv(out / "stat_tests.csv", tests)

    # ---- hypervolume (objektif ternormalisasi terhadap ref_cost & ref_time)
    norm = lambda c, t: (c / inst.ref_cost, t / inst.ref_time)  # noqa: E731
    seeds = sorted({r["seed"] for r in rows if r["algorithm"] != "Greedy"})
    sets = defaultdict(dict)  # sets[algo][seed] = [(f1n, f2n)]
    for a in algos + ["Greedy"]:
        for s in (seeds if a != "Greedy" else [0]):
            sets[a][s] = [norm(r["cost_rp"], r["mean_arrival_min"]) for r in rows
                          if r["algorithm"] == a and r["seed"] == s and r["feasible"]]
    for s, front, *_ in nsga:
        sets["NSGA-II"][s] = [norm(ev.cost, ev.mean_arrival) for _, ev in front]
    all_pts = [p for a in sets for pts in sets[a].values() for p in pts]
    ref = (max(p[0] for p in all_pts) * 1.1, max(p[1] for p in all_pts) * 1.1)
    hv_rows = []
    for a in algos + ["NSGA-II", "Greedy"]:
        for s, pts in sorted(sets[a].items()):
            hv_rows.append({"algorithm": a, "seed": s, "hypervolume": hypervolume_2d(pts, ref),
                            "n_nondominated": len(nondominated(pts))})
    write_csv(out / "hypervolume.csv", hv_rows)

    # ---- front gabungan NSGA-II
    union = [(ev.cost, ev.mean_arrival, routes, ev) for _, front, *_ in nsga for routes, ev in front]
    nd = set(nondominated([(c, t) for c, t, *_ in union]))
    front_sol, seen = [], set()
    for c, t, routes, ev in sorted(union, key=lambda x: (x[0], x[1])):
        if (c, t) in nd and (c, t) not in seen:
            seen.add((c, t))
            front_sol.append((routes, ev))
    write_csv(out / "nsga2_front.csv", [
        {"cost_rp": ev.cost, "mean_arrival_min": ev.mean_arrival, "makespan_min": ev.makespan,
         "km": ev.km, "n_vehicles": ev.n_vehicles} for _, ev in front_sol])

    # ---- solusi terbaik tiap algoritma (bobot utama)
    best = {}
    for a in ["Greedy"] + algos:
        cand = [r for r in main_rows if r["algorithm"] == a]
        r = min(cand, key=lambda x: x["fitness"])
        routes = routes_of[(a, w0, r["seed"])]
        best[a] = (routes, inst.evaluate(routes), r["fitness"])
    # titik-titik khas NSGA-II: termurah, tercepat, dan "knee" (terdekat ke titik ideal)
    fn = np.array([norm(ev.cost, ev.mean_arrival) for _, ev in front_sol])
    ideal, nadir = fn.min(axis=0), fn.max(axis=0)
    scaled = (fn - ideal) / np.where(nadir > ideal, nadir - ideal, 1)
    knee = int(np.argmin(np.linalg.norm(scaled, axis=1)))
    picks = {"NSGA-II termurah": front_sol[0], "NSGA-II knee": front_sol[knee],
             "NSGA-II tercepat": front_sol[-1]}

    with open(out / "best_routes.txt", "w", encoding="utf-8") as f:
        f.write(f"Instance {name}: {inst.m} SPPG, {inst.n} sekolah, {inst.R} Granmax, "
                f"maks {inst.Q} sekolah/kendaraan\n")
        f.write(f"Bobot utama w = {w0} (w=1: murni bensin, w=0: murni waktu)\n\n")
        for label, (routes, ev, *rest) in list(best.items()) + [(k, v) for k, v in picks.items()]:
            fit = f", fitness {rest[0]:.4f}" if rest else ""
            f.write(f"== {label}: Rp{ev.cost:,.0f} ({ev.km:.2f} km, {ev.km / inst.km_per_liter:.2f} L), "
                    f"rata-rata tiba {ev.mean_arrival:.1f} mnt, terakhir {ev.makespan:.1f} mnt, "
                    f"{ev.n_vehicles} Granmax{fit}\n")
            f.write(describe_routes(inst, routes) + "\n\n")

    # ---- grafik
    title_inst = f"{name} ({inst.m} SPPG, {inst.n} sekolah)"
    greedy_f = best["Greedy"][2]
    viz.plot_convergence({a: histories[(a, w0)] for a in algos}, greedy_f,
                         out / "fig_konvergensi.png", f"Konvergensi, w = {w0} — {title_inst}")
    viz.plot_boxplot({a: [r["fitness"] for r in main_rows if r["algorithm"] == a] for a in algos},
                     greedy_f, out / "fig_boxplot.png",
                     f"Fitness akhir {len(seeds)} seed, w = {w0} — {title_inst}")
    ws_points = {}
    for a in ["Greedy"] + algos:
        pts = []
        for w in exp["weights"]:
            cand = [r for r in rows if r["algorithm"] == a and r["w"] == w and r["feasible"]]
            if cand:
                r = min(cand, key=lambda x: x["fitness"])
                pts.append((r["cost_rp"], r["mean_arrival_min"], w))
        ws_points[a] = pts
    viz.plot_pareto([(ev.cost, ev.mean_arrival) for _, ev in front_sol], ws_points,
                    out / "fig_pareto.png", f"Trade-off biaya bensin vs waktu — {title_inst}")
    for a, (routes, ev, _) in best.items():
        viz.plot_routes_static(inst, routes, out / f"fig_rute_{a}.png",
                               f"Rute {a} (w = {w0}): Rp{ev.cost:,.0f}, rata-rata {ev.mean_arrival:.1f} mnt")
    layers = {a: (routes, ev) for a, (routes, ev, _) in best.items()}
    layers.update(picks)
    viz.map_routes_html(inst, layers, out / "peta_rute.html", cache_path=out / ".osrm_cache.json")

    # ringkasan di terminal
    print(f"\n=== {name}: ringkasan w = {w0} ===")
    print(f"{'algo':8}{'fitness mean±std':>22}{'best':>9}{'biaya Rp':>12}{'tiba mnt':>10}{'feas':>6}{'detik':>8}")
    for s in summarize(main_rows, ["algorithm"]):
        print(f"{s['algorithm']:8}{fmt(s['fitness_mean']):>13} ± {fmt(s['fitness_std']):<7}"
              f"{fmt(s['fitness_best']):>9}{s['cost_rp_mean']:>12,.0f}{s['mean_arrival_min_mean']:>10.2f}"
              f"{s['feasible_rate']:>6.0%}{s['runtime_s_mean']:>8.1f}")
    hv = defaultdict(list)
    for r in hv_rows:
        hv[r["algorithm"]].append(r["hypervolume"])
    print("hypervolume (mean): " + ", ".join(f"{a} {np.mean(v):.4f}" for a, v in hv.items()))
    for t in tests:
        print(f"Mann-Whitney {t['pair']}: p = {t['p_value']:.4g} -> lebih baik: {t['better_median']}"
              f"{'' if t['significant_5pct'] else ' (tidak signifikan)'}")


def load_checkpoint(path):
    """Baca hasil run yang sudah tersimpan: {key: hasil}. Record terakhir yang
    terpotong (proses terhenti saat menulis) diabaikan."""
    done = {}
    if path.exists():
        with open(path, "rb") as f:
            while True:
                try:
                    key, res = pickle.load(f)
                except (EOFError, pickle.UnpicklingError, ValueError):
                    break
                done[key] = res
    return done


def run_instance(name, config, seeds, budget, workers):
    exp = config["experiment"]
    out = ROOT / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    nsga_budget = budget * len(exp["weights"])  # = total evaluasi 1 algoritma weighted-sum

    # tiap run yang selesai langsung disimpan, jadi kalau proses terhenti
    # (mis. RAM habis) menjalankan ulang perintah yang sama akan melanjutkan
    ckpt = out / f".checkpoint_s{seeds}_b{budget}.pkl"
    done = load_checkpoint(ckpt)

    jobs = [(("Greedy", w, 0), task_single, (name, config, "Greedy", w, 0, budget))
            for w in exp["weights"]]
    # task terlama (ACO, NSGA-II) dikirim duluan agar beban seimbang
    jobs += [(("NSGA-II", None, seed), task_nsga2, (name, config, seed, nsga_budget))
             for seed in range(1, seeds + 1)]
    jobs += [((algo, w, seed), task_single, (name, config, algo, w, seed, budget))
             for algo in ["ACO", "GA", "SA"] for w in exp["weights"] for seed in range(1, seeds + 1)]
    results = {key: done[key] for key, *_ in jobs if key in done}
    if results:
        print(f"  {name}: melanjutkan, {len(results)}/{len(jobs)} run sudah ada di checkpoint")

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool, open(ckpt, "ab") as fck:
        futures = {pool.submit(fn, *args): key for key, fn, args in jobs if key not in results}
        for fut in as_completed(futures):
            key = futures[fut]
            results[key] = fut.result()
            pickle.dump((key, results[key]), fck)
            fck.flush()
            print(f"\r  {name}: {len(results)}/{len(jobs)} run selesai ({time.time() - t0:.0f} s)",
                  end="", flush=True)
    print()

    rows, routes_of, histories, nsga = [], {}, defaultdict(list), []
    for res in results.values():
        if len(res) == 3:
            row, routes, hist = res
            rows.append(row)
            routes_of[(row["algorithm"], row["w"], row["seed"])] = routes
            if row["algorithm"] != "Greedy":
                histories[(row["algorithm"], row["w"])].append(hist)
        else:
            nsga.append(res)
    rows.sort(key=lambda r: (r["algorithm"], r["w"], r["seed"]))
    nsga.sort(key=lambda x: x[0])
    report(name, config, rows, routes_of, histories, nsga, out)


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    exp = config["experiment"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", nargs="*", default=list(config["instances"]))
    ap.add_argument("--seeds", type=int, default=exp["n_seeds"])
    ap.add_argument("--budget", type=int, default=exp["budget_evals"])
    ap.add_argument("--workers", type=int, default=min(8, max(1, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--quick", action="store_true", help="budget 2000, 3 seed (uji cepat)")
    args = ap.parse_args()
    if args.quick:
        args.seeds, args.budget = 3, 2000
    print(f"seed = {args.seeds}, budget = {args.budget} evaluasi/run, worker = {args.workers}")
    for name in args.instances:
        run_instance(name, config, args.seeds, args.budget, args.workers)


if __name__ == "__main__":
    main()
