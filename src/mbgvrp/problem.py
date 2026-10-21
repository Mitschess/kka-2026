"""Definisi masalah: Multi-Depot VRP pengiriman MBG dari SPPG ke sekolah.

Indeks node: 0..m-1 = SPPG (depot), m..m+n-1 = sekolah.
Sekolah ke-s (0..n-1) berada di node m+s.

Sebuah solusi = daftar rute. Satu rute = satu Granmax: (depot, [sekolah, ...]).
Semua makanan selesai dimasak dan berangkat bersamaan di t = 0 (asumsi 3 & 4).

Objektif (keduanya diminimalkan, digabung jadi weighted sum di search.py):
  f1 = biaya bensin total (Rp)  = total km / km_per_liter * harga_pertalite
  f2 = rata-rata waktu tiba makanan di sekolah (menit sejak berangkat)

Constraint:
  - maksimal Q sekolah per kendaraan (default 3)
  - jumlah kendaraan per SPPG terbatas (dinaikkan bila sekolah terdekatnya kelebihan)
  - waktu tiba di tiap sekolah <= 180 menit (batas selesai masak -> sampai)
  - drop makanan 15 menit per sekolah (menunda sekolah berikutnya di rute)
Sekolah dilayani SPPG terdekat (assign_nearest); rute tiap SPPG dicari di search.py.
"""
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Evaluation:
    cost: float           # f1, Rupiah
    mean_arrival: float   # f2, menit
    makespan: float       # waktu tiba sekolah terakhir, menit
    km: float
    n_vehicles: int


class Instance:
    def __init__(self, name, nodes, dist_km, time_min, vehicles_per_depot, params):
        self.name = name
        self.nodes = nodes
        self.depot_idx = [i for i, n in enumerate(nodes) if n["type"] == "sppg"]
        self.m = len(self.depot_idx)
        self.n = len(nodes) - self.m
        assert self.depot_idx == list(range(self.m)), "SPPG harus di indeks awal"

        self.D = np.asarray(dist_km, dtype=float)
        self.T = np.asarray(time_min, dtype=float) * params.get("traffic_factor", 1.0)
        self.Q = params["max_schools_per_vehicle"]
        self.service = params["service_time_min"]
        self.max_time = params["max_delivery_time_min"]
        self.km_per_liter = params["km_per_liter"]
        self.fuel_price = params["fuel_price_per_liter"]
        self.return_to_depot = params["return_to_depot"]
        self.cost_per_km = self.fuel_price / self.km_per_liter

        self.vehicles_per_depot = list(vehicles_per_depot)

        # list-of-list untuk akses cepat di loop Python
        self._D = self.D.tolist()
        self._T = self.T.tolist()

        # Nilai acuan normalisasi: solusi "bintang" (tiap sekolah dikirim langsung
        # dari SPPG terdekat). ref_time = batas bawah rata-rata waktu tiba.
        schools = range(self.m, self.m + self.n)
        self.ref_time = float(np.mean([self.T[:self.m, j].min() for j in schools]))
        round_trip = self.D[:self.m, self.m:] + (self.D[self.m:, :self.m].T if self.return_to_depot else 0)
        self.ref_cost = float(round_trip.min(axis=0).sum() * self.cost_per_km)

    # ------------------------------------------------------------------ evaluasi
    def evaluate(self, routes):
        """routes: iterable (depot, [school_idx, ...]). Mengembalikan Evaluation."""
        D, T, m = self._D, self._T, self.m
        total_km = arrival_sum = makespan = 0.0
        n_vehicles = 0
        for d, seq in routes:
            if not seq:
                continue
            n_vehicles += 1
            prev, t = d, 0.0
            for s in seq:
                node = m + s
                t += T[prev][node]
                total_km += D[prev][node]
                arrival_sum += t
                makespan = max(makespan, t)
                t += self.service
                prev = node
            if self.return_to_depot:
                total_km += D[prev][d]
        return Evaluation(cost=total_km * self.cost_per_km, mean_arrival=arrival_sum / self.n,
                          makespan=makespan, km=total_km, n_vehicles=n_vehicles)


def assign_nearest(inst):
    """Tiap sekolah dilayani SPPG terdekat (jarak jalan). Mengembalikan daftar sekolah
    per SPPG. Armada SPPG yang kelebihan sekolah dinaikkan ke ceil(k / Q) (mengubah inst)."""
    owner = inst.D[:inst.m, inst.m:].argmin(axis=0)
    schools = [np.flatnonzero(owner == d).tolist() for d in range(inst.m)]
    inst.vehicles_per_depot = [max(v, -(-len(s) // inst.Q)) for v, s in zip(inst.vehicles_per_depot, schools)]
    return schools


def load_instance(root, name, config, overrides=None):
    """Baca data/instances/<name> + parameter dari config.json."""
    folder = Path(root) / "data" / "instances" / name
    with open(folder / "nodes.csv", encoding="utf-8") as f:
        nodes = list(csv.DictReader(f))
    for n in nodes:
        n["lat"], n["lon"] = float(n["lat"]), float(n["lon"])
    D = np.loadtxt(folder / "dist_km.csv", delimiter=",")
    T = np.loadtxt(folder / "time_min.csv", delimiter=",")
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))

    params = dict(config["problem"])
    vehicles = config["instances"][name]["vehicles_per_sppg"]
    if overrides:
        vehicles = overrides.pop("vehicles_per_sppg", vehicles)
        params.update(overrides)
    m = meta["n_sppg"]
    vehicles_per_depot = vehicles if isinstance(vehicles, list) else [vehicles] * m
    return Instance(name, nodes, D, T, vehicles_per_depot, params)
