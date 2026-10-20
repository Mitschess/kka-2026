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
import math
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPORT))

import numpy as np  # noqa: E402

from mbgvrp.problem import load_instance  # noqa: E402

# ============================================================== IDENTITAS (isi sendiri)
TEAM = [("[Nama Anggota 1]", "[NRP]"), ("[Nama Anggota 2]", "[NRP]"), ("[Nama Anggota 3]", "[NRP]")]
COURSE = "Konsep Kecerdasan Artifisial (KKA)"
LECTURER = "[Nama Dosen Pengampu]"
INSTITUTION = "[Departemen / Program Studi]<br>[Nama Institusi]"
DATE = "Oktober 2026"
GITHUB = "https://github.com/Mitschess/kka-2026"

SEARCH = ["BFS", "IDS", "DFS-B&B", "UCS", "A* (h1)", "A*", "GBFS"]
LOCAL = ["HC", "HC-Sideways", "Stochastic HC", "Random-Walk HC", "RR-HC", "EHC", "SA", "GA"]
INTEG = ["HC", "SA", "GA", "ACO"]
TOL = 1e-9

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
    "selman": "Selman, B., Kautz, H. A., &amp; Cohen, B. (1994). Noise strategies for improving local search. <i>Proceedings of the 12th National Conference on Artificial Intelligence (AAAI-94)</i>, 337–343.",
    "hoffmann": "Hoffmann, J., &amp; Nebel, B. (2001). The FF planning system: Fast plan generation through heuristic search. <i>Journal of Artificial Intelligence Research</i>, 14, 253–302.",
    "kirkpatrick": "Kirkpatrick, S., Gelatt, C. D., &amp; Vecchi, M. P. (1983). Optimization by simulated annealing. <i>Science</i>, 220(4598), 671–680.",
    "holland": "Holland, J. H. (1975). <i>Adaptation in Natural and Artificial Systems</i>. University of Michigan Press.",
    "goldberg": "Goldberg, D. E. (1989). <i>Genetic Algorithms in Search, Optimization, and Machine Learning</i>. Addison-Wesley.",
    "prins": "Prins, C. (2004). A simple and effective evolutionary algorithm for the vehicle routing problem. <i>Computers &amp; Operations Research</i>, 31(12), 1985–2002.",
    "dorigo": "Dorigo, M., &amp; Stützle, T. (2004). <i>Ant Colony Optimization</i>. MIT Press.",
    "mmas": "Stützle, T., &amp; Hoos, H. H. (2000). MAX–MIN Ant System. <i>Future Generation Computer Systems</i>, 16(8), 889–914.",
    "nsga2": "Deb, K., Pratap, A., Agarwal, S., &amp; Meyarivan, T. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II. <i>IEEE Transactions on Evolutionary Computation</i>, 6(2), 182–197.",
    "mann": "Mann, H. B., &amp; Whitney, D. R. (1947). On a test of whether one of two random variables is stochastically larger than the other. <i>Annals of Mathematical Statistics</i>, 18(1), 50–60.",
    "holm": "Holm, S. (1979). A simple sequentially rejective multiple test procedure. <i>Scandinavian Journal of Statistics</i>, 6(2), 65–70.",
    "derrac": "Derrac, J., García, S., Molina, D., &amp; Herrera, F. (2011). A practical tutorial on the use of nonparametric statistical tests as a methodology for comparing evolutionary and swarm intelligence algorithms. <i>Swarm and Evolutionary Computation</i>, 1(1), 3–18.",
    "osrm": "Luxen, D., &amp; Vetter, C. (2011). Real-time routing with OpenStreetMap data. <i>Proceedings of the 19th ACM SIGSPATIAL International Conference on Advances in Geographic Information Systems</i>, 513–516.",
    "osm": "OpenStreetMap contributors. (2026). <i>OpenStreetMap</i> [data set, diakses Oktober 2026]. https://www.openstreetmap.org",
    "who": "World Health Organization. (2006). <i>Five Keys to Safer Food Manual</i>. WHO.",
    "perpres": "Peraturan Presiden Republik Indonesia Nomor 83 Tahun 2024 tentang Badan Gizi Nasional.",
    "jawapos": "Jawa Pos. (2026, 14 Mei). Heboh kasus keracunan MBG di Surabaya, ternyata 84 SPPG di Kota Pahlawan belum punya sertifikat laik higiene. https://www.jawapos.com/surabaya-raya/2605140232/",
    "times": "Times Indonesia. (2026). 200 siswa keracunan MBG di Surabaya, Emil Dardak ancam sanksi tegas SPPG Tembok Dukuh. https://timesindonesia.co.id/peristiwa-daerah/589872/",
    "antara1": "ANTARA Jawa Timur. (2025). SPPG Polrestabes Surabaya layani 3.119 porsi MBG. https://jatim.antaranews.com/berita/983209/",
    "antara2": "ANTARA Jawa Timur. (2025). Dapur SPPG Simokerto resmi beroperasi dengan pemberdayaan lokal. https://jatim.antaranews.com/berita/1041086/",
    "prisma": "Pemerintah Kota Surabaya (Prisma). (2025, 16 Agustus). Peresmian Dapur MBG di Wisma Kedung Asem Indah, Kelurahan Kedung Baruk, Kecamatan Rungkut. https://prisma.surabaya.go.id/",
    "clarke": "Clarke, G., &amp; Wright, J. W. (1964). Scheduling of vehicles from a central depot to a number of delivery points. <i>Operations Research</i>, 12(4), 568–581.",
    "talbi": "Talbi, E.-G. (2009). <i>Metaheuristics: From Design to Implementation</i>. Wiley.",
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


def pval(p):
    return num(p, 3) if p >= 0.001 else f"{p:.1e}".replace(".", ",")


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
        res = ROOT / "results" / name
        X = {"inst": load_instance(ROOT, name, config), "res": res}
        X["ls"] = {r["algorithm"]: floats(r) for r in read_csv(res / "ls_summary.csv")}
        X["ls_runs"] = [floats(r) for r in read_csv(res / "ls_runs.csv")]
        X["ls_tests"] = {r["pair"]: r for r in read_csv(res / "ls_stat_tests.csv")}
        X["ls_best"] = json.loads((res / "ls_best.json").read_text(encoding="utf-8"))
        X["integ"] = {r["algorithm"]: floats(r) for r in read_csv(res / "summary_main_w.csv")}
        X["front"] = [floats(r) for r in read_csv(res / "nsga2_front.csv")]
        hv = defaultdict(list)
        for r in read_csv(res / "hypervolume.csv"):
            hv[r["algorithm"]].append(float(r["hypervolume"]))
        X["hv"] = {a: float(np.mean(v)) for a, v in hv.items()}
        X["sweep"] = [floats(r) for r in read_csv(res / "ls_sweep.csv")] if (res / "ls_sweep.csv").exists() else []
        X["sens"] = [floats(r) for r in read_csv(res / "sensitivity.csv")] if (res / "sensitivity.csv").exists() else []
        data[name] = X
    data["_real"] = [floats(r) for r in read_csv(ROOT / "results" / "search_real.csv")]
    data["_scal"] = [floats(r) for r in read_csv(ROOT / "results" / "search_summary.csv")]
    data["_scal_runs"] = [floats(r) for r in read_csv(ROOT / "results" / "search_scaling.csv")]
    return data


def ls_test(X, a, b):
    t = X["ls_tests"].get(f"{a} vs {b}") or X["ls_tests"].get(f"{b} vs {a}")
    return float(t["p_holm"]), t["significant_5pct"] == "True", t["better_mean"]


def best_ls(X):
    return min(LOCAL, key=lambda a: (X["ls"][a]["fitness_mean"], -X["ls"][a]["success_rate"],
                                     X["ls"][a]["runtime_s_mean"]))



def heuristic_ratios(config, data):
    """Rata-rata h(awal)/optimum untuk h1 dan h2 pada sub-masalah nyata Bagian A."""
    from mbgvrp.router import Router
    from mbgvrp.search import RoutingProblem
    w, pen = config["experiment"]["main_weight"], config["experiment"]["penalty"]
    r1, r2 = [], []
    for name in config["instances"]:
        X = data[name]
        inst = X["inst"]
        top = best_ls(X)
        per = defaultdict(list)
        for d, seq in X["ls_best"][top]["routes"]:
            per[d].extend(seq)
        router = Router(inst, w, pen)
        for d, sch in per.items():
            opt = router.cost(d, sum(1 << s for s in sch))
            p = RoutingProblem(inst, d, sorted(sch), w)
            r1.append(p.h_nearest(p.initial) / opt)
            r2.append(p.h(p.initial) / opt)
    return {"h1": float(np.mean(r1)), "h2": float(np.mean(r2))}


