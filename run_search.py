"""Eksperimen: rute terbaik di dalam satu SPPG dengan algoritma pencarian
(BFS, IDS, DFS-B&B, UCS, A* (h1), A*, GBFS).

A1. Sub-masalah nyata: sekolah dibagi ke SPPG terdekat (assign_nearest), lalu rute tiap
    SPPG dicari dengan ketujuh algoritma. Rute A* (optimal) disimpan sebagai rute terbaik.
A2. Skalabilitas: k = 3..12 sekolah acak dari sekolah terdekat tiap SPPG
    (armada 3 Granmax; untuk k > 9 armada dinaikkan ke ceil(k/3)).

Contoh:  python run_search.py --workers 4
Hasil:   results/search_real.csv, results/search_scaling.csv, results/search_summary.csv,
         results/fig_search_scaling.png, results/fig_search_gap.png,
         results/<instance>/rute_terbaik.json|txt, fig_rute_terbaik.png, peta_rute_terbaik.html
"""
import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mbgvrp import viz  # noqa: E402
from mbgvrp.problem import assign_nearest, load_instance  # noqa: E402
from mbgvrp.search import SEARCHES, RoutingProblem  # noqa: E402

_CACHE = {}
TEXT_COLS = ("instance", "depot", "algorithm", "status", "part", "optimal")


def _instance(name, config):
    if name not in _CACHE:
        _CACHE[name] = load_instance(ROOT, name, config)
    return _CACHE[name]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return [{k: (v if k in TEXT_COLS else float(v)) for k, v in r.items()} for r in csv.DictReader(f)]


def task(name, config, meta, depot, schools, vehicles, max_nodes):
    """Jalankan semua algoritma pada satu sub-masalah. Optimum acuan = biaya UCS."""
    inst = _instance(name, config)
    w = config["search"]["weight"]
    results = {a: fn(RoutingProblem(inst, depot, schools, w, vehicles), max_nodes=max_nodes)
               for a, fn in SEARCHES.items()}
    ucs = results["UCS"]
    opt = ucs.cost if ucs.status == "ok" else float("nan")
    rows = []
    for a, res in results.items():
        found = res.status == "ok" or (res.status == "batas" and res.routes)
        gap = (res.cost - opt) / opt * 100 if found else float("nan")
        if a in ("A*", "A* (h1)", "DFS-B&B") and res.status == "ok" and ucs.status == "ok":
            assert abs(gap) < 1e-6, f"{a} tidak optimal: {res.cost} vs {opt}"
        rows.append({**meta, "instance": name, "depot": inst.nodes[depot]["id"], "k": len(schools),
                     "vehicles": vehicles, "algorithm": a, "status": res.status,
                     "cost": res.cost, "optimum": opt, "gap_pct": gap,
                     "optimal": bool(found and abs(gap) < 1e-6), "expanded": res.expanded,
                     "generated": res.generated, "max_stored": res.max_stored,
                     "runtime_s": res.runtime_s, "n_trips": len(res.routes)})
    return rows, results["A*"].routes


def run_all(jobs, workers):
    out, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(task, *args): args for args in jobs}
        for k, fut in enumerate(as_completed(futs), start=1):
            out.append((futs[fut], *fut.result()))
            print(f"\r  {k}/{len(futs)} sub-masalah selesai ({time.time() - t0:.0f} s)", end="", flush=True)
    print()
    return out


def describe_routes(inst, routes):
    lines = []
    for v, (d, seq) in enumerate(routes, start=1):
        t, prev, km = 0.0, d, 0.0
        parts = [inst.nodes[d]["id"]]
        for s in seq:
            i = inst.m + s
            t += inst.T[prev, i]
            km += inst.D[prev, i]
            parts.append(f"{inst.nodes[i]['name']} (tiba {t:.1f} mnt)")
            t += inst.service
            prev = i
        if inst.return_to_depot:
            km += inst.D[prev, d]
            parts.append("kembali")
        lines.append(f"  Granmax {v:>2}: " + " -> ".join(parts) +
                     f"  [{km:.2f} km, Rp{km * inst.cost_per_km:,.0f}]")
    return "\n".join(lines)


def save_best_routes(name, config, routes):
    """Rute terbaik seluruh instance (A* per SPPG): JSON, teks, grafik statis, dan peta jalan."""
    inst = _instance(name, config)
    out = ROOT / "results" / name
    ev = inst.evaluate(routes)
    (out / "rute_terbaik.json").write_text(json.dumps({
        "routes": [[int(d), [int(s) for s in seq]] for d, seq in routes], "cost_rp": ev.cost,
        "km": ev.km, "mean_arrival_min": ev.mean_arrival, "makespan_min": ev.makespan,
        "n_vehicles": ev.n_vehicles}, indent=1), encoding="utf-8")
    (out / "rute_terbaik.txt").write_text(
        f"Instance {name}: {inst.m} SPPG, {inst.n} sekolah, maks {inst.Q} sekolah/Granmax\n"
        "Sekolah ke SPPG terdekat, rute optimal tiap SPPG (A*)\n\n"
        f"== Rp{ev.cost:,.0f} ({ev.km:.2f} km, {ev.km / inst.km_per_liter:.2f} L), "
        f"rata-rata tiba {ev.mean_arrival:.1f} mnt, terakhir {ev.makespan:.1f} mnt, "
        f"{ev.n_vehicles} Granmax\n{describe_routes(inst, routes)}\n", encoding="utf-8")
    viz.plot_routes_static(inst, routes, out / "fig_rute_terbaik.png",
                           f"Rute terbaik (A*): Rp{ev.cost:,.0f}, rata-rata {ev.mean_arrival:.1f} mnt")
    viz.map_routes_html(inst, {"Rute terbaik (A*)": (routes, ev)}, out / "peta_rute_terbaik.html",
                        cache_path=out / ".osrm_cache.json")


