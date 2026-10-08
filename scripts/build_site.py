"""Kumpulkan hasil (animasi, peta, grafik) ke folder site/ untuk hosting statis (Vercel dll).

Jalankan setelah run_experiments.py, run_sensitivity.py, dan make_animation.py:
  python scripts/build_site.py
Deploy:
  vercel deploy site --prod
"""
import csv
import html
import json
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
FILES = ["animasi.html", "peta_rute.html", "best_routes.txt"]
FIGS = [
    ("fig_pareto.png", "Trade-off biaya bensin vs waktu tiba (Pareto front NSGA-II + weighted sum)"),
    ("fig_konvergensi.png", "Konvergensi SA, GA, ACO (median 30 seed)"),
    ("fig_boxplot.png", "Sebaran fitness akhir 30 seed"),
    ("fig_rute_Greedy.png", "Rute terbaik Greedy"),
    ("fig_rute_SA.png", "Rute terbaik SA"),
    ("fig_rute_GA.png", "Rute terbaik GA"),
    ("fig_rute_ACO.png", "Rute terbaik ACO"),
    ("fig_sens_kapasitas_biaya.png", "Sensitivitas kapasitas: biaya"),
    ("fig_sens_kapasitas_waktu.png", "Sensitivitas kapasitas: waktu"),
    ("fig_sens_macet.png", "Sensitivitas kemacetan vs batas 3 jam"),
]
ORDER = ["Greedy", "SA", "GA", "ACO"]


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def instance_section(name, cfg):
    src = ROOT / "results" / name
    dst = SITE / name
    dst.mkdir(parents=True, exist_ok=True)
    for fn in FILES + [f for f, _ in FIGS]:
        if (src / fn).exists():
            shutil.copy2(src / fn, dst / fn)

    inst = cfg["instances"][name]
    n_sppg, n_sch = len(inst["sppg_ids"]), inst["n_schools"]
    summary = {r["algorithm"]: r for r in read_csv(src / "summary_main_w.csv")}
    hv = defaultdict(list)
    for r in read_csv(src / "hypervolume.csv"):
        hv[r["algorithm"]].append(float(r["hypervolume"]))
    best = min((summary[a] for a in ORDER if a in summary), key=lambda r: float(r["fitness_mean"]))

    rows = []
    for a in ORDER:
        r = summary.get(a)
        if not r:
            continue
        std = f" ± {float(r['fitness_std']):.4f}" if a != "Greedy" else ""
        cls = ' class="best"' if r is best else ""
        rows.append(f"<tr{cls}><td>{a}</td><td>{float(r['fitness_mean']):.4f}{std}</td>"
                    f"<td>Rp{float(r['cost_rp_mean']):,.0f}</td><td>{float(r['mean_arrival_min_mean']):.1f} mnt</td>"
                    f"<td>{float(r['runtime_s_mean']):.1f} s</td>"
                    f"<td>{sum(hv[a]) / len(hv[a]):.3f}</td></tr>")
    if hv.get("NSGA-II"):
        rows.append(f"<tr><td>NSGA-II</td><td colspan=4 class=muted>multi-objektif (Pareto front), "
                    f"tidak dinilai dengan satu fitness</td><td>{sum(hv['NSGA-II']) / len(hv['NSGA-II']):.3f}</td></tr>")

    figs = "".join(
        f'<figure><a href="{name}/{f}"><img src="{name}/{f}" alt="{html.escape(c)}" loading="lazy"></a>'
        f"<figcaption>{html.escape(c)}</figcaption></figure>"
        for f, c in FIGS if (src / f).exists())
    return f"""
<section>
  <h2>{name} <span class=muted>· {n_sppg} SPPG, {n_sch} sekolah</span></h2>
  <div class=links>
    <a class=primary href="{name}/animasi.html">▶ Animasi algoritma &amp; pengiriman</a>
    <a href="{name}/peta_rute.html">Peta rute interaktif</a>
    <a href="{name}/best_routes.txt">Rute terbaik (teks)</a>
  </div>
  <div class=tablewrap><table>
    <thead><tr><th>Algoritma</th><th>Fitness (mean ± std)</th><th>Biaya bensin</th>
      <th>Rata-rata tiba</th><th>Waktu/run</th><th>Hypervolume</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
  <p class=muted>Bobot w = {cfg['experiment']['main_weight']}, {cfg['experiment']['n_seeds']} seed,
    {cfg['experiment']['budget_evals']:,} evaluasi per run. Fitness lebih kecil = lebih baik;
    hypervolume lebih besar = trade-off lebih baik.</p>
  <div class=gallery>{figs}</div>
</section>"""


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    SITE.mkdir(exist_ok=True)
    for p in SITE.iterdir():  # bersihkan hasil lama, tapi pertahankan link project Vercel
        if p.name == ".vercel":
            continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    sections = "".join(instance_section(n, cfg) for n in cfg["instances"]
                       if (ROOT / "results" / n / "summary_main_w.csv").exists())
    page = f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rute MBG Surabaya</title>
<meta name="description" content="Optimasi rute distribusi Makan Bergizi Gratis dari SPPG ke sekolah di Surabaya: Greedy, SA, GA, ACO, NSGA-II.">
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
  <h1>Optimasi Rute Distribusi MBG di Surabaya</h1>
  <p class=lead>Pengiriman Makan Bergizi Gratis dari SPPG (dapur) ke sekolah memakai Granmax,
    dimodelkan sebagai <b>Multi-Depot Vehicle Routing Problem bi-objektif</b>: meminimalkan biaya
    bensin dan rata-rata waktu tiba makanan, dengan batas 3 sekolah per Granmax dan 3 jam sejak
    makanan selesai dimasak.</p>
  <ul>
    <li>Algoritma: Greedy (baseline), Simulated Annealing, Genetic Algorithm, Ant Colony Optimization (MAX-MIN), NSGA-II.</li>
    <li>Data: sekolah dari OpenStreetMap, lokasi SPPG dari berita (koordinat perkiraan), jarak &amp; waktu tempuh jalan asli dari OSRM.</li>
  </ul>
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
