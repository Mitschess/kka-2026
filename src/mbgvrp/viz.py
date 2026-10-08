"""Visualisasi: grafik untuk laporan (PNG) dan peta rute interaktif (HTML, folium)."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402

# warna mengikuti entitas (algoritma), urutan tetap & sudah divalidasi CVD
COLORS = {"Greedy": "#52514e", "SA": "#2a78d6", "GA": "#eb6834", "ACO": "#1baf7a",
          "NSGA-II": "#4a3aa7"}
MARKERS = {"Greedy": "s", "SA": "o", "GA": "^", "ACO": "D", "NSGA-II": "."}
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


def plot_boxplot(values, greedy_f, path, title):
    """values: {algo: [fitness akhir per seed]}"""
    algos = list(values)
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    bp = ax.boxplot([values[a] for a in algos], widths=0.5, patch_artist=True,
                    medianprops={"color": INK, "linewidth": 1.5})
    for patch, a in zip(bp["boxes"], algos):
        patch.set_facecolor(COLORS[a])
        patch.set_alpha(0.35)
        patch.set_edgecolor(COLORS[a])
    for i, a in enumerate(algos, start=1):
        jitter = np.random.default_rng(0).uniform(-0.12, 0.12, len(values[a]))
        ax.scatter(np.full(len(values[a]), i) + jitter, values[a], s=18, color=COLORS[a], zorder=3)
    ax.axhline(greedy_f, color=COLORS["Greedy"], linestyle="--", linewidth=1.5)
    ax.text(len(algos) + 0.45, greedy_f, "Greedy", color=INK2, va="bottom", ha="right", fontsize=9)
    ax.set_xticks(range(1, len(algos) + 1), algos)
    _style(ax, title, "", "Fitness akhir (lebih kecil = lebih baik)")
    _save(fig, path)


def plot_pareto(nsga_front, ws_points, path, title):
    """nsga_front: [(biaya, waktu)] gabungan seluruh seed NSGA-II (sudah non-dominated)
    ws_points: {algo: [(biaya, waktu, w)]} solusi terbaik weighted-sum per bobot."""
    fig, ax = plt.subplots(figsize=(7.5, 5))
    f = sorted(nsga_front)
    ax.step([p[0] / 1000 for p in f], [p[1] for p in f], where="post", color=COLORS["NSGA-II"],
            linewidth=2, label="NSGA-II (Pareto front)")
    ax.scatter([p[0] / 1000 for p in f], [p[1] for p in f], s=14, color=COLORS["NSGA-II"])
    for algo, pts in ws_points.items():
        ax.scatter([p[0] / 1000 for p in pts], [p[1] for p in pts], s=70, marker=MARKERS[algo],
                   facecolor="none" if algo != "Greedy" else COLORS[algo],
                   edgecolor=COLORS[algo], linewidth=1.8, label=f"{algo} (weighted sum)")
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