def plots(config, algos, summary, scaling, real):
    cfg = config["search"]
    per_k = len(scaling) // len(algos) // len(cfg["scaling_k"])
    viz.plot_search_scaling(summary, ROOT / "results" / "fig_search_scaling.png",
                            f"Skalabilitas pencarian di dalam satu SPPG ({cfg['scaling_instance']}, "
                            f"{per_k} sub-masalah per k)")
    small = [r for r in scaling + real if r["k"] <= 9]
    viz.plot_search_gap({a: [r["gap_pct"] for r in small if r["algorithm"] == a] for a in algos},
                        ROOT / "results" / "fig_search_gap.png",
                        "Selisih biaya terhadap optimum (sub-masalah k <= 9)")


def summarize_scaling(config, algos, scaling):
    summary = []
    for k in config["search"]["scaling_k"]:
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
    return summary


def run_real(config, algos, args):
    """A1: sub-masalah nyata per SPPG; menyimpan rute terbaik tiap instance."""
    jobs = []
    for name in config["instances"]:
        inst = _instance(name, config)
        owned = assign_nearest(inst)
        jobs += [(name, config, {"part": "nyata", "sample": 0}, d, schools, inst.vehicles_per_depot[d],
                  args.max_nodes) for d, schools in enumerate(owned) if schools]
    done = run_all(jobs, args.workers)
    order = {a: i for i, a in enumerate(algos)}
    real = sorted((r for _, rows, _ in done for r in rows),
                  key=lambda r: (r["instance"], r["depot"], order[r["algorithm"]]))
    write_csv(ROOT / "results" / "search_real.csv", real)
    for name in config["instances"]:
        routes = [rt for job, _, trips in done if job[0] == name for rt in trips]
        save_best_routes(name, config, routes)

    print(f"\n{'algoritma':10}{'optimal':>9}{'gap rata2':>11}{'ekspansi':>11}{'memori maks':>13}{'detik':>9}")
    for a in algos:
        rs = [r for r in real if r["algorithm"] == a]
        print(f"{a:10}{sum(r['optimal'] for r in rs):>5}/{len(rs):<3}{np.nanmean([r['gap_pct'] for r in rs]):>10.1f}%"
              f"{sum(r['expanded'] for r in rs):>11}{max(r['max_stored'] for r in rs):>13}"
              f"{sum(r['runtime_s'] for r in rs):>9.2f}")
    return real


def run_scaling(config, algos, args):
    """A2: skalabilitas, k = 3..12 pada sekolah terdekat tiap SPPG."""
    cfg = config["search"]
    inst = _instance(cfg["scaling_instance"], config)
    rng = np.random.default_rng(2026)
    jobs = []
    for d in range(inst.m):
        pool = np.argsort(inst.D[d, inst.m:])[:cfg["scaling_pool"]].tolist()
        for k in cfg["scaling_k"]:
            vehicles = max(inst.vehicles_per_depot[d], -(-k // inst.Q))
            for i in range(cfg["scaling_samples"]):
                schools = sorted(int(s) for s in rng.choice(pool, k, replace=False))
                jobs.append((cfg["scaling_instance"], config, {"part": "skala", "sample": i}, d, schools,
                             vehicles, args.max_nodes))
    jobs.sort(key=lambda j: -len(j[4]))     # pekerjaan terberat (k besar) dikirim duluan
    order = {a: i for i, a in enumerate(algos)}
    scaling = sorted((r for _, rows, _ in run_all(jobs, args.workers) for r in rows),
                     key=lambda r: (r["k"], r["depot"], r["sample"], order[r["algorithm"]]))
    write_csv(ROOT / "results" / "search_scaling.csv", scaling)
    summary = summarize_scaling(config, algos, scaling)
    write_csv(ROOT / "results" / "search_summary.csv", summary)

    print(f"\n{'k':>3} " + "".join(f"{a:>11}" for a in algos) + "   (median node diekspansi; * = ada yang kena batas)")
    for k in cfg["scaling_k"]:
        cells = []
        for a in algos:
            s = next(x for x in summary if x["k"] == k and x["algorithm"] == a)
            cells.append(f"{s['expanded_median']:>10.0f}{'*' if s['solved_rate'] < 1 else ' '}")
        print(f"{k:>3} " + "".join(cells))
    return scaling, summary


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=min(4, max(1, (os.cpu_count() or 2) - 1)))
    ap.add_argument("--max-nodes", type=int, default=config["search"]["max_nodes"])
    ap.add_argument("--skip-scaling", action="store_true")
    ap.add_argument("--plots-only", action="store_true", help="gambar ulang grafik dari CSV yang ada")
    args = ap.parse_args()
    algos = list(SEARCHES)
    if args.plots_only:
        res = ROOT / "results"
        plots(config, algos, read_csv(res / "search_summary.csv"), read_csv(res / "search_scaling.csv"),
              read_csv(res / "search_real.csv"))
        return
    real = run_real(config, algos, args)
    if not args.skip_scaling:
        scaling, summary = run_scaling(config, algos, args)
        plots(config, algos, summary, scaling, real)


if __name__ == "__main__":
    main()
