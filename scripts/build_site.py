"""Kumpulkan hasil (animasi, peta, grafik) ke folder site/ untuk hosting statis (Vercel dll).

Halaman depan (src/mbgvrp/site_template.html) interaktif: peta rute tiap algoritma pencarian
(BFS, IDS, DFS-B&B, UCS, A* h1, A* h2, GBFS) di jalan asli, grafik perbandingan, dan grafik skalabilitas.
Semua angka dibaca dari hasil yang sudah ada; tidak ada pencarian yang dijalankan ulang.
Jalankan setelah run_search.py dan make_animation.py:
  python scripts/build_site.py
Deploy:
  vercel deploy site --prod
"""
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
TEMPLATE = ROOT / "src" / "mbgvrp" / "site_template.html"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from make_animation import RECORDERS, simplify  # noqa: E402
from mbgvrp.problem import load_instance  # noqa: E402
from mbgvrp.viz import DEPOT_COLORS, SEARCH_ORDER  # noqa: E402

REFERENCE = "A*"                                     # rute terbaik (optimal) acuan
ROUTE_ORDER = ["UCS", "A*", "A* (h1)", "DFS-B&B", "IDS", "BFS", "GBFS"]
ROUTE_LABEL = {"A*": "A* (h2)", "DFS-B&B": "DFS + B&B", "GBFS": "Greedy best-first"}
ROUTE_OPTIMAL = {"UCS", "A*", "A* (h1)", "DFS-B&B"}   # menjamin solusi optimal bila selesai
ROUTE_DESC = {
    "UCS": "Selalu mengekspansi node dengan biaya jalur g(n) terkecil. Optimal; dipakai sebagai acuan selisih.",
    "A*": "f = g + h2. h2 = relaksasi penugasan sekolah ke slot Granmax (algoritma Hungaria): admissible "
          "dan tajam, jadi node yang diekspansi jauh lebih sedikit.",
    "A* (h1)": "f = g + h1. h1 = jalan masuk termurah ke tiap sekolah tersisa (admissible). Optimal, "
               "tapi heuristiknya lemah sehingga hampir seperti UCS.",
    "DFS-B&B": "Telusuri dalam-dulu, simpan solusi terbaik, pangkas cabang yang biayanya sudah ≥ solusi itu. "
               "Optimal bila selesai sebelum batas node.",
    "IDS": "DFS berulang dengan batas kedalaman yang terus naik: hasilnya sama dengan BFS dengan memori "
           "kecil, tapi banyak node diulang.",
    "BFS": "Telusuri lapis demi lapis (FIFO). Menemukan solusi dengan langkah paling sedikit, yaitu Granmax "
           "paling sedikit, bukan yang termurah.",
    "GBFS": "Hanya mengikuti heuristik h(n) dan mengabaikan g(n). Sangat cepat, tapi rutenya bisa jauh "
            "dari optimal.",
}
TITLES = {"surabaya_utara": ("Surabaya Utara", "Utara"), "surabaya_6sppg": ("Surabaya 6 SPPG", "6 SPPG")}

ROUTE_FILES = {"txt": "rute_terbaik.txt", "folium": "peta_rute_terbaik.html", "anim": "animasi.html"}
SEARCH_FIGS = [
    ("fig_search_scaling.png", "Grafik skalabilitas (PNG)"),
    ("fig_search_gap.png", "Grafik selisih biaya (PNG)"),
]
ANALYTICS = ('<script>\n'
             '  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };\n'
             '</script>\n'
             '<script defer src="/_vercel/insights/script.js"></script>\n')


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def algo_slug(algo):
    return {"A* (h1)": "astar_h1", "A*": "astar_h2", "DFS-B&B": "dfs_bb"}.get(algo, algo.lower())


def search_stats(rows):
    """Statistik pencarian satu algoritma, dijumlahkan dari semua SPPG di instance."""
    gaps = [g for g in (float(r["gap_pct"]) for r in rows) if g == g]   # buang nan
    return {
        "expanded": sum(int(r["expanded"]) for r in rows),
        "max_stored": max(int(r["max_stored"]) for r in rows),
        "runtime_s": sum(float(r["runtime_s"]) for r in rows),
        "gap_mean_pct": sum(gaps) / len(gaps) if gaps else 0.0,
        "optimal_rate": sum(r["optimal"] == "True" for r in rows) / len(rows),
        "limit": any(r["status"] != "ok" for r in rows),
    }


def status(algo, stats):
    if algo in ROUTE_OPTIMAL:
        return "limit" if stats["limit"] else "optimal"
    return "optimal" if stats["optimal_rate"] == 1 else "suboptimal"


def vehicles(inst, routes):
    """Jadwal tiap Granmax untuk tampilan: waktu tiba tiap sekolah, km, dan biaya bensin."""
    out = []
    for d, seq in routes:
        if not seq:
            continue
        t, prev, km, stops = 0.0, d, 0.0, []
        for s in seq:
            i = inst.m + s
            t += inst.T[prev, i]
            km += inst.D[prev, i]
            stops.append([int(s), round(float(t), 2)])
            t += inst.service
            prev = i
        if inst.return_to_depot:
            km += inst.D[prev, d]
        out.append({"d": int(d), "stops": stops, "km": round(float(km), 3), "cost": round(float(km * inst.cost_per_km))})
    return out