# ---------------------------------------------------------------------- isi laporan
def build_html(config, data, toc_pages=None):
    D, C = Doc(), Cite()
    exp, prob, asg, scfg = config["experiment"], config["problem"], config["assignment"], config["search"]
    names = list(config["instances"])
    small, big = names[0], names[-1]
    S, B = data[small], data[big]
    w0, seeds, budget = exp["main_weight"], asg["n_seeds"], asg["budget_evals"]
    cpk = prob["fuel_price_per_liter"] / prob["km_per_liter"]
    IB = B["inst"]

    # ---- angka Bagian A
    real, scal, scal_runs = data["_real"], data["_scal"], data["_scal_runs"]

    def agg_real(a):
        rs = [r for r in real if r["algorithm"] == a]
        return dict(n=len(rs), opt=sum(r["optimal"] == "True" for r in rs),
                    gap=float(np.nanmean([r["gap_pct"] for r in rs])),
                    gap_max=float(np.nanmax([r["gap_pct"] for r in rs])),
                    exp=sum(r["expanded"] for r in rs), mem=max(r["max_stored"] for r in rs),
                    rt=sum(r["runtime_s"] for r in rs),
                    trips=float(np.mean([r["n_trips"] for r in rs])))
    RA = {a: agg_real(a) for a in SEARCH}
    ks = sorted({int(r["k"]) for r in scal})

    def sc(k, a, key):
        return next(r[key] for r in scal if int(r["k"]) == k and r["algorithm"] == a)
    solved_all = {a: max([k for k in ks if sc(k, a, "solved_rate") == 1] or [0]) for a in SEARCH}
    k9 = 9 if 9 in ks else max(ks)
    kmax = max(ks)
    ratio_ucs_astar_real = RA["UCS"]["exp"] / RA["A*"]["exp"]
    ratio_h1_h2_real = RA["A* (h1)"]["exp"] / RA["A*"]["exp"]
    ratio_k9 = sc(k9, "UCS", "expanded_median") / sc(k9, "A*", "expanded_median")
    ratio_kmax = sc(kmax, "UCS", "expanded_median") / sc(kmax, "A*", "expanded_median")
    blind_gap_small = [r["gap_pct"] for r in scal_runs if r["algorithm"] == "BFS" and r["k"] <= 9]
    gbfs_gap_small = [r["gap_pct"] for r in scal_runs if r["algorithm"] == "GBFS" and r["k"] <= 9]
    real_k = sorted({int(r["k"]) for r in real})

    # ---- angka Bagian B
    topB, topS = best_ls(B), best_ls(S)
    bkB, bkS = B["ls_best"]["best_known_fitness"], S["ls_best"]["best_known_fitness"]
    gB, gS = B["ls_best"]["Greedy"], S["ls_best"]["Greedy"]
    solB = B["ls_best"][topB]
    sav_B = (gB["cost_rp"] - solB["cost_rp"]) / gB["cost_rp"] * 100
    integ_best_B = min(INTEG, key=lambda a: B["integ"][a]["fitness_mean"])
    ib = B["integ"][integ_best_B]
    rank_B = sorted(LOCAL, key=lambda a: (B["ls"][a]["fitness_mean"], -B["ls"][a]["success_rate"]))
    perfect_S = all(S["ls"][a]["success_rate"] == 1 for a in LOCAL)
    better_than_integ = [a for a in LOCAL if B["ls"][a]["fitness_mean"] < ib["fitness_mean"]]
    space_B = IB.n * math.log10(IB.m)
    space_S = S["inst"].n * math.log10(S["inst"].m)
    h_ratio = heuristic_ratios(config, data)
    bfs_eq_ids = all(abs(a["cost"] - b["cost"]) < 1e-9 for a in real if a["algorithm"] == "BFS"
                     for b in real if b["algorithm"] == "IDS" and b["instance"] == a["instance"]
                     and b["depot"] == a["depot"])
    integ_best_S = min(S["integ"][a]["fitness_best"] for a in INTEG)

    parts = []
    P = parts.append

    # ------------------------------------------------------------------ sampul
    team_rows = "".join(f"<tr><td>{esc(n)}</td><td>{esc(nrp)}</td></tr>" for n, nrp in TEAM)
    P(f"""
<section class="cover">
  <div class="cover-kicker">Final Project · {esc(COURSE)}</div>
  <h1 class="cover-title">Optimasi Rute Distribusi Makan Bergizi Gratis dari SPPG ke Sekolah di Surabaya</h1>
  <div class="cover-sub">Pendekatan Dua Tingkat: Algoritma Pencarian (BFS, IDS, DFS Branch and Bound, UCS, A*,
  Greedy Best-First) untuk Rute per SPPG dan Pencarian Lokal (Hill Climbing beserta variannya, Simulated
  Annealing, Genetic Algorithm) untuk Pembagian Sekolah</div>
  <div class="cover-box">
    <div class="cover-label">Disusun oleh</div>
    <table class="cover-team">{team_rows}</table>
    <div class="cover-label">Dosen pengampu</div>
    <div>{esc(LECTURER)}</div>
  </div>
  <div class="cover-foot">{INSTITUTION}<br>{DATE}</div>
</section>""")

    # ------------------------------------------------------------------ abstrak
    P(D.unnumbered("abstrak", "RINGKASAN"))
    P(f"""<p>Program Makan Bergizi Gratis (MBG) mengirim makanan matang setiap hari dari dapur
<b>Satuan Pelayanan Pemenuhan Gizi (SPPG)</b> ke sekolah. Rute pengiriman menentukan biaya bensin yang
ditanggung SPPG sekaligus lamanya makanan menunggu sebelum dimakan. Laporan ini memodelkan distribusi MBG
di Surabaya sebagai <b>Multi-Depot Vehicle Routing Problem (MDVRP) bi-objektif</b> (biaya bensin Granmax dan
rata-rata waktu tiba makanan) dengan batas 3 sekolah per Granmax, armada terbatas per SPPG, bongkar 15 menit
per sekolah, dan batas 180 menit sejak makanan selesai dimasak. Data memakai lokasi SPPG dari berita,
sekolah dari OpenStreetMap, serta jarak dan waktu tempuh jalan asli dari OSRM.</p>
<p>Masalah dipecah menjadi dua tingkat yang sesuai dengan materi kuliah. <b>Bagian A</b> menyusun rute
Granmax di dalam satu SPPG sebagai pencarian di ruang keadaan dan membandingkan BFS, Iterative Deepening,
DFS dengan Branch and Bound, Uniform-Cost Search, A*, dan Greedy Best-First Search. <b>Bagian B</b> membagi
sekolah ke SPPG dengan delapan algoritma pencarian lokal: Hill Climbing (HC) beserta lima variannya
(<i>sideways</i>, <i>stochastic</i>, <i>random-walk</i>, <i>random-restart</i>, <i>enforced</i>), Simulated
Annealing, dan Genetic Algorithm. Setiap pembagian dinilai dengan rute optimal hasil Bagian A.</p>
<p>Di Bagian A, UCS, A*, dan DFS-B&amp;B selalu menemukan rute optimal. BFS dan IDS hanya menemukan rute
dengan Granmax paling sedikit (rata-rata {pct(RA['BFS']['gap'])} lebih mahal dari optimum pada sub-masalah
nyata), sedangkan Greedy Best-First paling cepat tetapi rata-rata {pct(RA['GBFS']['gap'])} lebih mahal.
Heuristik admissible baru berbasis penugasan slot membuat A* mengekspansi {num(ratio_ucs_astar_real, 0)}
kali lebih sedikit node daripada UCS. Di Bagian B ({seeds} seed, {num(budget, 0)} evaluasi per run),
semua algoritma mencapai solusi terbaik yang sama pada instance kecil. Pada instance {IB.m} SPPG dan
{IB.n} sekolah, {topB} memberi rata-rata terbaik ({num(B['ls'][topB]['fitness_mean'], 4)}) dan
{len(better_than_integ)} dari 8 algoritma lebih baik daripada metaheuristik terintegrasi terbaik dari
eksperimen awal ({integ_best_B}, {num(ib['fitness_mean'], 4)}). Rute terbaik menghemat biaya bensin
{pct(sav_B)} dibanding heuristik Greedy.</p>
<p class="kw"><b>Kata kunci:</b> MDVRP, algoritma pencarian, A*, heuristik admissible, Hill Climbing,
Enforced Hill Climbing, Simulated Annealing, Genetic Algorithm, Makan Bergizi Gratis, Surabaya.</p>""")

    # ------------------------------------------------------------------ daftar isi
    P('<h1 class="bab plain" id="toc">DAFTAR ISI</h1><div class="toc">')
    toc_placeholder_index = len(parts)
    P("")  # diisi setelah semua heading terkumpul
    P("</div>")

    # ================================================================== BAB 1
    P(D.bab("PENDAHULUAN"))
    P(D.h2("1.1", "Latar Belakang"))
    P(f"""<p>Program Makan Bergizi Gratis (MBG) dijalankan pemerintah sejak 6 Januari 2025 di bawah Badan
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
depot (<i>multi-depot</i>) {C('cordeau')}. Di dalamnya ada dua keputusan yang sifatnya berbeda.
<b>Pertama</b>, setiap sekolah dilayani oleh SPPG yang mana. Keputusan ini sangat besar ruangnya: untuk
{IB.n} sekolah dan {IB.m} SPPG ada {IB.m}<sup>{IB.n}</sup> ≈ 10<sup>{space_B:.0f}</sup> kemungkinan
pembagian, sehingga cocok diselesaikan dengan <b>pencarian lokal</b> (Hill Climbing dan kerabatnya,
Simulated Annealing, Genetic Algorithm) dari materi Kuliah 6 {C('aima')}. <b>Kedua</b>, di dalam satu SPPG,
sekolah-sekolahnya dibagi ke Granmax dan diurutkan. Karena satu SPPG hanya melayani beberapa sekolah
(paling banyak 3 Granmax × 3 sekolah = 9), keputusan ini cukup kecil untuk dicari secara sistematis dengan
<b>algoritma pencarian</b> di ruang keadaan dari Kuliah 2 dan 3, mulai dari pencarian buta (BFS, IDS, DFS)
hingga pencarian berinformasi (UCS, A*, Greedy Best-First).</p>""")
    P(D.h2("1.2", "Rumusan Masalah"))
    P(f"""<p>Diberikan sejumlah SPPG di Surabaya, masing-masing dengan {config['instances'][big]['vehicles_per_sppg']}
Granmax, dan sekumpulan sekolah penerima MBG, tentukan sekolah mana yang dilayani oleh SPPG mana, oleh Granmax
mana, dan dengan urutan bagaimana, sehingga:</p>
<ol>
<li><b>biaya bensin total</b> paling rendah (jarak tempuh / {num(prob['km_per_liter'], 0)} km per liter
× Rp{num(prob['fuel_price_per_liter'], 0)} per liter Pertalite), dan</li>
<li><b>rata-rata waktu tiba</b> makanan di sekolah paling rendah,</li>
</ol>
<p>dengan syarat setiap Granmax melayani paling banyak {prob['max_schools_per_vehicle']} sekolah, bongkar
muat {prob['service_time_min']} menit per sekolah, dan makanan tiba paling lambat
{prob['max_delivery_time_min']} menit setelah selesai dimasak. Pertanyaan penelitiannya:</p>
<ol>
<li>Untuk menyusun rute di dalam satu SPPG, bagaimana perbandingan BFS, IDS, DFS dengan Branch and Bound,
UCS, A*, dan Greedy Best-First Search dalam hal optimalitas, jumlah node yang diekspansi, memori, dan
waktu? Seberapa besar pengaruh kualitas heuristik terhadap A*?</li>
<li>Untuk membagi sekolah ke SPPG, algoritma pencarian lokal mana di antara Hill Climbing, HC dengan
<i>sideways moves</i>, Stochastic HC, Random-Walk HC, Random-Restart HC, Enforced HC, Simulated Annealing,
dan Genetic Algorithm yang memberi solusi terbaik dan paling konsisten dengan anggaran evaluasi yang sama?</li>
<li>Seberapa baik pendekatan dua tingkat ini dibandingkan heuristik Greedy dan metaheuristik terintegrasi
yang mencari langsung di ruang rute penuh, dan seberapa sensitif solusinya terhadap asumsi kapasitas,
kemacetan, dan efisiensi bensin?</li>
</ol>""")
    P(D.h2("1.3", "Tujuan"))
    P("""<ol>
<li>Membangun model MDVRP bi-objektif distribusi MBG dengan data jalan asli Surabaya.</li>
<li>Merumuskan rute di dalam satu SPPG sebagai masalah pencarian dan membandingkan enam algoritma pencarian
(ditambah dua versi heuristik A*) secara terukur.</li>
<li>Merumuskan pembagian sekolah ke SPPG sebagai masalah pencarian lokal dan membandingkan delapan algoritma
secara adil dan teruji statistik.</li>
<li>Menghasilkan rute yang dapat dibaca langsung oleh pengelola SPPG beserta visualisasi peta.</li>
</ol>""")
    P(D.h2("1.4", "Manfaat"))
    P(f"""<ul>
<li><b>Bagi pengelola SPPG:</b> rute konkret dengan biaya bensin {pct(sav_B)} lebih rendah daripada
heuristik greedy pada instance besar, beserta pilihan kompromi bila SPPG lebih mengutamakan kecepatan.</li>
<li><b>Bagi pembuat kebijakan:</b> gambaran kuantitatif pengaruh jumlah sekolah per kendaraan dan
kemacetan terhadap biaya dan batas waktu konsumsi.</li>
<li><b>Secara akademik:</b> contoh penerapan seluruh keluarga algoritma pencarian dan pencarian lokal dari
materi kuliah pada satu masalah nyata, termasuk perancangan heuristik admissible dan uji statistik.</li>
</ul>""")
    P(D.h2("1.5", "Batasan dan Asumsi"))
    P(f"""<ul>
<li>Lalu lintas lancar dan semua lampu hijau: waktu tempuh memakai durasi OSRM kondisi lancar
(dilonggarkan pada analisis sensitivitas kemacetan).</li>
<li>Semua makanan selesai dimasak dan diberangkatkan bersamaan (t = 0); setiap Granmax melakukan satu
perjalanan dan kembali ke SPPG.</li>
<li>Kendaraan Granmax berbahan bakar Pertalite Rp{num(prob['fuel_price_per_liter'], 0)}/liter dengan
konsumsi {num(prob['km_per_liter'], 0)} km/liter (batas atas rentang 10–14 km/liter), atau
{rp(cpk)} per km.</li>
<li>"Maksimal 3 sekolah" diartikan per kendaraan; jumlah porsi per sekolah dianggap muat dalam satu
Granmax.</li>
<li>Koordinat SPPG adalah perkiraan hasil geocoding alamat yang diberitakan, bukan titik resmi BGN.</li>
</ul>""")

    # ================================================================== BAB 2
    P(D.bab("METODE"))
    P(D.h2("2.1", "Alur Penelitian"))
    P("""<div class="flow">
<div><b>1. Data</b><br>SPPG (berita) + sekolah (OpenStreetMap) + jarak &amp; waktu jalan (OSRM)</div>
<div><b>2. Model</b><br>MDVRP bi-objektif, digabung menjadi satu fitness F</div>
<div><b>3. Dekomposisi</b><br>Bagian B: sekolah → SPPG; Bagian A: rute di dalam SPPG</div>
<div><b>4. Bagian A</b><br>BFS, IDS, DFS-B&amp;B, UCS, A*, Greedy Best-First</div>
<div><b>5. Bagian B</b><br>6 varian Hill Climbing, Simulated Annealing, Genetic Algorithm</div>
<div><b>6. Analisis</b><br>optimalitas, node, memori, uji statistik, peta, sensitivitas</div>
</div>""")
    P(D.h2("2.2", "Data dan Pembentukan Instance"))
    inst_rows = []
    for name in names:
        I = data[name]["inst"]
        spec = config["instances"][name]
        inst_rows.append([f"<code>{name}</code>", ", ".join(s.replace("SPPG-", "") for s in spec["sppg_ids"]),
                          str(I.n), str(I.R), num(spec["radius_km"], 0) + " km",
                          f"{I.m}<sup>{I.n}</sup> ≈ 10<sup>{I.n * math.log10(I.m):.1f}</sup>".replace(".", ",")])
    t, tl = D.table(["Instance", "SPPG", "Sekolah", "Granmax", "Radius", "Kemungkinan pembagian*"], inst_rows,
                    "Dua instance yang diuji. *Jumlah cara membagi sekolah ke SPPG (ruang Bagian B).")
    fig, fl = D.figure("figs/fig_wilayah.png", "Lokasi SPPG (bintang) dan sekolah (lingkaran) pada kedua "
                       "instance di Surabaya.")
    P(f"""<p>Lokasi SPPG diambil dari pemberitaan resmi dan media (Polrestabes/Krembangan, Simokerto,
Tembok Dukuh, Kedung Baruk/Rungkut, Jemur Wonosari, Mulyorejo) {C('jawapos', 'times', 'antara1', 'antara2', 'prisma')},
lalu di-geocode dengan Nominatim/OpenStreetMap. Sebanyak 751 sekolah jenjang SD/MI/SMP/MTs di Kota Surabaya
diunduh dari OpenStreetMap {C('osm')} melalui Overpass API. Untuk setiap instance, SPPG secara bergiliran
mengambil sekolah acak (seed tetap) dalam radius {num(config['instances'][big]['radius_km'], 0)} km,
sehingga daerah layanan antar-SPPG bisa tumpang tindih dan pembagian sekolah antar-SPPG ikut menjadi
keputusan. Jarak (km) dan waktu tempuh (menit) antar semua titik dihitung dengan OSRM {C('osrm')} di atas
jaringan jalan OpenStreetMap, bukan jarak garis lurus. {tl} merangkum instance yang dipakai dan {fl}
menunjukkan lokasinya.</p>{t}{fig}""")

    P(D.h2("2.3", "Formulasi Masalah"))
    P(f"""<p>Misalkan <i>D</i> = {{1, …, m}} himpunan SPPG (depot), <i>S</i> = {{1, …, n}} himpunan sekolah,
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
<p>Kedua objektif digabung dengan <i>weighted sum</i> ternormalisasi menjadi satu fitness:</p>
<div class="eq"><i>F<sub>w</sub></i> = <i>w</i> · <i>f</i><sub>1</sub>/<i>f</i><sub>1</sub><sup>ref</sup> +
(1 − <i>w</i>) · <i>f</i><sub>2</sub>/<i>f</i><sub>2</sub><sup>ref</sup> + {num(exp['penalty'], 0)} · <i>V</i></div>
<p>dengan <i>f</i><sub>1</sub><sup>ref</sup> biaya solusi "bintang" (setiap sekolah diantar pulang-pergi
dari SPPG terdekat) dan <i>f</i><sub>2</sub><sup>ref</sup> rata-rata waktu tempuh langsung dari SPPG
terdekat (batas bawah <i>f</i><sub>2</sub>), sehingga kedua suku berskala sekitar 1. <i>V</i> adalah
besar pelanggaran (kelebihan kapasitas + kelebihan armada + menit keterlambatan/10); penalti membuat
solusi tidak layak selalu kalah dari solusi layak. Bobot utama <i>w</i> = {num(w0, 1)} (biaya dan waktu
sama penting); bobot lain {{0; 0,25; 0,75; 1}} dipakai untuk memetakan trade-off. Yang penting untuk
Bagian A: <i>F<sub>w</sub></i> adalah <b>jumlah kontribusi tiap ruas perjalanan</b>, yaitu jarak ruas
(untuk <i>f</i><sub>1</sub>) dan waktu tiba di sekolah ujung ruas (untuk <i>f</i><sub>2</sub>), sehingga
dapat dipakai langsung sebagai biaya jalur dalam algoritma pencarian.</p>""")

    P(D.h2("2.4", "Dekomposisi Dua Tingkat"))
    P(f"""<p>Misalkan pembagian sekolah ke SPPG sudah ditetapkan dan dinyatakan sebagai vektor <i>x</i>, dengan
<i>x<sub>s</sub></i> = SPPG yang melayani sekolah <i>s</i>. Granmax dari SPPG yang berbeda tidak berbagi apa
pun: armadanya terpisah, dan semua berangkat pada t = 0. Karena itu biaya rute setiap SPPG dapat dicari
sendiri-sendiri, dan fitness terbaik untuk pembagian <i>x</i> adalah</p>
<div class="eq"><i>F</i>(<i>x</i>) = Σ<sub><i>d</i>∈<i>D</i></sub> <i>R</i>*(<i>d</i>, <i>S<sub>d</sub></i>(<i>x</i>)),
&nbsp;&nbsp; <i>S<sub>d</sub></i>(<i>x</i>) = {{<i>s</i> : <i>x<sub>s</sub></i> = <i>d</i>}}</div>
<p>dengan <i>R</i>*(<i>d</i>, <i>A</i>) biaya rute optimal SPPG <i>d</i> untuk himpunan sekolah <i>A</i>.
Meminimalkan <i>F</i>(<i>x</i>) atas semua pembagian <i>x</i> memberi optimum masalah asli, jadi
dekomposisi ini <b>eksak</b>, bukan pendekatan. Pola "bagi dulu, rutekan kemudian"
(<i>cluster-first, route-second</i>) dikenal dalam literatur VRP {C('gillett', 'fisher')}. Bedanya, di sini
tahap rute diselesaikan optimal dan tahap pembagian dicari dengan pencarian lokal.</p>
<div class="flow">
<div><b>Bagian B (Kuliah 6)</b><br>Pencarian lokal di ruang pembagian <i>x</i>: pindah / tukar sekolah antar-SPPG</div>
<div><b>Fitness</b><br><i>F</i>(<i>x</i>) = jumlah biaya rute optimal tiap SPPG</div>
<div><b>Bagian A (Kuliah 2–3)</b><br>Pencarian di ruang keadaan rute satu SPPG: UCS, A*, dan lainnya</div>
</div>
<p>Pembagian kerja ini sesuai dengan ukuran masing-masing ruang. Ruang pembagian sangat besar
(10<sup>{space_B:.0f}</sup> pada instance besar) tetapi strukturnya sederhana, sehingga cocok untuk
pencarian lokal yang tidak menyimpan jalur. Ruang rute satu SPPG kecil (paling banyak 9 sekolah) tetapi
biayanya bergantung pada urutan, sehingga cocok untuk pencarian sistematis yang bisa menjamin optimal.</p>""")

    # ---- 2.5 Bagian A
    P(D.h2("2.5", "Bagian A: Rute di Dalam Satu SPPG"))
    P(D.h3("2.5.1", "Formulasi ruang keadaan"))
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
    P(f"""<p>Rute satu SPPG dibangun langkah demi langkah seperti masalah pencarian rute pada umumnya
{C('aima')}. {tl} merangkum formulasinya. Satu komponen keadaan, waktu <i>t</i>, diperlukan karena biaya
langkah berikutnya (waktu tiba) bergantung pada kapan Granmax berangkat dari posisi sekarang. Pemecah
simetri pada komponen "pembuka" tidak membuang solusi: setiap himpunan rute tetap dapat ditulis dengan
Granmax diurutkan menurut sekolah pertamanya. Dengan aturan ini, satu SPPG dengan 9 sekolah dan 3 Granmax
memiliki 9!/3! = 60.480 rute lengkap yang berbeda, cukup kecil untuk pencarian sistematis. Aksi pulang
dari sekolah langsung menuju keadaan dengan posisi SPPG, sehingga graf keadaannya tidak memiliki siklus.
Untuk deteksi keadaan berulang, <i>t</i> hanya ikut dibandingkan selama Granmax masih bisa menambah
sekolah; setelah itu <i>t</i> tidak lagi memengaruhi biaya ke depan.</p>{t}""")

    P(D.h3("2.5.2", "Algoritma pencarian buta"))
    P(f"""<ul>
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
</ul>""")
    P(D.h3("2.5.3", "Pencarian berinformasi dan heuristik"))
    P(f"""<p>Ketiga algoritma berikut adalah <i>best-first graph search</i> dengan antrian prioritas, yang
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
Karakteristik keenam algoritma dirangkum pada Tabel 2.{D.tab + 1}.</p>""")
    a_rows = [
        ["BFS", "FIFO", "tes goal saat dibangkitkan", "tidak*", "O(<i>b<sup>d</sup></i>)"],
        ["IDS", "LIFO, batas kedalaman naik", "DFS diulang", "tidak*", "O(<i>bd</i>)"],
        ["DFS-B&amp;B", "LIFO, anak termurah dulu", "pangkas <i>g</i> ≥ terbaik", "ya", "O(<i>bd</i>)"],
        ["UCS", "prioritas <i>g</i>", "–", "ya", "O(<i>b</i><sup>1+⌊C*/ε⌋</sup>)"],
        ["A*", "prioritas <i>g</i> + <i>h</i>", "h1 atau h2", "ya", "eksponensial, bergantung <i>h</i>"],
        ["GBFS", "prioritas <i>h</i>", "h2", "tidak", "bergantung <i>h</i>"],
    ]
    t, tl = D.table(["Algoritma", "Frontier", "Catatan", "Optimal?", "Memori"], a_rows,
                    "Algoritma pencarian Bagian A. *Hanya optimal jika semua biaya langkah sama.", cls="small")
    P(t)

    # ---- 2.6 Bagian B
    P(D.h2("2.6", "Bagian B: Pembagian Sekolah ke SPPG"))
    P(D.h3("2.6.1", "Representasi, fitness, dan tetangga"))
    nb_S = S["inst"].n * (S["inst"].m - 1)
    nb_B = IB.n * (IB.m - 1)
    P(f"""<p>Keadaan adalah vektor pembagian <i>x</i> = (<i>x</i><sub>1</sub>, …, <i>x<sub>n</sub></i>) dengan
<i>x<sub>s</sub></i> ∈ {{1, …, m}}. Fitness-nya adalah <i>F</i>(<i>x</i>) pada subbab 2.4: jumlah biaya rute
optimal setiap SPPG. SPPG yang menerima lebih dari 3 × 3 = 9 sekolah memerlukan Granmax tambahan dan
dikenai penalti {num(exp['penalty'], 0)} per Granmax, begitu juga keterlambatan di atas 3 jam. Untuk GA,
<i>fitness</i> dinyatakan sebagai 1/<i>F</i> (makin besar makin baik). Dua jenis langkah membentuk
tetangga:</p>
<ul>
<li><b>pindah(s, d)</b>: sekolah <i>s</i> dipindah ke SPPG <i>d</i> ({nb_S} tetangga di {small},
{nb_B} di {big});</li>
<li><b>tukar(s, u)</b>: dua sekolah dari SPPG berbeda bertukar SPPG (sekitar {num(S['inst'].n ** 2 / 3, 0)}
dan {num(IB.n ** 2 * (1 - 1 / IB.m) / 2, 0)} tetangga). Langkah ini penting saat SPPG sudah penuh, karena
pindah saja akan langsung kena penalti.</li>
</ul>
<p>Setiap evaluasi tetangga cukup menghitung ulang dua SPPG yang berubah. Biaya rute optimal
<i>R</i>*(<i>d</i>, <i>A</i>) dihitung oleh <b>evaluator rute</b> yang menyelesaikan masalah yang sama dengan
Bagian A, tetapi dengan enumerasi lengkap: biaya setiap trip (≤ 3 sekolah, urutan terbaik dari ≤ 3! = 6
permutasi) disimpan di cache, lalu semua partisi himpunan sekolah menjadi ≤ 3 trip (paling banyak 280 partisi
untuk 9 sekolah) dijumlahkan sekaligus dengan NumPy. Hasilnya identik dengan UCS dan A*: diperiksa pada semua
sub-masalah Bagian A dan 300 himpunan acak berukuran 1–12, dengan selisih maksimum di bawah 10<sup>−14</sup>.
Evaluator ini butuh sekitar 50 mikrodetik per sub-masalah, ribuan kali lebih cepat daripada menjalankan A*
di setiap evaluasi, sehingga anggaran {num(budget, 0)} evaluasi per run menjadi praktis.</p>""")

    P(D.h3("2.6.2", "Delapan algoritma pencarian lokal"))
    pc = asg["algorithms"]
    P(f"""<p>Semua algoritma dimulai dari pembagian acak yang menghormati kapasitas SPPG (≤ 9 sekolah per
SPPG). Untuk seed yang sama, semua algoritma memakai pembagian awal yang sama.</p>
<ul>
<li><b>Hill Climbing (HC)</b>, versi <i>steepest-ascent</i> {C('aima')}: evaluasi semua tetangga, pindah ke
yang terbaik bila memperbaiki, berhenti bila tidak ada yang memperbaiki (optimum lokal).</li>
<li><b>HC dengan <i>sideways moves</i></b>: seperti HC, tetapi boleh pindah ke tetangga yang sama baiknya
(Δ<i>F</i> = 0) paling banyak {pc['HC-Sideways']['max_sideways']} kali berturut-turut, untuk menyeberangi
<i>plateau</i>.</li>
<li><b>Stochastic HC</b>: memilih acak di antara semua tetangga yang memperbaiki, bukan yang terbaik.</li>
<li><b>Random-Walk HC</b>: dengan peluang <i>p</i> = {num(pc['Random-Walk HC']['p_walk'], 2)} mengambil
langkah acak, selain itu langkah terbaik; di optimum lokal juga mengambil langkah acak. Ide pencampuran
langkah serakah dan acak ini berasal dari WalkSAT {C('selman')}. Nilai <i>p</i> dipilih dari
{{0,01; 0,02; 0,05; 0,1; 0,2}} dengan 5 seed terpisah (seed 100–104) yang tidak dipakai dalam evaluasi.</li>
<li><b>Random-Restart HC (RR-HC)</b>: HC diulang dari pembagian acak baru sampai anggaran habis, dan solusi
terbaik disimpan. Slide kuliah menyebut varian ini yang paling layak dipakai bila hanya boleh memilih
satu.</li>
<li><b>Enforced HC (EHC)</b> {C('hoffmann')}: dari keadaan sekarang, lakukan BFS di graf tetangga sampai
ditemukan keadaan yang <i>lebih baik</i>, lalu pindah ke sana. Di luar optimum lokal, langkah pertama yang
memperbaiki langsung diambil (<i>first improvement</i>). Di optimum lokal, BFS turun ke kedalaman 2
(kombinasi dua langkah), dengan node kedalaman 1 dibuka mulai dari yang paling menjanjikan. Bila BFS sampai
kedalaman 2 habis tanpa perbaikan, EHC berhenti.</li>
<li><b>Simulated Annealing (SA)</b> {C('kirkpatrick')}: tetangga acak (pindah atau tukar, peluang sama),
diterima bila lebih baik atau dengan peluang <i>e</i><sup>−Δ<i>F</i>/<i>T</i></sup> bila lebih buruk.
<i>T</i><sub>0</sub> diatur agar rata-rata langkah memburuk diterima dengan peluang
{num(pc['SA']['accept_prob_init'], 1)}, lalu turun geometrik hingga
{pc['SA']['final_temp_ratio']:g} × <i>T</i><sub>0</sub> di akhir anggaran.</li>
<li><b>Genetic Algorithm (GA)</b> {C('holland', 'goldberg')}: kromosom = nomor SPPG untuk tiap sekolah,
<i>fitness</i> = 1/<i>F</i>. Populasi {pc['GA']['pop_size']}, seleksi turnamen
(<i>k</i> = {pc['GA']['tournament_k']}), <i>crossover</i> uniform dengan peluang
{num(pc['GA']['p_crossover'], 1)}, mutasi mengganti SPPG setiap gen dengan peluang 1/<i>n</i>, dan
elitisme {pc['GA']['n_elite']} individu.</li>
</ul>
<pre>Hill Climbing (steepest)               Enforced Hill Climbing
x ← pembagian acak                     x ← pembagian acak
loop:                                  loop:
  y ← tetangga terbaik dari x            BFS dari x (kedalaman ≤ 2) sampai
  if F(y) ≥ F(x): return x                 ketemu y dengan F(y) &lt; F(x)
  x ← y                                  if tidak ketemu: return x
                                         x ← y</pre>""")
    b_rows = [
        ["HC", "tetangga terbaik", "tidak", "tidak (berhenti)"],
        ["HC-Sideways", "terbaik, boleh datar", "tidak", "hanya plateau"],
        ["Stochastic HC", "acak di antara yang memperbaiki", "tidak", "tidak (berhenti)"],
        ["Random-Walk HC", "terbaik / acak (p = 0,05)", "ya, langkah acak", "ya"],
        ["RR-HC", "HC dari titik acak berulang", "tidak", "ya, mulai ulang"],
        ["EHC", "BFS sampai lebih baik", "ya, di dalam BFS", "ya, lompatan 2 langkah"],
        ["SA", "tetangga acak", "ya, peluang e<sup>−Δ<i>F</i>/<i>T</i></sup>", "ya"],
        ["GA", "populasi + crossover", "ya (seleksi)", "ya"],
    ]
    t, tl = D.table(["Algoritma", "Cara melangkah", "Menerima langkah lebih buruk?", "Keluar dari optimum lokal?"],
                    b_rows, "Ringkasan algoritma Bagian B.", cls="small")
    P(f"<p>{tl} merangkum perbedaannya.</p>{t}")

    P(D.h2("2.7", "Pembanding"))
    P(f"""<p>Dua kelompok pembanding dipakai untuk menilai pendekatan dua tingkat:</p>
<ul>
<li><b>Greedy</b>: heuristik konstruktif yang setiap langkahnya menambahkan sekolah dengan biaya inkremental
terkecil, baik di ujung rute yang belum penuh maupun dengan membuka Granmax baru {C('clarke')}.</li>
<li><b>Metaheuristik terintegrasi</b> dari eksperimen awal proyek ini, yang mencari langsung di ruang rute
penuh tanpa dekomposisi: HC dan SA pada permutasi sekolah dengan pemisah Granmax, GA dengan kromosom urutan
sekolah dan decoder greedy {C('prins')}, MAX-MIN Ant System {C('dorigo', 'mmas')}, dan NSGA-II {C('nsga2')}
untuk Pareto front. Masing-masing dijalankan {exp['n_seeds']} seed dengan
{num(exp['budget_evals'], 0)} evaluasi per run.</li>
</ul>""")

    P(D.h2("2.8", "Desain Eksperimen dan Metrik"))
    n_scal = len([r for r in scal_runs if r["algorithm"] == "UCS"])
    P(f"""<ul>
<li><b>Bagian A, sub-masalah nyata:</b> himpunan sekolah setiap SPPG pada solusi terbaik Bagian B
({len(real) // len(SEARCH)} sub-masalah dari kedua instance, {min(real_k)}–{max(real_k)} sekolah per SPPG).</li>
<li><b>Bagian A, skalabilitas:</b> untuk <i>k</i> = {ks[0]}–{ks[-1]} sekolah, setiap SPPG di {scfg['scaling_instance']}
mengambil {scfg['scaling_samples']} sampel acak dari {scfg['scaling_pool']} sekolah terdekatnya
({n_scal} sub-masalah). Armada 3 Granmax; untuk <i>k</i> &gt; 9 armada dinaikkan ke ⌈<i>k</i>/3⌉ agar tetap
layak. Setiap pencarian dihentikan bila sudah membangkitkan {num(scfg['max_nodes'] / 1e6, 0)} juta node.
Metrik: optimal atau tidak, selisih biaya terhadap optimum, node diekspansi, node tersimpan maksimum (proksi
memori), dan waktu.</li>
<li><b>Bagian B:</b> {seeds} seed per algoritma per instance, masing-masing {num(budget, 0)} evaluasi
<i>F</i>. Varian HC tanpa mekanisme keluar (HC, HC-Sideways, Stochastic HC) berhenti lebih awal di optimum
lokal dan memakai lebih sedikit evaluasi. Metrik: <i>F</i> (rata-rata, simpangan baku, terbaik), tingkat
sukses (persentase run yang mencapai solusi terbaik yang pernah ditemukan semua run), jumlah evaluasi sampai
solusi terbaik run itu ditemukan, dan waktu komputasi.</li>
<li><b>Uji statistik:</b> Mann-Whitney U dua sisi {C('mann')} untuk 28 pasangan algoritma Bagian B, dengan
koreksi Holm {C('holm')}. Uji non-parametrik dipakai karena hasil metaheuristik umumnya tidak berdistribusi
normal {C('derrac')}.</li>
<li><b>Trade-off dan sensitivitas:</b> RR-HC dipilih karena direkomendasikan materi kuliah, cepat, dan (seperti
terlihat di subbab 3.3) tidak berbeda signifikan dari algoritma terbaik. RR-HC dijalankan pada 5 bobot
<i>w</i> (10 seed per bobot) dan dibandingkan dengan Pareto front NSGA-II. Algoritma yang sama dijalankan ulang dengan kapasitas 1–4
sekolah per Granmax, faktor kemacetan 1–10 kali waktu tempuh, dan konsumsi 10 atau 14 km/liter.</li>
</ul>""")

    # ================================================================== BAB 3
    P(D.bab("EKSPERIMEN DAN PEMBAHASAN"))
    P(D.h2("3.1", "Implementasi dan Lingkungan"))
    P(f"""<p class="gh">Kode lengkap: <a href="{GITHUB}">{GITHUB}</a></p>
<p>Seluruh metode diimplementasikan dari nol dalam Python 3.12 (NumPy; SciPy untuk uji statistik dan
algoritma Hungaria; Matplotlib dan Folium untuk visualisasi), tanpa pustaka optimasi siap pakai. Eksperimen
dijalankan paralel (<code>ProcessPoolExecutor</code>, 4 proses) dengan checkpoint per run, pada laptop AMD Ryzen 7
7435HS (8 core/16 thread), RAM 16 GB, Windows 11. Struktur utama repositori:</p>
<pre>src/mbgvrp/problem.py        model masalah &amp; fungsi evaluasi
src/mbgvrp/search.py         Bagian A: BFS, IDS, DFS-B&amp;B, UCS, A* (h1, h2), GBFS
src/mbgvrp/router.py         evaluator rute optimal per SPPG (dipakai Bagian B)
src/mbgvrp/local_search.py   Bagian B: 6 varian Hill Climbing, SA, GA
src/mbgvrp/algorithms.py     pembanding terintegrasi: Greedy, HC, SA, GA, ACO, NSGA-II
run_search.py                eksperimen Bagian A
run_assignment.py            eksperimen Bagian B (+ sweep bobot)
run_sensitivity.py           analisis sensitivitas
results/                     CSV, grafik, peta rute interaktif (HTML)</pre>""")

    # ---- 3.2 Bagian A
    P(D.h2("3.2", "Hasil Bagian A: Rute di Dalam Satu SPPG"))
    rows = []
    for a in SEARCH:
        r = RA[a]
        rows.append(["<b>A* (h2)</b>" if a == "A*" else a, f"{r['opt']}/{r['n']}",
                     "0" if r["gap"] < 1e-6 else pct(r["gap"]), "0" if r["gap_max"] < 1e-6 else pct(r["gap_max"]),
                     num(r["trips"], 1), num(r["exp"], 0), num(r["mem"], 0), num(r["rt"], 2) + " s"])
    t, tl = D.table(["Algoritma", "Optimal", "Selisih rata-rata", "Selisih maks.", "Granmax", "Node diekspansi (total)",
                     "Memori maks. (node)", "Waktu total"], rows,
                    f"Hasil pada {RA['UCS']['n']} sub-masalah nyata (sekolah tiap SPPG pada solusi terbaik Bagian B). "
                    "Selisih = kelebihan biaya terhadap optimum.", cls="num")
    fsc, fscl = D.figure("../results/fig_search_scaling.png",
                         f"Median node yang diekspansi (kiri) dan node tersimpan maksimum (kanan) terhadap jumlah sekolah "
                         f"<i>k</i>, skala log. Titik <i>k</i> yang tidak semua sub-masalahnya selesai sebelum batas "
                         f"{num(scfg['max_nodes'] / 1e6, 0)} juta node tidak digambar.", width="100%")
    fgap, fgapl = D.figure("../results/fig_search_gap.png",
                           "Rata-rata selisih biaya terhadap optimum untuk semua sub-masalah dengan <i>k</i> ≤ 9.",
                           width="78%")
    hit = [a for a in SEARCH if solved_all[a] < kmax]
    by_k = defaultdict(list)
    for a in hit:
        by_k[solved_all[a]].append(a)
    limit_text = ("Sebelum batas " + num(scfg["max_nodes"] / 1e6, 0) + " juta node dibangkitkan, "
                  + "; ".join(" dan ".join(v) + " hanya mampu menyelesaikan semua sub-masalah sampai <i>k</i> = "
                              + str(k) for k, v in sorted(by_k.items()))
                  + ", sedangkan " + join_id(["A* (h2)" if a == "A*" else a for a in SEARCH if a not in hit])
                  + " masih selesai sampai <i>k</i> = " + str(kmax) + ".") if hit else         "Semua algoritma masih selesai sebelum batas node."
    P(f"""<p>{tl} merangkum hasil pada sub-masalah nyata dan {fscl} memperlihatkan pertumbuhannya terhadap
jumlah sekolah. Empat temuan utama:</p>
<ol>
<li><b>Optimalitas sesuai teori.</b> UCS, kedua versi A*, dan DFS-B&amp;B menemukan rute optimal di semua
sub-masalah, dan nilainya sama persis dengan evaluator rute Bagian B. BFS dan IDS {'selalu menghasilkan rute yang sama' if bfs_eq_ids else 'sama-sama menghasilkan rute'}
(goal terdangkal) dengan rata-rata {num(RA['BFS']['trips'], 1)} Granmax, lebih sedikit daripada rute
optimal yang rata-rata memakai {num(RA['UCS']['trips'], 1)} Granmax. Lebih sedikit Granmax memang menghemat
ruas pulang, tetapi sekolah kedua dan ketiga di setiap Granmax menunggu lebih lama, sehingga biaya total
rata-rata {pct(RA['BFS']['gap'])} lebih tinggi (paling buruk {pct(RA['BFS']['gap_max'])}). Ini contoh nyata
pernyataan bahwa BFS hanya optimal bila semua langkah berbiaya sama.</li>
<li><b>Heuristik yang baik memangkas pencarian secara drastis.</b> Pada sub-masalah nyata, A* dengan h2
mengekspansi {num(ratio_ucs_astar_real, 0)} kali lebih sedikit node daripada UCS, sedangkan A* dengan h1 hanya
{num(RA['UCS']['exp'] / RA['A* (h1)']['exp'], 1)} kali lebih sedikit. Penyebabnya terlihat dari nilai
heuristik di keadaan awal: rata-rata h1 hanya {pct(h_ratio['h1'] * 100, 0)} dari biaya optimal karena
menganggap hampir semua sekolah bisa dicapai langsung dari SPPG, sedangkan h2 mencapai
{pct(h_ratio['h2'] * 100, 0)} karena memperhitungkan bahwa setiap Granmax hanya punya satu urutan pertama. {('Keunggulan ini stabil saat masalah membesar: median node UCS sekitar ' + num((ratio_k9 + ratio_kmax) / 2, 0) + ' kali median A* (h2), baik pada k = ' + str(k9) + ' maupun k = ' + str(kmax) + '.') if abs(ratio_k9 - ratio_kmax) / max(ratio_k9, ratio_kmax) < 0.2 else ('Pada k = ' + str(k9) + ' rasio median UCS terhadap A* (h2) adalah ' + num(ratio_k9, 0) + ' kali, dan pada k = ' + str(kmax) + ' menjadi ' + num(ratio_kmax, 0) + ' kali.')}
Sebaliknya, A* (h1) hampir tidak lebih hemat daripada UCS pada <i>k</i> besar.</li>
<li><b>Pencarian buta meledak lebih dulu.</b> Ruang keadaannya tumbuh eksponensial terhadap <i>k</i>.
BFS dan UCS harus menyimpan hampir seluruh keadaan yang dapat dicapai, sehingga memorinya terbesar.
IDS dan DFS-B&amp;B hanya menyimpan puluhan node, tetapi IDS mengulang tingkat-tingkat atas di setiap iterasi
dan DFS-B&amp;B hanya memangkas dengan <i>g</i>, tanpa batas bawah sisa biaya.
{limit_text}
Untuk ukuran SPPG nyata (≤ 9 sekolah) semua algoritma masih selesai dalam hitungan detik.</li>
<li><b>GBFS cepat tetapi tersesat.</b> Tanpa <i>g</i>, GBFS memilih langkah yang paling menurunkan perkiraan
biaya sisa, yaitu "menghabiskan" sekolah yang paling mahal dijangkau lebih dulu. Dalam masalah ini, itu berarti
sekolah jauh dikunjungi di awal trip, sehingga waktu tiba sekolah berikutnya memburuk. GBFS hanya mengekspansi
{num(RA['GBFS']['exp'], 0)} node untuk semua sub-masalah nyata, tetapi rata-rata {pct(RA['GBFS']['gap'])}
lebih mahal dari optimum (sampai {pct(RA['GBFS']['gap_max'])}). Pada semua sub-masalah dengan <i>k</i> ≤ 9,
rata-rata selisih GBFS {pct(float(np.nanmean(gbfs_gap_small)))} dan BFS {pct(float(np.nanmean(blind_gap_small)))}
({fgapl}).</li>
</ol>{t}{fsc}{fgap}
<p>Kesimpulan Bagian A: untuk rute satu SPPG, <b>A* dengan heuristik h2</b> adalah pilihan terbaik karena
optimal dan paling hemat node. UCS dan DFS-B&amp;B juga optimal tetapi lebih boros, sedangkan BFS, IDS, dan
GBFS tidak cocok karena mengabaikan biaya. Karena ukuran SPPG nyata kecil, evaluator rute Bagian B dapat
menghitung optimum yang sama dengan enumerasi yang lebih cepat lagi.</p>""")

    # ---- 3.3 Bagian B
    P(D.h2("3.3", "Hasil Bagian B: Pembagian Sekolah ke SPPG"))

    def ls_table(X, name):
        bk = X["ls_best"]["best_known_fitness"]
        top = best_ls(X)
        rows = []
        for a in LOCAL:
            s = X["ls"][a]
            rows.append([f"<b>{a}</b>" if a == top else a,
                         num(s["fitness_mean"], 4), num(s["fitness_std"], 4),
                         num(s["fitness_best"], 4), pct(s["success_rate"] * 100, 0),
                         num(s["n_evals_mean"], 0), num(s["evals_to_best_median"], 0),
                         num(s["runtime_s_mean"], 1) + " s"])
        return D.table(["Algoritma", "Rata-rata F", "Simp. baku", "Terbaik", "Sukses", "Evaluasi dipakai",
                        "Evaluasi s.d. terbaik*", "Waktu/run"], rows,
                       f"Hasil Bagian B di {name} (w = {num(w0, 1)}, {seeds} seed). Sukses = mencapai solusi terbaik "
                       f"yang diketahui (F = {num(bk, 4)}). *Median jumlah evaluasi sampai solusi terbaik run itu "
                       f"ditemukan.", cls="num")

    t1, t1l = ls_table(S, small)
    t2, t2l = ls_table(B, big)
    fb, fbl = D.figure(f"../results/{big}/fig_ls_boxplot.png",
                       f"Sebaran fitness akhir {seeds} seed tiap algoritma Bagian B di {big}.", width="92%")
    fc, fcl = D.figure(f"../results/{big}/fig_ls_konvergensi.png",
                       f"Konvergensi Bagian B di {big}: median fitness terbaik {seeds} seed terhadap jumlah evaluasi "
                       "(skala log). Run yang berhenti di optimum lokal diperpanjang datar.", width="92%")
    Lb, Ls = B["ls"], S["ls"]
    stuck = [a for a in ("HC", "HC-Sideways", "Stochastic HC") if Lb[a]["local_optimum_stop_rate"] > 0.5]
    escape = ["Random-Walk HC", "RR-HC", "EHC", "SA", "GA"]
    sig_pairs = [(k, v) for k, v in B["ls_tests"].items() if v["significant_5pct"] == "True"]
    p_hc_rr = ls_test(B, "HC", "RR-HC")
    p_sw = ls_test(B, "HC", "HC-Sideways")
    p_top2 = ls_test(B, rank_B[0], rank_B[1])
    same_sw = abs(Lb["HC"]["fitness_mean"] - Lb["HC-Sideways"]["fitness_mean"]) < 1e-12
    steps_hc = np.mean([r["steps"] for r in B["ls_runs"] if r["algorithm"] == "HC"])
    steps_stoch = np.mean([r["steps"] for r in B["ls_runs"] if r["algorithm"] == "Stochastic HC"])
    finals = sorted({round(r["fitness"], 9) for r in B["ls_runs"]})
    top3_ns = all(not ls_test(B, a, b)[1] for i, a in enumerate(rank_B[:3]) for b in rank_B[i + 1:3])
    second_best = finals[1] if len(finals) > 1 else finals[0]
    P(f"""<p>{t1l} dan {t2l} menyajikan hasilnya. Pada <b>{small}</b> ({S['inst'].m} SPPG, {S['inst'].n} sekolah,
10<sup>{space_S:.1f}</sup> kemungkinan pembagian) {'<b>semua delapan algoritma mencapai solusi yang sama di semua ' + str(seeds) + ' seed</b>' if perfect_S else 'hampir semua run mencapai solusi terbaik yang sama'}
(F = {num(bkS, 4)}), termasuk HC biasa yang hanya butuh sekitar {num(Ls['HC']['n_evals_mean'], 0)} evaluasi.
{'Nilai ini juga sama dengan nilai terbaik yang pernah ditemukan metaheuristik terintegrasi di eksperimen awal.' if abs(integ_best_S - bkS) < 1e-6 else ('Metaheuristik terintegrasi di eksperimen awal paling baik hanya mencapai ' + num(integ_best_S, 4) + '.')}
Karena delapan algoritma yang cara kerjanya berbeda konvergen ke titik yang sama dari 30 titik awal acak,
solusi ini kemungkinan besar optimum global instance kecil. Instance kecil tidak membedakan algoritma; yang
membedakan adalah biayanya: HC biasa paling hemat evaluasi, sedangkan SA dan GA menghabiskan seluruh anggaran.</p>
{t1}
<p>Instance <b>{big}</b> (10<sup>{space_B:.1f}</sup> kemungkinan pembagian) memperlihatkan perbedaan yang jelas
({fbl}). Urutan rata-rata fitness: {' &lt; '.join(f'{a} ({num(Lb[a]["fitness_mean"], 4)})' for a in rank_B)}.
{len(sig_pairs)} dari 28 pasangan berbeda signifikan setelah koreksi Holm. Beberapa pola yang menonjol:</p>
<ol>
<li><b>HC biasa terjebak di optimum lokal.</b> {', '.join(stuck) if stuck else 'Varian HC tanpa mekanisme keluar'}
berhenti di optimum lokal di {'semua' if min(Lb[a]['local_optimum_stop_rate'] for a in stuck) == 1 else 'sebagian besar'} run
setelah rata-rata {num(Lb['HC']['n_evals_mean'], 0)} (HC) dan {num(Lb['Stochastic HC']['n_evals_mean'], 0)}
(Stochastic HC) evaluasi, jauh sebelum anggaran habis. HC hanya mencapai solusi terbaik di
{pct(Lb['HC']['success_rate'] * 100, 0)} run, dengan rata-rata {pct(Lb['HC']['gap_mean_pct'], 2)} di atas solusi
terbaik dan simpangan baku terbesar ({num(Lb['HC']['fitness_std'], 4)}). Stochastic HC lebih baik
(sukses {pct(Lb['Stochastic HC']['success_rate'] * 100, 0)}, p<sub>Holm</sub> = {pval(ls_test(B, 'HC', 'Stochastic HC')[0])}):
karena tidak selalu mengambil langkah tercuram, ia menempuh jalur yang lebih panjang
(rata-rata {num(steps_stoch / max(steps_hc, 1), 1)} kali lebih banyak langkah daripada HC) dan
lebih sering berakhir di optimum lokal yang baik.</li>
<li><b><i>Sideways moves</i> tidak berpengaruh.</b> HC-Sideways {'memberi hasil yang identik' if same_sw else 'hampir sama'}
dengan HC (p<sub>Holm</sub> = {pval(p_sw[0])}). Fitness di sini adalah bilangan real dari jarak dan waktu jalan
asli, sehingga dua tetangga hampir tidak pernah bernilai persis sama: lanskapnya tidak punya <i>plateau</i>.
Mekanisme ini berguna untuk masalah dengan fitness diskret (misalnya 8-queens), bukan untuk masalah ini.</li>
<li><b>Mekanisme keluar dari optimum lokal adalah kuncinya.</b> Rata-rata kelima algoritma yang punya mekanisme
keluar (Random-Walk HC, RR-HC, EHC, SA, GA) berada {pct(max(Lb[a]['gap_mean_pct'] for a in escape), 2)} atau kurang
di atas solusi terbaik, dengan simpangan baku paling besar {num(max(Lb[a]['fitness_std'] for a in escape), 4)},
dan {'semuanya' if all(ls_test(B, 'HC', a)[1] for a in escape) else 'sebagian besar'} signifikan lebih baik
daripada HC biasa. Yang terbaik adalah {', '.join(rank_B[:3])}
(sukses {', '.join(pct(Lb[a]['success_rate'] * 100, 0) for a in rank_B[:3])}); ketiganya
{'tidak berbeda signifikan satu sama lain' if top3_ns else 'sebagian berbeda signifikan'}. RR-HC, yang direkomendasikan slide kuliah, signifikan lebih baik daripada HC
biasa (p<sub>Holm</sub> = {pval(p_hc_rr[0])}). Banyak run yang "gagal" sebenarnya berhenti di optimum lokal
kedua terbaik yang hanya {pct((second_best - bkB) / bkB * 100, 3)} lebih buruk.</li>
<li><b>Efisiensi berbeda jauh.</b> EHC menemukan solusi terbaiknya setelah median
{num(Lb['EHC']['evals_to_best_median'], 0)} evaluasi, karena di luar optimum lokal ia langsung mengambil langkah
pertama yang memperbaiki dan baru memakai BFS dua langkah saat terjebak. SA membutuhkan median
{num(Lb['SA']['evals_to_best_median'], 0)} evaluasi karena sengaja menjelajah pada suhu tinggi, dan per run
paling lambat ({num(Lb['SA']['runtime_s_mean'], 0)} s) karena setiap langkah acaknya menghasilkan himpunan sekolah
baru yang rutenya belum pernah dihitung. GA menemukan solusi terbaiknya setelah median
{num(Lb['GA']['evals_to_best_median'], 0)} evaluasi.</li>
<li>Selisih dua algoritma teratas, {rank_B[0]} dan {rank_B[1]},
{'signifikan' if p_top2[1] else 'tidak signifikan'} (p<sub>Holm</sub> = {pval(p_top2[0])}).</li>
</ol>{t2}{fb}
<p>{fcl} memperlihatkan dinamika pencariannya. Varian HC turun paling cepat di awal karena setiap langkahnya
adalah langkah terbaik dari ratusan tetangga, lalu mendatar ketika terjebak. EHC turun hampir secepat HC dan
terus membaik. SA bertahan pada fitness tinggi selama suhu masih tinggi, lalu turun tajam di paruh kedua
anggaran. GA bergerak lebih lambat di awal karena setiap individu baru dievaluasi penuh.</p>{fc}""")

    # ---- 3.4 Komparasi menyeluruh
    P(D.h2("3.4", "Komparasi Menyeluruh"))
    fk, fkl = D.figure("../results/fig_komparasi.png",
                       "Selisih fitness rata-rata terhadap solusi terbaik yang diketahui untuk Greedy, metaheuristik "
                       "terintegrasi (eksperimen awal), dan pendekatan dua tingkat.", width="100%")
    rows = []
    for a in ["Greedy"] + INTEG:
        s = B["integ"][a]
        rows.append(["Greedy (baseline)" if a == "Greedy" else f"{a} terintegrasi",
                     num(s["fitness_mean"], 4), num(s["fitness_best"], 4),
                     pct((s["fitness_mean"] - bkB) / bkB * 100, 2), rp(s["cost_rp_mean"]),
                     num(s["runtime_s_mean"], 1) + " s"])
    for a in [topB, "RR-HC"] if topB != "RR-HC" else [topB]:
        s = B["ls"][a]
        rows.append([f"<b>{a} + rute optimal</b>", num(s["fitness_mean"], 4), num(s["fitness_best"], 4),
                     pct(s["gap_mean_pct"], 2), rp(s["cost_rp_mean"]), num(s["runtime_s_mean"], 1) + " s"])
    t, tl = D.table(["Metode", "Fitness rata-rata", "Terbaik", "Selisih thd terbaik diketahui", "Biaya bensin rata-rata",
                     "Waktu/run"], rows, f"Pendekatan dua tingkat vs pembanding di {big} (w = {num(w0, 1)}).", cls="num")
    P(f"""<p>{fkl} dan {tl} membandingkan pendekatan dua tingkat dengan pembanding. Metaheuristik
terintegrasi terbaik di eksperimen awal adalah {integ_best_B} dengan rata-rata {num(ib['fitness_mean'], 4)},
atau {pct((ib['fitness_mean'] - bkB) / bkB * 100, 2)} di atas solusi terbaik yang diketahui, dan nilai
terbaiknya ({num(ib['fitness_best'], 4)}) tidak pernah mencapai solusi itu. Sebaliknya,
{len(better_than_integ)} dari 8 algoritma dua tingkat memiliki rata-rata lebih baik daripada {integ_best_B},
termasuk {', '.join(a for a in better_than_integ if a in ('HC', 'Stochastic HC', 'HC-Sideways')) or 'varian HC sederhana'}.
Algoritma yang sama (HC, SA, GA) jauh lebih kuat di ruang pembagian daripada di ruang rute penuh. Ada tiga
alasan. Pertama, ruang pembagian (10<sup>{space_B:.0f}</sup>) jauh lebih kecil daripada ruang permutasi rute.
Kedua, setiap titik di ruang pembagian langsung dinilai dengan rute <i>terbaiknya</i>, sehingga pencarian
lokal tidak perlu sekaligus "belajar" mengurutkan sekolah. Ketiga, langkah pindah dan tukar selalu menghasilkan
solusi yang masuk akal. Temuan ini sejalan dengan pengalaman dalam literatur VRP bahwa representasi dan
pemanfaatan struktur masalah sering lebih menentukan daripada pilihan metaheuristiknya {C('prins', 'talbi')}.</p>{fk}{t}""")

    # ---- 3.5 Trade-off
    P(D.h2("3.5", "Trade-off Biaya Bensin dan Waktu Tiba"))
    sweep = B["sweep"]
    fr = B["front"]
    c_min, c_max = min(r["cost_rp"] for r in fr), max(r["cost_rp"] for r in fr)
    t_min, t_max = min(r["mean_arrival_min"] for r in fr), max(r["mean_arrival_min"] for r in fr)
    if sweep:
        sweep_algo = sweep[0]["algorithm"]
        pts = {}
        for r in sweep:
            if r["w"] not in pts or r["fitness"] < pts[r["w"]]["fitness"]:
                pts[r["w"]] = r
        fp, fpl = D.figure(f"../results/{big}/fig_ls_pareto.png",
                           f"Solusi {sweep_algo} + rute optimal untuk lima bobot <i>w</i> dibandingkan dengan Pareto "
                           f"front NSGA-II terintegrasi di {big}.", width="88%")
        dom = 0
        for w_, r in pts.items():
            if any(f["cost_rp"] <= r["cost_rp"] and f["mean_arrival_min"] <= r["mean_arrival_min"]
                   and (f["cost_rp"] < r["cost_rp"] or f["mean_arrival_min"] < r["mean_arrival_min"]) for f in fr):
                dom += 1
        notes = []
        if 0.25 in pts and pts[0.25]["mean_arrival_min"] <= pts[0.0]["mean_arrival_min"] + 0.05                 and pts[0.25]["cost_rp"] < pts[0.0]["cost_rp"]:
            notes.append(f"Bobot ekstrem mengabaikan salah satu objektif sepenuhnya: solusi <i>w</i> = 0,25 hampir "
                         f"sama cepatnya dengan <i>w</i> = 0 tetapi {rp(pts[0.0]['cost_rp'] - pts[0.25]['cost_rp'])} "
                         f"lebih murah.")
        if c_min - pts[1.0]["cost_rp"] < 200 and t_max < pts[1.0]["mean_arrival_min"] - 0.5:
            notes.append(f"Hal yang sama terjadi di ujung lain: titik termurah NSGA-II ({rp(c_min)}) hanya "
                         f"{rp(c_min - pts[1.0]['cost_rp'])} lebih mahal daripada solusi <i>w</i> = 1, tetapi "
                         f"makanan tiba {num(pts[1.0]['mean_arrival_min'] - t_max, 1)} menit lebih cepat.")
        extreme_note = (" ".join(notes) + " ") if notes else ""
        srows = [[num(w_, 2), rp(r["cost_rp"]), num(r["mean_arrival_min"], 1) + " mnt",
                  num(r["makespan_min"], 1) + " mnt", str(int(r["n_vehicles"]))] for w_, r in sorted(pts.items())]
        t, tl = D.table(["Bobot w", "Biaya bensin", "Rata-rata tiba", "Tiba terakhir", "Granmax"], srows,
                        f"Solusi terbaik {sweep_algo} + rute optimal per bobot di {big} "
                        f"(w = 1: murni bensin, w = 0: murni waktu).", cls="num")
        P(f"""<p>Bobot <i>w</i> mengatur prioritas antara bensin dan waktu. {tl} dan {fpl} menunjukkan solusi
{sweep_algo} untuk lima bobot. Solusi termurah (<i>w</i> = 1) menghabiskan {rp(pts[1.0]['cost_rp'])} dengan
rata-rata tiba {num(pts[1.0]['mean_arrival_min'], 1)} menit, sedangkan solusi tercepat (<i>w</i> = 0)
{num(pts[0.0]['mean_arrival_min'], 1)} menit dengan biaya {rp(pts[0.0]['cost_rp'])}. Pareto front NSGA-II
terintegrasi dari eksperimen awal berisi {len(fr)} solusi dari {rp(c_min)} ({num(t_max, 1)} menit) sampai
{rp(c_max)} ({num(t_min, 1)} menit). {'Tidak ada' if dom == 0 else str(dom)} dari {len(pts)} solusi dua tingkat
yang didominasi oleh front NSGA-II{', artinya setiap titik dua tingkat berada di atau di luar front tersebut' if dom == 0 else ''}.
{extreme_note}NSGA-II tetap berguna untuk menyajikan banyak pilihan sekaligus, sedangkan pendekatan dua tingkat
dengan bobot tertentu menghasilkan titik yang lebih baik untuk bobot itu.</p>{t}{fp}""")
    else:
        P("<p>(Jalankan <code>python run_assignment.py --sweep RR-HC --seeds 10</code> untuk bagian ini.)</p>")

    # ---- 3.6 Rute terbaik
    P(D.h2("3.6", "Rute Terbaik dan Interpretasi Praktis"))
    from figures import fig_rute
    route_png = REPORT / "figs" / f"fig_rute_{big}_terbaik.png"
    fig_rute(config, big, topB, REPORT / "figs" / f"fig_cover_{big}.png", title=False, source="ls_best.json")
    fig_rute(config, big, topB, route_png, source="ls_best.json",
             title=f"{topB} + rute optimal: {rp(solB['cost_rp'])} · {num(solB['km'], 1)} km · rata-rata tiba "
                   f"{num(solB['mean_arrival_min'], 1)} mnt · {solB['n_vehicles']} Granmax")
    fr_, frl = D.figure(f"figs/{route_png.name}",
                        f"Rute terbaik di {big} (w = {num(w0, 1)}). Warna = SPPG asal; angka = urutan kunjungan. "
                        f"Rute mengikuti jalan asli (OSRM).", width="80%")
    lens = defaultdict(int)
    for _, seq in solB["routes"]:
        lens[len(seq)] += 1
    mix = [f"{lens[k]} mengantar ke {k} sekolah" for k in sorted(lens) if lens[k]]
    route_mix = ", ".join(mix[:-1]) + (", dan " if len(mix) > 2 else " dan ") + mix[-1] if len(mix) > 1 else mix[0]
    per_sppg = defaultdict(int)
    for d, seq in solB["routes"]:
        per_sppg[d] += len(seq)
    P(f"""<p>{frl} menampilkan solusi terbaik di {big}: {solB['n_vehicles']} Granmax menempuh total
{num(solB['km'], 1)} km dengan biaya bensin {rp(solB['cost_rp'])} per hari, rata-rata makanan tiba
{num(solB['mean_arrival_min'], 1)} menit setelah berangkat, dan sekolah terakhir menerima makanan pada menit
ke-{num(solB['makespan_min'], 1)}. Solusi Greedy pada bobot yang sama menempuh {num(gB['km'], 1)} km
({rp(gB['cost_rp'])}). Selisihnya {rp(gB['cost_rp'] - solB['cost_rp'])} per hari untuk enam SPPG; dengan asumsi
sekitar 200 hari sekolah per tahun, angka ini setara ±{rp((gB['cost_rp'] - solB['cost_rp']) * 200)} per tahun
hanya untuk {IB.n} sekolah pada instance ini.</p>
<p>Dari {len(solB['routes'])} Granmax yang dipakai, {route_mix}. Jumlah sekolah per SPPG bervariasi dari
{min(per_sppg.values())} sampai {max(per_sppg.values())}: pembagian terbaik tidak sekadar membagi rata atau
memilih SPPG terdekat, tetapi menyeimbangkan jarak dengan jumlah Granmax yang tersedia. Rute penuh 3 sekolah
hanya dipilih bila sekolah-sekolahnya berdekatan, karena sekolah ketiga harus menunggu tambahan 2 × 15 menit
bongkar ditambah waktu tempuh. Rute lengkap per Granmax, nama sekolah, dan jam tibanya tersedia di
<code>results/{big}/ls_best_routes.txt</code> dan peta interaktif <code>peta_rute_terbaik.html</code>.</p>{fr_}""")

    # ---- 3.7 Sensitivitas
    P(D.h2("3.7", "Analisis Sensitivitas"))
    sens = B["sens"]
    if sens:
        best_sens = {}
        for r in sens:
            key = (r["scenario"], float(r["value"]))
            if key not in best_sens or r["fitness"] < best_sens[key]["fitness"]:
                best_sens[key] = r

        def sv(sc_, v, k):
            return float(best_sens[(sc_, float(v))][k])

        sens_algo = sens[0].get("algorithm", "")
        fs1, fs1l = D.figure(f"../results/{big}/fig_sens_kapasitas_biaya.png",
                             "Pengaruh kapasitas maksimum sekolah per Granmax terhadap biaya bensin.", width="60%")
        fs2, fs2l = D.figure(f"../results/{big}/fig_sens_macet.png",
                             "Pengaruh faktor kemacetan terhadap waktu tiba; garis merah = batas 180 menit.", width="60%")
        traffic_vals = sorted({float(r["value"]) for r in sens if r["scenario"] == "macet"})
        f120 = next((v for v in traffic_vals if sv("macet", v, "makespan_min") > 120), None)
        off = ~np.eye(IB.D.shape[0], dtype=bool)
        speed = IB.D[off].sum() / IB.T[off].sum() * 60  # km/jam rata-rata OSRM (lancar)
        q4_same = abs(sv("kapasitas", 4, "cost_rp") - sv("kapasitas", 3, "cost_rp")) < 1
        P(f"""<p>Analisis sensitivitas memakai {sens_algo} + rute optimal (5 seed per skenario).
<b>Kapasitas per Granmax</b> ({fs1l}). Bila setiap Granmax hanya boleh ke 1 sekolah, biaya naik menjadi
{rp(sv('kapasitas', 1, 'cost_rp'))} dengan {int(sv('kapasitas', 1, 'n_vehicles'))} Granmax, atau
{pct((sv('kapasitas', 1, 'cost_rp') / sv('kapasitas', 3, 'cost_rp') - 1) * 100, 0)} lebih mahal daripada
kapasitas 3 ({rp(sv('kapasitas', 3, 'cost_rp'))}). {'Menaikkan kapasitas dari 3 ke 4 tidak mengubah biaya pada bobot seimbang, karena rute 4 sekolah terlalu merugikan waktu tiba.' if q4_same else f"Kapasitas 4 memberi biaya {rp(sv('kapasitas', 4, 'cost_rp'))}."}</p>
<p><b>Kemacetan dan batas 3 jam</b> ({fs2l}). Dengan waktu tempuh lancar, sekolah terakhir menerima makanan
pada menit ke-{num(sv('macet', 1, 'makespan_min'), 0)}, jauh di bawah 180 menit. Bahkan saat waktu tempuh
dikalikan {num(traffic_vals[-1], 0)}, yang setara kecepatan rata-rata hanya ±{num(speed / traffic_vals[-1], 0)} km/jam,
waktu tiba terakhir {num(sv('macet', traffic_vals[-1], 'makespan_min'), 0)} menit
{'masih memenuhi batas' if sv('macet', traffic_vals[-1], 'makespan_min') <= 180 else 'melampaui batas'}.
Jadi, untuk sebaran SPPG-sekolah seperti ini, batas 3 jam bukan constraint yang aktif. Bila standar keamanan
pangan diperketat (misalnya 2 jam sesuai anjuran WHO {C('who')}), batas tersebut mulai terlampaui pada faktor
kemacetan sekitar {num(f120, 0) if f120 else 'di atas ' + num(traffic_vals[-1], 0)}
(kecepatan ±{num(speed / f120, 0) if f120 else '-'} km/jam).</p>
<p><b>Efisiensi bensin.</b> Konsumsi 10 km/liter (batas bawah rentang Granmax) menaikkan biaya menjadi
{rp(sv('km_per_liter', 10, 'cost_rp'))} (+{pct((sv('km_per_liter', 10, 'cost_rp') / sv('km_per_liter', 14, 'cost_rp') - 1) * 100, 0)}).
Rutenya praktis sama, karena biaya per km hanya mengubah skala objektif pertama.</p>{fs1}{fs2}""")
    else:
        P("<p>(Jalankan <code>python run_sensitivity.py</code> untuk bagian ini.)</p>")

    P(D.h2("3.8", "Keterbatasan"))
    P("""<ul>
<li>Optimalitas global Bagian B tidak dibuktikan (tidak memakai solver MILP); kualitas dinilai terhadap solusi
terbaik yang ditemukan semua run. Optimalitas Bagian A (rute per SPPG) terjamin.</li>
<li>Koordinat SPPG adalah perkiraan; jumlah porsi per sekolah dan kapasitas muatan riil Granmax belum dimodelkan.</li>
<li>Waktu tempuh OSRM adalah kondisi lancar; kemacetan hanya dimodelkan sebagai faktor pengali seragam.</li>
<li>Pencarian sistematis Bagian A layak karena satu SPPG paling banyak 9 sekolah. Untuk SPPG yang melayani
puluhan sekolah per Granmax, perlu heuristik yang lebih kuat atau pencarian lokal juga di tingkat rute.</li>
<li>Parameter algoritma memakai nilai umum dari literatur; hanya peluang langkah acak Random-Walk HC yang disetel
(dengan seed terpisah).</li>
</ul>""")

    # ================================================================== BAB 4
    P(D.bab("KESIMPULAN"))
    P(D.h2("4.1", "Kesimpulan"))
    P(f"""<ol>
<li>Distribusi MBG dari SPPG ke sekolah dapat dimodelkan sebagai MDVRP bi-objektif dengan data jalan asli
Surabaya, lalu dipecah secara eksak menjadi dua tingkat: pembagian sekolah ke SPPG dan rute di dalam
setiap SPPG.</li>
<li><b>Bagian A (algoritma pencarian).</b> UCS, A*, dan DFS-B&amp;B selalu optimal; BFS dan IDS hanya
meminimalkan jumlah Granmax sehingga rata-rata {pct(RA['BFS']['gap'])} lebih mahal; GBFS paling cepat tetapi
rata-rata {pct(RA['GBFS']['gap'])} lebih mahal karena mengabaikan biaya jalur. A* dengan heuristik admissible
h2 (relaksasi penugasan slot) mengekspansi {num(ratio_ucs_astar_real, 0)} kali lebih sedikit node daripada UCS
dan {num(ratio_h1_h2_real, 0)} kali lebih sedikit daripada A* dengan heuristik sederhana. Kualitas heuristik
lebih menentukan daripada pilihan algoritmanya.</li>
<li><b>Bagian B (pencarian lokal).</b> Pada instance kecil semua algoritma mencapai solusi yang sama. Pada
instance besar, HC biasa, HC-Sideways, dan Stochastic HC sering terjebak di optimum lokal; <i>sideways moves</i>
tidak membantu karena lanskapnya tidak punya plateau. Algoritma dengan mekanisme keluar dari optimum lokal
jauh lebih andal, dan {topB} memberi rata-rata terbaik. RR-HC, yang direkomendasikan materi kuliah, mencapai
solusi terbaik di {pct(Lb['RR-HC']['success_rate'] * 100, 0)} run, sedangkan EHC paling hemat evaluasi.</li>
<li>Pendekatan dua tingkat lebih baik daripada metaheuristik terintegrasi terbaik ({integ_best_B}) dan
menurunkan biaya bensin {pct(sav_B)} dibanding Greedy ({rp(gB['cost_rp'] - solB['cost_rp'])} per hari untuk
{IB.n} sekolah). Algoritma yang sama bekerja jauh lebih baik ketika ruang pencariannya dirancang sesuai struktur
masalah.</li>
<li>Batas 3 jam tidak aktif pada kondisi Surabaya yang dimodelkan. Faktor yang paling memengaruhi biaya
adalah jumlah sekolah per Granmax dan efisiensi bensin kendaraan.</li>
</ol>""")
    P(D.h2("4.2", "Saran"))
    P("""<ul>
<li>Menambahkan jumlah porsi per sekolah dan kapasitas muatan Granmax (Capacitated MDVRP), serta
<i>time window</i> jam istirahat setiap sekolah.</li>
<li>Memakai waktu tempuh historis per jam (misalnya dari data lalu lintas) sebagai pengganti faktor
kemacetan seragam.</li>
<li>Untuk SPPG yang jauh lebih besar, mengganti pencarian sistematis Bagian A dengan A* berbobot, beam search,
atau pencarian lokal 2-opt, dan memakai batas bawah yang lebih kuat agar optimalitas Bagian B dapat dibuktikan
dengan branch and bound.</li>
<li>Memvalidasi koordinat SPPG dan daftar sekolah penerima dengan data resmi BGN/Dinas Pendidikan.</li>
</ul>""")

    # ================================================================== DAFTAR PUSTAKA
    P(D.unnumbered("pustaka", "DAFTAR PUSTAKA"))
    P('<ol class="refs">' + "".join(f"<li>{REFS[k]}</li>" for k in C.order) + "</ol>")

    # ------------------------------------------------------------------ daftar isi
    toc = []
    for level, hid, text in D.toc:
        if hid == "toc":
            continue
        page = toc_pages.get(hid, "") if toc_pages else ""
        toc.append(f'<div class="toc-l{level}"><a href="#{hid}">{esc(text)}</a>'
                   f'<span class="dots"></span><span class="pg">{page}</span></div>')
    parts[toc_placeholder_index] = "".join(toc)

    body = "\n".join(parts)
    css = (REPORT / "report.css").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>Optimasi Rute Distribusi MBG Surabaya</title>
<style>{css}</style></head>
<body>{body}</body></html>""", D.toc


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
    from figures import fig_wilayah
    from html_to_docx import html_to_docx
    if not (REPORT / "figs" / "fig_wilayah.png").exists():
        fig_wilayah(config, REPORT / "figs" / "fig_wilayah.png")
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
