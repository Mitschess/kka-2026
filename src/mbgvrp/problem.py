"""Definisi masalah: Multi-Depot VRP pengiriman MBG dari SPPG ke sekolah.

Indeks node: 0..m-1 = SPPG (depot), m..m+n-1 = sekolah.
Sekolah ke-s (0..n-1) berada di node m+s.

Sebuah solusi = daftar rute. Satu rute = satu Granmax: (depot, [sekolah, ...]).
Semua makanan selesai dimasak dan berangkat bersamaan di t = 0 (asumsi 3 & 4).

Objektif (keduanya diminimalkan):
  f1 = biaya bensin total (Rp)  = total km / km_per_liter * harga_pertalite
  f2 = rata-rata waktu tiba makanan di sekolah (menit sejak berangkat)

Constraint:
  - maksimal Q sekolah per kendaraan (default 3)
  - jumlah kendaraan per SPPG terbatas
  - waktu tiba di tiap sekolah <= 180 menit (batas selesai masak -> sampai)
  - drop makanan 15 menit per sekolah (menunda sekolah berikutnya di rute)
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
    cap_excess: int       # jumlah sekolah yang melebihi kapasitas kendaraan
    late_min: float       # total menit keterlambatan di atas batas waktu
    veh_excess: int       # jumlah rute yang melebihi armada SPPG

    @property
    def violation(self):
        return self.cap_excess + self.veh_excess + self.late_min / 10.0

    @property
    def feasible(self):
        return self.violation == 0


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
        # daftar kendaraan: vehicle_depot[k] = SPPG asal kendaraan k
        self.vehicle_depot = [d for d in range(self.m) for _ in range(self.vehicles_per_depot[d])]
        self.R = len(self.vehicle_depot)

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
        total_km = 0.0
        arrival_sum = 0.0
        makespan = 0.0
        cap_excess = 0
        late = 0.0
        used = [0] * self.m
        for d, seq in routes:
            if not seq:
                continue
            used[d] += 1
            if len(seq) > self.Q:
                cap_excess += len(seq) - self.Q
            prev, t = d, 0.0
            for s in seq:
                node = m + s
                t += T[prev][node]
                total_km += D[prev][node]
                arrival_sum += t
                if t > makespan:
                    makespan = t
                if t > self.max_time:
                    late += t - self.max_time
                t += self.service
                prev = node
            if self.return_to_depot:
                total_km += D[prev][d]
        veh_excess = sum(max(0, u - v) for u, v in zip(used, self.vehicles_per_depot))
        return Evaluation(cost=total_km * self.cost_per_km, mean_arrival=arrival_sum / self.n,
                          makespan=makespan, km=total_km, n_vehicles=sum(used),
                          cap_excess=cap_excess, late_min=late, veh_excess=veh_excess)

    def scalarize(self, ev, w, penalty):
        """Weighted sum ternormalisasi: w * f1/ref + (1-w) * f2/ref + penalti."""
        return (w * ev.cost / self.ref_cost + (1 - w) * ev.mean_arrival / self.ref_time
                + penalty * ev.violation)

    def check_complete(self, routes):
        visited = sorted(s for _, seq in routes for s in seq)
        return visited == list(range(self.n))

    # --------------------------------------------------------------- utilitas
    def school_name(self, s):
        return self.nodes[self.m + s]["name"]

    def depot_name(self, d):
        return self.nodes[d]["name"]


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
