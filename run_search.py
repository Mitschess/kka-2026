"""Eksperimen Bagian A: routing di dalam satu SPPG dengan algoritma pencarian
(BFS, IDS, DFS-B&B, UCS, A* (h1), A*, GBFS).

A1. Sub-masalah nyata: sekolah milik tiap SPPG pada solusi terbaik Bagian B
    (results/<instance>/ls_best.json, jadi jalankan run_assignment.py dulu).
A2. Skalabilitas: k = 3..12 sekolah acak dari sekolah terdekat tiap SPPG
    (armada 3 Granmax; untuk k > 9 armada dinaikkan ke ceil(k/3)).

Contoh:  python run_search.py --workers 4
Hasil:   results/search_real.csv, results/search_scaling.csv, results/search_summary.csv,
         results/fig_search_scaling.png, results/fig_search_gap.png
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mbgvrp.problem import load_instance  # noqa: E402
from mbgvrp.router import Router  # noqa: E402
from mbgvrp.search import SEARCHES, RoutingProblem  # noqa: E402
from run_experiments import write_csv  # noqa: E402

_CACHE = {}


def _instance(name, config):
    if name not in _CACHE:
        _CACHE[name] = load_instance(ROOT, name, config)
    return _CACHE[name]


def task(name, config, meta, depot, schools, vehicles, algo, max_nodes):
    inst = _instance(name, config)
    w, penalty = config["experiment"]["main_weight"], config["experiment"]["penalty"]
    router = Router(inst, w, penalty)
    router.V[depot] = vehicles
    opt = router.cost(depot, sum(1 << s for s in schools))
    res = SEARCHES[algo](RoutingProblem(inst, depot, schools, w, vehicles), max_nodes=max_nodes)
    ok = res.status == "ok" or (res.status == "batas" and res.routes)
    gap = (res.cost - opt) / opt * 100 if ok else float("nan")
    if algo in ("UCS", "A*", "A* (h1)") and res.status == "ok":
        assert abs(gap) < 1e-6, f"{algo} tidak optimal: {res.cost} vs {opt}"
    row = dict(meta)
    row.update({"instance": name, "depot": inst.nodes[depot]["id"], "k": len(schools),
                "vehicles": vehicles, "algorithm": algo, "status": res.status,
                "cost": res.cost, "optimum": opt, "gap_pct": gap,
                "optimal": bool(ok and abs(gap) < 1e-6), "expanded": res.expanded,
                "generated": res.generated, "max_stored": res.max_stored,
                "runtime_s": res.runtime_s, "n_trips": len(res.routes)})
    return row


def run_all(jobs, workers):
    rows, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(task, *args) for args in jobs]
        for k, fut in enumerate(as_completed(futs), start=1):
            rows.append(fut.result())
            print(f"\r  {k}/{len(futs)} pencarian selesai ({time.time() - t0:.0f} s)", end="", flush=True)
    print()
    return rows


def plots(config, algos, summary, scaling, real):
    from mbgvrp import viz
    cfg = config["search"]
    per_k = len(scaling) // len(algos) // len(cfg["scaling_k"])
    viz.plot_search_scaling(summary, ROOT / "results" / "fig_search_scaling.png",
                            f"Skalabilitas pencarian di dalam satu SPPG ({cfg['scaling_instance']}, "
                            f"{per_k} sub-masalah per k)")
    small = [r for r in scaling + real if r["k"] <= 9]
    viz.plot_search_gap({a: [r["gap_pct"] for r in small if r["algorithm"] == a] for a in algos},
                        ROOT / "results" / "fig_search_gap.png",
                        "Selisih biaya terhadap optimum (sub-masalah k <= 9)")


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    cfg = config["search"]
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=min(4, max(1, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--max-nodes", type=int, default=cfg["max_nodes"])
    ap.add_argument("--skip-scaling", action="store_true")
    ap.add_argument("--plots-only", action="store_true", help="gambar ulang grafik dari CSV yang ada")
    args = ap.parse_args()
    algos = list(SEARCHES)
    order = {a: i for i, a in enumerate(algos)}
    if args.plots_only:
        import csv
        read = lambda f: [{k: (float(v) if k not in ("instance", "depot", "algorithm", "status", "part", "optimal") else v)  # noqa: E731
                           for k, v in r.items()} for r in csv.DictReader(open(ROOT / "results" / f, encoding="utf-8"))]
        plots(config, algos, read("search_summary.csv"), read("search_scaling.csv"), read("search_real.csv"))
        return

    # ---- A1: sub-masalah nyata dari solusi terbaik Bagian B
    jobs = []
    for name in config["instances"]:
        inst = _instance(name, config)
        best = json.loads((ROOT / "results" / name / "ls_best.json").read_text(encoding="utf-8"))
        top = min((k for k in best if k not in ("best_known_fitness", "Greedy")),
                  key=lambda k: best[k]["fitness"])
        per = defaultdict(list)
        for d, seq in best[top]["routes"]:
            per[d].extend(seq)
        for d, schools in sorted(per.items()):
            meta = {"part": "nyata", "sample": 0}
            jobs += [(name, config, meta, d, sorted(schools), inst.vehicles_per_depot[d], a, args.max_nodes)
                     for a in algos]
    real = sorted(run_all(jobs, args.workers),
                  key=lambda r: (r["instance"], r["depot"], order[r["algorithm"]]))
    write_csv(ROOT / "results" / "search_real.csv", real)

    print(f"\n{'algoritma':10}{'optimal':>9}{'gap rata2':>11}{'ekspansi':>11}{'memori maks':>13}{'detik':>9}")
    for a in algos:
        rs = [r for r in real if r["algorithm"] == a]
        print(f"{a:10}{sum(r['optimal'] for r in rs):>5}/{len(rs):<3}{np.nanmean([r['gap_pct'] for r in rs]):>10.1f}%"
              f"{sum(r['expanded'] for r in rs):>11}{max(r['max_stored'] for r in rs):>13}"
              f"{sum(r['runtime_s'] for r in rs):>9.2f}")
    if args.skip_scaling:
        return

    # ---- A2: skalabilitas
    name = cfg["scaling_instance"]
    inst = _instance(name, config)
    rng = np.random.default_rng(2026)
    jobs = []
    for d in range(inst.m):
        pool = np.argsort(inst.D[d, inst.m:])[:cfg["scaling_pool"]].tolist()
        for k in cfg["scaling_k"]:
            vehicles = max(inst.vehicles_per_depot[d], -(-k // inst.Q))
            for i in range(cfg["scaling_samples"]):
                schools = sorted(int(s) for s in rng.choice(pool, k, replace=False))
                meta = {"part": "skala", "sample": i}
                jobs += [(name, config, meta, d, schools, vehicles, a, args.max_nodes) for a in algos]
    # pekerjaan terberat (k besar) dikirim duluan
    jobs.sort(key=lambda j: -len(j[4]))
    scaling = sorted(run_all(jobs, args.workers),
                     key=lambda r: (r["k"], r["depot"], r["sample"], order[r["algorithm"]]))
    write_csv(ROOT / "results" / "search_scaling.csv", scaling)

    summary = []
    for k in cfg["scaling_k"]:
        for a in algos:
            rs = [r for r in scaling if r["k"] == k and r["algorithm"] == a]
            solved = [r for r in rs if r["status"] == "ok"]
            summary.append({
                "k": k, "algorithm": a, "runs": len(rs), "solved_rate": len(solved) / len(rs),
                "optimal_rate": np.mean([r["optimal"] for r in rs]),
                "gap_mean_pct": float(np.nanmean([r["gap_pct"] for r in solved])) if solved else float("nan"),
                "expanded_median": float(np.median([r["expanded"] for r in rs])),
                "generated_median": float(np.median([r["generated"] for r in rs])),
                "max_stored_median": float(np.median([r["max_stored"] for r in rs])),
                "runtime_s_median": float(np.median([r["runtime_s"] for r in rs])),
            })
    write_csv(ROOT / "results" / "search_summary.csv", summary)

    plots(config, algos, summary, scaling, real)

    print(f"\n{'k':>3} " + "".join(f"{a:>11}" for a in algos) + "   (median node diekspansi; * = ada yang kena batas)")
    for k in cfg["scaling_k"]:
        cells = []
        for a in algos:
            s = next(x for x in summary if x["k"] == k and x["algorithm"] == a)
            cells.append(f"{s['expanded_median']:>10.0f}{'*' if s['solved_rate'] < 1 else ' '}")
        print(f"{k:>3} " + "".join(cells))


if __name__ == "__main__":
    main()
