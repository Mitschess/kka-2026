"""Kumpulkan hasil (animasi, peta, grafik) ke folder site/ untuk hosting statis (Vercel dll).

Dua case ditampilkan per instance: Alokasi SPPG (Bagian B: HC, SA, GA) dan Rute terbaik
di dalam satu SPPG (Bagian A: BFS, UCS, A*, GBFS, DFS-B&B). Jalankan setelah
run_assignment.py, run_search.py dan make_animation.py:
  python scripts/build_site.py
Deploy:
  vercel deploy site --prod
"""
import csv
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

ALLOC_ORDER = ["HC", "SA", "GA"]
ROUTE_ORDER = ["UCS", "A*", "DFS-B&B", "BFS", "GBFS"]
ROUTE_LABEL = {"GBFS": "Greedy", "DFS-B&B": "DFS"}
ROUTE_OPTIMAL = {"UCS", "A*", "DFS-B&B"}   # menjamin solusi optimal

ALLOC_FILES = ["ls_best_routes.txt", "peta_rute_terbaik.html"]
ALLOC_FIGS = [
    ("fig_ls_tradeoff.png", "Trade-off biaya vs waktu: HC/SA/GA + rute optimal (sweep bobot w = 0 … 1)"),
    ("fig_ls_konvergensi.png", "Konvergensi HC, SA, GA (median 30 seed)"),
    ("fig_ls_boxplot.png", "Sebaran fitness akhir 30 seed"),
    ("fig_rute_terbaik.png", "Rute terbaik keseluruhan"),
]
SEARCH_FIGS = [
    ("fig_search_scaling.png", "Skalabilitas pencarian (node diekspansi vs jumlah sekolah k)"),
    ("fig_search_gap.png", "Selisih biaya terhadap optimum per algoritma (sub-masalah k ≤ 9)"),
]


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_search_real():
    path = ROOT / "results" / "search_real.csv"
    return read_csv(path) if path.exists() else []


def route_summary(rows, instance):
    out = []
    for a in ROUTE_ORDER:
        rs = [r for r in rows if r["instance"] == instance and r["algorithm"] == a]
        if not rs:
            continue
        gaps = []
        for r in rs:
            try:
                g = float(r["gap_pct"])
            except ValueError:
                continue
            if g == g:  # buang nan
                gaps.append(g)
        out.append({
            "algorithm": a, "label": ROUTE_LABEL.get(a, a), "n": len(rs),
            "optimal_rate": sum(r["optimal"] == "True" for r in rs) / len(rs),
            "gap_mean_pct": sum(gaps) / len(gaps) if gaps else 0.0,
            "expanded_sum": sum(int(r["expanded"]) for r in rs),
            "runtime_s_sum": sum(float(r["runtime_s"]) for r in rs),
        })
    return out


def alloc_table(src, name):
    summary = {r["algorithm"]: r for r in read_csv(src / "ls_summary.csv")}
    rows = [summary[a] for a in ALLOC_ORDER if a in summary]
    if not rows:
        return ""
    best = min(rows, key=lambda r: float(r["fitness_mean"]))
    trs = []
    for r in rows:
        cls = ' class="best"' if r is best else ""
        trs.append(f"<tr{cls}><td>{r['algorithm']}</td>"
                   f"<td>{float(r['fitness_mean']):.4f} ± {float(r['fitness_std']):.4f}</td>"
                   f"<td>Rp{float(r['cost_rp_mean']):,.0f}</td>"
                   f"<td>{float(r['mean_arrival_min_mean']):.1f} mnt</td>"
                   f"<td>{float(r['runtime_s_mean']):.1f} s</td></tr>")
    return f"""<div class=tablewrap><table>
    <thead><tr><th>Algoritma</th><th>Fitness (mean ± std)</th><th>Biaya bensin</th>
      <th>Rata-rata tiba</th><th>Waktu/run</th></tr></thead>
    <tbody>{''.join(trs)}</tbody>
  </table></div>"""


def route_table(rows):
    if not rows:
        return ""
    optimal_rows = [r for r in rows if r["algorithm"] in ROUTE_OPTIMAL]
    best = min(optimal_rows, key=lambda r: r["expanded_sum"]) if optimal_rows else min(rows, key=lambda r: r["gap_mean_pct"])
    trs = []
    for r in rows:
        cls = ' class="best"' if r is best else ""
        note = "optimal" if r["algorithm"] in ROUTE_OPTIMAL else f"{r['optimal_rate']:.0%} optimal"
        gap = 0.0 if abs(r["gap_mean_pct"]) < 0.05 else r["gap_mean_pct"]
        trs.append(f"<tr{cls}><td>{r['label']}</td><td>{note}</td>"
                   f"<td>{gap:.1f}%</td>"
                   f"<td>{r['expanded_sum']:,}</td><td>{r['runtime_s_sum'] * 1000:.1f} ms</td></tr>")
    return f"""<div class=tablewrap><table>
    <thead><tr><th>Algoritma</th><th>Status</th><th>Gap rata-rata</th>
      <th>Node diekspansi (total)</th><th>Waktu (total)</th></tr></thead>
    <tbody>{''.join(trs)}</tbody>
  </table></div>"""


