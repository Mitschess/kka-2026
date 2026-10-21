"""Bangun Final Report (Word .docx) dari hasil eksperimen.

  python report/build_report.py          # -> report/Laporan_Final_MBG_VRP.docx
  python report/build_report.py --pdf    # (opsional) juga cetak PDF lewat Edge/Chrome

Semua angka diambil dari results/ (CSV/JSON), jadi laporan selalu sinkron dengan
eksperimen terakhir. Identitas tim di bagian IDENTITAS di bawah -> isi sendiri
(atau langsung edit di Word). Isi laporan ditulis sekali sebagai HTML (build_html),
lalu dikonversi ke DOCX oleh html_to_docx.py. Jika Microsoft Word terpasang, daftar
isi (field TOC) langsung di-update; jika tidak, di Word: klik kanan daftar isi -> Update Field.
"""
import csv
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPORT))

import numpy as np  # noqa: E402

from mbgvrp.problem import assign_nearest, load_instance  # noqa: E402
from mbgvrp.search import RoutingProblem  # noqa: E402

# ============================================================== IDENTITAS (isi sendiri)
TEAM = [("[Nama Anggota 1]", "[NRP]"), ("[Nama Anggota 2]", "[NRP]"), ("[Nama Anggota 3]", "[NRP]")]
COURSE = "Konsep Kecerdasan Artifisial (KKA)"
LECTURER = "[Nama Dosen Pengampu]"
INSTITUTION = "[Departemen / Program Studi]<br>[Nama Institusi]"
DATE = "Oktober 2026"
GITHUB = "https://github.com/Mitschess/kka-2026"

SEARCH = ["BFS", "IDS", "DFS-B&B", "UCS", "A* (h1)", "A*", "GBFS"]

# ---------------------------------------------------------------------- pustaka
REFS = {
    "dantzig": "Dantzig, G. B., &amp; Ramser, J. H. (1959). The truck dispatching problem. <i>Management Science</i>, 6(1), 80–91.",
    "toth": "Toth, P., &amp; Vigo, D. (Eds.). (2014). <i>Vehicle Routing: Problems, Methods, and Applications</i> (2nd ed.). SIAM.",
    "cordeau": "Cordeau, J.-F., Gendreau, M., &amp; Laporte, G. (1997). A tabu search heuristic for periodic and multi-depot vehicle routing problems. <i>Networks</i>, 30(2), 105–119.",
    "aima": "Russell, S., &amp; Norvig, P. (2021). <i>Artificial Intelligence: A Modern Approach</i> (4th ed.). Pearson.",
    "fisher": "Fisher, M. L., &amp; Jaikumar, R. (1981). A generalized assignment heuristic for vehicle routing. <i>Networks</i>, 11(2), 109–124.",
    "gillett": "Gillett, B. E., &amp; Miller, L. R. (1974). A heuristic algorithm for the vehicle-dispatch problem. <i>Operations Research</i>, 22(2), 340–349.",
    "dijkstra": "Dijkstra, E. W. (1959). A note on two problems in connexion with graphs. <i>Numerische Mathematik</i>, 1, 269–271.",
    "korf": "Korf, R. E. (1985). Depth-first iterative-deepening: An optimal admissible tree search. <i>Artificial Intelligence</i>, 27(1), 97–109.",
    "land": "Land, A. H., &amp; Doig, A. G. (1960). An automatic method of solving discrete programming problems. <i>Econometrica</i>, 28(3), 497–520.",
    "hart": "Hart, P. E., Nilsson, N. J., &amp; Raphael, B. (1968). A formal basis for the heuristic determination of minimum cost paths. <i>IEEE Transactions on Systems Science and Cybernetics</i>, 4(2), 100–107.",
    "kuhn": "Kuhn, H. W. (1955). The Hungarian method for the assignment problem. <i>Naval Research Logistics Quarterly</i>, 2(1–2), 83–97.",
    "pearl": "Pearl, J. (1984). <i>Heuristics: Intelligent Search Strategies for Computer Problem Solving</i>. Addison-Wesley.",
    "osrm": "Luxen, D., &amp; Vetter, C. (2011). Real-time routing with OpenStreetMap data. <i>Proceedings of the 19th ACM SIGSPATIAL International Conference on Advances in Geographic Information Systems</i>, 513–516.",
    "osm": "OpenStreetMap contributors. (2026). <i>OpenStreetMap</i> [data set, diakses Oktober 2026]. https://www.openstreetmap.org",
    "who": "World Health Organization. (2006). <i>Five Keys to Safer Food Manual</i>. WHO.",
    "perpres": "Peraturan Presiden Republik Indonesia Nomor 83 Tahun 2024 tentang Badan Gizi Nasional.",
    "jawapos": "Jawa Pos. (2026, 14 Mei). Heboh kasus keracunan MBG di Surabaya, ternyata 84 SPPG di Kota Pahlawan belum punya sertifikat laik higiene. https://www.jawapos.com/surabaya-raya/2605140232/",
    "times": "Times Indonesia. (2026). 200 siswa keracunan MBG di Surabaya, Emil Dardak ancam sanksi tegas SPPG Tembok Dukuh. https://timesindonesia.co.id/peristiwa-daerah/589872/",
    "antara1": "ANTARA Jawa Timur. (2025). SPPG Polrestabes Surabaya layani 3.119 porsi MBG. https://jatim.antaranews.com/berita/983209/",
    "antara2": "ANTARA Jawa Timur. (2025). Dapur SPPG Simokerto resmi beroperasi dengan pemberdayaan lokal. https://jatim.antaranews.com/berita/1041086/",
    "prisma": "Pemerintah Kota Surabaya (Prisma). (2025, 16 Agustus). Peresmian Dapur MBG di Wisma Kedung Asem Indah, Kelurahan Kedung Baruk, Kecamatan Rungkut. https://prisma.surabaya.go.id/",
}


class Cite:
    """Nomor pustaka otomatis menurut urutan pertama kali dikutip."""

    def __init__(self):
        self.order = []

    def __call__(self, *keys):
        nums = []
        for k in keys:
            if k not in self.order:
                self.order.append(k)
            nums.append(self.order.index(k) + 1)
        nums.sort()
        # rentang berurutan diringkas: [3, 4, 5] -> [3–5]
        out, i = [], 0
        while i < len(nums):
            j = i
            while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
                j += 1
            out.append(f"{nums[i]}–{nums[j]}" if j - i >= 2 else ", ".join(map(str, nums[i:j + 1])))
            i = j + 1
        return "[" + ", ".join(out) + "]"


# ---------------------------------------------------------------------- utilitas
def num(x, d=2):
    """Format angka gaya Indonesia: 12.345,67"""
    s = f"{x:,.{d}f}"
    return s.replace(",", "#").replace(".", ",").replace("#", ".")


def rp(x):
    return "Rp" + num(x, 0)


def pct(x, d=1):
    return num(x, d) + "%"


def join_id(items):
    """['a', 'b', 'c'] -> 'a, b, dan c'"""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + (", dan " if len(items) > 2 else " dan ") + items[-1]


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def floats(r):
    out = {}
    for k, v in r.items():
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            out[k] = v
    return out


def esc(s):
    return html.escape(str(s))


