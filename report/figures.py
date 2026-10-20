"""Gambar tambahan untuk laporan & presentasi: peta wilayah studi dan rute terbaik
di atas basemap Esri (rute mengikuti jalan asli dari cache OSRM animasi).

Dipanggil oleh report/build_report.py dan report/build_deck.js (lewat file PNG).
"""
import io
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mbgvrp.problem import load_instance  # noqa: E402
from mbgvrp.viz import DEPOT_COLORS, INK, INK2  # noqa: E402

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
TILE_CACHE = ROOT / "report" / ".tile_cache"
R_EARTH = 6378137.0


def merc(lat, lon):
    x = math.radians(lon) * R_EARTH
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R_EARTH
    return x, y


def _tile(z, x, y):
    path = TILE_CACHE / f"{z}_{x}_{y}.jpg"
    if not path.exists():
        TILE_CACHE.mkdir(parents=True, exist_ok=True)
        r = requests.get(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": "KKA-ETS-MBG-VRP/1.0"},
                         timeout=30)
        r.raise_for_status()
        path.write_bytes(r.content)
    return Image.open(io.BytesIO(path.read_bytes())).convert("RGB")


def basemap(ax, lat_min, lat_max, lon_min, lon_max, zoom=14):
    """Tempel tile Esri (proyeksi Web Mercator) ke ax yang memakai koordinat meter."""
    def tile_xy(lat, lon):
        n = 2 ** zoom
        x = (lon + 180) / 360 * n
        y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
        return x, y

    x0, y0 = tile_xy(lat_max, lon_min)
    x1, y1 = tile_xy(lat_min, lon_max)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    W, H = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
    canvas = Image.new("RGB", (W, H))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            canvas.paste(_tile(zoom, tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    # batas tile dalam meter mercator
    n = 2 ** zoom
    span = 2 * math.pi * R_EARTH
    left = tx0 / n * span - span / 2
    right = (tx1 + 1) / n * span - span / 2
    top = span / 2 - ty0 / n * span
    bottom = span / 2 - (ty1 + 1) / n * span
    ax.imshow(np.asarray(canvas), extent=(left, right, bottom, top), zorder=0)


def _frame(ax, xs, ys, pad=0.08):
    dx, dy = max(xs) - min(xs), max(ys) - min(ys)
    ax.set_xlim(min(xs) - dx * pad, max(xs) + dx * pad)
    ax.set_ylim(min(ys) - dy * pad, max(ys) + dy * pad)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#c9c8c3")


def _bbox(inst, pad=0.012):
    lat = [n["lat"] for n in inst.nodes]
    lon = [n["lon"] for n in inst.nodes]
    return min(lat) - pad, max(lat) + pad, min(lon) - pad, max(lon) + pad


def draw_points(ax, inst, label_depots=True):
    for i in range(inst.m, inst.m + inst.n):
        x, y = merc(inst.nodes[i]["lat"], inst.nodes[i]["lon"])
        ax.scatter(x, y, s=34, color="white", edgecolor=INK, linewidth=1.1, zorder=5)
    for d in range(inst.m):
        x, y = merc(inst.nodes[d]["lat"], inst.nodes[d]["lon"])
        ax.scatter(x, y, s=260, marker="*", color=DEPOT_COLORS[d % 6], edgecolor=INK, linewidth=1, zorder=6)
        if label_depots:
            ax.annotate(inst.nodes[d]["id"].replace("SPPG-", ""), (x, y), xytext=(8, -12),
                        textcoords="offset points", fontsize=9, weight="bold", color=INK, zorder=7,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))


def fig_wilayah(config, out_path):
    names = list(config["instances"])
    fig, axes = plt.subplots(1, len(names), figsize=(11, 5.6))
    for ax, name in zip(axes, names):
        inst = load_instance(ROOT, name, config)
        lat_min, lat_max, lon_min, lon_max = _bbox(inst)
        basemap(ax, lat_min, lat_max, lon_min, lon_max, zoom=13 if inst.m > 3 else 14)
        draw_points(ax, inst)
        x0, y0 = merc(lat_min + 0.006, lon_min + 0.006)
        x1, y1 = merc(lat_max - 0.006, lon_max - 0.006)
        _frame(ax, [x0, x1], [y0, y1], pad=0.0)
        ax.set_title(f"{name}: {inst.m} SPPG (bintang), {inst.n} sekolah (lingkaran)", loc="left",
                     fontsize=11, color=INK)
    fig.text(0.99, 0.01, "Tiles © Esri · data © kontributor OpenStreetMap", ha="right", fontsize=7, color=INK2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=170, facecolor="white")
    plt.close(fig)


def fig_rute(config, name, label, out_path, title=None, source="best_solutions.json"):
    """Rute solusi `label` dari results/<name>/<source> di atas basemap."""
    inst = load_instance(ROOT, name, config)
    res = ROOT / "results" / name
    sol = json.loads((res / source).read_text(encoding="utf-8"))[label]
    cache = res / ".osrm_legs_cache.json"
    pairs = []
    for d, seq in sol["routes"]:
        path = [d] + [inst.m + s for s in seq] + [d]
        pairs += list(zip(path[:-1], path[1:]))
    sys.path.insert(0, str(ROOT))
    from make_animation import LegCache   # geometri jalan per ruas (OSRM), di-cache
    lc = LegCache(inst, cache)
    if any(f"{a}-{b}" not in lc.data for a, b in pairs):
        lc.ensure(pairs)
        lc.save()
    legs = lc.data

    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    lat_min, lat_max, lon_min, lon_max = _bbox(inst, pad=0.006)
    basemap(ax, lat_min, lat_max, lon_min, lon_max, zoom=14)
    for d, seq in sol["routes"]:
        path = [d] + [inst.m + s for s in seq] + [d]
        for a, b in zip(path[:-1], path[1:]):
            pts = legs.get(f"{a}-{b}") or [[inst.nodes[a]["lat"], inst.nodes[a]["lon"]],
                                            [inst.nodes[b]["lat"], inst.nodes[b]["lon"]]]
            xy = np.array([merc(p[0], p[1]) for p in pts])
            ax.plot(xy[:, 0], xy[:, 1], color=DEPOT_COLORS[d % 6], linewidth=2.4, alpha=0.9, zorder=3,
                    solid_capstyle="round")
        for k, s in enumerate(seq, start=1):
            x, y = merc(inst.nodes[inst.m + s]["lat"], inst.nodes[inst.m + s]["lon"])
            ax.annotate(str(k), (x, y), xytext=(5, 5), textcoords="offset points", fontsize=7.5,
                        color=INK, zorder=8)
    draw_points(ax, inst)
    xs = [merc(n["lat"], n["lon"])[0] for n in inst.nodes]
    ys = [merc(n["lat"], n["lon"])[1] for n in inst.nodes]
    _frame(ax, xs, ys, pad=0.06)
    if title is not False:  # title=False -> tanpa judul (dipakai untuk gambar sampul)
        ax.set_title(title or f"{label}: Rp{sol['cost_rp']:,.0f} · {sol['km']:.1f} km · rata-rata tiba "
                              f"{sol['mean_arrival_min']:.1f} mnt · {sol['n_vehicles']} Granmax",
                     loc="left", fontsize=10.5, color=INK)
    ax.text(0.99, 0.01, "Tiles © Esri · rute OSRM/OpenStreetMap", transform=ax.transAxes, ha="right",
            fontsize=7, color=INK2, zorder=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=170, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    out = ROOT / "report" / "figs"
    out.mkdir(parents=True, exist_ok=True)
    fig_wilayah(cfg, out / "fig_wilayah.png")
    print("ok", out / "fig_wilayah.png")
