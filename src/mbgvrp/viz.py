"""Visualisasi: grafik untuk laporan (PNG) dan peta rute interaktif (HTML, folium)."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402

# warna mengikuti entitas (algoritma), urutan tetap & sudah divalidasi CVD
COLORS = {"Greedy": "#52514e", "SA": "#2a78d6", "GA": "#eb6834", "HC": "#1baf7a"}
MARKERS = {"Greedy": "s", "SA": "o", "GA": "^", "HC": "D"}
# palet kategorikal 8 slot (urutan tetap) untuk Bagian A (pencarian) & B (pencarian lokal)
PALETTE8 = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEARCH_ORDER = ["BFS", "IDS", "DFS-B&B", "UCS", "A* (h1)", "A*", "GBFS"]
LS_ORDER = ["HC", "HC-Sideways", "Stochastic HC", "Random-Walk HC", "RR-HC", "EHC", "SA", "GA"]
SEARCH_COLORS = dict(zip(SEARCH_ORDER, PALETTE8))
LS_COLORS = dict(zip(LS_ORDER, PALETTE8))
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
DEPOT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7", "#e34948", "#008300"]


def _style(ax, title, xlabel, ylabel):
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2)


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


# --------------------------------------------------------------- grafik eksperimen
def plot_convergence(histories, greedy_f, path, title):
    """histories: {algo: [[(evals, best_f), ...] per seed]} -> median + rentang IQR."""
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for algo, runs in histories.items():
        grid = np.linspace(min(h[0][0] for h in runs), min(h[-1][0] for h in runs), 100)
        curves = np.array([np.interp(grid, [e for e, _ in h], [f for _, f in h]) for h in runs])
        med = np.median(curves, axis=0)
        q1, q3 = np.percentile(curves, [25, 75], axis=0)
        ax.plot(grid, med, color=COLORS[algo], linewidth=2, label=f"{algo} (median)")
        ax.fill_between(grid, q1, q3, color=COLORS[algo], alpha=0.15, linewidth=0)
    ax.axhline(greedy_f, color=COLORS["Greedy"], linestyle="--", linewidth=1.5, label="Greedy")
    all_end = [h[-1][1] for runs in histories.values() for h in runs]
    ax.set_ylim(min(all_end + [greedy_f]) * 0.97, max(greedy_f * 1.6, min(all_end) * 1.3))
    _style(ax, title, "Jumlah evaluasi solusi", "Fitness terbaik (lebih kecil = lebih baik)")
    ax.legend(frameon=False)
    _save(fig, path)


def plot_boxplot(values, greedy_f, path, title, colors=None, figsize=(7.5, 4.5), rotate=0, zoom=None):
    """values: {algo: [fitness akhir per seed]}. greedy_f=None: tanpa garis Greedy.
    zoom=(lo, hi): tambah panel kedua yang memperbesar rentang fitness [lo, hi]."""
    pal = colors or COLORS
    algos = list(values)
    if zoom:
        fig, axes = plt.subplots(2, 1, figsize=(figsize[0], figsize[1] * 1.55), sharex=True,
                                 gridspec_kw={"height_ratios": [1.15, 1]})
    else:
        fig, ax0 = plt.subplots(figsize=figsize)
        axes = [ax0]
    for k, ax in enumerate(axes):
        bp = ax.boxplot([values[a] for a in algos], widths=0.5, patch_artist=True, showfliers=False,
                        medianprops={"color": INK, "linewidth": 1.5})
        for patch, a in zip(bp["boxes"], algos):
            patch.set_facecolor(pal[a])
            patch.set_alpha(0.35)
            patch.set_edgecolor(pal[a])
        for i, a in enumerate(algos, start=1):
            jitter = np.random.default_rng(0).uniform(-0.12, 0.12, len(values[a]))
            ax.scatter(np.full(len(values[a]), i) + jitter, values[a], s=18, color=pal[a], zorder=3)
        if greedy_f is not None and k == 0:
            ax.axhline(greedy_f, color=COLORS["Greedy"], linestyle="--", linewidth=1.5)
            ax.text(len(algos) + 0.45, greedy_f, "Greedy", color=INK2, va="bottom", ha="right", fontsize=9)
        ax.set_xticks(range(1, len(algos) + 1), algos, rotation=rotate, ha="right" if rotate else "center")
        if k == 0:
            _style(ax, title, "", "Fitness akhir (lebih kecil = lebih baik)")
        else:
            ax.set_ylim(*zoom)
            ax.ticklabel_format(axis="y", useOffset=False)
            _style(ax, "", "", "Diperbesar")
    if zoom:
        axes[0].tick_params(labelbottom=False)
    _save(fig, path)


def plot_convergence_log(histories, budget, ref_f, ref_label, path, title, colors, inset=None, styles=None):
    """histories: {algo: [[(evals, best_f), ...] per seed]}. Sumbu x logaritmik; run yang
    berhenti lebih awal (optimum lokal) diperpanjang datar sampai anggaran habis.
    inset=(x0, x1, y0, y1): panel kecil yang memperbesar ujung kurva. styles: {algo: linestyle}."""
    fig, ax = plt.subplots(figsize=(9, 4.8))
    grid = np.unique(np.logspace(1, np.log10(budget), 160).round())
    ends, curves_of = [], {}
    for algo, runs in histories.items():
        curves = []
        for h in runs:
            e = [x for x, _ in h] + [budget]
            f = [y for _, y in h] + [h[-1][1]]
            idx = np.searchsorted(e, grid, side="right") - 1
            curves.append(np.where(idx >= 0, np.array(f)[np.clip(idx, 0, None)], np.nan))
        med = np.nanmedian(np.array(curves), axis=0)
        curves_of[algo] = med
        ends.append(med[-1])
    axes = [ax]
    if inset:
        ins = ax.inset_axes([0.06, 0.1, 0.31, 0.45])
        axes.append(ins)
    for a_ in axes:
        for algo, med in curves_of.items():
            a_.plot(grid, med, color=colors[algo], linewidth=2, linestyle=(styles or {}).get(algo, "-"),
                    label=algo if a_ is ax else None)
    ax.axhline(ref_f, color=COLORS["Greedy"], linestyle="--", linewidth=1.5)
    ax.text(grid[0], ref_f, f" {ref_label}", color=INK2, va="bottom", fontsize=9)
    ax.set_xscale("log")
    lo = min(ends)
    ax.set_ylim(lo - 0.02 * lo, max(ref_f, lo) + 0.25 * (max(ref_f, lo) - lo) + 0.01)
    _style(ax, title, "Jumlah evaluasi fitness (skala log)", "Fitness terbaik, median 30 seed")
    if inset:
        ins.set_xscale("log")
        ins.set_xlim(inset[0], inset[1])
        ins.set_ylim(inset[2], inset[3])
        ins.ticklabel_format(axis="y", useOffset=False)
        ins.tick_params(labelsize=8, colors=INK2)
        ins.grid(True, color=GRID, linewidth=0.6)
        ins.set_title("diperbesar", fontsize=8, color=INK2, loc="left")
        ax.indicate_inset_zoom(ins, edgecolor=INK2)
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(1.01, 1))
    _save(fig, path)


def plot_tradeoff(ws_points, path, title, annotate=False):
    """ws_points: {algo: [(biaya, waktu, w)]} solusi terbaik weighted-sum per bobot w.
    annotate=True: tulis nilai w di samping tiap titik."""
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for algo, pts in ws_points.items():
        col = COLORS.get(algo) or LS_COLORS.get(algo, "#2a78d6")   # COLORS: eksperimen lama, LS: Bagian B
        pts = sorted(pts)
        ax.plot([p[0] / 1000 for p in pts], [p[1] for p in pts], color=col, linewidth=1.2,
                alpha=0.6)
        ax.scatter([p[0] / 1000 for p in pts], [p[1] for p in pts], s=70, marker=MARKERS.get(algo, "o"),
                   facecolor="none" if algo != "Greedy" else col,
                   edgecolor=col, linewidth=1.8, label=f"{algo} (w = 0 … 1)")
        if annotate:
            for c, t, w in pts:
                ax.annotate(f"w = {w:g}", (c / 1000, t), xytext=(6, 4), textcoords="offset points",
                            fontsize=8.5, color=INK2)
    _style(ax, title, "Biaya bensin total (ribu Rp)", "Rata-rata waktu tiba di sekolah (menit)")
    ax.legend(frameon=False)
    _save(fig, path)


def plot_sensitivity(xs, series, path, title, xlabel, ylabel, hline=None):
    """series: {label: [nilai per x]} - satu sumbu y, garis per label.
    hline: (nilai, label) garis batas horizontal, mis. batas waktu 180 menit."""
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    if hline:
        ax.axhline(hline[0], color="#e34948", linestyle="--", linewidth=1.5)
        ax.text(xs[0], hline[0], f" {hline[1]}", color=INK2, va="bottom", fontsize=9)
    palette = ["#2a78d6", "#eb6834", "#1baf7a"]
    for (label, ys), c in zip(series.items(), palette):
        ax.plot(xs, ys, color=c, linewidth=2, marker="o", markersize=7, label=label)
        ax.annotate(label, (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                    color=INK2, fontsize=9, va="center")
    ax.set_xticks(xs)
    ax.margins(x=0.15)
    _style(ax, title, xlabel, ylabel)
    if len(series) > 1:
        ax.legend(frameon=False)
    _save(fig, path)


# --------------------------------------------------------------------- peta rute
def plot_routes_static(inst, routes, path, title):
    """Peta statis (koordinat lat/lon, garis lurus antar titik) untuk laporan/PPT."""
    fig, ax = plt.subplots(figsize=(7, 7))
    lat = [n["lat"] for n in inst.nodes]
    lon = [n["lon"] for n in inst.nodes]
    for d, seq in routes:
        c = DEPOT_COLORS[d % len(DEPOT_COLORS)]
        path_idx = [d] + [inst.m + s for s in seq] + ([d] if inst.return_to_depot else [])
        ax.plot([lon[i] for i in path_idx], [lat[i] for i in path_idx], color=c, linewidth=1.8,
                alpha=0.85)
        for k, s in enumerate(seq, start=1):
            i = inst.m + s
            ax.annotate(str(k), (lon[i], lat[i]), xytext=(4, 4), textcoords="offset points",
                        fontsize=7, color=INK2)
    ax.scatter(lon[inst.m:], lat[inst.m:], s=28, color="white", edgecolor=INK, zorder=3,
               label="Sekolah")
    for d in range(inst.m):
        ax.scatter(lon[d], lat[d], s=180, marker="*", color=DEPOT_COLORS[d % len(DEPOT_COLORS)],
                   edgecolor=INK, zorder=4)
        ax.annotate(inst.nodes[d]["id"], (lon[d], lat[d]), xytext=(7, -10),
                    textcoords="offset points", fontsize=9, color=INK, weight="bold")
    ax.set_aspect(1 / np.cos(np.radians(np.mean(lat))))
    ax.ticklabel_format(useOffset=False, style="plain")
    _style(ax, title, "Bujur", "Lintang")
    _save(fig, path)


def _road_geometry(points, cache):
    """Geometri jalan dari OSRM untuk rute (list (lat, lon)); fallback garis lurus."""
    key = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    if key in cache:
        return cache[key]
    try:
        r = requests.get(f"https://router.project-osrm.org/route/v1/driving/{key}",
                         params={"overview": "full", "geometries": "geojson"},
                         headers={"User-Agent": "KKA-ETS-MBG-VRP/1.0"}, timeout=30)
        coords = r.json()["routes"][0]["geometry"]["coordinates"]
        geom = [(lat, lon) for lon, lat in coords]
    except Exception:  # noqa: BLE001
        geom = list(points)
    cache[key] = geom
    return geom


def map_routes_html(inst, solutions, path, cache_path=None):
    """Peta interaktif folium. solutions: {nama_layer: (routes, Evaluation)}.
    Tiap solusi jadi satu layer yang bisa dinyalakan/dimatikan."""
    import folium

    cache = {}
    if cache_path and Path(cache_path).exists():
        cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))

    lat0 = np.mean([n["lat"] for n in inst.nodes])
    lon0 = np.mean([n["lon"] for n in inst.nodes])
    # OSM (403) dan CARTO (watermark "API key required") menolak halaman yang dibuka
    # langsung dari file lokal karena tidak ada Referer; tile Esri tetap bisa dipakai
    fmap = folium.Map(location=[lat0, lon0], zoom_start=13, tiles=None)
    esri = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
    folium.TileLayer(esri.format("World_Street_Map"), name="Peta jalan (Esri)",
                     attr="Tiles &copy; Esri", max_zoom=19).add_to(fmap)
    folium.TileLayer(esri.format("Canvas/World_Light_Gray_Base"), name="Peta abu-abu (Esri)",
                     attr="Tiles &copy; Esri", max_zoom=16).add_to(fmap)

    for li, (layer_name, (routes, ev)) in enumerate(solutions.items()):
        layer = folium.FeatureGroup(name=f"{layer_name}: Rp{ev.cost:,.0f} | {ev.mean_arrival:.1f} mnt",
                                    show=(li == 0))
        for v, (d, seq) in enumerate(routes, start=1):
            c = DEPOT_COLORS[d % len(DEPOT_COLORS)]
            idx = [d] + [inst.m + s for s in seq] + ([d] if inst.return_to_depot else [])
            pts = [(inst.nodes[i]["lat"], inst.nodes[i]["lon"]) for i in idx]
            names = " → ".join(inst.nodes[i]["name"] for i in idx)
            folium.PolyLine(_road_geometry(pts, cache), color=c, weight=4, opacity=0.8,
                            tooltip=f"Granmax {v} ({inst.nodes[d]['id']}): {names}").add_to(layer)
            t = 0.0
            prev = d
            for k, s in enumerate(seq, start=1):
                i = inst.m + s
                t += inst.T[prev, i]
                folium.CircleMarker(
                    [inst.nodes[i]["lat"], inst.nodes[i]["lon"]], radius=6, color=c, fill=True,
                    fill_color="white", fill_opacity=1, weight=3,
                    tooltip=f"{inst.nodes[i]['name']} — urutan {k}, tiba {t:.1f} menit").add_to(layer)
                t += inst.service
                prev = i
        layer.add_to(fmap)

    for d in range(inst.m):
        node = inst.nodes[d]
        folium.Marker([node["lat"], node["lon"]], tooltip=f"{node['id']}: {node['name']}",
                      icon=folium.Icon(color="black", icon="cutlery", prefix="fa")).add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.save(str(path))
    if cache_path:
        Path(cache_path).write_text(json.dumps(cache), encoding="utf-8")


# ------------------------------------------------------- Bagian A (algoritma pencarian)
SEARCH_MARKERS = {"BFS": "o", "IDS": "s", "DFS-B&B": "D", "UCS": "^", "A* (h1)": "v", "A*": "*",
                  "GBFS": "P"}


def plot_search_scaling(summary, path, title):
    """summary: baris {k, algorithm, solved_rate, expanded_median, max_stored_median}.
    Dua panel (small multiples, sumbu y log): node diekspansi dan node tersimpan.
    Titik k yang tidak semua sub-masalahnya selesai (kena batas node) tidak digambar."""
    algos = list(dict.fromkeys(r["algorithm"] for r in summary))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    panels = [("expanded_median", "Node diekspansi (median, skala log)"),
              ("max_stored_median", "Node tersimpan maksimum (median, skala log)")]
    for ax, (col, ylabel) in zip(axes, panels):
        for a in algos:
            rs = [r for r in summary if r["algorithm"] == a and r["solved_rate"] == 1]
            ax.plot([r["k"] for r in rs], [max(r[col], 1) for r in rs], color=SEARCH_COLORS[a],
                    marker=SEARCH_MARKERS[a], markersize=8 if a != "A*" else 11, linewidth=2,
                    label="A* (h2)" if a == "A*" else a)
        ax.set_yscale("log")
        ks = sorted({r["k"] for r in summary})
        ax.set_xticks(ks)
        _style(ax, "", "Jumlah sekolah di SPPG (k)", ylabel)
    axes[0].legend(frameon=False, fontsize=9)
    fig.suptitle(title, x=0.01, ha="left", fontsize=12, color=INK)
    _save(fig, path)


def plot_search_gap(gaps, path, title):
    """gaps: {algo: [selisih % terhadap optimum per sub-masalah]} -> batang rata-rata."""
    algos = list(gaps)
    means = [float(np.nanmean(gaps[a])) for a in algos]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    y = np.arange(len(algos))[::-1]
    ax.barh(y, means, height=0.55, color=[SEARCH_COLORS[a] for a in algos])
    for yi, v in zip(y, means):
        ax.text(v + max(means) * 0.01, yi, f"{v:.1f}%" if v > 1e-6 else "0% (optimal)",
                va="center", fontsize=9, color=INK2)
    ax.set_yticks(y, ["A* (h2)" if a == "A*" else a for a in algos])
    ax.set_xlim(0, max(means) * 1.2 + 1)
    _style(ax, title, "Rata-rata selisih biaya terhadap optimum (%)", "")
    ax.grid(axis="y", visible=False)
    _save(fig, path)
