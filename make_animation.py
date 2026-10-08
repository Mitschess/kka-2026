"""Animasi gaya VisuAlgo: (1) jalannya algoritma mencari rute, (2) Granmax mengantar MBG.

Setiap algoritma dijalankan sekali (seed 1, bobot utama w) dengan callback `trace`
untuk merekam langkah-langkahnya. Untuk Greedy/SA/GA/ACO hasilnya sama persis dengan
run seed 1 di eksperimen (trace tidak memakai rng). NSGA-II memakai anggaran yang sama
dengan algoritma lain (bukan 5x seperti di eksperimen) supaya animasinya tidak terlalu panjang.

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

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mbgvrp import algorithms as A  # noqa: E402
from mbgvrp import encoding as enc  # noqa: E402
from mbgvrp.construct import decode_order  # noqa: E402
from mbgvrp.problem import load_instance  # noqa: E402
from mbgvrp.viz import DEPOT_COLORS  # noqa: E402

TEMPLATE = ROOT / "src" / "mbgvrp" / "animation_template.html"
N_COARSE = 160          # perkiraan jumlah frame "cepat" per algoritma
TOP_PHEROMONE = 70      # jumlah jalur feromon terkuat yang digambar (ACO)


def pack(routes):
    """[(depot, [sekolah...])] -> [[depot, s1, s2, ...]] (rute kosong dibuang)."""
    return [[int(d)] + [int(s) for s in seq] for d, seq in routes if len(seq)]


class Recorder:
    """Mengubah event trace menjadi frame animasi {l, r, m, i, ...}."""

    def __init__(self, inst, w, penalty):
        self.inst, self.w, self.penalty = inst, w, penalty
        self.frames = []

    def metrics(self, routes, f=None):
        ev = self.inst.evaluate(routes)
        if f is None:
            f = self.inst.scalarize(ev, self.w, self.penalty)
        served = sum(len(seq) for _, seq in routes)
        # evaluate() membagi dengan n; untuk solusi parsial (Greedy di tengah jalan)
        # rata-rata dihitung atas sekolah yang sudah masuk rute saja
        mean = ev.mean_arrival * self.inst.n / served if served else 0.0
        out = {"f": round(f, 4), "Biaya bensin": f"Rp{ev.cost:,.0f}",
               "Rata-rata tiba": f"{mean:.1f} mnt", "Granmax": ev.n_vehicles}
        if served < self.inst.n:
            out["Sekolah di rute"] = f"{served}/{self.inst.n}"
        if not ev.feasible:
            out["Melanggar"] = (f"kapasitas +{ev.cap_excess}" if ev.cap_excess else "") + \
                               (f" armada +{ev.veh_excess}" if ev.veh_excess else "") + \
                               (f" telat {ev.late_min:.0f} mnt" if ev.late_min else "")
        return out

    def add(self, line, routes, msg, info=None, f=None, **extra):
        i = dict(info or {})
        i.update(self.metrics(routes, f))
        fr = {"l": line, "r": pack(routes), "m": msg, "i": i}
        fr.update(extra)
        self.frames.append(fr)


# ----------------------------------------------------------------------------- Greedy
GREEDY_CODE = [
    "rute ← kosong; semua sekolah belum dilayani",
    "while masih ada sekolah belum dilayani:",
    "  for tiap sekolah j × tiap opsi (ujung rute / Granmax baru):",
    "    Δ ← w·Δbiaya/ref + (1−w)·tiba_j/(n·ref)",
    "  pilih opsi feasible (tiba ≤ 180 mnt) dengan Δ terkecil",
    "  tambahkan sekolah j ke rute tersebut",
    "return rute",
]


def record_greedy(inst, w, penalty, cfg):
    rec = Recorder(inst, w, penalty)
    steps = []
    res = A.run_greedy(inst, w, penalty, trace=lambda ev, **d: steps.append(d))
    rec.add(0, [], "Mulai dari nol: belum ada Granmax yang berangkat.")
    prev = []
    for k, d in enumerate(steps, start=1):
        s = d["school"]
        name = inst.school_name(s)
        info = {"Langkah": f"{k}/{inst.n}"}
        rec.add(1, prev, f"Masih ada {inst.n - k + 1} sekolah yang belum dilayani.", info)
        rec.add(3, prev, f"Menilai {d['n_options']} kombinasi (sekolah, opsi) yang feasible.", info)
        how = "membuka Granmax baru dari SPPG" if d["new_route"] else "menyambung di ujung rute"
        rec.add(4, prev, f"Δ terkecil: {name} ({how}), tiba {d['arrive']:.1f} mnt.", info, hl=[s])
        rec.add(5, d["routes"], f"{name} ditambahkan ke rute.", info, hl=[s])
        prev = d["routes"]
    rec.add(6, res.routes, "Selesai: semua sekolah sudah punya Granmax.", f=res.fitness)
    return rec.frames, res.routes


# -------------------------------------------------------------------------------- SA
SA_CODE = [
    "x ← solusi acak (urutan sekolah + pemisah antar-Granmax)",
    "T ← T₀   (kenaikan f rata-rata diterima dg peluang 0.8)",
    "for iter = 1 … N:",
    "  y ← tetangga(x)   (swap / insert / inversion acak)",
    "  Δ ← f(y) − f(x)",
    "  if Δ ≤ 0 or rand() < e^(−Δ/T):",
    "    x ← y          ▸ diterima",
    "  else: buang y    ▸ ditolak",
    "  T ← α·T          (pendinginan geometrik)",
    "return x terbaik",
]


def record_sa(inst, w, penalty, cfg, budget, seed):
    rec = Recorder(inst, w, penalty)
    events = []
    rng = np.random.default_rng(seed * 1000 + int(w * 100))
    res = A.run_sa(inst, w, penalty, budget=budget, rng=rng, trace=lambda ev, **d: events.append((ev, d)),
                   **cfg["algorithms"]["sa"])
    init = events[0][1]
    steps = [d for ev, d in events[1:]]
    N = len(steps)
    detail = set(range(1, 6)) | set(range(N // 3, N // 3 + 2)) | set(range(N - 2, N + 1))
    every = max(1, N // N_COARSE)
    x0 = enc.decode(inst, init["x"])
    rec.add(0, x0, "Solusi awal acak: biasanya masih melanggar kapasitas (penalti besar).", f=init["fx"])
    rec.add(1, x0, f"Suhu awal T₀ = {init['T0']:.4f}, α = {init['cooling']:.6f}.",
            {"T": f"{init['T0']:.4f}"}, f=init["fx"])
    for d in steps:
        it = d["it"]
        if it not in detail and it % every:
            continue
        x = enc.decode(inst, d["x"])
        y = enc.decode(inst, d["y"])
        delta = d["fy"] - d["fx"]
        p = 1.0 if delta <= 0 else math.exp(-delta / d["temp"])
        info = {"Iterasi": f"{it:,}/{N:,}", "T": f"{d['temp']:.5f}", "f(x)": round(d["fx"], 4),
                "f terbaik": round(d["best_f"], 4)}
        new_x, new_f = (y, d["fy"]) if d["accepted"] else (x, d["fx"])
        if it in detail:
            rec.add(3, y, "Kandidat tetangga y dari x (satu operasi acak).", info, f=d["fy"])
            rec.add(4, y, f"Δ = f(y) − f(x) = {delta:+.4f}", dict(info, Δ=f"{delta:+.4f}"), f=d["fy"])
            rec.add(5, y, ("Δ ≤ 0: y lebih baik, langsung diterima." if delta <= 0 else
                           f"y lebih buruk, peluang diterima e^(−Δ/T) = {p:.3f}"),
                    dict(info, Δ=f"{delta:+.4f}", **{"P(terima)": f"{p:.3f}"}), f=d["fy"])
            rec.add(6 if d["accepted"] else 7, new_x,
                    "y diterima, menjadi solusi sekarang." if d["accepted"] else "y ditolak, x tetap.",
                    info, f=new_f)
            rec.add(8, new_x, "Suhu diturunkan sedikit.", info, f=new_f)
        else:
            rec.add(6 if d["accepted"] else 7, new_x,
                    f"Iterasi {it:,}: {'diterima' if d['accepted'] else 'ditolak'} "
                    f"(T makin kecil → makin jarang menerima solusi buruk).", info, f=new_f)
    rec.add(9, res.routes, "Selesai: kembalikan solusi terbaik yang pernah ditemukan.", f=res.fitness)
    return rec.frames, res.routes


# -------------------------------------------------------------------------------- GA
GA_CODE = [
    "P ← 100 urutan sekolah acak",
    "evaluasi: decoder greedy mengubah urutan → rute",
    "for gen = 1 … G:",
    "  P' ← 2 individu elit terbaik dari P",
    "  while |P'| < 100:",
    "    p1, p2 ← tournament(P, k = 3)",
    "    anak ← order_crossover(p1, p2)   (peluang 0.9)",
    "    if rand() < 0.3: anak ← mutasi(anak)",
    "    P' ← P' ∪ {anak}",
    "  P ← P'",
    "return individu terbaik",
]


def record_ga(inst, w, penalty, cfg, budget, seed):
    rec = Recorder(inst, w, penalty)
    gens, children = [], []

    def tr(ev, **d):
        if ev == "ga_gen":
            i = int(np.argmin(d["fit"]))
            gens.append({"gen": d["gen"], "best": d["pop"][i].copy(), "best_f": float(d["fit"][i]),
                         "mean_f": float(np.mean(d["fit"])), "evals": d["evals"]})
        elif d["gen"] == 1 and len(children) < 3:
            children.append({k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in d.items()})

    rng = np.random.default_rng(seed * 1000 + int(w * 100))
    res = A.run_ga(inst, w, penalty, budget=budget, rng=rng, trace=tr, **cfg["algorithms"]["ga"])
    dec = lambda order: decode_order(inst, order.tolist(), w)  # noqa: E731
    G = gens[-1]["gen"]
    every = max(1, G // N_COARSE)

    def info(g):
        return {"Generasi": f"{g['gen']}/{G}", "f terbaik": round(g["best_f"], 4),
                "f rata-rata": round(g["mean_f"], 4), "Evaluasi": f"{g['evals']:,}"}

    g0 = gens[0]
    rec.add(0, dec(g0["best"]), "100 kromosom acak. Kromosom = urutan sekolah diproses.", info(g0),
            f=g0["best_f"])
    rec.add(1, dec(g0["best"]), "Decoder menaruh sekolah satu per satu di opsi termurah. "
            "Peta: individu terbaik.", info(g0), f=g0["best_f"])
    for c in children:
        ci = info(g0)
        rec.add(5, dec(c["p1"]), "Tournament: ambil 3 acak, yang terbaik jadi induk 1 (di peta).", ci)
        rec.add(6, dec(c["child"]) if c["crossed"] else dec(c["p1"]),
                "Order crossover: potongan urutan dari p1, sisanya mengikuti urutan p2." if c["crossed"]
                else "Tanpa crossover (peluang 0.1): anak = salinan p1.", ci)
        rec.add(7, dec(c["child"]), "Anak dimutasi (swap/insert/inversion)." if c["mutated"]
                else "Tidak dimutasi kali ini.", ci, f=c["child_f"])
        rec.add(8, dec(c["child"]), "Anak masuk populasi baru.", ci, f=c["child_f"])
    for g in gens[1:]:
        if g["gen"] % every and g["gen"] not in (1, G):
            continue
        rec.add(9, dec(g["best"]), f"Generasi {g['gen']}: peta menampilkan individu terbaik.", info(g),
                f=g["best_f"])
    rec.add(10, res.routes, "Selesai: kembalikan individu terbaik.", f=res.fitness)
    return rec.frames, res.routes


# ------------------------------------------------------------------------------- ACO
ACO_CODE = [
    "τ ← τmax pada semua jalur",
    "for iter = 1 … I:",
    "  for semut k = 1 … 20:",
    "    bangun rute: pilih (rute, sekolah) ∝ τ^α · (1/Δ)^β",
    "  catat semut terbaik iterasi ini",
    "  τ ← (1 − ρ)·τ          (penguapan, ρ = 0.1)",
    "  deposit 1/f di jalur semut terbaik (tiap 5 iterasi: terbaik global)",
    "  batasi τ ke [τmin, τmax]   (MAX-MIN Ant System)",
    "return rute terbaik",
]


def pheromone_edges(inst, tau, tau_min, tau_max):
    n_nodes = inst.m + inst.n
    t = tau.copy()
    np.fill_diagonal(t, 0)
    flat = np.argsort(t, axis=None)[::-1][:TOP_PHEROMONE]
    out = []
    for f in flat:
        a, b = divmod(int(f), n_nodes)
        v = (t[a, b] - tau_min) / (tau_max - tau_min) if tau_max > tau_min else 0
        if v > 0.02:
            out.append([a, b, round(float(v), 3)])
    return out


def record_aco(inst, w, penalty, cfg, budget, seed):
    rec = Recorder(inst, w, penalty)
    ants, iters = [], []
    params = cfg["algorithms"]["aco"]
    n_ants = params["n_ants"]
    total_iters = budget // n_ants
    every = max(1, total_iters // N_COARSE)

    def tr(ev, **d):
        if ev == "aco_ant":
            if d["it"] < 2 and d["ant"] < 3:
                ants.append(d)
        elif d["it"] < 2 or d["it"] % every == 0 or d["it"] == total_iters - 1:
            d = dict(d, ph=pheromone_edges(inst, d["tau"], d["tau_min"], d["tau_max"]))
            del d["tau"]
            iters.append(d)

    rng = np.random.default_rng(seed * 1000 + int(w * 100))
    res = A.run_aco(inst, w, penalty, budget=budget, rng=rng, trace=tr, **params)
    I = iters[-1]["it"] + 1
    rec.add(0, [], "Semua jalur diberi feromon maksimum yang sama.", ph=[])
    for d in iters:
        it = d["it"]
        info = {"Iterasi": f"{it + 1}/{I}", "f iterasi": round(d["it_best_f"], 4),
                "f terbaik": round(d["best_f"], 4), "Evaluasi": f"{d['evals']:,}"}
        if it < 2:
            for a in (x for x in ants if x["it"] == it):
                rec.add(3, a["routes"], f"Semut {a['ant'] + 1} membangun rute secara probabilistik.",
                        info, f=a["f"])
            rec.add(4, d["it_best_routes"], "Semut terbaik pada iterasi ini.", info, f=d["it_best_f"])
            rec.add(5, d["it_best_routes"], "Feromon menguap 10% di semua jalur.", info,
                    f=d["it_best_f"], ph=d["ph"])
            rec.add(6, d["best_routes"] if d["deposit_best"] else d["it_best_routes"],
                    "Feromon ditambah di jalur semut terbaik (garis cokelat = feromon kuat).",
                    info, f=d["best_f"] if d["deposit_best"] else d["it_best_f"], ph=d["ph"])
        rec.add(7, d["best_routes"], f"Iterasi {it + 1}: feromon terkonsentrasi di jalur yang bagus.",
                info, f=d["best_f"], ph=d["ph"])
    rec.add(8, res.routes, "Selesai: kembalikan rute terbaik.", f=res.fitness, ph=iters[-1]["ph"])
    return rec.frames, res.routes


# ---------------------------------------------------------------------------- NSGA-II
NSGA_CODE = [
    "P ← 100 individu acak (urutan sekolah + gen bobot decoder)",
    "evaluasi 2 objektif: biaya bensin & rata-rata waktu tiba",
    "for gen = 1 … G:",
    "  Q ← 100 anak (tournament rank+crowding, crossover, mutasi)",
    "  R ← P ∪ Q",
    "  urutkan R ke front non-dominated F1, F2, …",
    "  P ← F1, F2, … sampai 100 (front terakhir dipilih via crowding distance)",
    "return front F1 (Pareto)",
]


def knee_index(points):
    p = np.array(points)
    lo, hi = p.min(axis=0), p.max(axis=0)
    sc = (p - lo) / np.where(hi > lo, hi - lo, 1)
    return int(np.argmin(np.linalg.norm(sc, axis=1)))


def record_nsga2(inst, w, penalty, cfg, budget, seed):
    rec = Recorder(inst, w, penalty)
    gens = []
    G_est = budget // cfg["algorithms"]["nsga2"]["pop_size"] - 1
    every = max(1, G_est // N_COARSE)

    def tr(ev, **d):
        if d["gen"] > 1 and d["gen"] % every and d["gen"] < G_est:
            return
        rank = {}
        for r, fr in enumerate(d["fronts"]):
            for p in fr:
                rank[p] = r
        f1 = [i for i in d["fronts"][0] if d["viol"][i] == 0]
        knee = None
        if f1:
            k = f1[knee_index([d["objs"][i] for i in f1])]
            knee = decode_order(inst, d["pop"][k][0].tolist(), d["pop"][k][1])
        sc = [[round(o[0] * inst.ref_cost), round(o[1] * inst.ref_time, 2), min(rank[i], 3),
               int(d["viol"][i] > 0)] for i, o in enumerate(d["objs"])]
        gens.append({"gen": d["gen"], "knee": knee, "sc": sc, "evals": d["evals"],
                     "n_f1": len(f1)})

    rng = np.random.default_rng(seed * 1000 + 999)
    res = A.run_nsga2(inst, budget, rng, trace=tr, **cfg["algorithms"]["nsga2"])
    G = gens[-1]["gen"]

    for g in gens:
        info = {"Generasi": f"{g['gen']}/{G}", "Solusi di F1": g["n_f1"], "Evaluasi": f"{g['evals']:,}"}
        routes = g["knee"] or []
        msg_k = "Peta: solusi kompromi (knee) di F1." if g["knee"] else "Belum ada solusi feasible di F1."
        if g["gen"] == 0:
            rec.add(0, routes, "Populasi awal acak. Grafik: biaya vs waktu tiap individu.", info, sc=g["sc"])
            rec.add(1, routes, msg_k, info, sc=g["sc"])
        elif g["gen"] == 1:
            rec.add(3, routes, "Buat 100 anak dari induk hasil tournament.", info, sc=g["sc"])
            rec.add(4, routes, "Gabungkan induk + anak = 200 individu.", info, sc=g["sc"])
            rec.add(5, routes, "Urutkan per front: F1 (biru) tidak didominasi solusi lain.", info, sc=g["sc"])
            rec.add(6, routes, "Ambil 100 terbaik untuk generasi berikutnya. " + msg_k, info, sc=g["sc"])
        else:
            rec.add(6, routes, f"Generasi {g['gen']}: front F1 makin maju ke kiri-bawah. " + msg_k,
                    info, sc=g["sc"])
    pts = [(ev.cost / inst.ref_cost, ev.mean_arrival / inst.ref_time) for _, ev in res.front]
    routes, ev = res.front[knee_index(pts)]
    final_sc = [[round(e.cost), round(e.mean_arrival, 2), 0, 0] for _, e in res.front]
    rec.add(7, routes, f"Selesai: {len(res.front)} solusi Pareto. Peta: solusi knee "
            f"(Rp{ev.cost:,.0f}, {ev.mean_arrival:.1f} mnt).", sc=final_sc)
    return rec.frames, routes


# ------------------------------------------------------------------------ pengiriman
DELIVERY_CODE = [
    "semua Granmax berangkat t = 0 (makanan selesai dimasak)",
    "for tiap Granmax (berjalan paralel):",
    "  for tiap sekolah j di rute:",
    "    jalan ke j   (waktu tempuh jalan asli, OSRM)",
    "    tiba di j: cek t ≤ 180 menit",
    "    drop makanan 15 menit",
    "  kembali ke SPPG",
    "biaya = total km ÷ 14 km/L × Rp10.000",
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
        # kalau OSRM gagal: garis lurus (tidak disimpan ke cache, dicoba lagi lain kali)
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

    algos = {}
    for label, code, fn, args in [
        ("Greedy", GREEDY_CODE, record_greedy, ()),
        ("SA", SA_CODE, record_sa, (budget, seed)),
        ("GA", GA_CODE, record_ga, (budget, seed)),
        ("ACO", ACO_CODE, record_aco, (budget, seed)),
        ("NSGA-II", NSGA_CODE, record_nsga2, (budget, seed)),
    ]:
        t0 = time.time()
        frames, routes = fn(inst, w, pen, cfg, *args)
        algos[label] = {"code": code, "frames": frames, "final": pack(routes)}
        print(f"  {label:8} {len(frames):4} frame  ({time.time() - t0:.0f} s)")

    legs = LegCache(inst, out / ".osrm_legs_cache.json")
    for label, a in algos.items():
        routes = [(r[0], r[1:]) for r in a["final"]]
        a["delivery"] = delivery_plan(inst, routes, legs)
    legs.save()

    data = {
        "instance": name, "m": inst.m, "n": inst.n, "Q": inst.Q, "service": inst.service,
        "max_time": inst.max_time, "w": w, "seed": seed, "budget": budget,
        "colors": DEPOT_COLORS, "delivery_code": DELIVERY_CODE,
        "nodes": [{"id": n["id"], "name": n["name"], "lat": n["lat"], "lon": n["lon"]} for n in inst.nodes],
        "algos": algos,
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
    for a in data["algos"].values():
        for fr in a["frames"]:
            for r in fr["r"]:
                nodes = [r[0]] + [data["m"] + s for s in r[1:]] + [r[0]]
                pairs.update(zip(nodes[:-1], nodes[1:]))
            pairs.update((a_, b_) for a_, b_, _ in fr.get("ph", []))
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
            if "legs" not in data:
                attach_legs(data, out)
                (out / ".animasi_data.json").write_text(json.dumps(data), encoding="utf-8")
            render_html(data, out / "animasi.html")
        else:
            build(name, cfg, args.budget, args.seed)


if __name__ == "__main__":
    main()
