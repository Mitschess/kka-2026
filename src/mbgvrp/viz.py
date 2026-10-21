"""Visualisasi: grafik untuk laporan (PNG) dan peta rute interaktif (HTML, folium)."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402

# palet kategorikal 8 slot (urutan tetap, sudah divalidasi CVD) untuk algoritma pencarian
PALETTE8 = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEARCH_ORDER = ["BFS", "IDS", "DFS-B&B", "UCS", "A* (h1)", "A*", "GBFS"]
SEARCH_COLORS = dict(zip(SEARCH_ORDER, PALETTE8))
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
