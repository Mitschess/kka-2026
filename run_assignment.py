"""Eksperimen Bagian B: penugasan sekolah -> SPPG dengan 8 algoritma pencarian lokal.
Rute di dalam tiap SPPG selalu dihitung optimal (Router, setara UCS/A* Bagian A).

Contoh:
  python run_assignment.py                          # semua instance, setting config.json
  python run_assignment.py --instances surabaya_6sppg --workers 4
  python run_assignment.py --quick                  # uji cepat (anggaran & seed kecil)
  python run_assignment.py --sweep EHC --seeds 10   # trade-off biaya vs waktu (semua bobot)

Hasil per instance di results/<instance>/ :
  ls_runs.csv            semua run (algoritma, seed, objektif, evaluasi, waktu)
  ls_summary.csv         ringkasan per algoritma (mean/std/best, tingkat sukses)
  ls_stat_tests.csv      uji Mann-Whitney U antar algoritma + koreksi Holm
  ls_best.json           penugasan & rute terbaik tiap algoritma
  ls_best_routes.txt     rute terbaik dalam bahasa manusia
  fig_ls_boxplot.png, fig_ls_konvergensi.png, fig_rute_terbaik.png, peta_rute_terbaik.html
  ls_sweep.csv, fig_ls_pareto.png    (mode --sweep)
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

from mbgvrp import local_search as LS  # noqa: E402
from mbgvrp.problem import load_instance  # noqa: E402
from run_experiments import describe_routes, load_checkpoint, write_csv  # noqa: E402

_CACHE = {}
TOL = 1e-9


def _instance(name, config):
    if name not in _CACHE:
        _CACHE[name] = load_instance(ROOT, name, config)
    return _CACHE[name]


def task(name, config, algo, w, seed, budget):
    inst = _instance(name, config)
    params = config["assignment"]["algorithms"][algo]
    # seed yang sama -> penugasan awal acak yang sama untuk semua algoritma
    res = LS.run(algo, inst, w, config["experiment"]["penalty"], budget,
                 np.random.default_rng(seed), **params)
    ev = res.evaluation
    row = {"instance": name, "algorithm": algo, "w": w, "seed": seed, "fitness": res.fitness,
           "cost_rp": ev.cost, "mean_arrival_min": ev.mean_arrival, "makespan_min": ev.makespan,
           "km": ev.km, "liter": ev.km / inst.km_per_liter, "n_vehicles": ev.n_vehicles,
           "feasible": ev.feasible, "runtime_s": res.runtime_s, "n_evals": res.n_evals,
           "evals_to_best": res.extra.get("evals_to_best", 0), "stopped": res.extra["stopped"],
           "restarts": res.extra.get("restarts", 0), "steps": res.extra.get("steps", 0),
           "router_subproblems": res.extra["router_subproblems"]}
    return row, res.routes, res.assignment, res.history


def greedy_reference(inst, w, penalty):
    from mbgvrp import algorithms as A
    res = A.run_greedy(inst, w, penalty)
    return res.fitness, res.routes, res.evaluation


def run_parallel(jobs, ckpt, workers, label):
    done = load_checkpoint(ckpt)
    results = {key: done[key] for key, _ in jobs if key in done}
    if results:
        print(f"  {label}: melanjutkan, {len(results)}/{len(jobs)} run sudah ada di checkpoint")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool, open(ckpt, "ab") as fck:
        futures = {pool.submit(task, *args): key for key, args in jobs if key not in results}
        for fut in as_completed(futures):
            key = futures[fut]
            results[key] = fut.result()
            pickle.dump((key, results[key]), fck)
            fck.flush()
            print(f"\r  {label}: {len(results)}/{len(jobs)} run selesai ({time.time() - t0:.0f} s)",
                  end="", flush=True)
    print()
    return results


# ---------------------------------------------------------------------- pelaporan
def summarize(rows, best_known):
    out = []
    for algo in dict.fromkeys(r["algorithm"] for r in rows):
        rs = [r for r in rows if r["algorithm"] == algo]
        f = np.array([r["fitness"] for r in rs])
        out.append({
            "algorithm": algo, "runs": len(rs),
            "fitness_mean": f.mean(), "fitness_std": f.std(ddof=1) if len(rs) > 1 else 0.0,
            "fitness_best": f.min(), "fitness_median": float(np.median(f)), "fitness_worst": f.max(),
            "success_rate": float(np.mean(f <= best_known * (1 + TOL))),
            "gap_mean_pct": float(np.mean((f - best_known) / best_known * 100)),
            "cost_rp_mean": np.mean([r["cost_rp"] for r in rs]),
            "mean_arrival_min_mean": np.mean([r["mean_arrival_min"] for r in rs]),
            "makespan_min_mean": np.mean([r["makespan_min"] for r in rs]),
            "feasible_rate": np.mean([r["feasible"] for r in rs]),
            "n_evals_mean": np.mean([r["n_evals"] for r in rs]),
            "evals_to_best_median": float(np.median([r["evals_to_best"] for r in rs])),
            "local_optimum_stop_rate": np.mean([r["stopped"] == "optimum lokal" for r in rs]),
            "restarts_mean": np.mean([r["restarts"] for r in rs]),
            "runtime_s_mean": np.mean([r["runtime_s"] for r in rs]),
        })
    return out


def stat_tests(rows, algos):
    from scipy.stats import mannwhitneyu
    tests = []
    for i, a in enumerate(algos):
        for b in algos[i + 1:]:
            fa = [r["fitness"] for r in rows if r["algorithm"] == a]
            fb = [r["fitness"] for r in rows if r["algorithm"] == b]
            if np.allclose(fa, fa[0]) and np.allclose(fb, fa[0]):
                stat, p = len(fa) * len(fb) / 2, 1.0   # semua run identik
            else:
                stat, p = mannwhitneyu(fa, fb, alternative="two-sided")
            ma, mb = np.mean(fa), np.mean(fb)
            tests.append({"pair": f"{a} vs {b}", "U": stat, "p_value": p, "mean_a": ma, "mean_b": mb,
                          "better_mean": a if ma < mb - TOL else (b if mb < ma - TOL else "seri")})
    order = sorted(range(len(tests)), key=lambda k: tests[k]["p_value"])
    running = 0.0
    for rank, k in enumerate(order):
        running = max(running, min(1.0, (len(tests) - rank) * tests[k]["p_value"]))
        tests[k]["p_holm"] = running
        tests[k]["significant_5pct"] = running < 0.05
    return tests


def report(name, config, results, budget, out):
    from mbgvrp import viz

    inst = _instance(name, config)
    w0 = config["experiment"]["main_weight"]
    penalty = config["experiment"]["penalty"]
    algos = [a for a in config["assignment"]["algorithms"]]

    rows, routes_of, assign_of, hist = [], {}, {}, defaultdict(list)
    for (algo, w, seed), (row, routes, x, h) in results.items():
        rows.append(row)
        routes_of[(algo, seed)], assign_of[(algo, seed)] = routes, x
        hist[algo].append(h)
    rows.sort(key=lambda r: (algos.index(r["algorithm"]), r["seed"]))
    best_known = min(r["fitness"] for r in rows)

    write_csv(out / "ls_runs.csv", rows)
    summary = summarize(rows, best_known)
    write_csv(out / "ls_summary.csv", summary)
    tests = stat_tests(rows, algos)
    write_csv(out / "ls_stat_tests.csv", tests)

    g_fit, g_routes, g_ev = greedy_reference(inst, w0, penalty)
    best = {}
    for a in algos:
        r = min((r for r in rows if r["algorithm"] == a), key=lambda r: (r["fitness"], r["seed"]))
        routes = routes_of[(a, r["seed"])]
        best[a] = (routes, inst.evaluate(routes), r["fitness"], assign_of[(a, r["seed"])], r["seed"])
    best_json = {"best_known_fitness": best_known,
                 "Greedy": {"routes": [[int(d), [int(s) for s in seq]] for d, seq in g_routes],
                            "fitness": g_fit, "cost_rp": g_ev.cost, "km": g_ev.km,
                            "mean_arrival_min": g_ev.mean_arrival, "makespan_min": g_ev.makespan,
                            "n_vehicles": g_ev.n_vehicles}}
    for a, (routes, ev, fit, x, seed) in best.items():
        best_json[a] = {"routes": [[int(d), [int(s) for s in seq]] for d, seq in routes],
                        "assignment": [int(v) for v in x], "seed": seed, "fitness": fit,
                        "cost_rp": ev.cost, "km": ev.km, "mean_arrival_min": ev.mean_arrival,
                        "makespan_min": ev.makespan, "n_vehicles": ev.n_vehicles}
    (out / "ls_best.json").write_text(json.dumps(best_json, indent=1), encoding="utf-8")

    top = min(algos, key=lambda a: (best[a][2], algos.index(a)))
    with open(out / "ls_best_routes.txt", "w", encoding="utf-8") as f:
        f.write(f"Instance {name}: {inst.m} SPPG, {inst.n} sekolah, {inst.R} Granmax, "
                f"maks {inst.Q} sekolah/kendaraan, bobot w = {w0}\n")
        f.write("Bagian B (penugasan sekolah -> SPPG, pencarian lokal) + rute optimal per SPPG\n\n")
        items = [("Greedy (baseline)", g_routes, g_ev, g_fit)]
        items += [(a, best[a][0], best[a][1], best[a][2]) for a in algos]
        for label, routes, ev, fit in items:
            f.write(f"== {label}: Rp{ev.cost:,.0f} ({ev.km:.2f} km, {ev.km / inst.km_per_liter:.2f} L), "
                    f"rata-rata tiba {ev.mean_arrival:.1f} mnt, terakhir {ev.makespan:.1f} mnt, "
                    f"{ev.n_vehicles} Granmax, fitness {fit:.4f}\n")
            f.write(describe_routes(inst, routes) + "\n\n")

    title_inst = f"{name} ({inst.m} SPPG, {inst.n} sekolah)"
    finals = [r["fitness"] for r in rows]
    spread = max(finals) - best_known
    zoom = (best_known - 0.0003, best_known + 0.004) if spread > 0.01 else None
    viz.plot_boxplot({a: [r["fitness"] for r in rows if r["algorithm"] == a] for a in algos}, None,
                     out / "fig_ls_boxplot.png",
                     f"Fitness akhir {len(rows) // len(algos)} seed, w = {w0} — {title_inst}",
                     colors=viz.LS_COLORS, figsize=(8.5, 4.8), rotate=25, zoom=zoom)
    viz.plot_convergence_log(dict(hist), budget, g_fit, "Greedy", out / "fig_ls_konvergensi.png",
                             f"Konvergensi Bagian B, w = {w0} — {title_inst}", viz.LS_COLORS,
                             inset=(5e3, budget * 1.1, best_known - 0.001, best_known + 0.03) if zoom else None,
                             styles={"HC-Sideways": (0, (4, 3))})
    routes, ev = best[top][0], best[top][1]
    viz.plot_routes_static(inst, routes, out / "fig_rute_terbaik.png",
                           f"Rute terbaik ({top}): Rp{ev.cost:,.0f}, rata-rata {ev.mean_arrival:.1f} mnt")
    viz.map_routes_html(inst, {f"Terbaik ({top})": (routes, ev), "Greedy": (g_routes, g_ev)},
                        out / "peta_rute_terbaik.html", cache_path=out / ".osrm_cache.json")

    print(f"\n=== {name}: Bagian B, w = {w0}, best-known F = {best_known:.4f} "
          f"(Greedy {g_fit:.4f}) ===")
    print(f"{'algo':16}{'mean +- std':>19}{'best':>9}{'sukses':>8}{'evals':>9}{'ke-best':>9}{'detik':>8}")
    for s in summary:
        print(f"{s['algorithm']:16}{s['fitness_mean']:>10.4f} +- {s['fitness_std']:<6.4f}"
              f"{s['fitness_best']:>9.4f}{s['success_rate']:>8.0%}{s['n_evals_mean']:>9.0f}"
              f"{s['evals_to_best_median']:>9.0f}{s['runtime_s_mean']:>8.1f}")
    sig = [t for t in tests if t["significant_5pct"]]
    print(f"{len(sig)}/{len(tests)} pasangan berbeda signifikan (Holm 5%)")


def report_sweep(name, config, algo, results, out):
    from mbgvrp import viz
    from mbgvrp.metrics import nondominated

    inst = _instance(name, config)
    rows = sorted((r for r, *_ in results.values()), key=lambda r: (r["w"], r["seed"]))
    write_csv(out / "ls_sweep.csv", rows)
    pts = []
    for w in config["experiment"]["weights"]:
        r = min((r for r in rows if r["w"] == w), key=lambda r: r["fitness"])
        pts.append((r["cost_rp"], r["mean_arrival_min"], w))
    front_file = out / "nsga2_front.csv"
    front = []
    if front_file.exists():
        with open(front_file, encoding="utf-8") as f:
            front = [(float(r["cost_rp"]), float(r["mean_arrival_min"])) for r in csv.DictReader(f)]
    viz.plot_pareto(nondominated(front) if front else [], {algo: pts},
                    out / "fig_ls_pareto.png",
                    f"Trade-off biaya vs waktu: {algo} + rute optimal vs NSGA-II — {name}")
    print(f"\n=== {name}: sweep {algo} ===")
    for c, t, w in pts:
        print(f"  w = {w:4}: Rp{c:,.0f}, rata-rata tiba {t:.2f} mnt")


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg = config["assignment"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", nargs="*", default=list(config["instances"]))
    ap.add_argument("--seeds", type=int, default=cfg["n_seeds"])
    ap.add_argument("--budget", type=int, default=cfg["budget_evals"])
    ap.add_argument("--workers", type=int, default=min(4, max(1, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--quick", action="store_true", help="anggaran 20000, 3 seed (uji cepat)")
    ap.add_argument("--sweep", metavar="ALGO", help="jalankan ALGO di semua bobot (trade-off)")
    args = ap.parse_args()
    if args.quick:
        args.seeds, args.budget = 3, 20000
    print(f"seed = {args.seeds}, anggaran = {args.budget} evaluasi/run, worker = {args.workers}")
    w0 = config["experiment"]["main_weight"]
    for name in args.instances:
        out = ROOT / "results" / name
        out.mkdir(parents=True, exist_ok=True)
        if args.sweep:
            jobs = [((args.sweep, w, s), (name, config, args.sweep, w, s, args.budget))
                    for w in config["experiment"]["weights"] for s in range(1, args.seeds + 1)]
            ckpt = out / f".ls_sweep_{args.sweep}_s{args.seeds}_b{args.budget}.pkl"
            results = run_parallel(jobs, ckpt, args.workers, name)
            report_sweep(name, config, args.sweep, results, out)
            continue
        # algoritma terlama dikirim duluan agar beban worker seimbang
        slow_first = ["SA", "GA"] + [a for a in cfg["algorithms"] if a not in ("SA", "GA")]
        jobs = [((a, w0, s), (name, config, a, w0, s, args.budget))
                for a in slow_first for s in range(1, args.seeds + 1)]
        ckpt = out / f".ls_checkpoint_s{args.seeds}_b{args.budget}.pkl"
        results = run_parallel(jobs, ckpt, args.workers, name)
        report(name, config, results, args.budget, out)


if __name__ == "__main__":
    main()
