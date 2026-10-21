"""Animasi gaya VisuAlgo, dua tahap: (1) pencarian rute terbaik di dalam tiap SPPG
(BFS, UCS, A*, GBFS, DFS-B&B), (2) Granmax mengantar MBG memakai rute hasil algoritma yang sama.

Tahap 1: sekolah dibagi ke SPPG terdekat, lalu pencarian semua SPPG dianimasikan bersamaan
(tiap SPPG di kemajuannya sendiri, selesai bersamaan). Pseudocode dan penjelasan mengikuti SPPG
dengan sekolah terbanyak. Pencarian animasi dibatasi ANIM_MAX_NODES node (DFS-B&B di SPPG besar
berhenti dengan rute terbaik sementara). Algoritma dijalankan dengan callback `trace` (search.py).

Contoh:
  python make_animation.py                          # semua instance
  python make_animation.py --instances surabaya_utara
Hasil: results/<instance>/animasi.html  (buka di browser, butuh internet untuk peta)
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mbgvrp.problem import assign_nearest, load_instance  # noqa: E402
from mbgvrp.search import SEARCHES, RoutingProblem  # noqa: E402
from mbgvrp.viz import DEPOT_COLORS  # noqa: E402

TEMPLATE = ROOT / "src" / "mbgvrp" / "animation_template.html"
N_COARSE = 160          # perkiraan jumlah frame "cepat" per algoritma
ANIM_MAX_NODES = 300_000  # batas node pencarian yang direkam untuk animasi


def pack(routes):
    """[(depot, [sekolah...])] -> [[depot, s1, s2, ...]] (rute kosong dibuang)."""
    return [[int(d)] + [int(s) for s in seq] for d, seq in routes if len(seq)]


# ============================================================ pencarian rute terbaik
# Di dalam satu SPPG (sub-masalah nyata dengan sekolah terdekat).
BESTFIRST_LINES = {"init": 0, "pop": 2, "goal": 3, "kept": 6, "discard": 7}
ASTAR_LINES = {"init": 0, "pop": 3, "goal": 4, "kept": 7, "discard": 8}
BFS_LINES = {"init": 0, "pop": 2, "goal": 5, "kept": 6, "discard": 7}

UCS_CODE = [
    "frontier <- priority queue berisi akar, urut g(n) = biaya jalur",
    "while frontier tidak kosong:",
    "  n <- keluarkan node ber-g(n) terkecil",
    "  if n = goal: kembalikan rute n",
    "  for tiap aksi (antar sekolah j / pulang ke SPPG) dari n:",
    "    anak <- terapkan aksi, g(anak) = g(n) + biaya langkah",
    "    jalur termurah ke keadaan anak -> simpan & masuk frontier",
    "    else: buang (sudah ada jalur lebih murah)",
]
GBFS_CODE = [
    "frontier <- priority queue berisi akar, urut h(n) saja (abai g)",
    "while frontier tidak kosong:",
    "  n <- keluarkan node ber-h(n) terkecil",
    "  if n = goal: kembalikan rute n (belum tentu optimal)",
    "  for tiap aksi (antar sekolah j / pulang ke SPPG) dari n:",
    "    anak <- terapkan aksi",
    "    jalur termurah ke keadaan anak -> simpan & masuk frontier",
    "    else: buang",
]
ASTAR_CODE = [
    "frontier <- priority queue berisi akar, urut f(n) = g(n) + h(n)",
    "h(n): batas bawah penugasan sekolah tersisa -> slot kendaraan (Hungaria)",
    "while frontier tidak kosong:",
    "  n <- keluarkan node ber-f(n) terkecil",
    "  if n = goal: kembalikan rute n (optimal, h admissible)",
    "  for tiap aksi (antar sekolah j / pulang ke SPPG) dari n:",
    "    anak <- terapkan aksi, g(anak) = g(n) + biaya langkah",
    "    jalur termurah ke keadaan anak -> simpan & masuk frontier urut f",
    "    else: buang",
]
BFS_CODE = [
    "frontier <- FIFO berisi akar; reached <- {akar}",
    "while frontier tidak kosong:",
    "  n <- keluarkan dari depan frontier",
    "  for tiap aksi (antar sekolah j / pulang ke SPPG) dari n:",
    "    anak <- terapkan aksi",
    "    if anak = goal: kembalikan rute anak",
    "    elif keadaan anak belum reached: simpan & masuk frontier (belakang)",
    "    else: buang (sudah pernah dikunjungi)",
]
DFSBB_CODE = [
    "stack <- [akar]; terbaik <- tak ada",
    "while stack tidak kosong:",
    "  n <- keluarkan dari atas stack (LIFO)",
    "  if g(n) >= g(terbaik): buang n (dipangkas B&B)",
    "  elif n = goal: terbaik <- n (incumbent baru)",
    "  else: anak-anak <- semua aksi dari n, urut termurah di atas stack",
    "return rute terbaik",
]


def _node_info(problem, node, extra=None):
    rem = node.state[0]
    done = problem.k - bin(rem).count("1")
    i = {"f": round(node.g, 4), "g(n)": round(node.g, 4), "Sekolah terlayani": f"{done}/{problem.k}"}
    if extra:
        i.update(extra)
    return i


def record_bestfirst(problem, algo, lines, f_fn):
    events = []
    res = SEARCHES[algo](problem, max_nodes=ANIM_MAX_NODES, trace=lambda ev, **d: events.append((ev, d)))
    N = sum(1 for ev, _ in events if ev == "expand")
    every = max(1, N // N_COARSE)
    detail = set(range(min(5, N))) | set(range(max(0, N - 3), N))

    def info(node, frontier=None, extra=None):
        i = _node_info(problem, node, extra)
        i["f"] = round(f_fn(node), 4)
        if frontier is not None:
            i["Frontier"] = frontier
        return i

    start_node = events[0][1]["node"]
    frames = [{"l": lines["init"], "r": pack(problem.routes_of(start_node)),
              "m": "Mulai dari SPPG, belum ada sekolah dikunjungi.", "i": info(start_node)}]
    exp_i = -1
    for ev, d in events[1:]:
        if ev == "expand":
            exp_i += 1
            node = d["node"]
            if exp_i in detail or not exp_i % every:
                frames.append({"l": lines["pop"], "r": pack(problem.routes_of(node)),
                               "i": info(node, d["frontier"]),
                               "m": f"Ekspansi ke-{exp_i + 1}/{N}: keluarkan node terbaik dari frontier."})
        elif ev == "child" and exp_i in detail:
            child, kept = d["child"], d["kept"]
            a = child.action
            hl = [problem.schools[a - 1]] if a else []
            line = lines["kept"] if kept else lines["discard"]
            msg = ("Anak masuk frontier (jalur termurah ke keadaannya)." if kept else
                   "Keadaan sudah tercapai dengan jalur lebih murah: dibuang.")
            frames.append({"l": line, "r": pack(problem.routes_of(child)), "i": info(child), "m": msg, "hl": hl})
        elif ev == "goal":
            node = d["node"]
            frames.append({"l": lines["goal"], "r": pack(problem.routes_of(node)), "i": info(node),
                           "m": "Goal: semua sekolah terlayani, kembali ke SPPG."})
    return frames, res.routes


def record_bfs(problem):
    events = []
    res = SEARCHES["BFS"](problem, max_nodes=ANIM_MAX_NODES, trace=lambda ev, **d: events.append((ev, d)))
    N = sum(1 for ev, _ in events if ev == "expand")
    every = max(1, N // N_COARSE)
    detail = set(range(min(5, N))) | set(range(max(0, N - 3), N))

    def info(node, frontier=None):
        i = _node_info(problem, node)
        if frontier is not None:
            i["Frontier"] = frontier
        return i

    start_node = events[0][1]["node"]
    frames = [{"l": BFS_LINES["init"], "r": pack(problem.routes_of(start_node)),
              "m": "Mulai dari SPPG, belum ada sekolah dikunjungi.", "i": info(start_node)}]
    exp_i = -1
    for ev, d in events[1:]:
        if ev == "expand":
            exp_i += 1
            node = d["node"]
            if exp_i in detail or not exp_i % every:
                frames.append({"l": BFS_LINES["pop"], "r": pack(problem.routes_of(node)),
                               "i": info(node, d["frontier"]),
                               "m": f"Ekspansi ke-{exp_i + 1}/{N}: keluarkan node dari depan frontier."})
        elif ev == "child" and exp_i in detail:
            child, kept = d["child"], d["kept"]
            a = child.action
            hl = [problem.schools[a - 1]] if a else []
            line = BFS_LINES["kept"] if kept else BFS_LINES["discard"]
            msg = "Keadaan baru: simpan & masuk belakang frontier." if kept else "Sudah pernah dikunjungi: buang."
            frames.append({"l": line, "r": pack(problem.routes_of(child)), "i": info(child), "m": msg, "hl": hl})
        elif ev == "goal":
            node = d["node"]
            frames.append({"l": BFS_LINES["goal"], "r": pack(problem.routes_of(node)), "i": info(node),
                           "m": "Anak = goal: semua sekolah terlayani, kembali ke SPPG."})
    return frames, res.routes


def record_dfsbb(problem):
    events = []
    res = SEARCHES["DFS-B&B"](problem, max_nodes=ANIM_MAX_NODES, trace=lambda ev, **d: events.append((ev, d)))
    N = sum(1 for ev, _ in events if ev == "expand")
    every = max(1, N // N_COARSE)
    detail = set(range(min(5, N))) | set(range(max(0, N - 3), N))

    start_node = events[0][1]["node"]
    frames = [{"l": 0, "r": pack(problem.routes_of(start_node)),
              "m": "Mulai: stack hanya berisi akar, belum ada incumbent.",
              "i": _node_info(problem, start_node)}]
    exp_i, best_g = -1, math.inf
    for ev, d in events[1:]:
        if ev == "expand":
            exp_i += 1
            node = d["node"]
            if exp_i in detail or not exp_i % every:
                frames.append({"l": 2, "r": pack(problem.routes_of(node)),
                               "i": _node_info(problem, node, {"Frontier": d["frontier"]}),
                               "m": f"Ekspansi ke-{exp_i + 1}/{N}: keluarkan node teratas stack."})
        elif ev == "prune" and exp_i in detail:
            node = d["node"]
            frames.append({"l": 3, "r": pack(problem.routes_of(node)),
                           "i": _node_info(problem, node, {"g(terbaik)": round(best_g, 4)}),
                           "m": "g(n) >= g(terbaik): dipangkas."})
        elif ev == "incumbent":
            node = d["node"]
            best_g = node.g
            frames.append({"l": 4, "r": pack(problem.routes_of(node)), "i": _node_info(problem, node),
                           "m": "Goal ditemukan: jadi incumbent (solusi terbaik sejauh ini)."})
        elif ev == "child" and exp_i in detail:
            child, kept = d["child"], d["kept"]
            a = child.action
            hl = [problem.schools[a - 1]] if a else []
            msg = "Anak masuk stack." if kept else "g(anak) >= incumbent: tidak masuk stack."
            frames.append({"l": 5, "r": pack(problem.routes_of(child)), "i": _node_info(problem, child),
                           "m": msg, "hl": hl})
    done = "Selesai: kembalikan rute terbaik (incumbent terakhir)." if res.status == "ok" else \
        "Batas node animasi tercapai: rute terbaik sementara (belum tentu optimal)."
    frames.append({"l": 6, "r": pack(res.routes), "m": done,
                  "i": {"f": round(res.cost, 4), "g(n)": round(res.cost, 4),
                        "Sekolah terlayani": f"{problem.k}/{problem.k}"}})
    return frames, res.routes



RECORDERS = {
    "BFS": (BFS_CODE, lambda p: record_bfs(p)),
    "UCS": (UCS_CODE, lambda p: record_bestfirst(p, "UCS", BESTFIRST_LINES, lambda n: n.g)),
    "A*": (ASTAR_CODE, lambda p: record_bestfirst(p, "A*", ASTAR_LINES, lambda n: n.g + p.h(n.state))),
    "GBFS": (GBFS_CODE, lambda p: record_bestfirst(p, "GBFS", BESTFIRST_LINES, lambda n: p.h(n.state))),
    "DFS-B&B": (DFSBB_CODE, record_dfsbb),
}


def merge_info(infos):
    """Gabung nilai tiap SPPG: angka dijumlahkan, "terlayani a/b" dijumlahkan, sisanya dari SPPG pemimpin."""
    out = dict(infos[0])
    for key, val in infos[0].items():
        if key == "Sekolah terlayani":
            parts = [i[key].split("/") for i in infos if key in i]
            out[key] = f"{sum(int(a) for a, _ in parts)}/{sum(int(b) for _, b in parts)}"
        elif isinstance(val, (int, float)):
            out[key] = round(sum(i[key] for i in infos if key in i), 4)
    return out


def spend_info(inst, routes):
    """Biaya bensin & rata-rata tiba rute di frame ini (rute sementara dianggap pulang ke SPPG)."""
    served = sum(len(r) - 1 for r in routes)
    ev = inst.evaluate((r[0], r[1:]) for r in routes)
    return {"Biaya bensin": f"Rp{ev.cost:,.0f}",
            "Rata-rata tiba": f"{ev.mean_arrival * inst.n / served:.1f} mnt" if served else "–",
            "Granmax": ev.n_vehicles}


def merge_frames(inst, per_depot, lead):
    """per_depot: [(depot_id, frames)]. Frame ke-t gabungan memakai frame tiap SPPG pada kemajuan
    yang sama (indeks dibagi rata), jadi semua SPPG selesai bersamaan. Pseudocode, penjelasan, dan
    sorotan sekolah mengikuti SPPG pemimpin (sekolah terbanyak)."""
    T = len(per_depot[lead][1])
    merged = []
    for t in range(T):
        cur = [frames[round(t * (len(frames) - 1) / (T - 1))] if T > 1 else frames[0] for _, frames in per_depot]
        head = cur[lead]
        routes = [r for fr in cur for r in fr["r"]]
        info = merge_info([fr["i"] for fr in cur])
        info.update(spend_info(inst, routes))
        frame = {"l": head["l"], "r": routes, "m": f"[{per_depot[lead][0]}] {head['m']}", "i": info}
        hl = sorted({h for fr in cur for h in fr.get("hl", [])})
        if hl:
            frame["hl"] = hl
        merged.append(frame)
    return merged


# ------------------------------------------------------------------------ pengiriman
DELIVERY_CODE = [
    "semua Granmax berangkat t = 0 (makanan selesai dimasak)",
    "for tiap Granmax (berjalan paralel):",
    "  for tiap sekolah j di rute:",
    "    jalan ke j   (waktu tempuh jalan asli, OSRM)",
    "    tiba di j: cek t <= 180 menit",
    "    drop makanan 15 menit",
    "  kembali ke SPPG",
    "biaya = total km / 14 km/L x Rp10.000",
]


class LegCache:
    """Geometri jalan per ruas (node a -> node b) dari OSRM, disimpan di file cache."""

    def __init__(self, inst, path):
        self.inst, self.path = inst, path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _fetch(self, idx):
        """Satu request OSRM untuk rangkaian titik idx -> simpan geometri tiap ruas."""
        keys = [f"{a}-{b}" for a, b in zip(idx[:-1], idx[1:])]
        pts = ";".join(f"{self.inst.nodes[i]['lon']:.6f},{self.inst.nodes[i]['lat']:.6f}" for i in idx)
        for attempt in range(3):
            try:
                r = requests.get(f"https://router.project-osrm.org/route/v1/driving/{pts}",
                                 params={"overview": "false", "steps": "true", "geometries": "geojson"},
                                 headers={"User-Agent": "KKA-ETS-MBG-VRP/1.0"}, timeout=60)
                legs = r.json()["routes"][0]["legs"]
                for k, leg in zip(keys, legs):
                    coords = []
                    for st in leg["steps"]:
                        for lon, lat in st["geometry"]["coordinates"]:
                            if not coords or coords[-1] != [round(lat, 6), round(lon, 6)]:
                                coords.append([round(lat, 6), round(lon, 6)])
                    self.data[k] = coords
                time.sleep(0.5)  # sopan ke server demo OSRM
                return True
            except Exception as e:  # noqa: BLE001
                print(f"    OSRM gagal ({e}), coba lagi")
                time.sleep(3 * (attempt + 1))
        return False

    def _straight(self, a, b):
        return [[self.inst.nodes[i]["lat"], self.inst.nodes[i]["lon"]] for i in (a, b)]

    def route(self, idx):
        keys = [f"{a}-{b}" for a, b in zip(idx[:-1], idx[1:])]
        if not all(k in self.data for k in keys):
            self._fetch(idx)
        return [self.data.get(k) or self._straight(a, b) for k, (a, b) in zip(keys, zip(idx[:-1], idx[1:]))]

    def ensure(self, pairs, chunk=60):
        """Ambil geometri banyak ruas (a, b) sekaligus. Ruas yang belum ada dirangkai jadi
        jalan-jalan panjang (tiap ruas dilalui tepat sekali), lalu tiap potongan `chunk`
        titik = satu request OSRM (OSRM mengembalikan geometri per ruas)."""
        todo = {}
        for a, b in sorted(set(pairs)):
            if a != b and f"{a}-{b}" not in self.data:
                todo.setdefault(a, []).append(b)
        walks = []
        while todo:
            v = next(iter(todo))
            walk = [v]
            while todo.get(v):
                nxt = todo[v].pop()
                if not todo[v]:
                    del todo[v]
                walk.append(nxt)
                v = nxt
            walks.append(walk)
        chunks = [w[i:i + chunk] for w in walks for i in range(0, max(1, len(w) - 1), chunk - 1)]
        chunks = [c for c in chunks if len(c) > 1]
        for k, c in enumerate(chunks, start=1):
            print(f"\r    OSRM ruas jalan: request {k}/{len(chunks)}", end="", flush=True)
            self._fetch(c)
            if k % 10 == 0:
                self.save()
        if chunks:
            print()

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")


def delivery_plan(inst, routes, legs):
    """Jadwal tiap Granmax: ruas jalan + waktu mulai/selesai, mengikuti model (matriks T)."""
    vehicles = []
    for v, (d, seq) in enumerate((r for r in routes if r[1]), start=1):
        idx = [d] + [inst.m + s for s in seq] + ([d] if inst.return_to_depot else [])
        geoms = legs.route(idx)
        t, segs, stops = 0.0, [], []
        for k, (a, b) in enumerate(zip(idx[:-1], idx[1:])):
            dt = float(inst.T[a, b])
            segs.append({"a": a, "b": b, "t0": round(t, 3), "t1": round(t + dt, 3),
                         "km": round(float(inst.D[a, b]), 3), "g": simplify(geoms[k])})
            t += dt
            if b >= inst.m:
                stops.append({"s": b - inst.m, "arr": round(t, 3), "dep": round(t + inst.service, 3)})
                t += inst.service
        vehicles.append({"v": v, "d": d, "segs": segs, "stops": stops, "end": round(t, 3)})
    ev = inst.evaluate(routes)
    return {"veh": vehicles, "cost": round(ev.cost), "km": round(ev.km, 2),
            "mean": round(ev.mean_arrival, 2), "makespan": round(ev.makespan, 2)}

# ------------------------------------------------------------------------------- main
def build(name, cfg):
    inst = load_instance(ROOT, name, cfg)
    w = cfg["search"]["weight"]
    out = ROOT / "results" / name
    print(f"{name}: {inst.m} SPPG, {inst.n} sekolah")

    # ---- tahap 1: pencarian rute semua SPPG, dianimasikan bersamaan
    owned = assign_nearest(inst)
    depots = [d for d in range(inst.m) if owned[d]]
    lead = max(range(len(depots)), key=lambda i: len(owned[depots[i]]))
    problems = [RoutingProblem(inst, d, owned[d], w) for d in depots]
    print(f"  [rute] {len(depots)} SPPG paralel; pseudocode mengikuti {inst.nodes[depots[lead]]['id']} "
          f"({len(owned[depots[lead]])} sekolah)")
    route = {}
    for label, (code, record) in RECORDERS.items():
        t0 = time.time()
        recs = [record(p) for p in problems]
        frames = merge_frames(inst, [(inst.nodes[d]["id"], fr) for d, (fr, _) in zip(depots, recs)], lead)
        route[label] = {"code": code, "frames": frames, "final": pack([r for _, rt in recs for r in rt])}
        print(f"  [rute]    {label:8} {len(frames):4} frame  ({time.time() - t0:.0f} s)")

    # ---- tahap 2: pengiriman memakai rute hasil tiap algoritma
    legs = LegCache(inst, out / ".osrm_legs_cache.json")
    for label, a in route.items():
        a["delivery"] = delivery_plan(inst, [(r[0], r[1:]) for r in a["final"]], legs)
    legs.save()

    data = {
        "instance": name, "m": inst.m, "n": inst.n, "Q": inst.Q, "service": inst.service,
        "max_time": inst.max_time, "w": w,
        "colors": DEPOT_COLORS, "delivery_code": DELIVERY_CODE,
        "nodes": [{"id": n["id"], "name": n["name"], "lat": n["lat"], "lon": n["lon"]} for n in inst.nodes],
        "route": route,
        "route_depot": {"id": inst.nodes[depots[lead]]["id"], "name": inst.nodes[depots[lead]]["name"],
                        "k": len(owned[depots[lead]]), "n_depots": len(depots)},
    }
    attach_legs(data, out)
    (out / ".animasi_data.json").write_text(json.dumps(data), encoding="utf-8")
    render_html(data, out / "animasi.html")


def simplify(coords, tol=5e-5):
    """Douglas-Peucker (tol dalam derajat, 5e-5 ~ 5 m) agar file HTML tidak terlalu besar."""
    if len(coords) <= 2:
        return coords
    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        i, j = stack.pop()
        (y1, x1), (y2, x2) = coords[i], coords[j]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-12
        best, idx = 0.0, None
        for k in range(i + 1, j):
            y, x = coords[k]
            dist = abs(dy * (x - x1) - dx * (y - y1)) / norm
            if dist > best:
                best, idx = dist, k
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [[round(c[0], 5), round(c[1], 5)] for c, k in zip(coords, keep) if k]


def attach_legs(data, out):
    """Geometri jalan asli untuk setiap ruas yang muncul di animasi tahap 1, sehingga
    rute di setiap frame digambar mengikuti jalan (bukan garis lurus)."""
    pairs = set()
    for a in data["route"].values():
        for fr in a["frames"]:
            for r in fr["r"]:
                nodes = [r[0]] + [data["m"] + s for s in r[1:]] + [r[0]]
                pairs.update(zip(nodes[:-1], nodes[1:]))
    legs = LegCache(SimpleNamespace(nodes=data["nodes"]), out / ".osrm_legs_cache.json")
    print(f"  {len(pairs)} ruas jalan dipakai di animasi")
    legs.ensure(pairs)
    legs.save()
    data["legs"] = {f"{a}-{b}": simplify(legs.data[f"{a}-{b}"]) for a, b in pairs
                    if a != b and f"{a}-{b}" in legs.data}
    missing = len(pairs) - len(data["legs"])
    if missing:
        print(f"  {missing} ruas tanpa geometri (OSRM gagal) -> digambar garis lurus")


def render_html(data, path):
    html = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    path.write_text(html.replace("/*__DATA__*/null", payload), encoding="utf-8")
    print(f"  -> {path}  ({path.stat().st_size / 1e6:.1f} MB)")


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", nargs="*", default=list(cfg["instances"]))
    ap.add_argument("--html-only", action="store_true",
                    help="hanya render ulang HTML dari data tersimpan (setelah mengubah template)")
    args = ap.parse_args()
    for name in args.instances:
        out = ROOT / "results" / name
        if args.html_only:
            data = json.loads((out / ".animasi_data.json").read_text(encoding="utf-8"))
            render_html(data, out / "animasi.html")
        else:
            build(name, cfg)


if __name__ == "__main__":
    main()