def road_legs(src, inst, algos):
    """Geometri jalan asli (OSRM, dari cache make_animation) untuk setiap ruas rute yang ditampilkan."""
    cache_path = src / ".osrm_legs_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    pairs = set()
    for a in algos:
        for v in a["vehicles"]:
            idx = [v["d"]] + [inst.m + s for s, _ in v["stops"]] + [v["d"]]
            pairs.update(zip(idx[:-1], idx[1:]))
    legs = {f"{a}-{b}": simplify(cache[f"{a}-{b}"]) for a, b in sorted(pairs) if f"{a}-{b}" in cache}
    if len(legs) < len(pairs):
        print(f"  {src.name}: {len(pairs) - len(legs)} ruas tanpa geometri jalan -> garis lurus "
              "(jalankan make_animation.py untuk mengisi cache)")
    return legs


def instance_data(name, cfg, search_rows):
    src, dst = ROOT / "results" / name, SITE / name
    dst.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, fn in ROUTE_FILES.items():
        if (src / fn).exists():
            shutil.copy2(src / fn, dst / fn)
            files[key] = f"{name}/{fn}"

    inst = load_instance(ROOT, name, cfg)
    summary = json.loads((src / "rute_algoritma.json").read_text(encoding="utf-8"))
    algos = []
    for order, a in enumerate(ROUTE_ORDER):
        if a not in summary:
            continue
        r = summary[a]
        rows = [x for x in search_rows if x["instance"] == name and x["algorithm"] == a]
        stats = search_stats(rows)
        vs = vehicles(inst, r["routes"])
        png = f"fig_rute_{algo_slug(a)}.png"
        if (src / png).exists():
            shutil.copy2(src / png, dst / png)
        algos.append({
            "key": a, "label": ROUTE_LABEL.get(a, a), "slot": SEARCH_ORDER.index(a) + 1, "order": order,
            "desc": ROUTE_DESC[a], "status": status(a, stats), "note": r["note"],
            "cost_rp": r["cost_rp"], "km": r["km"], "n_vehicles": r["n_vehicles"],
            "mean_arrival_min": r["mean_arrival_min"], "served": r["served"],
            "makespan_min": max((t for v in vs for _, t in v["stops"]), default=0.0),
            "search": stats, "vehicles": vs, "png": f"{name}/{png}" if (dst / png).exists() else None,
        })
    title, short = TITLES.get(name, (name, name))
    return {
        "name": name, "title": title, "short": short, "m": inst.m, "n": inst.n,
        "nodes": [{"id": n["id"], "name": n["name"], "lat": round(n["lat"], 6), "lon": round(n["lon"], 6)}
                  for n in inst.nodes],
        "legs": road_legs(src, inst, algos), "algos": algos, "files": files,
    }


def scaling_data(cfg):
    path = ROOT / "results" / "search_summary.csv"
    rows = read_csv(path) if path.exists() else []
    name = cfg["search"]["scaling_instance"]
    algos = []
    for a in SEARCH_ORDER:
        rs = [r for r in rows if r["algorithm"] == a]
        if rs:
            algos.append({"key": a, "label": ROUTE_LABEL.get(a, a), "slot": SEARCH_ORDER.index(a) + 1, "rows": [
                {"k": int(r["k"]), "expanded": float(r["expanded_median"]), "stored": float(r["max_stored_median"]),
                 "runtime": float(r["runtime_s_median"]), "solved": float(r["solved_rate"])} for r in rs]})
    return {"ks": cfg["search"]["scaling_k"], "algos": algos, "instance_title": TITLES.get(name, (name,))[0],
            "per_k": int(rows[0]["runs"]) if rows else 0}


def add_analytics(path):
    """Vercel Web Analytics di <head> (halaman hasil generator lain tidak memuatnya sendiri)."""
    text = path.read_text(encoding="utf-8")
    if "_vercel/insights" in text or "</head>" not in text:
        return
    i = text.index("</head>")
    path.write_text(text[:i] + ANALYTICS + text[i:], encoding="utf-8")


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    path = ROOT / "results" / "search_real.csv"
    search_rows = read_csv(path) if path.exists() else []
    SITE.mkdir(exist_ok=True)
    for p in SITE.iterdir():  # bersihkan hasil lama, tapi pertahankan link project Vercel
        if p.name == ".vercel":
            continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()

    figures = []
    for fn, caption in SEARCH_FIGS:  # grafik pencarian tidak spesifik per instance -> site/ root
        if (ROOT / "results" / fn).exists():
            shutil.copy2(ROOT / "results" / fn, SITE / fn)
            figures.append([fn, caption])

    instances = [instance_data(n, cfg, search_rows) for n in cfg["instances"]
                 if (ROOT / "results" / n / "rute_algoritma.json").exists()]
    biggest = max(instances, key=lambda i: i["n"])["name"]
    p = cfg["problem"]
    data = {
        "instances": instances, "default_instance": biggest, "hero_instance": biggest, "reference": REFERENCE,
        "depot_colors": DEPOT_COLORS, "anim_algos": list(RECORDERS), "figures": figures,
        "scaling": scaling_data(cfg), "max_nodes": cfg["search"]["max_nodes"],
        "params": {"Q": p["max_schools_per_vehicle"], "service": p["service_time_min"],
                   "max_time": p["max_delivery_time_min"], "km_per_liter": p["km_per_liter"],
                   "fuel_price": p["fuel_price_per_liter"], "w": cfg["search"]["weight"]},
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
    (SITE / "index.html").write_text(html, encoding="utf-8")

    for page in SITE.rglob("*.html"):
        add_analytics(page)
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"site/ siap: {sum(1 for p in SITE.rglob('*') if p.is_file())} file, {size / 1e6:.1f} MB "
          f"(index.html {(SITE / 'index.html').stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