def figs_html(name, src, dst, figs):
    out = []
    for fn, caption in figs:
        if (src / fn).exists():
            shutil.copy2(src / fn, dst / fn)
            out.append(f'<figure><a href="{name}/{fn}"><img src="{name}/{fn}" alt="{html.escape(caption)}" '
                       f'loading="lazy"></a><figcaption>{html.escape(caption)}</figcaption></figure>')
    return "".join(out)


def instance_section(name, cfg, search_rows):
    src = ROOT / "results" / name
    dst = SITE / name
    dst.mkdir(parents=True, exist_ok=True)
    for fn in ALLOC_FILES:
        if (src / fn).exists():
            shutil.copy2(src / fn, dst / fn)
    if (src / "animasi.html").exists():
        shutil.copy2(src / "animasi.html", dst / "animasi.html")

    inst = cfg["instances"][name]
    n_sppg, n_sch = len(inst["sppg_ids"]), inst["n_schools"]
    route_rows = route_summary(search_rows, name)

    alloc_figs = figs_html(name, src, dst, ALLOC_FIGS)
    route_depot = ""
    best_json = src / "ls_best.json"
    if best_json.exists():
        best = json.loads(best_json.read_text(encoding="utf-8"))
        top = min((k for k in best if k not in ("best_known_fitness", "Greedy")),
                  key=lambda k: best[k]["fitness"])
        route_depot = f" — sub-masalah nyata dianimasikan di {name}/animasi.html#stage=2 (SPPG terbesar, " \
                      f"penugasan terbaik {top})"

    return f"""
<section>
  <h2>{name} <span class=muted>· {n_sppg} SPPG, {n_sch} sekolah</span></h2>

  <h3>Case 1 — Alokasi SPPG → sekolah <span class=muted>(Hill Climbing, Simulated Annealing, Genetic Algorithm)</span></h3>
  <div class=links>
    <a class=primary href="{name}/animasi.html#stage=1">▶ Animasi alokasi</a>
    <a href="{name}/peta_rute_terbaik.html">Peta rute terbaik</a>
    <a href="{name}/ls_best_routes.txt">Rute terbaik (teks)</a>
  </div>
  {alloc_table(src, name)}
  <p class=muted>Bobot w = {cfg['experiment']['main_weight']}, {cfg['assignment']['n_seeds']} seed,
    {cfg['assignment']['budget_evals']:,} evaluasi per run. Fitness lebih kecil = lebih baik.
    Rute tiap SPPG selalu dihitung optimal (Router), jadi fitness di atas murni mengukur kualitas alokasi.</p>
  <div class=gallery>{alloc_figs}</div>

  <h3>Case 2 — Rute terbaik di dalam satu SPPG <span class=muted>(UCS, A*, DFS, BFS, Greedy)</span></h3>
  <div class=links>
    <a class=primary href="{name}/animasi.html#stage=2">▶ Animasi pencarian rute</a>
  </div>
  {route_table(route_rows)}
  <p class=muted>Diagregasi dari semua SPPG di instance ini (sub-masalah nyata: sekolah milik tiap SPPG
    pada penugasan terbaik Case 1){route_depot}. UCS, A* dan DFS (branch and bound) menjamin rute
    optimal; BFS menjamin jumlah Granmax paling sedikit (bukan termurah); Greedy (best-first) tercepat
    tapi tidak menjamin optimal.</p>
</section>"""


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    search_rows = read_search_real()
    SITE.mkdir(exist_ok=True)
    for p in SITE.iterdir():  # bersihkan hasil lama, tapi pertahankan link project Vercel
        if p.name == ".vercel":
            continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()

    # grafik skalabilitas pencarian tidak spesifik per instance -> taruh di site/ root
    top_figs = []
    for fn, caption in SEARCH_FIGS:
        if (ROOT / "results" / fn).exists():
            shutil.copy2(ROOT / "results" / fn, SITE / fn)
            top_figs.append(f'<figure><a href="{fn}"><img src="{fn}" alt="{html.escape(caption)}" '
                            f'loading="lazy"></a><figcaption>{html.escape(caption)}</figcaption></figure>')
    search_figs = "".join(top_figs)

    sections = "".join(instance_section(n, cfg, search_rows) for n in cfg["instances"]
                       if (ROOT / "results" / n / "ls_summary.csv").exists())
    page = f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rute MBG Surabaya</title>
