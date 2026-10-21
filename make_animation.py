"""Animasi gaya VisuAlgo, tiga tahap: (1) alokasi sekolah -> SPPG (Bagian B: HC, SA, GA),
(2) pencarian rute terbaik di dalam satu SPPG (Bagian A: BFS, UCS, A*, GBFS, DFS-B&B),
(3) Granmax mengantar MBG memakai solusi terbaik tahap 1.

Tahap 1 jalan di seluruh instance (semua sekolah); tiap langkah rute tiap SPPG dihitung
optimal oleh Router sehingga petanya selalu solusi lengkap yang valid. Tahap 2 jalan di
satu sub-masalah nyata (SPPG dengan sekolah terbanyak, dari penugasan terbaik Bagian B,
dibatasi k <= 9 supaya DFS-B&B/BFS tidak meledak) -- sama dengan sub-masalah di
run_search.py. Semua algoritma dijalankan dengan callback `trace` (search.py,
local_search.py), hasilnya identik dengan run seed 1 di eksperimen (trace tidak memakai rng).

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
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mbgvrp import local_search as LS  # noqa: E402
from mbgvrp.problem import load_instance  # noqa: E402
from mbgvrp.router import Router  # noqa: E402
from mbgvrp.search import SEARCHES, RoutingProblem  # noqa: E402
from mbgvrp.viz import DEPOT_COLORS  # noqa: E402

TEMPLATE = ROOT / "src" / "mbgvrp" / "animation_template.html"
N_COARSE = 160          # perkiraan jumlah frame "cepat" per algoritma


def pack(routes):
    """[(depot, [sekolah...])] -> [[depot, s1, s2, ...]] (rute kosong dibuang)."""
    return [[int(d)] + [int(s) for s in seq] for d, seq in routes if len(seq)]


# ============================================================================= Bagian B
# Alokasi sekolah -> SPPG (penugasan x[s] = SPPG). Rute tiap SPPG dihitung optimal oleh
# Router di setiap langkah, jadi peta selalu menampilkan solusi lengkap yang valid.
class AllocRecorder:
    def __init__(self, inst, w, penalty, router):
        self.inst, self.w, self.penalty, self.router = inst, w, penalty, router
        self.frames = []

    def routes_for(self, x):
        masks = [0] * self.inst.m
        for s, d in enumerate(x):
            masks[d] |= 1 << s
        return self.router.all_routes(masks)

    def metrics(self, routes, f=None):
        ev = self.inst.evaluate(routes)
        if f is None:
            f = self.inst.scalarize(ev, self.w, self.penalty)
        out = {"f": round(f, 4), "Biaya bensin": f"Rp{ev.cost:,.0f}",
               "Rata-rata tiba": f"{ev.mean_arrival:.1f} mnt", "Granmax": ev.n_vehicles}
        if not ev.feasible:
            out["Melanggar"] = (f"kapasitas +{ev.cap_excess}" if ev.cap_excess else "") + \
                               (f" armada +{ev.veh_excess}" if ev.veh_excess else "") + \
                               (f" telat {ev.late_min:.0f} mnt" if ev.late_min else "")
        return out

    def add(self, line, x, msg, info=None, f=None, hl=None):
        routes = self.routes_for(x)
        i = dict(info or {})
        i.update(self.metrics(routes, f))
        fr = {"l": line, "r": pack(routes), "m": msg, "i": i}
        if hl:
            fr["hl"] = list(hl)
        self.frames.append(fr)


HC_CODE = [
    "x <- penugasan sekolah -> SPPG acak (hormati kapasitas armada)",
    "while True:",
    "  tetangga <- semua pindah(s -> SPPG lain) & tukar(s, u) dari x",
    "  (pindah/tukar) dF terkecil <- hasil terbaik dari semua tetangga",
    "  if dF < 0:",
    "    x <- tetangga itu        > naik satu langkah",
    "  else:                      > optimum lokal",
    "    berhenti, kembalikan x",
]


def record_hc_alloc(inst, w, penalty, budget, seed, params):
    router = Router(inst, w, penalty)
    rec = AllocRecorder(inst, w, penalty, router)
    events = []
    rng = np.random.default_rng(seed * 1000 + int(w * 100))
    res = LS.run("HC", inst, w, penalty, budget, rng, trace=lambda ev, **d: events.append((ev, d)), **params)
    init = next(d for ev, d in events if ev == "hc_init")
    steps = [d for ev, d in events if ev == "hc_step"]
    N = len(steps)
    detail = set(range(min(5, N))) | set(range(max(0, N - 2), N))
    every = max(1, N // N_COARSE)
    rec.add(0, init["x"], "Penugasan awal acak: tiap sekolah dapat SPPG sembarang (hormati kapasitas).",
            f=init["F"])
    for k, d in enumerate(steps):
        if k not in detail and k % every:
            continue
        x_before = d["x"]
        kind, school, v = d["move"]
        x_after = list(x_before)
        if kind == 0:
            x_after[school] = v
        else:
            x_after[school], x_after[v] = x_after[v], x_after[school]
        info = {"Langkah": f"{k + 1:,}/{N:,}", "dF": f"{d['dF']:+.4f}", "Evaluasi": f"{d['evals']:,}"}
        rec.add(2, x_before, f"Langkah {k + 1}/{N}: nilai semua pindah & tukar dari x.", info, f=d["F"],
                hl=[school])
        if kind == 0:
            msg = f"dF terkecil: pindahkan {inst.school_name(school)} ke {inst.depot_name(v)}."
        else:
            msg = f"dF terkecil: tukar {inst.school_name(school)} <-> {inst.school_name(v)}."
        rec.add(4, x_after, msg, info, f=d["F"] + d["dF"], hl=[school] + ([v] if kind == 1 else []))
    rec.add(6, res.assignment, "Optimum lokal (tidak ada tetangga lebih baik): berhenti.", f=res.fitness)
    return rec.frames, res.routes


SA_CODE = [
    "x <- penugasan sekolah -> SPPG acak (hormati kapasitas)",
    "T <- T0   (dF memburuk rata-rata diterima dg peluang 0.8)",
    "for iter = 1 ... N:",
    "  y <- tetangga acak dari x (satu pindah atau tukar)",
    "  dF <- F(y) - F(x)",
    "  if dF <= 0 or rand() < e^(-dF/T):",
    "    x <- y          > diterima",
    "  else: buang y     > ditolak",
    "  T <- a.T          (pendinginan geometrik)",
    "return x terbaik",
]


def record_sa_alloc(inst, w, penalty, budget, seed, params):
    router = Router(inst, w, penalty)
    rec = AllocRecorder(inst, w, penalty, router)
    events = []
    rng = np.random.default_rng(seed * 1000 + int(w * 100))
    res = LS.run("SA", inst, w, penalty, budget, rng, trace=lambda ev, **d: events.append((ev, d)), **params)
    init = next(d for ev, d in events if ev == "sa_init")
    steps = [d for ev, d in events if ev == "sa_step"]
    N = len(steps)
    alpha = init["alpha"]
    detail = set(range(5)) | set(range(N // 3, N // 3 + 2)) | set(range(max(0, N - 2), N))
    every = max(1, N // N_COARSE)
    rec.add(0, init["x"], "Penugasan awal acak: biasanya masih melanggar kapasitas (penalti besar).",
            f=init["F"])
    rec.add(1, init["x"], f"Suhu awal T0 = {init['T0']:.4f}.", {"T": f"{init['T0']:.4f}"}, f=init["F"])
    for k, d in enumerate(steps):
        if k not in detail and k % every:
            continue
        x_before = d["x"]
        kind, school, v = d["move"]
        x_after = list(x_before)
        if kind == 0:
            x_after[school] = v
        else:
            x_after[school], x_after[v] = x_after[v], x_after[school]
        f_after = d["F"] + d["dF"]
        p = 1.0 if d["dF"] <= 0 else math.exp(-d["dF"] / d["T"])
        info = {"Iterasi": f"{k + 1:,}/{N:,}", "T": f"{d['T']:.5f}", "dF": f"{d['dF']:+.4f}"}
        if k in detail:
            rec.add(3, x_after, "Tetangga y dari x (satu pindah/tukar acak).", info, f=f_after)
            rec.add(5, x_after, ("dF <= 0: y lebih baik, langsung diterima." if d["dF"] <= 0 else
                                  f"y lebih buruk, peluang diterima e^(-dF/T) = {p:.3f}"),
                    dict(info, **{"P(terima)": f"{p:.3f}"}), f=f_after)
            rec.add(6 if d["accepted"] else 7, x_after if d["accepted"] else x_before,
                    "y diterima, menjadi solusi sekarang." if d["accepted"] else "y ditolak, x tetap.",
                    info, f=f_after if d["accepted"] else d["F"])
            rec.add(8, x_after if d["accepted"] else x_before, f"Suhu diturunkan: T <- {d['T'] * alpha:.5f}.",
                    info, f=f_after if d["accepted"] else d["F"])
        else:
            rec.add(6 if d["accepted"] else 7, x_after if d["accepted"] else x_before,
                    f"Iterasi {k + 1:,}: {'diterima' if d['accepted'] else 'ditolak'} "
                    f"(T makin kecil -> makin jarang menerima solusi buruk).", info,
                    f=f_after if d["accepted"] else d["F"])
    rec.add(9, res.assignment, "Selesai: kembalikan x terbaik yang pernah ditemukan.", f=res.fitness)
    return rec.frames, res.routes


GA_CODE = [
    "P <- 100 kromosom acak (gen ke-s = SPPG untuk sekolah s)",
    "evaluasi tiap kromosom: F = total biaya rute optimal tiap SPPG",
    "for gen = 1 ... G:",
    "  P' <- 2 individu elit terbaik dari P",
    "  while |P'| < 100:",
    "    p1, p2 <- tournament(P, k = 3)",
    "    anak <- uniform crossover(p1, p2)  (peluang 0.9; tiap gen 50:50 p1/p2)",
    "    tiap gen anak diacak ulang dg peluang 1/n  (mutasi)",
    "    P' <- P' + {anak}",
    "  P <- P'",
    "return individu terbaik",
]


def record_ga_alloc(inst, w, penalty, budget, seed, params):
    router = Router(inst, w, penalty)
    rec = AllocRecorder(inst, w, penalty, router)
    gens, children = [], []

    def tr(ev, **d):
        if ev == "ga_gen":
            i = int(np.argmin(d["fit"]))
            gens.append({"gen": d["gen"], "best": d["pop"][i], "best_f": float(d["fit"][i]),
                        "mean_f": float(np.mean(d["fit"])), "evals": d["evals"]})
        elif ev == "ga_child" and d["gen"] == 1 and len(children) < 3:
            children.append(dict(d))

    rng = np.random.default_rng(seed * 1000 + int(w * 100))
    res = LS.run("GA", inst, w, penalty, budget, rng, trace=tr, **params)
    G = gens[-1]["gen"]
    every = max(1, G // N_COARSE)

    def info(g):
        return {"Generasi": f"{g['gen']}/{G}", "f terbaik": round(g["best_f"], 4),
                "f rata-rata": round(g["mean_f"], 4), "Evaluasi": f"{g['evals']:,}"}

    g0 = gens[0]
    rec.add(0, g0["best"], "100 kromosom acak. Gen ke-s = SPPG sekolah s.", info(g0), f=g0["best_f"])
    rec.add(1, g0["best"], "Evaluasi: F = total biaya rute optimal tiap SPPG. Peta: individu terbaik.",
            info(g0), f=g0["best_f"])
    for c in children:
        ci = info(g0)
        rec.add(5, c["p1"], "Tournament: ambil 3 acak, terbaik jadi induk 1 (di peta).", ci)
        rec.add(6, c["child"] if c["crossed"] else c["p1"],
                "Uniform crossover: tiap gen diambil 50:50 dari p1/p2." if c["crossed"]
                else "Tanpa crossover (peluang 0.1): anak = salinan p1.", ci)
        rec.add(7, c["child"], "Sebagian gen anak diacak ulang (mutasi)." if c["mutated"]
                else "Tidak ada gen yang dimutasi kali ini.", ci, f=c["child_f"])
        rec.add(8, c["child"], "Anak masuk populasi baru.", ci, f=c["child_f"])
    for g in gens[1:]:
        if g["gen"] % every and g["gen"] not in (1, G):
            continue
        rec.add(9, g["best"], f"Generasi {g['gen']}: peta menampilkan individu terbaik.", info(g), f=g["best_f"])
    rec.add(10, res.assignment, "Selesai: kembalikan individu terbaik.", f=res.fitness)
    return rec.frames, res.routes


# ============================================================================= Bagian A
# Pencarian rute terbaik di dalam satu SPPG (sub-masalah nyata dari Bagian B).
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
    res = SEARCHES[algo](problem, trace=lambda ev, **d: events.append((ev, d)))
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
    res = SEARCHES["BFS"](problem, trace=lambda ev, **d: events.append((ev, d)))
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
    res = SEARCHES["DFS-B&B"](problem, trace=lambda ev, **d: events.append((ev, d)))
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
    frames.append({"l": 6, "r": pack(res.routes), "m": "Selesai: kembalikan rute terbaik (incumbent terakhir).",
                  "i": {"f": round(res.cost, 4), "g(n)": round(res.cost, 4),
                        "Sekolah terlayani": f"{problem.k}/{problem.k}"}})
    return frames, res.routes


def pick_subproblem(inst, out):
    """Depot sub-masalah nyata untuk tahap 2: dari penugasan terbaik Bagian B
    (ls_best.json), ambil SPPG dengan sekolah terbanyak, dibatasi k <= 9 supaya
    BFS/DFS-B&B tetap cepat dianimasikan (sama batas dengan run_search.py)."""
    best = json.loads((out / "ls_best.json").read_text(encoding="utf-8"))
    top = min((k for k in best if k not in ("best_known_fitness", "Greedy")),
              key=lambda k: best[k]["fitness"])
    per_depot = defaultdict(list)
    for d, seq in best[top]["routes"]:
        per_depot[d].extend(seq)
    candidates = sorted(per_depot.items(), key=lambda kv: -len(kv[1]))
    for d, schools in candidates:
        if len(schools) <= 9:
            return d, sorted(schools)
    d, schools = candidates[-1]
    return d, sorted(schools)


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
                         "km": round(float(inst.D[a, b]), 3), "g": geoms[k]})
            t += dt
            if b >= inst.m:
                stops.append({"s": b - inst.m, "arr": round(t, 3), "dep": round(t + inst.service, 3)})
                t += inst.service
        vehicles.append({"v": v, "d": d, "segs": segs, "stops": stops, "end": round(t, 3)})
    ev = inst.evaluate(routes)
    return {"veh": vehicles, "cost": round(ev.cost), "km": round(ev.km, 2),
            "mean": round(ev.mean_arrival, 2), "makespan": round(ev.makespan, 2)}


# ------------------------------------------------------------------------------- main
def build(name, cfg, budget, seed):
    inst = load_instance(ROOT, name, cfg)
    w = cfg["experiment"]["main_weight"]
    pen = cfg["experiment"]["penalty"]
    out = ROOT / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    print(f"{name}: {inst.m} SPPG, {inst.n} sekolah")

    # ---- tahap 1: Alokasi SPPG (Bagian B)
    alloc = {}
    for label, code, fn in [
        ("HC", HC_CODE, record_hc_alloc),
        ("SA", SA_CODE, record_sa_alloc),
        ("GA", GA_CODE, record_ga_alloc),
    ]:
        t0 = time.time()
        params = cfg["assignment"]["algorithms"][label]
        frames, routes = fn(inst, w, pen, budget, seed, params)
        alloc[label] = {"code": code, "frames": frames, "final": pack(routes)}
        print(f"  [alokasi] {label:8} {len(frames):4} frame  ({time.time() - t0:.0f} s)")

    legs = LegCache(inst, out / ".osrm_legs_cache.json")
    for label, a in alloc.items():
        routes = [(r[0], r[1:]) for r in a["final"]]
        a["delivery"] = delivery_plan(inst, routes, legs)
    legs.save()

    # ---- tahap 2: Rute terbaik dalam satu SPPG (Bagian A), sub-masalah nyata
    depot, schools = pick_subproblem(inst, out)
    print(f"  [rute] sub-masalah: {inst.nodes[depot]['id']} ({inst.nodes[depot]['name']}), "
          f"{len(schools)} sekolah")
    problem = RoutingProblem(inst, depot, schools, w)
    route = {}
    for label, code, fn, args in [
        ("BFS", BFS_CODE, record_bfs, ()),
        ("UCS", UCS_CODE, record_bestfirst, ("UCS", BESTFIRST_LINES, lambda n: n.g)),
        ("A*", ASTAR_CODE, record_bestfirst, ("A*", ASTAR_LINES, lambda n: n.g + problem.h(n.state))),
        ("GBFS", GBFS_CODE, record_bestfirst, ("GBFS", BESTFIRST_LINES, lambda n: problem.h(n.state))),
        ("DFS-B&B", DFSBB_CODE, record_dfsbb, ()),
    ]:
        t0 = time.time()
        frames, routes = fn(problem, *args) if args else fn(problem)
        route[label] = {"code": code, "frames": frames, "final": pack(routes)}
        print(f"  [rute]    {label:8} {len(frames):4} frame  ({time.time() - t0:.0f} s)")

    data = {
        "instance": name, "m": inst.m, "n": inst.n, "Q": inst.Q, "service": inst.service,
        "max_time": inst.max_time, "w": w, "seed": seed, "budget": budget,
        "colors": DEPOT_COLORS, "delivery_code": DELIVERY_CODE,
        "nodes": [{"id": n["id"], "name": n["name"], "lat": n["lat"], "lon": n["lon"]} for n in inst.nodes],
        "alloc": alloc, "route": route,
        "route_depot": {"id": inst.nodes[depot]["id"], "name": inst.nodes[depot]["name"], "k": len(schools)},
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
    """Geometri jalan asli untuk setiap ruas yang muncul di animasi tahap 1 & 2, sehingga
    rute di setiap frame digambar mengikuti jalan (bukan garis lurus)."""
    pairs = set()
    for group in (data["alloc"], data["route"]):
        for a in group.values():
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
    ap.add_argument("--budget", type=int, default=cfg["experiment"]["budget_evals"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--html-only", action="store_true",
                    help="hanya render ulang HTML dari data tersimpan (setelah mengubah template)")
    args = ap.parse_args()
    for name in args.instances:
        out = ROOT / "results" / name
        if args.html_only:
            data = json.loads((out / ".animasi_data.json").read_text(encoding="utf-8"))
            render_html(data, out / "animasi.html")
        else:
            build(name, cfg, args.budget, args.seed)


if __name__ == "__main__":
    main()
