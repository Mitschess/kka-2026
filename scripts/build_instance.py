"""Bangun instance VRP (titik SPPG + sekolah + matriks jarak/waktu jalan asli).

Langkah:
1. Baca data/raw/sppg.csv dan data/raw/schools_osm.csv
2. Pilih sekolah: round-robin, tiap SPPG bergantian mengambil sekolah acak
   (seed tetap) dalam radius radius_km yang belum terpilih, sampai jumlah
   sekolah = n_schools (lihat config.json)
3. Hitung matriks jarak (km) dan waktu tempuh (menit) lewat OSRM (OpenStreetMap
   routing, kondisi jalan lancar -> sesuai asumsi "tidak ada macet").
   Kalau OSRM gagal, pakai jarak haversine x 1.4 dan kecepatan 30 km/jam.

Output: data/instances/<nama>/{nodes.csv, dist_km.csv, time_min.csv, meta.json}

Jalankan:  python scripts/build_instance.py            (semua instance di config)
           python scripts/build_instance.py surabaya_utara
"""
import csv
import json
import math
import random
import sys
from datetime import date
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"User-Agent": "KKA-ETS-MBG-VRP/1.0"}
OSRM_URL = "https://router.project-osrm.org/table/v1/driving/"
MIN_SEPARATION_KM = 0.03  # sekolah yang titiknya < 30 m dianggap duplikat


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def select_schools(sppg, schools, n_schools, radius_km, seed):
    """Tiap SPPG bergantian mengambil sekolah acak dalam radius `radius_km`."""
    rng = random.Random(seed)
    pools = []
    for s in sppg:
        pool = [x for x in schools
                if haversine_km(s["lat"], s["lon"], x["lat"], x["lon"]) <= radius_km]
        rng.shuffle(pool)
        pools.append(iter(pool))

    chosen, names = [], set()
    while len(chosen) < n_schools:
        added = False
        for it in pools:
            if len(chosen) >= n_schools:
                break
            for cand in it:
                if cand["name"].lower() in names:
                    continue
                if any(haversine_km(cand["lat"], cand["lon"], c["lat"], c["lon"]) < MIN_SEPARATION_KM
                       for c in chosen):
                    continue
                chosen.append(cand)
                names.add(cand["name"].lower())
                added = True
                break
        if not added:
            raise ValueError("Sekolah dalam radius tidak cukup, perbesar radius_km")
    return chosen


def osrm_matrix(nodes):
    coords = ";".join(f"{n['lon']:.6f},{n['lat']:.6f}" for n in nodes)
    resp = requests.get(OSRM_URL + coords, params={"annotations": "distance,duration"},
                        headers=HEADERS, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise RuntimeError(data)
    dist_km = np.array(data["distances"], dtype=float) / 1000.0
    time_min = np.array(data["durations"], dtype=float) / 60.0
    return dist_km, time_min


def fallback_matrix(nodes, detour=1.4, speed_kmh=30.0):
    n = len(nodes)
    dist_km = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_km[i, j] = detour * haversine_km(nodes[i]["lat"], nodes[i]["lon"],
                                                      nodes[j]["lat"], nodes[j]["lon"])
    return dist_km, dist_km / speed_kmh * 60.0


def build(name, spec):
    sppg_all = {r["id"]: r for r in read_csv(ROOT / "data" / "raw" / "sppg.csv")}
    sppg = []
    for sid in spec["sppg_ids"]:
        r = dict(sppg_all[sid])
        r["lat"], r["lon"] = float(r["lat"]), float(r["lon"])
        sppg.append(r)
    schools = read_csv(ROOT / "data" / "raw" / "schools_osm.csv")
    for s in schools:
        s["lat"], s["lon"] = float(s["lat"]), float(s["lon"])

    chosen = select_schools(sppg, schools, spec["n_schools"], spec["radius_km"], spec["seed"])
    nodes = ([{"id": s["id"], "type": "sppg", "name": s["name"], "lat": s["lat"], "lon": s["lon"]}
              for s in sppg] +
             [{"id": s["osm_id"], "type": "school", "name": s["name"], "lat": s["lat"], "lon": s["lon"]}
              for s in chosen])

    try:
        dist_km, time_min = osrm_matrix(nodes)
        source = "OSRM (router.project-osrm.org, profil driving, data OpenStreetMap)"
    except Exception as exc:  # noqa: BLE001
        print(f"  OSRM gagal ({exc}); pakai haversine x1.4 @30 km/jam")
        dist_km, time_min = fallback_matrix(nodes)
        source = "fallback haversine x1.4, 30 km/jam"

    out = ROOT / "data" / "instances" / name
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "nodes.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "id", "type", "name", "lat", "lon"])
        writer.writeheader()
        for i, n in enumerate(nodes):
            writer.writerow({"index": i, **n})
    np.savetxt(out / "dist_km.csv", dist_km, delimiter=",", fmt="%.4f")
    np.savetxt(out / "time_min.csv", time_min, delimiter=",", fmt="%.4f")
    meta = {"name": name, "n_sppg": len(sppg), "n_schools": len(chosen),
            "vehicles_per_sppg": spec["vehicles_per_sppg"], "radius_km": spec["radius_km"],
            "seed": spec["seed"], "matrix_source": source,
            "built_on": date.today().isoformat()}
    with open(out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"  {name}: {len(sppg)} SPPG, {len(chosen)} sekolah, matriks dari {source}")


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(config["instances"])
    for name in names:
        build(name, config["instances"][name])


if __name__ == "__main__":
    main()