<meta name="description" content="Optimasi distribusi Makan Bergizi Gratis dari SPPG ke sekolah di Surabaya: alokasi SPPG (HC, SA, GA) dan rute terbaik (UCS, A*, DFS, BFS, Greedy).">
<style>
  :root {{ --bg:#f6f6f4; --surface:#fff; --ink:#1d1d1b; --muted:#6b6b66; --line:#e2e2de; --accent:#2a78d6; --best:#eaf2fc; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#141413; --surface:#1e1e1c; --ink:#ececea; --muted:#a3a39d; --line:#33332f; --accent:#5b9be6; --best:#1d2b3d; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  main {{ max-width:1080px; margin:0 auto; padding:32px 16px 64px; }}
  h1 {{ font-size:28px; line-height:1.2; margin:0 0 8px; }}
  h2 {{ font-size:20px; margin:0 0 12px; }}
  h3 {{ font-size:15px; margin:22px 0 10px; }}
  section > h3:first-of-type {{ margin-top:4px; }}
  .muted {{ color:var(--muted); font-weight:400; }}
  .lead {{ font-size:16px; max-width:760px; }}
  section {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:20px; margin-top:24px; }}
  .links {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .links a {{ color:var(--ink); text-decoration:none; border:1px solid var(--line); border-radius:8px; padding:8px 12px; }}
  .links a:hover {{ border-color:var(--accent); }}
  .links a.primary {{ background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }}
  .tablewrap {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; min-width:560px; }}
  th, td {{ text-align:right; padding:8px 10px; border-bottom:1px solid var(--line); }}
  th:first-child, td:first-child {{ text-align:left; }}
  th {{ font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:600; }}
  td.muted {{ text-align:left; }}
  tr.best td {{ background:var(--best); font-weight:600; }}
  .gallery {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; margin-top:16px; }}
  figure {{ margin:0; }}
  figure img {{ width:100%; height:auto; border:1px solid var(--line); border-radius:8px; background:#fff; display:block; }}
  figcaption {{ font-size:13px; color:var(--muted); margin-top:4px; }}
  ul {{ padding-left:20px; }}
  footer {{ margin-top:32px; font-size:13px; color:var(--muted); }}
</style>
</head>
<body>
<main>
  <h1>Optimasi Distribusi MBG di Surabaya</h1>
  <p class=lead>Pengiriman Makan Bergizi Gratis dari SPPG (dapur) ke sekolah memakai Granmax,
    dimodelkan sebagai <b>Multi-Depot Vehicle Routing Problem bi-objektif</b> (biaya bensin
    &amp; waktu tiba), dipecah menjadi dua case independen:</p>
  <ul>
    <li><b>Case 1 — alokasi SPPG:</b> sekolah mana dilayani SPPG mana. Dibandingkan: Hill Climbing,
      Simulated Annealing, Genetic Algorithm (pencarian lokal, Kuliah 6).</li>
    <li><b>Case 2 — rute terbaik:</b> urutan kunjungan Granmax di dalam satu SPPG. Dibandingkan:
      Uniform-Cost Search, A*, DFS (branch and bound), BFS, Greedy best-first (pencarian, Kuliah 2 &amp; 3).</li>
    <li>Data: sekolah dari OpenStreetMap, lokasi SPPG dari berita (koordinat perkiraan), jarak &amp; waktu tempuh jalan asli dari OSRM.</li>
  </ul>
  <section>
    <h2>Case 2 — skalabilitas pencarian rute <span class=muted>(semua ukuran sub-masalah)</span></h2>
    <p class=muted>UCS, A* dan DFS (branch and bound) selalu optimal; BFS dan Greedy best-first tidak.
      A* mengekspansi node jauh lebih sedikit seiring k membesar karena heuristik Hungaria (h2).</p>
    <div class=gallery>{search_figs}</div>
  </section>
  {sections}
  <footer>Proyek ETS Konsep Kecerdasan Artifisial. Data peta © kontributor OpenStreetMap, routing OSRM, tile peta © Esri.</footer>
</main>
</body>
</html>
"""
    (SITE / "index.html").write_text(page, encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"site/ siap: {sum(1 for p in SITE.rglob('*') if p.is_file())} file, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