class Doc:
    """Penomoran gambar/tabel otomatis per bab."""

    def __init__(self):
        self.chapter = 0
        self.fig = 0
        self.tab = 0
        self.toc = []  # (level, id, text)

    def bab(self, title):
        self.chapter += 1
        self.fig = self.tab = 0
        hid = f"bab{self.chapter}"
        text = f"BAB {self.chapter} {title}"
        self.toc.append((1, hid, text))
        return f'<h1 id="{hid}" class="bab"><span>BAB {self.chapter}</span>{esc(title)}</h1>'

    def h2(self, numtxt, title):
        hid = "s" + numtxt.replace(".", "_")
        self.toc.append((2, hid, f"{numtxt} {title}"))
        return f'<h2 id="{hid}">{numtxt} {esc(title)}</h2>'

    def h3(self, numtxt, title):
        return f'<h3>{numtxt} {esc(title)}</h3>'

    def unnumbered(self, hid, title):
        self.toc.append((1, hid, title))
        return f'<h1 id="{hid}" class="bab plain">{esc(title)}</h1>'

    def figure(self, src, caption, width="100%"):
        self.fig += 1
        label = f"Gambar {self.chapter}.{self.fig}"
        return (f'<figure><img src="{src}" style="width:{width}">'
                f'<figcaption><b>{label}.</b> {caption}</figcaption></figure>'), label

    def table(self, header, rows, caption, cls=""):
        self.tab += 1
        label = f"Tabel {self.chapter}.{self.tab}"
        th = "".join(f"<th>{h}</th>" for h in header)
        trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        return (f'<div class="tbl"><div class="tcap"><b>{label}.</b> {caption}</div>'
                f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'), label



# ---------------------------------------------------------------------- data
def load_all(config):
    data = {}
    for name in config["instances"]:
        inst = load_instance(ROOT, name, config)
        owned = assign_nearest(inst)
        best = json.loads((ROOT / "results" / name / "rute_terbaik.json").read_text(encoding="utf-8"))
        data[name] = {"inst": inst, "owned": owned, "best": best}
    res = ROOT / "results"
    data["_real"] = [floats(r) for r in read_csv(res / "search_real.csv")]
    data["_scal"] = [floats(r) for r in read_csv(res / "search_summary.csv")]
    data["_scal_runs"] = [floats(r) for r in read_csv(res / "search_scaling.csv")]
    return data


def heuristic_ratios(config, data):
    """Rata-rata h(awal)/optimum untuk h1 dan h2 pada sub-masalah nyata."""
    w = config["search"]["weight"]
    r1, r2 = [], []
    for name in config["instances"]:
        inst = data[name]["inst"]
        opt = {r["depot"]: r["optimum"] for r in data["_real"]
               if r["instance"] == name and r["algorithm"] == "UCS"}
        for d, schools in enumerate(data[name]["owned"]):
            if schools:
                p = RoutingProblem(inst, d, schools, w, inst.vehicles_per_depot[d])
                r1.append(p.h_nearest(p.initial) / opt[inst.nodes[d]["id"]])
                r2.append(p.h(p.initial) / opt[inst.nodes[d]["id"]])
    return {"h1": float(np.mean(r1)), "h2": float(np.mean(r2))}


def aggregate_real(real, algo):
    rs = [r for r in real if r["algorithm"] == algo]
    return dict(n=len(rs), opt=sum(r["optimal"] == "True" for r in rs),
                unfinished=sum(r["status"] != "ok" for r in rs),
                gap=float(np.nanmean([r["gap_pct"] for r in rs])),
                gap_max=float(np.nanmax([r["gap_pct"] for r in rs])),
                exp=sum(r["expanded"] for r in rs), mem=max(r["max_stored"] for r in rs),
                rt=sum(r["runtime_s"] for r in rs), trips=float(np.mean([r["n_trips"] for r in rs])))


def build_context(config, data):
    """Semua angka yang dipakai teks laporan, dihitung sekali dari results/."""
    names = list(config["instances"])
    real, scal, scal_runs = data["_real"], data["_scal"], data["_scal_runs"]
    ks = sorted({int(r["k"]) for r in scal})

    def sc(k, a, key):
        return next(r[key] for r in scal if int(r["k"]) == k and r["algorithm"] == a)

    k9 = 9 if 9 in ks else max(ks)
    ra = {a: aggregate_real(real, a) for a in SEARCH}
    return dict(
        config=config, data=data, prob=config["problem"], scfg=config["search"], names=names,
        small=names[0], big=names[-1], big_inst=data[names[-1]]["inst"],
        w0=config["search"]["weight"], cpk=config["problem"]["fuel_price_per_liter"] / config["problem"]["km_per_liter"],
        real=real, scal=scal, scal_runs=scal_runs, ks=ks, kmax=max(ks), k9=k9, sc=sc, RA=ra,
        solved_all={a: max([k for k in ks if sc(k, a, "solved_rate") == 1] or [0]) for a in SEARCH},
        ratio_real=ra["UCS"]["exp"] / ra["A*"]["exp"], ratio_h1_real=ra["UCS"]["exp"] / ra["A* (h1)"]["exp"],
        ratio_k9=sc(k9, "UCS", "expanded_median") / sc(k9, "A*", "expanded_median"),
        ratio_kmax=sc(max(ks), "UCS", "expanded_median") / sc(max(ks), "A*", "expanded_median"),
        blind_gap_small=[r["gap_pct"] for r in scal_runs if r["algorithm"] == "BFS" and r["k"] <= 9],
        gbfs_gap_small=[r["gap_pct"] for r in scal_runs if r["algorithm"] == "GBFS" and r["k"] <= 9],
        real_k=sorted({int(r["k"]) for r in real}), h_ratio=heuristic_ratios(config, data),
        bfs_eq_ids=all(abs(a["cost"] - b["cost"]) < 1e-9 for a in real if a["algorithm"] == "BFS"
                       for b in real if b["algorithm"] == "IDS" and b["status"] == "ok"
                       and b["instance"] == a["instance"] and b["depot"] == a["depot"]),
    )


# ---------------------------------------------------------------------- isi laporan
def sec_cover(c):
    team_rows = "".join(f"<tr><td>{esc(n)}</td><td>{esc(nrp)}</td></tr>" for n, nrp in TEAM)
    return f"""
<section class="cover">
  <div class="cover-kicker">Midterm Project · {esc(COURSE)}</div>
  <h1 class="cover-title">Optimasi Rute Distribusi Makan Bergizi Gratis dari SPPG ke Sekolah di Surabaya</h1>
  <div class="cover-sub">Perbandingan Algoritma Pencarian (BFS, Iterative Deepening, DFS Branch and Bound,
  Uniform-Cost Search, A*, Greedy Best-First) untuk Menyusun Rute Granmax</div>
  <div class="cover-box">
    <div class="cover-label">Disusun oleh</div>
    <table class="cover-team">{team_rows}</table>
    <div class="cover-label">Dosen pengampu</div>
    <div>{esc(LECTURER)}</div>
  </div>
  <div class="cover-foot">{INSTITUTION}<br>{DATE}</div>
</section>"""


def sec_abstract(c, D):
    RA, IB = c["RA"], c["big_inst"]
    return D.unnumbered("abstrak", "RINGKASAN") + f"""<p>Program Makan Bergizi Gratis (MBG) mengirim makanan matang setiap hari dari dapur
<b>Satuan Pelayanan Pemenuhan Gizi (SPPG)</b> ke sekolah. Rute pengiriman menentukan biaya bensin yang
ditanggung SPPG sekaligus lamanya makanan menunggu sebelum dimakan. Laporan ini memodelkan distribusi MBG
di Surabaya sebagai <b>Multi-Depot Vehicle Routing Problem (MDVRP) bi-objektif</b> (biaya bensin Granmax dan
rata-rata waktu tiba makanan) dengan batas 3 sekolah per Granmax, armada terbatas per SPPG, bongkar 15 menit
per sekolah, dan batas 180 menit sejak makanan selesai dimasak. Data memakai lokasi SPPG dari berita,
sekolah dari OpenStreetMap, serta jarak dan waktu tempuh jalan asli dari OSRM.</p>
<p>Setiap sekolah dilayani SPPG terdekat, sehingga rute tiap SPPG dapat dicari sendiri-sendiri sebagai
masalah pencarian di ruang keadaan. Tujuh algoritma dibandingkan: BFS, Iterative Deepening (IDS), DFS dengan
Branch and Bound, Uniform-Cost Search (UCS), A* dengan dua heuristik admissible (h1 dan h2 yang dirancang
sendiri), dan Greedy Best-First Search (GBFS). Perbandingan dilakukan pada {RA['UCS']['n']} sub-masalah nyata dari
dua instance dan pada sub-masalah acak berukuran 3–{c['kmax']} sekolah.</p>
<p>UCS, A*, dan DFS-B&amp;B menemukan rute optimal bila pencarian selesai. BFS dan IDS hanya menemukan rute
dengan Granmax paling sedikit (rata-rata {pct(RA['BFS']['gap'])} lebih mahal dari optimum pada sub-masalah
nyata), sedangkan GBFS paling cepat tetapi rata-rata {pct(RA['GBFS']['gap'])} lebih mahal. Heuristik berbasis
penugasan slot (h2) membuat A* mengekspansi {num(c['ratio_real'], 0)} kali lebih sedikit node daripada UCS
pada sub-masalah nyata. Pada instance {IB.m} SPPG dan {IB.n} sekolah, rute terbaik menurunkan biaya bensin
{pct(100 * (1 - c['data'][c['big']]['best']['cost_rp'] / IB.ref_cost))} dibanding mengirim langsung satu Granmax
per sekolah.</p>
<p class="kw"><b>Kata kunci:</b> MDVRP, algoritma pencarian, A*, heuristik admissible, Uniform-Cost Search,
Makan Bergizi Gratis, Surabaya.</p>"""


def sec_background(c, D, C):
    IB = c["big_inst"]
    return D.h2("1.1", "Latar Belakang") + f"""<p>Program Makan Bergizi Gratis (MBG) dijalankan pemerintah sejak 6 Januari 2025 di bawah Badan
Gizi Nasional (BGN) yang dibentuk melalui Peraturan Presiden Nomor 83 Tahun 2024 {C('perpres')}. Makanan
dimasak di dapur SPPG lalu diantar ke sekolah penerima setiap hari sekolah. Di Surabaya saja tercatat
133 SPPG per Mei 2026 {C('jawapos')}, dan satu SPPG dapat melayani ribuan porsi untuk belasan sekolah; SPPG
Polrestabes Surabaya, misalnya, menyalurkan 3.119 porsi ke 16 sekolah di Kecamatan Krembangan {C('antara1')}.</p>
<p>Distribusi ini punya dua kepentingan yang saling tarik-menarik. Dari sisi <b>biaya</b>, setiap
kilometer Granmax berarti bensin, dan rute yang tidak efisien berulang setiap hari. Dari sisi
<b>keamanan pangan</b>, makanan matang sebaiknya tidak dibiarkan terlalu lama pada suhu ruang;
WHO menganjurkan makanan matang tidak dibiarkan pada suhu ruang lebih dari 2 jam {C('who')}. Kasus keracunan
ratusan siswa yang dikaitkan dengan salah satu SPPG di Surabaya pada Mei 2026 {C('times')} menunjukkan bahwa
waktu antara memasak dan konsumsi bukan sekadar detail teknis. Menggabungkan banyak sekolah dalam satu
perjalanan menghemat bensin, tetapi membuat sekolah terakhir menerima makanan lebih lambat. Sebaliknya,
mengirim langsung ke setiap sekolah mempercepat waktu tiba tetapi boros bensin.</p>
<p>Masalah ini adalah varian <i>Vehicle Routing Problem</i> (VRP) {C('dantzig', 'toth')} dengan banyak
depot (<i>multi-depot</i>) {C('cordeau')}. Karena setiap sekolah dilayani SPPG terdekatnya, satu SPPG hanya
mengurus beberapa sekolah (pada {c['big']} paling banyak {max(len(s) for s in c['data'][c['big']]['owned'])}
sekolah). Ruang rutenya cukup kecil untuk dicari secara sistematis dengan <b>algoritma pencarian</b> di ruang
keadaan dari Kuliah 2 dan 3 {C('aima')}, mulai dari pencarian buta (BFS, IDS, DFS) hingga pencarian
berinformasi (UCS, A*, Greedy Best-First). Laporan ini membandingkan ketujuh algoritma itu pada data jalan asli
Surabaya.</p>"""


def sec_problem(c, D):
    prob, cfg = c["prob"], c["config"]
    return D.h2("1.2", "Rumusan Masalah") + f"""<p>Diberikan sejumlah SPPG di Surabaya, masing-masing dengan {cfg['instances'][c['big']]['vehicles_per_sppg']}
Granmax, dan sekumpulan sekolah penerima MBG yang masing-masing dilayani SPPG terdekat, tentukan Granmax mana
yang mengantar ke sekolah mana dan dengan urutan bagaimana, sehingga:</p>
<ol>
<li><b>biaya bensin total</b> paling rendah (jarak tempuh / {num(prob['km_per_liter'], 0)} km per liter
× Rp{num(prob['fuel_price_per_liter'], 0)} per liter Pertalite), dan</li>
<li><b>rata-rata waktu tiba</b> makanan di sekolah paling rendah,</li>
</ol>
<p>dengan syarat setiap Granmax melayani paling banyak {prob['max_schools_per_vehicle']} sekolah, bongkar
muat {prob['service_time_min']} menit per sekolah, dan makanan tiba paling lambat
{prob['max_delivery_time_min']} menit setelah selesai dimasak. Pertanyaan penelitiannya:</p>
<ol>
<li>Bagaimana perbandingan BFS, IDS, DFS dengan Branch and Bound, UCS, A*, dan Greedy Best-First Search
dalam optimalitas, jumlah node yang diekspansi, memori, dan waktu pada sub-masalah nyata?</li>
<li>Bagaimana pertumbuhan biaya pencarian tiap algoritma saat jumlah sekolah per SPPG naik?</li>
<li>Seberapa besar pengaruh kualitas heuristik terhadap A*?</li>
</ol>"""


def sec_goals(c, D):
    return D.h2("1.3", "Tujuan") + """<ol>
<li>Membangun model MDVRP bi-objektif distribusi MBG dengan data jalan asli Surabaya.</li>
<li>Merumuskan rute di dalam satu SPPG sebagai masalah pencarian dan membandingkan enam algoritma pencarian
(A* dengan dua versi heuristik) secara terukur.</li>
<li>Merancang heuristik admissible yang kuat untuk masalah ini dan mengukur dampaknya pada A*.</li>
<li>Menghasilkan rute yang dapat dibaca langsung oleh pengelola SPPG beserta visualisasi peta.</li>
</ol>""" + D.h2("1.4", "Manfaat") + f"""<ul>
<li><b>Bagi pengelola SPPG:</b> rute konkret dengan biaya bensin lebih rendah daripada pengiriman langsung
satu Granmax per sekolah, beserta jam tiba tiap sekolah.</li>
<li><b>Bagi pembuat kebijakan:</b> gambaran kuantitatif trade-off antara biaya bensin dan lamanya makanan di jalan.</li>
<li><b>Secara akademik:</b> contoh penerapan keluarga algoritma pencarian dari materi kuliah pada satu masalah
nyata, termasuk perancangan heuristik admissible dan pengukuran skalabilitas.</li>
</ul>"""


def sec_assumptions(c, D):
    prob = c["prob"]
    return D.h2("1.5", "Batasan dan Asumsi") + f"""<ul>
<li>Lalu lintas lancar dan semua lampu hijau: waktu tempuh memakai durasi OSRM kondisi lancar.</li>
<li>Semua makanan selesai dimasak dan diberangkatkan bersamaan (t = 0); setiap Granmax melakukan satu
perjalanan dan kembali ke SPPG.</li>
<li>Kendaraan Granmax berbahan bakar Pertalite Rp{num(prob['fuel_price_per_liter'], 0)}/liter dengan
konsumsi {num(prob['km_per_liter'], 0)} km/liter (batas atas rentang 10–14 km/liter), atau
{rp(c['cpk'])} per km.</li>
<li>"Maksimal 3 sekolah" diartikan per kendaraan; jumlah porsi per sekolah dianggap muat dalam satu
Granmax. Bila sekolah terdekat suatu SPPG melebihi 3 Granmax × 3 sekolah, armada SPPG itu ditambah.</li>
<li>Setiap sekolah dilayani SPPG terdekat (jarak jalan); pembagian sekolah antar-SPPG tidak dioptimasi.</li>
<li>Koordinat SPPG adalah perkiraan hasil geocoding alamat yang diberitakan, bukan titik resmi BGN.</li>
</ul>"""


def sec_chapter1(c, D, C):
    return D.bab("PENDAHULUAN") + sec_background(c, D, C) + sec_problem(c, D) + sec_goals(c, D) + sec_assumptions(c, D)


def sec_data(c, D, C):
    cfg, data = c["config"], c["data"]
    rows = []
    for name in c["names"]:
        I, spec = data[name]["inst"], cfg["instances"][name]
        rows.append([f"<code>{name}</code>", ", ".join(s.replace("SPPG-", "") for s in spec["sppg_ids"]),
                     str(I.n), str(sum(I.vehicles_per_depot)), num(spec["radius_km"], 0) + " km"])
    t, tl = D.table(["Instance", "SPPG", "Sekolah", "Granmax", "Radius"], rows, "Dua instance yang diuji.")
    fig, fl = D.figure("figs/fig_wilayah.png", "Lokasi SPPG (bintang) dan sekolah (lingkaran) pada kedua "
                       "instance di Surabaya.")
    return D.h2("2.2", "Data dan Pembentukan Instance") + f"""<p>Lokasi SPPG diambil dari pemberitaan resmi dan media (Polrestabes/Krembangan, Simokerto,
Tembok Dukuh, Kedung Baruk/Rungkut, Jemur Wonosari, Mulyorejo) {C('jawapos', 'times', 'antara1', 'antara2', 'prisma')},
lalu di-geocode dengan Nominatim/OpenStreetMap. Sebanyak 751 sekolah jenjang SD/MI/SMP/MTs di Kota Surabaya
diunduh dari OpenStreetMap {C('osm')} melalui Overpass API. Untuk setiap instance, SPPG secara bergiliran
mengambil sekolah acak (seed tetap) dalam radius {num(cfg['instances'][c['big']]['radius_km'], 0)} km.
Jarak (km) dan waktu tempuh (menit) antar semua titik dihitung dengan OSRM {C('osrm')} di atas
jaringan jalan OpenStreetMap, bukan jarak garis lurus. {tl} merangkum instance yang dipakai dan {fl}
menunjukkan lokasinya.</p>{t}{fig}"""


def sec_formulation(c, D):
    prob = c["prob"]
    return D.h2("2.3", "Formulasi Masalah") + f"""<p>Misalkan <i>D</i> = {{1, …, m}} himpunan SPPG (depot), <i>S</i> = {{1, …, n}} himpunan sekolah,
dan setiap SPPG <i>d</i> memiliki <i>K<sub>d</sub></i> Granmax. Solusi adalah sekumpulan rute
<i>r</i> = (<i>d</i>, <i>s</i><sub>1</sub>, …, <i>s<sub>k</sub></i>) yang berangkat dari SPPG <i>d</i>,
mengunjungi <i>k</i> sekolah, lalu kembali ke <i>d</i>. Dengan <i>dist</i>(·,·) jarak jalan (km) dan
<i>t</i>(·,·) waktu tempuh (menit), waktu tiba di sekolah ke-<i>j</i> pada rute adalah</p>
<div class="eq"><i>a</i>(<i>s<sub>j</sub></i>) = Σ<sub><i>i</i>=1..<i>j</i></sub> <i>t</i>(<i>s</i><sub><i>i</i>−1</sub>, <i>s<sub>i</sub></i>) + {prob['service_time_min']} · (<i>j</i> − 1),
&nbsp;&nbsp; <i>s</i><sub>0</sub> = <i>d</i></div>
<p>karena setiap sekolah sebelumnya membutuhkan {prob['service_time_min']} menit untuk bongkar makanan.
Dua objektif yang diminimalkan:</p>
<div class="eq"><i>f</i><sub>1</sub> = (Rp{num(prob['fuel_price_per_liter'], 0)} / {num(prob['km_per_liter'], 0)} km·L<sup>−1</sup>) ·
Σ<sub><i>r</i></sub> [ Σ<sub><i>i</i></sub> <i>dist</i>(<i>s</i><sub><i>i</i>−1</sub>, <i>s<sub>i</sub></i>) + <i>dist</i>(<i>s<sub>k</sub></i>, <i>d</i>) ]
&nbsp;&nbsp;&nbsp; (biaya bensin, Rp)</div>
<div class="eq"><i>f</i><sub>2</sub> = (1/<i>n</i>) · Σ<sub><i>s</i>∈<i>S</i></sub> <i>a</i>(<i>s</i>)
&nbsp;&nbsp;&nbsp; (rata-rata waktu tiba, menit)</div>
<p>dengan constraint: (C1) setiap sekolah dilayani tepat satu kali; (C2) setiap rute memuat paling banyak
<i>Q</i> = {prob['max_schools_per_vehicle']} sekolah; (C3) jumlah rute dari SPPG <i>d</i> paling banyak
<i>K<sub>d</sub></i>; (C4) <i>a</i>(<i>s</i>) ≤ {prob['max_delivery_time_min']} menit untuk semua sekolah.
Waktu tiba rata-rata dipilih sebagai objektif kedua (bukan total waktu tempuh) karena dengan asumsi
kecepatan konstan, total waktu tempuh hanya kelipatan jarak sehingga kedua objektif akan identik;
rata-rata waktu tiba justru bertentangan dengan jarak dan memunculkan trade-off yang nyata.</p>
<p>Kedua objektif digabung dengan <i>weighted sum</i> ternormalisasi menjadi satu fungsi biaya:</p>
<div class="eq"><i>F<sub>w</sub></i> = <i>w</i> · <i>f</i><sub>1</sub>/<i>f</i><sub>1</sub><sup>ref</sup> +
(1 − <i>w</i>) · <i>f</i><sub>2</sub>/<i>f</i><sub>2</sub><sup>ref</sup></div>
<p>dengan <i>f</i><sub>1</sub><sup>ref</sup> biaya solusi "bintang" (setiap sekolah diantar pulang-pergi
dari SPPG terdekat) dan <i>f</i><sub>2</sub><sup>ref</sup> rata-rata waktu tempuh langsung dari SPPG
terdekat (batas bawah <i>f</i><sub>2</sub>), sehingga kedua suku berskala sekitar 1. Bobot yang dipakai
<i>w</i> = {num(c['w0'], 1)} (biaya dan waktu sama penting). Yang penting untuk algoritma pencarian:
<i>F<sub>w</sub></i> adalah <b>jumlah kontribusi tiap ruas perjalanan</b>, yaitu jarak ruas
(untuk <i>f</i><sub>1</sub>) dan waktu tiba di sekolah ujung ruas (untuk <i>f</i><sub>2</sub>), sehingga
dapat dipakai langsung sebagai biaya jalur.</p>"""


def sec_assignment(c, D, C):
    data = c["data"]
    rows = [[f"<code>{n}</code>"] + [str(len(s)) for s in data[n]["owned"]]
            + [""] * (max(data[m]["inst"].m for m in c["names"]) - data[n]["inst"].m) for n in c["names"]]
    head = ["Instance"] + [f"SPPG {i + 1}" for i in range(max(data[n]["inst"].m for n in c["names"]))]
    t, tl = D.table(head, rows, "Jumlah sekolah yang dilayani tiap SPPG setelah penugasan ke SPPG terdekat.", cls="num")
    return D.h2("2.4", "Penugasan Sekolah ke SPPG Terdekat") + f"""<p>Setiap sekolah dilayani SPPG dengan jarak jalan terdekat (OSRM). Pola "bagi dulu, rutekan
kemudian" (<i>cluster-first, route-second</i>) dikenal dalam literatur VRP {C('gillett', 'fisher')}, dan di sini
tahap pembagiannya dibuat sesederhana mungkin agar fokus perbandingan ada pada algoritma pencarian rute.
Setelah penugasan tetap, Granmax dari SPPG berbeda tidak berbagi apa pun (armada terpisah, semua berangkat pada
t = 0), jadi rute tiap SPPG dapat dicari sendiri-sendiri. {tl} menunjukkan ukuran tiap sub-masalah. Bila suatu
SPPG menerima lebih dari {c['prob']['max_schools_per_vehicle']} Granmax × {c['prob']['max_schools_per_vehicle']}
sekolah, armadanya dinaikkan ke ⌈jumlah sekolah / {c['prob']['max_schools_per_vehicle']}⌉.</p>{t}"""


def sec_search_space(c, D, C):
    prob = c["prob"]
    st_rows = [
        ["Keadaan", "(sisa, posisi, muatan, <i>t</i>, dipakai, pembuka): sekolah yang belum dilayani, lokasi Granmax "
                    "yang sedang jalan, jumlah sekolah yang sudah dilayaninya, waktu siap berangkat dari posisi, jumlah "
                    "Granmax yang sudah berangkat, dan sekolah pertama Granmax terakhir"],
        ["Keadaan awal", "semua sekolah tersisa, posisi = SPPG, belum ada Granmax berangkat"],
        ["Aksi", "<b>antar(s)</b>: ke sekolah <i>s</i> yang tersisa (dari SPPG berarti memberangkatkan Granmax baru); "
                 "<b>pulang</b>: Granmax kembali ke SPPG"],
        ["Tes goal", "tidak ada sekolah tersisa dan posisi = SPPG"],
        ["Biaya langkah", "<i>w</i> · Rp(jarak ruas)/<i>f</i><sub>1</sub><sup>ref</sup> + (1 − <i>w</i>) · "
                          "waktu_tiba/(<i>n</i> · <i>f</i><sub>2</sub><sup>ref</sup>); biaya jalur = kontribusi SPPG ke <i>F</i>"],
        ["Pemangkasan", f"anak yang tiba &gt; {prob['max_delivery_time_min']} menit; anak yang sisanya tidak mungkin "
                        "terangkut Granmax tersisa; Granmax baru harus dibuka sekolah bernomor lebih besar dari pembuka "
                        "Granmax sebelumnya (memecah simetri urutan Granmax)"],
    ]
    t, tl = D.table(["Komponen", "Definisi"], st_rows, "Formulasi rute satu SPPG sebagai masalah pencarian.", cls="small")
    return D.h2("2.5", "Rute di Dalam Satu SPPG sebagai Masalah Pencarian") + D.h3("2.5.1", "Formulasi ruang keadaan") + f"""<p>Rute satu SPPG dibangun langkah demi langkah seperti masalah pencarian rute pada umumnya
{C('aima')}. {tl} merangkum formulasinya. Satu komponen keadaan, waktu <i>t</i>, diperlukan karena biaya
langkah berikutnya (waktu tiba) bergantung pada kapan Granmax berangkat dari posisi sekarang. Pemecah
simetri pada komponen "pembuka" tidak membuang solusi: setiap himpunan rute tetap dapat ditulis dengan
Granmax diurutkan menurut sekolah pertamanya. Dengan aturan ini, satu SPPG dengan 9 sekolah dan 3 Granmax
memiliki 9!/3! = 60.480 rute lengkap yang berbeda. Aksi pulang
dari sekolah langsung menuju keadaan dengan posisi SPPG, sehingga graf keadaannya tidak memiliki siklus.
Untuk deteksi keadaan berulang, <i>t</i> hanya ikut dibandingkan selama Granmax masih bisa menambah
sekolah; setelah itu <i>t</i> tidak lagi memengaruhi biaya ke depan.</p>{t}"""


def sec_algorithms(c, D, C):
    prob = c["prob"]
    a_rows = [
        ["BFS", "FIFO", "tes goal saat dibangkitkan", "tidak*", "O(<i>b<sup>d</sup></i>)"],
        ["IDS", "LIFO, batas kedalaman naik", "DFS diulang", "tidak*", "O(<i>bd</i>)"],
        ["DFS-B&amp;B", "LIFO, anak termurah dulu", "pangkas <i>g</i> ≥ terbaik", "ya", "O(<i>bd</i>)"],
        ["UCS", "prioritas <i>g</i>", "–", "ya", "O(<i>b</i><sup>1+⌊C*/ε⌋</sup>)"],
        ["A*", "prioritas <i>g</i> + <i>h</i>", "h1 atau h2", "ya", "eksponensial, bergantung <i>h</i>"],
        ["GBFS", "prioritas <i>h</i>", "h2", "tidak", "bergantung <i>h</i>"],
    ]
    t, tl = D.table(["Algoritma", "Frontier", "Catatan", "Optimal?", "Memori"], a_rows,
                    "Algoritma pencarian yang dibandingkan. *Hanya optimal jika semua biaya langkah sama.", cls="small")
    blind = f"""<ul>
<li><b>Breadth-First Search (BFS)</b> mengekspansi node per tingkat kedalaman dengan antrian FIFO, dengan tes
goal saat node dibangkitkan dan himpunan <i>reached</i> untuk menghindari keadaan berulang {C('aima')}.
Kedalaman goal = jumlah sekolah + jumlah Granmax, sehingga BFS menemukan rute dengan <b>Granmax paling
sedikit</b>. Rute itu hanya optimal bila semua langkah berbiaya sama, padahal di sini tidak.</li>
<li><b>Iterative Deepening Search (IDS)</b> {C('korf')} menjalankan DFS berbatas kedalaman 0, 1, 2, … sampai
goal ditemukan. Hasilnya sama dengan BFS (goal terdangkal), tetapi memorinya hanya sebanding dengan
kedalaman. Harganya, node di tingkat atas diekspansi berulang kali.</li>
<li><b>DFS dengan Branch and Bound (DFS-B&amp;B)</b> {C('land')} menelusuri dalam-dulu dengan anak termurah
lebih dulu. Setiap kali goal tercapai, biayanya menjadi batas atas; cabang yang biaya jalurnya sudah ≥
batas itu dipangkas. Optimal, dengan memori sekecil DFS.</li>
</ul>"""
    informed = f"""<p>Ketiga algoritma berikut adalah <i>best-first graph search</i> dengan antrian prioritas, yang
berbeda hanya pada fungsi evaluasi <i>f</i>(<i>n</i>): <b>UCS</b> {C('dijkstra')} memakai
<i>f</i> = <i>g</i> (biaya jalur sejauh ini); <b>A*</b> {C('hart')} memakai <i>f</i> = <i>g</i> + <i>h</i>;
<b>Greedy Best-First Search (GBFS)</b> memakai <i>f</i> = <i>h</i> saja {C('pearl')}. Jalur yang lebih
murah ke keadaan yang sudah tercatat menggantikan jalur lama. UCS optimal karena semua biaya langkah
positif; A* optimal bila <i>h</i> admissible (tidak pernah melebihi biaya sisa sebenarnya). Dua heuristik
admissible dirancang:</p>
<ul>
<li><b>h1 (jalan masuk termurah).</b> Setiap sekolah tersisa harus dimasuki dari suatu titik: dari SPPG
(Granmax baru), dari posisi sekarang, atau dari sekolah tersisa lain. Untuk tiap sekolah diambil jarak masuk
termurah dan waktu tiba termurah dari ketiga kemungkinan itu, ditambah minimal satu ruas pulang ke SPPG. Ini
perluasan dari heuristik "jarak ke sekolah belum dikunjungi terdekat".</li>
<li><b>h2 (relaksasi penugasan slot).</b> Kelemahan h1: hampir semua sekolah dianggap bisa dicapai langsung
dari SPPG, padahal setiap Granmax hanya punya <i>satu</i> sekolah urutan ke-1, satu urutan ke-2, dan satu
urutan ke-3. h2 menganggap setiap sekolah tersisa harus menempati satu <i>slot</i> (Granmax, urutan ke-<i>p</i>).
Untuk tiap jenis slot dihitung batas bawah biaya sekolah di slot itu: urutan ke-1 = langsung dari SPPG,
urutan ke-<i>p</i> ≥ 2 = melewati <i>p</i> − 1 sekolah tersisa lain ditambah {prob['service_time_min']}
menit bongkar per sekolah. Penugasan sekolah ke slot dengan total biaya minimum dihitung dengan algoritma
Hungaria {C('kuhn')}. Karena rute nyata mana pun juga menempatkan setiap sekolah di satu slot dengan biaya
setidaknya batas bawah slot tersebut, h2 tidak pernah melebihi biaya sebenarnya (admissible).</li>
</ul>
<p>GBFS memakai h2 yang sama dengan A* agar perbedaannya hanya pada ada atau tidaknya <i>g</i>.
Karakteristik keenam algoritma dirangkum pada {tl}.</p>"""
    return D.h3("2.5.2", "Algoritma pencarian buta") + blind + D.h3("2.5.3", "Pencarian berinformasi dan heuristik") + informed + t


def sec_design(c, D):
    scfg, RA = c["scfg"], c["RA"]
    ks = c["ks"]
    n_scal = len([r for r in c["scal_runs"] if r["algorithm"] == "UCS"])
    return D.h2("2.6", "Desain Eksperimen dan Metrik") + f"""<ul>
<li><b>Sub-masalah nyata:</b> himpunan sekolah setiap SPPG setelah penugasan terdekat
({RA['UCS']['n']} sub-masalah dari kedua instance, {min(c['real_k'])}–{max(c['real_k'])} sekolah per SPPG).</li>
<li><b>Skalabilitas:</b> untuk <i>k</i> = {ks[0]}–{ks[-1]} sekolah, setiap SPPG di {scfg['scaling_instance']}
mengambil {scfg['scaling_samples']} sampel acak dari {scfg['scaling_pool']} sekolah terdekatnya
({n_scal} sub-masalah). Armada 3 Granmax; untuk <i>k</i> &gt; 9 armada dinaikkan ke ⌈<i>k</i>/3⌉ agar tetap
layak. Setiap pencarian dihentikan bila sudah membangkitkan {num(scfg['max_nodes'] / 1e6, 0)} juta node.</li>
<li><b>Metrik:</b> optimal atau tidak, selisih biaya terhadap optimum, node diekspansi, node tersimpan maksimum
(proksi memori), dan waktu. Optimum acuan adalah biaya UCS (terbukti optimal); program memeriksa bahwa A*, A* (h1),
dan DFS-B&amp;B yang selesai menghasilkan biaya yang sama persis.</li>
</ul>"""


def sec_chapter2(c, D, C):
    flow = """<div class="flow">
<div><b>1. Data</b><br>SPPG (berita) + sekolah (OpenStreetMap) + jarak &amp; waktu jalan (OSRM)</div>
<div><b>2. Model</b><br>MDVRP bi-objektif, digabung menjadi satu biaya F</div>
<div><b>3. Penugasan</b><br>tiap sekolah ke SPPG terdekat</div>
<div><b>4. Pencarian rute</b><br>BFS, IDS, DFS-B&amp;B, UCS, A*, Greedy Best-First</div>
<div><b>5. Analisis</b><br>optimalitas, node, memori, skalabilitas, peta</div>
</div>"""
    return (D.bab("METODE") + D.h2("2.1", "Alur Penelitian") + flow + sec_data(c, D, C) + sec_formulation(c, D)
            + sec_assignment(c, D, C) + sec_search_space(c, D, C) + sec_algorithms(c, D, C) + sec_design(c, D))


def limit_sentence(c):
    """Kalimat batas node: algoritma mana yang berhenti sebelum k terbesar."""
    scfg, RA = c["scfg"], c["RA"]
    hit = [a for a in SEARCH if c["solved_all"][a] < c["kmax"]]
    if not hit:
        return "Semua algoritma masih selesai sebelum batas node."
    by_k = {}
    for a in hit:
        by_k.setdefault(c["solved_all"][a], []).append(a)
    parts = "; ".join(" dan ".join(v) + " hanya mampu menyelesaikan semua sub-masalah sampai <i>k</i> = " + str(k)
                      for k, v in sorted(by_k.items()))
    rest = join_id(["A* (h2)" if a == "A*" else a for a in SEARCH if a not in hit])
    return (f"Sebelum batas {num(scfg['max_nodes'] / 1e6, 0)} juta node dibangkitkan, {parts}, sedangkan {rest} "
            f"masih selesai sampai <i>k</i> = {c['kmax']}.")


def sec_real_results(c, D):
    RA, h = c["RA"], c["h_ratio"]
    rows = []
    for a in SEARCH:
        r = RA[a]
        rows.append(["<b>A* (h2)</b>" if a == "A*" else a, f"{r['opt']}/{r['n']}",
                     "0" if r["gap"] < 1e-6 else pct(r["gap"]), "0" if r["gap_max"] < 1e-6 else pct(r["gap_max"]),
                     num(r["trips"], 1), num(r["exp"], 0), num(r["mem"], 0), num(r["rt"], 2) + " s"])
    t, tl = D.table(["Algoritma", "Optimal", "Selisih rata-rata", "Selisih maks.", "Granmax", "Node diekspansi (total)",
                     "Memori maks. (node)", "Waktu total"], rows,
                    f"Hasil pada {RA['UCS']['n']} sub-masalah nyata. Selisih = kelebihan biaya terhadap optimum (UCS).",
                    cls="num")
    fgap, fgapl = D.figure("../results/fig_search_gap.png",
                           "Rata-rata selisih biaya terhadap optimum untuk semua sub-masalah dengan <i>k</i> ≤ 9.",
                           width="78%")
    dfs_cut = [r["gap_pct"] for r in c["real"] if r["algorithm"] == "DFS-B&B" and r["status"] != "ok"]
    dfs_note = (f" DFS-B&amp;B kehabisan batas node pada {len(dfs_cut)} sub-masalah terbesar dan hanya melaporkan "
                f"rute terbaik sementara (selisih sampai {pct(float(np.nanmax(dfs_cut)), 2)})." if dfs_cut else "")
    ids_note = (f" IDS tidak menemukan solusi sama sekali pada {RA['IDS']['unfinished']} sub-masalah terbesar."
                if RA["IDS"]["unfinished"] else "")
    same_ids = ("selalu menghasilkan rute yang sama" if c["bfs_eq_ids"]
                else "menghasilkan rute dengan jumlah Granmax yang sama") + " (goal terdangkal)"
    scaling_trend = (
        f"Keunggulan ini stabil saat masalah membesar: median node UCS sekitar "
        f"{num((c['ratio_k9'] + c['ratio_kmax']) / 2, 0)} kali median A* (h2), baik pada k = {c['k9']} maupun "
        f"k = {c['kmax']}." if abs(c["ratio_k9"] - c["ratio_kmax"]) / max(c["ratio_k9"], c["ratio_kmax"]) < 0.2 else
        f"Pada k = {c['k9']} rasio median UCS terhadap A* (h2) adalah {num(c['ratio_k9'], 0)} kali, dan pada "
        f"k = {c['kmax']} menjadi {num(c['ratio_kmax'], 0)} kali.")
    return D.h2("3.2", "Hasil pada Sub-masalah Nyata") + f"""<p>{tl} merangkum hasil pada sub-masalah nyata. Empat temuan utama:</p>
<ol>
<li><b>Optimalitas sesuai teori.</b> UCS dan kedua versi A* menemukan rute optimal di semua sub-masalah,
dan nilainya sama persis satu sama lain.{dfs_note}{ids_note} BFS dan IDS {same_ids} dengan
rata-rata {num(RA['BFS']['trips'], 1)} Granmax, lebih sedikit daripada rute optimal yang rata-rata memakai
{num(RA['UCS']['trips'], 1)} Granmax. Lebih sedikit Granmax memang menghemat ruas pulang, tetapi sekolah kedua dan
ketiga di setiap Granmax menunggu lebih lama, sehingga biaya total rata-rata {pct(RA['BFS']['gap'])} lebih tinggi
(paling buruk {pct(RA['BFS']['gap_max'])}). Ini contoh nyata pernyataan bahwa BFS hanya optimal bila semua
langkah berbiaya sama.</li>
<li><b>Heuristik yang baik memangkas pencarian secara drastis.</b> A* dengan h2 mengekspansi
{num(c['ratio_real'], 0)} kali lebih sedikit node daripada UCS, sedangkan A* dengan h1 nyaris tidak lebih
hemat daripada UCS ({num(c['ratio_h1_real'], 1)} kali). Penyebabnya terlihat dari nilai heuristik di keadaan awal:
rata-rata h1 hanya {pct(h['h1'] * 100, 0)} dari biaya optimal karena menganggap hampir semua sekolah bisa dicapai
langsung dari SPPG, sedangkan h2 mencapai {pct(h['h2'] * 100, 0)} karena memperhitungkan bahwa setiap Granmax
hanya punya satu urutan pertama. {scaling_trend}</li>
<li><b>Pencarian buta boros node.</b> BFS dan UCS harus menyimpan hampir seluruh keadaan yang dapat dicapai
(memori maksimum {num(RA['UCS']['mem'], 0)} node untuk UCS). IDS dan DFS-B&amp;B hanya menyimpan {num(max(RA['IDS']['mem'], RA['DFS-B&B']['mem']), 0)} node,
tetapi IDS mengulang tingkat-tingkat atas di setiap iterasi dan DFS-B&amp;B hanya memangkas dengan <i>g</i>, tanpa
batas bawah sisa biaya: IDS mengekspansi {num(RA['IDS']['exp'], 0)} node dan DFS-B&amp;B
{num(RA['DFS-B&B']['exp'], 0)} node, jauh lebih banyak daripada UCS ({num(RA['UCS']['exp'], 0)}).</li>
<li><b>GBFS cepat tetapi tersesat.</b> Tanpa <i>g</i>, GBFS memilih langkah yang paling menurunkan perkiraan
biaya sisa. GBFS hanya mengekspansi {num(RA['GBFS']['exp'], 0)} node untuk semua sub-masalah nyata, tetapi
rata-rata {pct(RA['GBFS']['gap'])} lebih mahal dari optimum (sampai {pct(RA['GBFS']['gap_max'])}). Pada semua
sub-masalah dengan <i>k</i> ≤ 9, rata-rata selisih GBFS {pct(float(np.nanmean(c['gbfs_gap_small'])))} dan BFS
{pct(float(np.nanmean(c['blind_gap_small'])))} ({fgapl}).</li>
</ol>{t}{fgap}"""


def sec_scaling(c, D):
    scfg, SC = c["scfg"], c["sc"]
    cells = []
    for k in c["ks"]:
        cells.append([str(k)] + ["batas" if SC(k, a, "solved_rate") < 1 else num(SC(k, a, "expanded_median"), 0)
                                 for a in SEARCH])
    t, tl = D.table(["<i>k</i>"] + ["A* (h2)" if a == "A*" else a for a in SEARCH], cells,
                    "Median node yang diekspansi menurut jumlah sekolah <i>k</i>. <i>batas</i> = ada sub-masalah "
                    "yang melewati batas node.", cls="num")
    fsc, fscl = D.figure("../results/fig_search_scaling.png",
                         "Median node yang diekspansi (kiri) dan node tersimpan maksimum (kanan) terhadap jumlah sekolah "
                         f"<i>k</i>, skala log. Titik <i>k</i> yang tidak semua sub-masalahnya selesai sebelum batas "
                         f"{num(scfg['max_nodes'] / 1e6, 0)} juta node tidak digambar.")
    return D.h2("3.3", "Skalabilitas terhadap Jumlah Sekolah") + f"""<p>{fscl} dan {tl} memperlihatkan pertumbuhan biaya pencarian terhadap <i>k</i>. Ruang
keadaannya tumbuh eksponensial, sehingga pencarian buta meledak lebih dulu. {limit_sentence(c)}
Pada sub-masalah nyata, waktu total IDS {num(c['RA']['IDS']['rt'], 1)} s dan DFS-B&amp;B
{num(c['RA']['DFS-B&B']['rt'], 1)} s, sedangkan A* (h2) hanya {num(c['RA']['A*']['rt'], 1)} s.</p>{fsc}{t}
<p>Kesimpulan: untuk rute satu SPPG, <b>A* dengan heuristik h2</b> adalah pilihan terbaik karena optimal dan
paling hemat node. UCS dan DFS-B&amp;B juga optimal tetapi lebih boros, sedangkan BFS, IDS, dan GBFS tidak
cocok karena mengabaikan biaya.</p>"""


def sec_best_routes(c, D):
    big, IB = c["big"], c["big_inst"]
    best = c["data"][big]["best"]
    cost_saving = 100 * (1 - best["cost_rp"] / IB.ref_cost)
    fr_, frl = D.figure(f"figs/fig_rute_{big}_terbaik.png",
                        f"Rute terbaik di {big} (w = {num(c['w0'], 1)}). Warna = SPPG asal; angka = urutan kunjungan. "
                        "Rute mengikuti jalan asli (OSRM).", width="80%")
    lens = {}
    per_sppg = {}
    for d, seq in best["routes"]:
        lens[len(seq)] = lens.get(len(seq), 0) + 1
        per_sppg[d] = per_sppg.get(d, 0) + len(seq)
    mix = [f"{lens[k]} mengantar ke {k} sekolah" for k in sorted(lens)]
    return D.h2("3.4", "Rute Terbaik dan Interpretasi Praktis") + f"""<p>{frl} menampilkan rute optimal (A*) di {big}: {best['n_vehicles']} Granmax menempuh total
{num(best['km'], 1)} km dengan biaya bensin {rp(best['cost_rp'])} per hari, rata-rata makanan tiba
{num(best['mean_arrival_min'], 1)} menit setelah berangkat, dan sekolah terakhir menerima makanan pada menit
ke-{num(best['makespan_min'], 1)}. Pembanding alami adalah pengiriman langsung (satu Granmax per sekolah, ke
SPPG terdekat) yang biayanya {rp(IB.ref_cost)} dengan rata-rata tiba {num(IB.ref_time, 1)} menit. Rute
gabungan menghemat biaya bensin {pct(cost_saving)} tetapi rata-rata waktu tiba naik
{num(best['mean_arrival_min'] - IB.ref_time, 1)} menit; inilah kompromi yang ditawarkan bobot
<i>w</i> = {num(c['w0'], 1)}. Batas {c['prob']['max_delivery_time_min']} menit jauh dari tercapai.</p>
<p>Dari {len(best['routes'])} Granmax yang dipakai, {join_id(mix)}. Jumlah sekolah per SPPG bervariasi dari
{min(per_sppg.values())} sampai {max(per_sppg.values())}. Sekolah ketiga dalam satu rute menunggu tambahan
2 × {c['prob']['service_time_min']} menit bongkar ditambah waktu tempuh, sehingga menambah sekolah ke rute selalu
menaikkan waktu tiba sekolah itu. Rute lengkap per Granmax, nama sekolah, dan jam tibanya tersedia di
<code>results/{big}/rute_terbaik.txt</code> dan peta interaktif <code>peta_rute_terbaik.html</code>.</p>{fr_}"""


def sec_chapter3(c, D):
    impl = f"""<p class="gh">Kode lengkap: <a href="{GITHUB}">{GITHUB}</a></p>
<p>Seluruh metode diimplementasikan dari nol dalam Python 3 (NumPy; SciPy untuk algoritma Hungaria; Matplotlib
dan Folium untuk visualisasi), tanpa pustaka optimasi siap pakai. Eksperimen dijalankan paralel
(<code>ProcessPoolExecutor</code>). Struktur utama repositori:</p>
<pre>src/mbgvrp/problem.py        model masalah, evaluasi, penugasan SPPG terdekat
src/mbgvrp/search.py         BFS, IDS, DFS-B&amp;B, UCS, A* (h1, h2), GBFS
run_search.py                eksperimen: sub-masalah nyata + skalabilitas
make_animation.py            animasi pencarian rute dan pengiriman
results/                     CSV, grafik, peta rute interaktif (HTML)</pre>"""
    limits = """<ul>
<li>Penugasan sekolah ke SPPG terdekat tidak dioptimasi; pembagian yang menyeimbangkan beban antar-SPPG bisa
menurunkan biaya total, tetapi di luar cakupan perbandingan ini.</li>
<li>Koordinat SPPG adalah perkiraan; jumlah porsi per sekolah dan kapasitas muatan riil Granmax belum dimodelkan.</li>
<li>Waktu tempuh OSRM adalah kondisi lancar; kemacetan tidak dimodelkan.</li>
<li>Pencarian sistematis layak karena satu SPPG paling banyak belasan sekolah. Untuk SPPG yang melayani puluhan
sekolah, perlu heuristik yang lebih kuat, A* berbobot, atau pencarian lokal di tingkat rute.</li>
<li>Optimum acuan adalah UCS; pada sub-masalah yang melewati batas node optimum tidak diketahui sehingga
selisihnya tidak dihitung.</li>
</ul>"""
    return (D.bab("EKSPERIMEN DAN PEMBAHASAN") + D.h2("3.1", "Implementasi dan Lingkungan") + impl
            + sec_real_results(c, D) + sec_scaling(c, D) + sec_best_routes(c, D)
            + D.h2("3.5", "Keterbatasan") + limits)


def sec_chapter4(c, D):
    RA, big, IB = c["RA"], c["big"], c["big_inst"]
    best = c["data"][big]["best"]
    return D.bab("KESIMPULAN") + D.h2("4.1", "Kesimpulan") + f"""<ol>
<li>Distribusi MBG dari SPPG ke sekolah dapat dimodelkan sebagai MDVRP bi-objektif dengan data jalan asli
Surabaya. Dengan penugasan sekolah ke SPPG terdekat, rute tiap SPPG menjadi masalah pencarian kecil yang
dapat diselesaikan secara sistematis.</li>
<li>UCS, A*, dan DFS-B&amp;B menemukan rute optimal bila pencarian selesai; BFS dan IDS hanya meminimalkan
jumlah Granmax sehingga rata-rata {pct(RA['BFS']['gap'])} lebih mahal; GBFS paling cepat tetapi rata-rata
{pct(RA['GBFS']['gap'])} lebih mahal karena mengabaikan biaya jalur.</li>
<li>A* dengan heuristik admissible h2 (relaksasi penugasan slot) mengekspansi {num(c['ratio_real'], 0)} kali lebih
sedikit node daripada UCS, sedangkan A* dengan heuristik sederhana h1 nyaris tidak lebih hemat daripada UCS.
Kualitas heuristik lebih menentukan daripada pilihan algoritmanya.</li>
<li>{limit_sentence(c)} Pada <i>k</i> = {c['kmax']}, median node A* (h2) hanya
{num(c['sc'](c['kmax'], 'A*', 'expanded_median'), 0)} dibanding {num(c['sc'](c['kmax'], 'UCS', 'expanded_median'), 0)}
untuk UCS.</li>
<li>Pada instance {big} ({IB.m} SPPG, {IB.n} sekolah), rute optimal menurunkan biaya bensin
{pct(100 * (1 - best['cost_rp'] / IB.ref_cost))} dibanding pengiriman langsung, dengan kenaikan rata-rata
waktu tiba {num(best['mean_arrival_min'] - IB.ref_time, 1)} menit.</li>
</ol>""" + D.h2("4.2", "Saran") + """<ul>
<li>Mengoptimasi penugasan sekolah ke SPPG (misalnya dengan pencarian lokal) agar beban antar-SPPG seimbang.</li>
<li>Menambahkan jumlah porsi per sekolah dan kapasitas muatan Granmax (Capacitated MDVRP), serta
<i>time window</i> jam istirahat setiap sekolah.</li>
<li>Memakai waktu tempuh historis per jam (misalnya dari data lalu lintas) sebagai pengganti kondisi lancar.</li>
<li>Untuk SPPG yang jauh lebih besar, memakai A* berbobot, beam search, atau pencarian lokal 2-opt.</li>
<li>Memvalidasi koordinat SPPG dan daftar sekolah penerima dengan data resmi BGN/Dinas Pendidikan.</li>
</ul>"""


def build_html(config, data, toc_pages=None):
    D, C = Doc(), Cite()
    c = build_context(config, data)
    parts = [sec_cover(c), sec_abstract(c, D), '<h1 class="bab plain" id="toc">DAFTAR ISI</h1><div class="toc">',
             "", "</div>"]
    toc_index = 3
    parts += [sec_chapter1(c, D, C), sec_chapter2(c, D, C), sec_chapter3(c, D), sec_chapter4(c, D),
              D.unnumbered("pustaka", "DAFTAR PUSTAKA"),
              '<ol class="refs">' + "".join(f"<li>{REFS[k]}</li>" for k in C.order) + "</ol>"]
    parts[toc_index] = "".join(
        f'<div class="toc-l{level}"><a href="#{hid}">{esc(text)}</a><span class="dots"></span>'
        f'<span class="pg">{toc_pages.get(hid, "") if toc_pages else ""}</span></div>'
        for level, hid, text in D.toc if hid != "toc")
    css = (REPORT / "report.css").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>Optimasi Rute Distribusi MBG Surabaya</title>
<style>{css}</style></head>
<body>{chr(10).join(parts)}</body></html>""", D.toc


# ---------------------------------------------------------------------- cetak PDF
def find_browser():
    for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"]:
        if Path(p).exists():
            return p
    for name in ["msedge", "google-chrome", "chromium", "chrome"]:
        if shutil.which(name):
            return shutil.which(name)
    raise SystemExit("Butuh Microsoft Edge atau Google Chrome untuk mencetak PDF")


def print_pdf(html_path, pdf_path):
    subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
                   check=True, capture_output=True)


def heading_pages(pdf_path, toc):
    """Cari halaman tempat setiap heading muncul (halaman daftar isi dilewati)."""
    from pypdf import PdfReader
    norm = lambda t: re.sub(r"\s+", " ", t or "").strip()  # noqa: E731
    pages = [norm(p.extract_text()) for p in PdfReader(str(pdf_path)).pages]
    toc_idx = {i for i, p in enumerate(pages) if "DAFTAR ISI" in p[:60]}
    found, start = {}, 1
    for level, hid, text in toc:
        if hid == "toc":
            continue
        key = norm(text)
        if key.startswith("BAB "):
            key = key.split(" ", 2)[2]   # judul bab saja, "BAB n" bisa terpisah baris
        for i in range(start, len(pages)):
            if i in toc_idx:
                continue
            if key in pages[i]:
                found[hid] = i + 1
                start = i
                break
    return found


def update_word_fields(docx_path):
    """Isi daftar isi & nomor halaman lewat Microsoft Word (Windows). Gagal -> diam saja."""
    if sys.platform != "win32":
        return False
    ps = (
        "$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
        f"$d = $w.Documents.Open('{docx_path.resolve()}'); "
        "foreach ($t in $d.TablesOfContents) { $t.Update() }; $d.Fields.Update() | Out-Null; "
        "$d.Save(); $d.Close(); $w.Quit()"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True, timeout=300)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    (REPORT / "figs").mkdir(exist_ok=True)
    from figures import fig_rute, fig_wilayah
    from html_to_docx import html_to_docx
    if not (REPORT / "figs" / "fig_wilayah.png").exists():
        fig_wilayah(config, REPORT / "figs" / "fig_wilayah.png")
    big = list(config["instances"])[-1]
    fig_rute(config, big, REPORT / "figs" / f"fig_cover_{big}.png", title=False)
    fig_rute(config, big, REPORT / "figs" / f"fig_rute_{big}_terbaik.png")
    data = load_all(config)

    page_html, toc = build_html(config, data)
    docx_path = REPORT / "Laporan_Final_MBG_VRP.docx"
    html_to_docx(page_html, docx_path, REPORT)
    toc_ok = update_word_fields(docx_path)
    print(f"-> {docx_path}" + ("" if toc_ok else "  (buka di Word lalu Update Field untuk mengisi daftar isi)"))

    if "--pdf" in sys.argv:
        html_path = REPORT / "laporan.html"
        pdf_path = REPORT / "Laporan_Final_MBG_VRP.pdf"
        html_path.write_text(page_html, encoding="utf-8")
        print_pdf(html_path, pdf_path)
        pages = heading_pages(pdf_path, toc)
        page_html, _ = build_html(config, data, toc_pages=pages)
        html_path.write_text(page_html, encoding="utf-8")
        print_pdf(html_path, pdf_path)
        print(f"-> {pdf_path}")


if __name__ == "__main__":
    main()
