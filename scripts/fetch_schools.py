"""Ambil data sekolah di Kota Surabaya dari OpenStreetMap (Overpass API).

Output: data/raw/schools_osm.csv  (osm_id, name, level, lat, lon)
Hanya sekolah jenjang SD/MI/SMP/MTs (sasaran utama MBG di sekolah) yang disimpan.

Jalankan:  python scripts/fetch_schools.py
"""
import csv
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "schools_osm.csv"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
QUERY = """
[out:json][timeout:90];
area["name"="Surabaya"]["boundary"="administrative"]->.a;
(node["amenity"="school"](area.a); way["amenity"="school"](area.a););
out center tags;
"""
HEADERS = {"User-Agent": "KKA-ETS-MBG-VRP/1.0"}

LEVEL_PATTERNS = [
    ("SD", r"\b(SD|SDN|SDS|SEKOLAH DASAR)\b"),
    ("MI", r"\b(MI|MIN|MADRASAH IBTIDAIYAH)\b"),
    ("SMP", r"\b(SMP|SMPN|SMPS|SEKOLAH MENENGAH PERTAMA)\b"),
    ("MTs", r"\b(MTS|MTSN|MADRASAH TSANAWIYAH)\b"),
]


def detect_level(name):
    upper = name.upper()
    for level, pattern in LEVEL_PATTERNS:
        if re.search(pattern, upper):
            return level
    return None


def main():
    elements = None
    for url in OVERPASS_URLS:  # server Overpass sering sibuk, coba mirror lain
        try:
            resp = requests.post(url, data={"data": QUERY}, headers=HEADERS, timeout=120)
            resp.raise_for_status()
            elements = resp.json()["elements"]
            break
        except (requests.RequestException, ValueError) as exc:
            print(f"  {url} gagal: {exc}")
    if elements is None:
        raise SystemExit("Semua server Overpass gagal, coba lagi nanti.")

    rows = []
    for e in elements:
        name = e.get("tags", {}).get("name", "").strip()
        level = detect_level(name) if name else None
        if level is None:
            continue
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        rows.append({"osm_id": f"{e['type']}/{e['id']}", "name": name, "level": level,
                     "lat": lat, "lon": lon})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["osm_id", "name", "level", "lat", "lon"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(elements)} objek sekolah dari OSM, {len(rows)} SD/MI/SMP/MTs disimpan ke {OUT}")


if __name__ == "__main__":
    main()
