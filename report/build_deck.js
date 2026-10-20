// Presentation deck (PPTX, ±15 menit) untuk proyek ETS MBG-VRP.
//   cd report && npm install && node build_deck.js
// Membaca angka langsung dari ../results (CSV/JSON) dan gambar dari ../results + ./figs
// (jalankan python report/build_report.py dulu agar figs/fig_rute_*.png ada).
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const ROOT = path.resolve(__dirname, "..");
const RES = path.join(ROOT, "results");
const OUT = path.join(__dirname, "Presentasi_MBG_VRP.pptx");
const CONFIG = JSON.parse(fs.readFileSync(path.join(ROOT, "config.json"), "utf8"));
const GITHUB = "github.com/Mitschess/kka-2026";
const TEAM = "[Nama Anggota 1] · [Nama Anggota 2] · [Nama Anggota 3]";

// ------------------------------------------------------------------ tema
const THEME = {
  name: "MBG Surabaya",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B1B1B", lt1: "FFFFFF", dk2: "16382C", lt2: "EEF4F0",
    accent1: "1F5C46", accent2: "E07A2E", accent3: "2A78D6", accent4: "1BAF7A",
    accent5: "E87BA4", accent6: "4A3AA7", hlink: "1F5C46", folHlink: "4A3AA7",
  },
};
const T = THEME.colors;
const MUTED = "5E6B65";
// palet kategorikal 8 slot (sama dengan grafik matplotlib di src/mbgvrp/viz.py)
const PAL8 = ["2A78D6", "EB6834", "1BAF7A", "EDA100", "E87BA4", "008300", "6250D6", "E34948"];
const SEARCH = ["BFS", "IDS", "DFS-B&B", "UCS", "A* (h1)", "A*", "GBFS"];
const LOCAL = ["HC", "HC-Sideways", "Stochastic HC", "Random-Walk HC", "RR-HC", "EHC", "SA", "GA"];
const LS_COLOR = Object.fromEntries(LOCAL.map((a, i) => [a, PAL8[i]]));
const SEARCH_COLOR = Object.fromEntries(SEARCH.map((a, i) => [a, PAL8[i]]));

// ------------------------------------------------------------------ data
function readCsv(p) {
  const [head, ...lines] = fs.readFileSync(p, "utf8").trim().split(/\r?\n/);
  const keys = head.split(",");
  return lines.map((l) => Object.fromEntries(l.split(",").map((v, i) => [keys[i], v])));
}
const names = Object.keys(CONFIG.instances);
const SMALL = names[0], BIG = names[names.length - 1];
const ls = {}, lsBest = {}, lsTests = {}, integ = {}, front = {};
for (const n of names) {
  ls[n] = Object.fromEntries(readCsv(path.join(RES, n, "ls_summary.csv")).map((r) => [r.algorithm, r]));
  lsBest[n] = JSON.parse(fs.readFileSync(path.join(RES, n, "ls_best.json"), "utf8"));
  lsTests[n] = Object.fromEntries(readCsv(path.join(RES, n, "ls_stat_tests.csv")).map((r) => [r.pair, r]));
  integ[n] = Object.fromEntries(readCsv(path.join(RES, n, "summary_main_w.csv")).map((r) => [r.algorithm, r]));
  front[n] = readCsv(path.join(RES, n, "nsga2_front.csv")).map((r) => ({ c: +r.cost_rp, t: +r.mean_arrival_min }));
}
const real = readCsv(path.join(RES, "search_real.csv"));
const scal = readCsv(path.join(RES, "search_summary.csv"));
const sweepFile = path.join(RES, BIG, "ls_sweep.csv");
const sweep = fs.existsSync(sweepFile) ? readCsv(sweepFile) : [];
const sens = readCsv(path.join(RES, BIG, "sensitivity.csv"));

const fmt = (x, d = 0) => Number(x).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });
const rp = (x) => "Rp" + fmt(x);
const SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹";
const pstr = (p) => {
  if (p >= 0.001) return fmt(p, 3);
  const [m, e] = Number(p).toExponential(0).split("e-");
  return `${m}×10⁻${[...e].map((c) => SUP[+c]).join("")}`;
};
const sup = (n) => [...String(n)].map((c) => SUP[+c]).join("");
const lsTest = (n, a, b) => lsTests[n][`${a} vs ${b}`] || lsTests[n][`${b} vs ${a}`];
const agg = (a) => {
  const rs = real.filter((r) => r.algorithm === a);
  const gaps = rs.map((r) => +r.gap_pct);
  return {
    n: rs.length, opt: rs.filter((r) => r.optimal === "True").length,
    gap: gaps.reduce((x, y) => x + y, 0) / rs.length, exp: rs.reduce((x, r) => x + +r.expanded, 0),
    mem: Math.max(...rs.map((r) => +r.max_stored)),
  };
};
const RA = Object.fromEntries(SEARCH.map((a) => [a, agg(a)]));
const KS = [...new Set(scal.map((r) => +r.k))].sort((a, b) => a - b);
const scv = (k, a, key) => +scal.find((r) => +r.k === k && r.algorithm === a)[key];
const solvedUpTo = (a) => Math.max(0, ...KS.filter((k) => scv(k, a, "solved_rate") === 1));
const rankLS = (n) => [...LOCAL].sort((a, b) => +ls[n][a].fitness_mean - +ls[n][b].fitness_mean || +ls[n][b].success_rate - +ls[n][a].success_rate);
const bestSens = {};
for (const r of sens) {
  const k = `${r.scenario}|${+r.value}`;
  if (!bestSens[k] || +r.fitness < +bestSens[k].fitness) bestSens[k] = r;
}
const sv = (sc, v, key) => +bestSens[`${sc}|${v}`][key];
const readMatrix = (f) => fs.readFileSync(path.join(ROOT, "data", "instances", BIG, f), "utf8").trim().split(/\r?\n/).map((l) => l.split(",").map(Number));
const Dm = readMatrix("dist_km.csv"), Tm = readMatrix("time_min.csv");
let sumD = 0, sumT = 0;
Dm.forEach((row, i) => row.forEach((d, j) => { if (i !== j) { sumD += d; sumT += Tm[i][j]; } }));
const SPEED = (sumD / sumT) * 60; // km/jam rata-rata kondisi lancar
const TF = [...new Set(sens.filter((r) => r.scenario === "macet").map((r) => +r.value))].sort((a, b) => a - b);
const F120 = TF.find((v) => sv("macet", v, "makespan_min") > 120);

function pngSize(p) {
  const b = fs.readFileSync(p);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
async function icon(Comp, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

// ------------------------------------------------------------------ deck
async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
  pres.title = "Optimasi Rute Distribusi MBG di Surabaya";
  pres.subject = "Final Project Konsep Kecerdasan Artifisial";
  pres.author = "Tim ETS KKA";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;
  const W = 13.333, M = 0.6;

  pres.defineSlideMaster({
    title: "DARK",
    background: { color: T.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 1.85, w: 6.9, h: 2.3, fontSize: 38, bold: true,
          color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: T.lt1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: W - 2 * M, h: 0.9, fontSize: 32,
          bold: true, color: C.text2, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "Rute MBG Surabaya · ETS Konsep Kecerdasan Artifisial",
          options: { x: M, y: 7.02, w: 7, h: 0.3, fontSize: 10, color: MUTED, margin: 0 } } },
    ],
    slideNumber: { x: W - M - 0.6, y: 7.02, w: 0.6, h: 0.3, fontSize: 10, color: MUTED, align: "right" },
  });

  const section = (t) => pres.addSection({ title: t });
  const content = (sec, title) => {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: sec });
    s.addText(title, { placeholder: "title" });
    return s;
  };
  const txt = (s, text, o) => s.addText(text, { isTextBox: true, margin: 0, fontSize: 16, color: C.text1, valign: "top", ...o });
  const card = (s, x, y, w, h, fill = T.lt2) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: fill } });
  const circleIcon = async (s, Comp, x, y, d, bg, fg = "FFFFFF") => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } });
    s.addImage({ data: await icon(Comp, fg), x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52 });
  };
  const image = (s, file, x, y, maxW, maxH) => {
    const { w, h } = pngSize(file);
    const k = Math.min(maxW / w, maxH / h);
    const iw = w * k, ih = h * k;
    s.addImage({ path: file, x: x + (maxW - iw) / 2, y: y + (maxH - ih) / 2, w: iw, h: ih });
  };
  const bullets = (s, items, o) =>
    txt(s, items.map((t, i) => ({ text: t, options: { bullet: { indent: 18 }, breakLine: i < items.length - 1, paraSpaceAfter: 8 } })), o);
  const chartBase = {
    catAxisLabelColor: MUTED, valAxisLabelColor: MUTED, catAxisLabelFontSize: 12, valAxisLabelFontSize: 11,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt",
    legendFontFace: "+mn-lt", titleFontFace: "+mn-lt",
    valGridLine: { color: "E2E6E3", size: 0.75 }, catGridLine: { style: "none" },
    catAxisLineShow: false, valAxisLineShow: false, legendFontSize: 12, legendColor: MUTED,
    dataLabelColor: "3A3A3A", dataLabelFontSize: 11, titleColor: "1B1B1B", titleFontSize: 14,
  };
  const statCard = (s, x, y, w, h, value, label, valueSize = 26) => {
    card(s, x, y, w, h);
    txt(s, value, { x: x + 0.2, y: y + 0.15, w: w - 0.4, h: 0.65, fontSize: valueSize, bold: true, color: C.accent1, fontFace: "Cambria" });
    txt(s, label, { x: x + 0.2, y: y + 0.82, w: w - 0.4, h: h - 0.95, fontSize: 13, color: MUTED });
  };

  const LB = ls[BIG], LS_ = ls[SMALL];
  const rB = rankLS(BIG);
  const top = rB[0];
  const top3ns = [[0, 1], [0, 2], [1, 2]].every(([i, j]) => lsTest(BIG, rB[i], rB[j]).significant_5pct !== "True");
  const bkB = lsBest[BIG].best_known_fitness;
  const sol = lsBest[BIG][top], g = lsBest[BIG].Greedy;
  const savePct = ((g.cost_rp - sol.cost_rp) / g.cost_rp) * 100;
  const integBest = ["HC", "SA", "GA", "ACO"].sort((a, b) => +integ[BIG][a].fitness_mean - +integ[BIG][b].fitness_mean)[0];
  const ib = integ[BIG][integBest];
  const nBetter = LOCAL.filter((a) => +LB[a].fitness_mean < +ib.fitness_mean).length;
  const ratioUA = RA.UCS.exp / RA["A*"].exp;
  const spaceB = CONFIG.instances[BIG].n_schools * Math.log10(CONFIG.instances[BIG].sppg_ids.length);
  const routePng = path.join(__dirname, "figs", `fig_rute_${BIG}_terbaik.png`);
  const coverPng = path.join(__dirname, "figs", `fig_cover_${BIG}.png`);

  // ============================================================ 1. judul
  section("Pembuka");
  {
    const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Pembuka" });
    s.addImage({ path: coverPng, x: 7.9, y: 0, w: W - 7.9, h: 7.5, sizing: { type: "cover", w: W - 7.9, h: 7.5 } });
    txt(s, "FINAL PROJECT · KONSEP KECERDASAN ARTIFISIAL", { x: M, y: 1.2, w: 7, h: 0.4, fontSize: 13, bold: true,
      color: "9FD3B9", charSpacing: 2 });
    s.addText("Optimasi Rute Distribusi Makan Bergizi Gratis di Surabaya", { placeholder: "title" });
    txt(s, "Algoritma pencarian (BFS, IDS, DFS-B&B, UCS, A*, Greedy Best-First) + pencarian lokal (6 varian Hill Climbing, SA, GA)",
      { x: M, y: 4.35, w: 7, h: 0.9, fontSize: 17, color: "D7E7DF" });
    txt(s, TEAM, { x: M, y: 5.9, w: 7, h: 0.4, fontSize: 14, color: "FFFFFF" });
    txt(s, "Oktober 2026", { x: M, y: 6.35, w: 7, h: 0.35, fontSize: 12, color: "9FB5AA" });
    s.addNotes("Pembukaan (±30 detik). Kami mengoptimasi rute Granmax yang mengantar Makan Bergizi Gratis dari dapur SPPG ke sekolah di Surabaya. Masalahnya kami pecah menjadi dua tingkat: rute di dalam satu SPPG diselesaikan dengan algoritma pencarian dari Kuliah 2–3, dan pembagian sekolah ke SPPG dengan pencarian lokal dari Kuliah 6.");
  }

  // ============================================================ 2. masalah
  section("Masalah");
  {
    const s = content("Masalah", "Hemat bensin atau makanan cepat sampai?");
    bullets(s, [
      "Setiap hari, dapur SPPG mengantar makanan matang ke banyak sekolah dengan Granmax.",
      "Menggabungkan sekolah dalam satu perjalanan menghemat bensin, tetapi sekolah terakhir menunggu lebih lama.",
      "Mengantar langsung ke tiap sekolah mempercepat waktu tiba, tetapi boros bensin.",
      "Pertanyaan: rute seperti apa yang terbaik, dan algoritma AI mana yang paling andal menemukannya?",
    ], { x: M, y: 1.6, w: 6.2, h: 4.6, fontSize: 18 });
    const stats = [
      ["133", "SPPG di Kota Surabaya (Mei 2026)", fa.FaUtensils],
      ["3.119", "porsi ke 16 sekolah dari satu SPPG (Krembangan)", fa.FaSchool],
      ["2 jam", "anjuran WHO: makanan matang jangan dibiarkan lebih lama di suhu ruang", fa.FaClock],
    ];
    for (let i = 0; i < stats.length; i++) {
      const y = 1.55 + i * 1.75;
      card(s, 7.4, y, 5.33, 1.5);
      await circleIcon(s, stats[i][2], 7.65, y + 0.3, 0.9, T.accent1);
      txt(s, stats[i][0], { x: 8.8, y: y + 0.18, w: 3.8, h: 0.65, fontSize: 30, bold: true, color: C.accent1, fontFace: "Cambria" });
      txt(s, stats[i][1], { x: 8.8, y: y + 0.82, w: 3.8, h: 0.6, fontSize: 13, color: MUTED });
    }
    s.addNotes("Konteks (±45 detik). Program MBG berjalan sejak Januari 2025. Di Surabaya ada 133 SPPG; satu SPPG bisa melayani ribuan porsi. Ada dua kepentingan yang bertentangan: biaya bensin dan keamanan pangan (waktu tunggu makanan).");
  }

  // ============================================================ 3. formulasi
  {
    const s = content("Masalah", "Model: Multi-Depot VRP dengan dua objektif");
    card(s, M, 1.5, 5.6, 5.2, "F6F8F7");
    const depot = { x: 2.2, y: 4.2 };
    const schools = [[1.2, 2.3], [2.6, 2.0], [4.4, 2.6], [4.9, 4.3], [4.2, 5.8], [1.4, 5.7]];
    const routes = [[0, 1], [2, 3], [4], [5]];
    const colors = [T.accent3, T.accent2, T.accent4, T.accent6];
    routes.forEach((r, k) => {
      const pts = [depot, ...r.map((i) => ({ x: schools[i][0], y: schools[i][1] })), depot];
      for (let j = 0; j < pts.length - 1; j++) {
        const a = pts[j], b = pts[j + 1];
        s.addShape(pres.shapes.LINE, { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(b.x - a.x) || 0.001,
          h: Math.abs(b.y - a.y) || 0.001, flipH: (b.x < a.x) !== (b.y < a.y), line: { color: colors[k], width: 2.5 } });
      }
    });
    schools.forEach(([x, y]) => s.addShape(pres.shapes.OVAL, { x: x - 0.17, y: y - 0.17, w: 0.34, h: 0.34,
      fill: { color: "FFFFFF" }, line: { color: "1B1B1B", width: 1.25 } }));
    await circleIcon(s, fa.FaUtensils, depot.x - 0.4, depot.y - 0.4, 0.8, T.accent1);
    txt(s, "SPPG", { x: depot.x - 0.6, y: depot.y + 0.45, w: 1.2, h: 0.3, fontSize: 12, bold: true, align: "center" });
    txt(s, "Setiap warna = 1 Granmax (maks 3 sekolah, kembali ke SPPG)", { x: M + 0.25, y: 6.25, w: 5.1, h: 0.35, fontSize: 12, color: MUTED });

    const P = CONFIG.problem;
    const objs = [
      ["f₁  Biaya bensin", `total km ÷ ${P.km_per_liter} km/L × Rp${fmt(P.fuel_price_per_liter)} (Pertalite)`, fa.FaGasPump, T.accent2],
      ["f₂  Rata-rata waktu tiba", "menit sejak makanan berangkat sampai tiba di sekolah", fa.FaClock, T.accent3],
    ];
    for (let i = 0; i < 2; i++) {
      const y = 1.5 + i * 1.3;
      await circleIcon(s, objs[i][2], 6.8, y + 0.1, 0.85, objs[i][3]);
      txt(s, objs[i][0], { x: 7.85, y, w: 4.9, h: 0.5, fontSize: 20, bold: true, color: C.text2, fontFace: "Cambria" });
      txt(s, objs[i][1], { x: 7.85, y: y + 0.5, w: 4.9, h: 0.6, fontSize: 15, color: MUTED });
    }
    txt(s, "Constraint", { x: 6.8, y: 4.25, w: 5.9, h: 0.4, fontSize: 18, bold: true, color: C.text2, fontFace: "Cambria" });
    const chips = [`maks ${P.max_schools_per_vehicle} sekolah / Granmax`, `${CONFIG.instances[BIG].vehicles_per_sppg} Granmax / SPPG`,
      `bongkar ${P.service_time_min} menit / sekolah`, `tiba ≤ ${P.max_delivery_time_min} menit setelah masak`];
    chips.forEach((c, i) => {
      const x = 6.8 + (i % 2) * 3.0, y = 4.8 + Math.floor(i / 2) * 0.75;
      card(s, x, y, 2.85, 0.6, T.lt2);
      txt(s, c, { x: x + 0.15, y: y + 0.05, w: 2.6, h: 0.5, fontSize: 14, valign: "middle", color: C.text1 });
    });
    txt(s, "Satu fitness: F = w·f₁/ref₁ + (1−w)·f₂/ref₂ + penalti", { x: 6.8, y: 6.35, w: 5.9, h: 0.4, fontSize: 13, italic: true, color: MUTED });
    s.addNotes("Formulasi (±1 menit). Depot = SPPG, pelanggan = sekolah. Objektif kedua rata-rata waktu tiba, bukan total waktu tempuh, karena tanpa macet total waktu sebanding dengan jarak. Kedua objektif digabung jadi satu fitness F dengan bobot w; F ini bisa dipecah menjadi jumlah biaya per ruas perjalanan, sehingga bisa dipakai langsung sebagai biaya jalur di algoritma pencarian.");
  }

  // ============================================================ 4. data
  {
    const s = content("Masalah", "Data jalan asli Surabaya");
    image(s, path.join(__dirname, "figs", "fig_wilayah.png"), M, 1.4, 8.4, 5.4);
    const items = [
      ["751", "SD/MI/SMP/MTs dari OpenStreetMap"],
      ["6", "SPPG dari berita (geocoding alamat)"],
      ["OSRM", "jarak & waktu tempuh jalan asli, bukan garis lurus"],
      ["2", `instance: ${CONFIG.instances[SMALL].n_schools} dan ${CONFIG.instances[BIG].n_schools} sekolah`],
    ];
    items.forEach(([big_, small_], i) => {
      const y = 1.55 + i * 1.3;
      txt(s, big_, { x: 9.35, y, w: 3.4, h: 0.6, fontSize: 30, bold: true, color: C.accent1, fontFace: "Cambria" });
      txt(s, small_, { x: 9.35, y: y + 0.6, w: 3.4, h: 0.55, fontSize: 14, color: MUTED });
    });
    s.addNotes("Data (±45 detik). Sekolah dari OpenStreetMap, SPPG dari pemberitaan lalu di-geocode (koordinat perkiraan). Setiap SPPG mengambil sekolah acak dalam radius 3 km sehingga wilayah layanan tumpang tindih. Matriks jarak dan waktu dari OSRM mengikuti jalan sebenarnya.");
  }

  // ============================================================ 5. dekomposisi
  section("Metode");
  {
    const s = content("Metode", "Dua keputusan, dua keluarga algoritma");
    const boxes = [
      { x: M, title: "Bagian B · Kuliah 6", head: "Sekolah mana dilayani SPPG mana?",
        body: `${CONFIG.instances[BIG].sppg_ids.length}${sup(CONFIG.instances[BIG].n_schools)} ≈ 10${sup(Math.round(spaceB))} kemungkinan → terlalu besar untuk ditelusuri, cocok untuk pencarian lokal`,
        algos: "Hill Climbing (6 varian) · Simulated Annealing · Genetic Algorithm", ic: fa.FaExchangeAlt, col: T.accent2 },
      { x: 6.95, title: "Bagian A · Kuliah 2–3", head: "Rute Granmax di dalam satu SPPG",
        body: "paling banyak 3 Granmax × 3 sekolah = 9 sekolah → cukup kecil untuk pencarian sistematis yang menjamin optimal",
        algos: "BFS · IDS · DFS + Branch & Bound · UCS · A* · Greedy Best-First", ic: fa.FaRoute, col: T.accent3 },
    ];
    for (const b of boxes) {
      card(s, b.x, 1.5, 5.78, 3.9);
      await circleIcon(s, b.ic, b.x + 0.3, 1.75, 0.8, b.col);
      txt(s, b.title, { x: b.x + 1.3, y: 1.75, w: 4.3, h: 0.35, fontSize: 13, bold: true, color: MUTED });
      txt(s, b.head, { x: b.x + 1.3, y: 2.1, w: 4.3, h: 0.5, fontSize: 20, bold: true, color: C.text1, fontFace: "Cambria" });
      txt(s, b.body, { x: b.x + 0.3, y: 2.85, w: 5.2, h: 1.2, fontSize: 15, color: C.text1 });
      txt(s, b.algos, { x: b.x + 0.3, y: 4.2, w: 5.2, h: 1.0, fontSize: 15, bold: true, color: b.col === T.accent2 ? "B4561A" : "1F5FAF" });
    }
    txt(s, "→", { x: 6.38, y: 3.0, w: 0.6, h: 0.6, fontSize: 30, bold: true, color: MUTED, align: "center" });
    card(s, M, 5.65, W - 2 * M, 1.1, "FFF4E8");
    txt(s, [
      { text: "F(x) = Σ biaya rute optimal tiap SPPG", options: { bold: true, fontFace: "Cambria", fontSize: 19, breakLine: true } },
      { text: "Granmax antar-SPPG tidak berbagi apa pun → dekomposisi ini eksak: pembagian terbaik + rute optimal = optimum masalah asli.", options: { fontSize: 14, color: MUTED } },
    ], { x: M + 0.3, y: 5.75, w: W - 2 * M - 0.6, h: 0.95 });
    s.addNotes("Ide utama (±1 menit). Masalah ini punya dua keputusan dengan sifat berbeda. Pembagian sekolah ke SPPG ruangnya sangat besar, jadi kami pakai pencarian lokal. Rute di dalam satu SPPG kecil, paling banyak 9 sekolah, jadi bisa dicari secara sistematis. Setiap pembagian dinilai dengan rute optimal tiap SPPG. Karena SPPG tidak saling berbagi Granmax, pemecahan ini tidak mengorbankan optimalitas.");
  }

  // ============================================================ 6. Bagian A: ruang keadaan + algoritma
  {
    const s = content("Metode", "Bagian A: rute satu SPPG sebagai masalah pencarian");
    const rows = [
      ["Keadaan", "sekolah tersisa, posisi, muatan Granmax, waktu, Granmax terpakai"],
      ["Aksi", "antar ke sekolah s  /  pulang ke SPPG"],
      ["Goal", "semua sekolah terlayani & Granmax di SPPG"],
      ["Biaya langkah", "kontribusi ruas ke F (bensin + waktu tiba)"],
      ["Pangkas", "tiba > 3 jam · sisa tak terangkut · simetri urutan Granmax"],
    ];
    rows.forEach(([k, v], i) => {
      const y = 1.5 + i * 0.68;
      txt(s, k, { x: M, y, w: 1.9, h: 0.6, fontSize: 15, bold: true, color: C.accent1, valign: "middle" });
      txt(s, v, { x: M + 1.95, y, w: 3.75, h: 0.6, fontSize: 14, valign: "middle" });
    });
    const algos = [
      ["BFS", "FIFO", "Granmax paling sedikit", false], ["IDS", "DFS berbatas naik", "sama dengan BFS, memori kecil", false],
      ["DFS-B&B", "LIFO + batas", "pangkas jika g ≥ terbaik", true], ["UCS", "f = g", "biaya jalur terkecil dulu", true],
      ["A*", "f = g + h", "h admissible (h1 / h2)", true], ["GBFS", "f = h", "cepat, abaikan g", false],
    ];
    for (let i = 0; i < algos.length; i++) {
      const x = 6.6 + (i % 2) * 3.1, y = 1.45 + Math.floor(i / 2) * 1.32;
      const [a, f, note, opt] = algos[i];
      card(s, x, y, 2.98, 1.18);
      s.addShape(pres.shapes.RECTANGLE, { x, y: y + 0.12, w: 0.09, h: 0.94, fill: { color: SEARCH_COLOR[a] }, line: { color: SEARCH_COLOR[a] } });
      txt(s, a, { x: x + 0.25, y: y + 0.1, w: 1.5, h: 0.42, fontSize: 18, bold: true, fontFace: "Cambria" });
      txt(s, opt ? "optimal" : "tidak optimal", { x: x + 1.55, y: y + 0.14, w: 1.3, h: 0.35, fontSize: 11, bold: true,
        color: opt ? "1F5C46" : "B4561A", align: "right" });
      txt(s, `${f} · ${note}`, { x: x + 0.25, y: y + 0.55, w: 2.6, h: 0.55, fontSize: 12, color: MUTED });
    }
    card(s, M, 5.15, 5.7, 1.6, "FFF4E8");
    txt(s, [
      { text: "Heuristik h2 (rancangan kami)", options: { bold: true, breakLine: true, fontSize: 15 } },
      { text: "Tiap Granmax hanya punya 1 sekolah urutan ke-1, ke-2, ke-3. Sekolah dipasangkan ke slot termurah (algoritma Hungaria) → batas bawah yang ketat dan tetap admissible.", options: { fontSize: 13, color: MUTED } },
    ], { x: M + 0.25, y: 5.25, w: 5.2, h: 1.45 });
    txt(s, "h1 (pembanding): jalan masuk termurah ke tiap sekolah tersisa", { x: 6.6, y: 5.5, w: 6.1, h: 0.9, fontSize: 14, color: MUTED });
    s.addNotes("Bagian A (±1 menit). Keadaan, aksi, goal, dan biaya langkah mengikuti format pencarian di kuliah. Biaya langkah adalah kontribusi ruas itu ke fitness, jadi biaya jalur = biaya SPPG. Kami membandingkan enam algoritma. Untuk A* kami merancang dua heuristik admissible. h1 sederhana: jalan masuk termurah ke tiap sekolah. h2 memperhitungkan bahwa setiap Granmax hanya punya satu urutan pertama, jadi tidak semua sekolah bisa dianggap tiba langsung dari SPPG.");
  }

  // ============================================================ 7. Bagian A: hasil
  section("Hasil");
  {
    const s = content("Hasil", "Bagian A: heuristik yang baik memangkas pencarian");
    image(s, path.join(RES, "fig_search_scaling.png"), M, 1.35, 8.3, 3.6);
    const order = ["UCS", "A* (h1)", "A*", "DFS-B&B", "BFS", "GBFS"];
    s.addChart(pres.charts.BAR, [{ name: "Selisih dari optimum (%)", labels: order.map((a) => (a === "A*" ? "A* (h2)" : a)), values: order.map((a) => +RA[a].gap.toFixed(1)) }], {
      x: 9.1, y: 1.35, w: 3.63, h: 3.6, barDir: "bar", chartColors: order.map((a) => SEARCH_COLOR[a]),
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"%"', showLegend: false, showTitle: true,
      title: "Lebih mahal dari optimum", valAxisHidden: true, valAxisMinVal: 0, catAxisOrientation: "maxMin", ...chartBase,
    });
    statCard(s, M, 5.2, 3.0, 1.6, `${RA.UCS.opt}/${RA.UCS.n}`, "sub-masalah nyata: UCS, A*, DFS-B&B selalu optimal");
    statCard(s, M + 3.15, 5.2, 3.0, 1.6, `${fmt(ratioUA, 0)}×`, "node lebih sedikit: A* (h2) vs UCS");
    statCard(s, M + 6.3, 5.2, 3.0, 1.6, `+${fmt(RA.BFS.gap, 0)}%`, "BFS/IDS: Granmax paling sedikit ≠ termurah");
    statCard(s, M + 9.45, 5.2, 2.68, 1.6, `+${fmt(RA.GBFS.gap, 0)}%`, "GBFS: cepat, tapi tersesat tanpa g");
    const hit = SEARCH.filter((a) => solvedUpTo(a) < KS[KS.length - 1]);
    s.addNotes(`Hasil Bagian A (±1,5 menit). Grafik kiri: node yang diekspansi dan memori terhadap jumlah sekolah, skala log. Pada sub-masalah nyata, UCS, A* dan DFS-B&B selalu optimal. BFS dan IDS memilih Granmax paling sedikit sehingga sekolah kedua dan ketiga menunggu lama: rata-rata ${fmt(RA.BFS.gap, 1)}% lebih mahal. GBFS mengabaikan biaya yang sudah dikeluarkan sehingga mengunjungi sekolah jauh lebih dulu. A* dengan h2 mengekspansi ${fmt(ratioUA, 0)} kali lebih sedikit node daripada UCS, sedangkan h1 hanya ${fmt(RA.UCS.exp / RA["A* (h1)"].exp, 1)} kali. ${hit.length ? hit.map((a) => `${a} hanya selesai sampai k = ${solvedUpTo(a)}`).join("; ") + " sebelum batas node." : ""}`);
  }

  // ============================================================ 8. Bagian B: algoritma
  {
    const s = content("Metode", "Bagian B: delapan algoritma pencarian lokal");
    const PC = CONFIG.assignment.algorithms;
    const algos = [
      ["HC", "Pindah ke tetangga terbaik; berhenti di optimum lokal", fa.FaMountain],
      ["HC-Sideways", `Boleh langkah datar (ΔF = 0), maks ${PC["HC-Sideways"].max_sideways}×`, fa.FaArrowRight],
      ["Stochastic HC", "Acak di antara langkah yang memperbaiki", fa.FaRandom],
      ["Random-Walk HC", `Peluang ${fmt(PC["Random-Walk HC"].p_walk, 2)} langkah acak, selain itu terbaik`, fa.FaShoePrints],
      ["RR-HC", "Ulang HC dari pembagian acak sampai anggaran habis", fa.FaRedo],
      ["EHC", "BFS dari optimum lokal sampai ketemu yang lebih baik", fa.FaSitemap],
      ["SA", "Terima langkah buruk dengan peluang e^(−ΔF/T)", fa.FaThermometerHalf],
      ["GA", "Kromosom = SPPG tiap sekolah, fitness = 1/F", fa.FaDna],
    ];
    const cw = 2.92, ch = 1.95, gx = 0.15, gy = 0.2;
    for (let i = 0; i < algos.length; i++) {
      const x = M + (i % 4) * (cw + gx), y = 1.45 + Math.floor(i / 4) * (ch + gy);
      const [a, idea, ic] = algos[i];
      card(s, x, y, cw, ch);
      await circleIcon(s, ic, x + 0.2, y + 0.22, 0.6, LS_COLOR[a]);
      txt(s, a, { x: x + 0.92, y: y + 0.27, w: cw - 1.0, h: 0.5, fontSize: 17, bold: true, fontFace: "Cambria", valign: "middle" });
      txt(s, idea, { x: x + 0.2, y: y + 0.95, w: cw - 0.4, h: 0.9, fontSize: 13, color: C.text1 });
    }
    txt(s, [
      { text: "Tetangga: ", options: { bold: true } },
      { text: "pindah satu sekolah ke SPPG lain, atau tukar dua sekolah antar-SPPG.  " },
      { text: "Adil: ", options: { bold: true } },
      { text: `${fmt(CONFIG.assignment.budget_evals)} evaluasi/run, ${CONFIG.assignment.n_seeds} seed, titik awal acak yang sama per seed.` },
    ], { x: M, y: 5.95, w: W - 2 * M, h: 0.8, fontSize: 15 });
    s.addNotes("Bagian B (±1 menit). Semua algoritma bergerak di ruang pembagian: vektor nomor SPPG untuk setiap sekolah. Fitness = jumlah biaya rute optimal tiap SPPG, dihitung oleh evaluator yang hasilnya identik dengan UCS/A* tetapi ribuan kali lebih cepat. Enam varian Hill Climbing berbeda dalam cara melangkah dan cara keluar dari optimum lokal; SA menerima langkah buruk secara probabilistik; GA memakai populasi.");
  }

  // ============================================================ 9. Bagian B: hasil
  {
    const s = content("Hasil", "Bagian B: kunci = cara keluar dari optimum lokal");
    image(s, path.join(RES, BIG, "fig_ls_boxplot.png"), M, 1.35, 7.0, 4.3);
    s.addChart(pres.charts.BAR, [{ name: "Sukses", labels: LOCAL, values: LOCAL.map((a) => +(LB[a].success_rate * 100).toFixed(0)) }], {
      x: 7.75, y: 1.35, w: 4.98, h: 4.3, barDir: "bar", chartColors: LOCAL.map((a) => LS_COLOR[a]),
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0"%"', showLegend: false, showTitle: true,
      title: `Run yang mencapai terbaik diketahui (${BIG})`, valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 115,
      catAxisOrientation: "maxMin", ...chartBase,
    });
    const tHR = lsTest(BIG, "HC", "RR-HC");
    bullets(s, [
      `${SMALL}: semua 8 algoritma mencapai solusi yang sama di semua seed.`,
      `${BIG}: HC biasa sering terjebak; sideways tidak membantu (fitness real, tanpa plateau).`,
      `RR-HC (rekomendasi kuliah) vs HC: p = ${pstr(+tHR.p_holm)}. EHC paling hemat evaluasi.`,
    ], { x: M, y: 5.8, w: W - 2 * M, h: 1.1, fontSize: 15 });
    s.addNotes(`Hasil Bagian B (±1,5 menit). Urutan rata-rata di ${BIG}: ${rB.join(" < ")}. HC, HC-Sideways, dan Stochastic HC berhenti di optimum lokal; HC-Sideways identik dengan HC karena fitness kita bilangan real dari jarak jalan asli, jadi hampir tidak ada tetangga yang sama persis. Algoritma dengan mekanisme keluar dari optimum lokal jauh lebih andal.`);
  }

  // ============================================================ 10. konvergensi
  {
    const s = content("Hasil", "Efisiensi: berapa evaluasi sampai solusi terbaik?");
    image(s, path.join(RES, BIG, "fig_ls_konvergensi.png"), M, 1.35, 7.9, 5.4);
    const effOrder = [...LOCAL].sort((a, b) => +LB[a].evals_to_best_median - +LB[b].evals_to_best_median);
    s.addChart(pres.charts.BAR, [{ name: "Evaluasi (ribu)", labels: effOrder, values: effOrder.map((a) => +(LB[a].evals_to_best_median / 1000).toFixed(1)) }], {
      x: 8.7, y: 1.35, w: 4.03, h: 4.0, barDir: "bar", chartColors: effOrder.map((a) => LS_COLOR[a]),
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", showLegend: false, showTitle: true,
      title: "Median evaluasi s.d. terbaik (ribu)", valAxisHidden: true, valAxisMinVal: 0, catAxisOrientation: "maxMin", ...chartBase,
    });
    txt(s, `SA paling lambat per run (${fmt(LB.SA.runtime_s_mean, 0)} s) karena tiap langkah acak menghasilkan himpunan sekolah baru; EHC ${fmt(LB.EHC.runtime_s_mean, 1)} s.`,
      { x: 8.7, y: 5.5, w: 4.03, h: 1.3, fontSize: 14, color: MUTED });
    s.addNotes("Konvergensi (±1 menit). Sumbu x skala log. Varian HC turun paling cepat di awal lalu mendatar. EHC turun hampir secepat HC dan terus membaik karena di optimum lokal ia mencari kombinasi dua langkah. SA sengaja bertahan di suhu tinggi dulu. GA lebih lambat di awal karena setiap individu dievaluasi penuh.");
  }

  // ============================================================ 11. komparasi menyeluruh
  {
    const s = content("Hasil", "Dua tingkat > metaheuristik terintegrasi");
    const items = [["Greedy", +integ[BIG].Greedy.fitness_mean, "52514E"],
      ...["HC", "SA", "GA", "ACO"].map((a) => [`${a} terintegrasi`, +integ[BIG][a].fitness_mean, "EB6834"]),
      ...LOCAL.map((a) => [`${a} (2 tingkat)`, +LB[a].fitness_mean, "2A78D6"])];
    items.sort((a, b) => a[1] - b[1]);
    s.addChart(pres.charts.BAR, [{ name: "Selisih", labels: items.map((x) => x[0]), values: items.map((x) => +(((x[1] - bkB) / bkB) * 100).toFixed(2)) }], {
      x: M, y: 1.35, w: 7.6, h: 5.45, barDir: "bar", chartColors: items.map((x) => x[2]),
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.00"%"', showLegend: false, showTitle: true,
      title: `Selisih rata-rata dari terbaik diketahui, ${BIG}`, valAxisHidden: true, valAxisMinVal: 0, catAxisOrientation: "maxMin",
      ...chartBase, catAxisLabelFontSize: 11,
    });
    statCard(s, 8.5, 1.45, 4.23, 1.55, `${nBetter} dari 8`, `algoritma dua tingkat lebih baik dari ${integBest} terintegrasi (terbaik di eksperimen awal)`);
    statCard(s, 8.5, 3.15, 4.23, 1.55, `−${fmt(savePct, 1)}%`, `biaya bensin vs Greedy (${rp(g.cost_rp)} → ${rp(sol.cost_rp)}/hari)`);
    txt(s, "Algoritma yang sama (HC, SA, GA) jauh lebih kuat di ruang pembagian + rute optimal daripada di ruang rute penuh: ruangnya lebih kecil dan setiap titik langsung dinilai dengan rute terbaiknya.",
      { x: 8.5, y: 4.9, w: 4.23, h: 1.9, fontSize: 14 });
    s.addNotes(`Komparasi menyeluruh (±1 menit). Oranye: metaheuristik terintegrasi dari eksperimen awal yang mencari langsung di ruang rute penuh. Biru: pendekatan dua tingkat. ${integBest} terintegrasi rata-rata ${fmt(((+ib.fitness_mean - bkB) / bkB) * 100, 2)}% di atas terbaik diketahui. Pesan utamanya: representasi yang sesuai struktur masalah lebih menentukan daripada pilihan metaheuristik.`);
  }

  // ============================================================ 12. trade-off
  if (sweep.length) {
    const s = content("Hasil", "Trade-off biaya bensin vs waktu tiba");
    image(s, path.join(RES, BIG, "fig_ls_pareto.png"), M, 1.35, 7.6, 5.4);
    const algo = sweep[0].algorithm;
    const best = {};
    for (const r of sweep) if (!best[+r.w] || +r.fitness < +best[+r.w].fitness) best[+r.w] = r;
    const ws = Object.keys(best).map(Number).sort((a, b) => b - a);
    ws.forEach((w, i) => {
      const r = best[w];
      const y = 1.45 + i * 0.95;
      card(s, 8.5, y, 4.23, 0.82);
      txt(s, `w = ${fmt(w, 2)}`, { x: 8.7, y: y + 0.1, w: 1.2, h: 0.62, fontSize: 15, bold: true, valign: "middle" });
      txt(s, `${rp(r.cost_rp)} · ${fmt(r.mean_arrival_min, 1)} mnt`, { x: 9.9, y: y + 0.1, w: 2.75, h: 0.62, fontSize: 15, valign: "middle", color: C.text1 });
    });
    txt(s, "w = 1: murni bensin · w = 0: murni waktu", { x: 8.5, y: 6.25, w: 4.23, h: 0.4, fontSize: 12, color: MUTED });
    s.addNotes(`Trade-off (±1 menit). ${algo} dengan rute optimal dijalankan untuk lima bobot dan dibandingkan dengan Pareto front NSGA-II dari eksperimen awal. Dari solusi termurah ke tercepat, rata-rata waktu tiba turun ${fmt(+best[1].mean_arrival_min - +best[0].mean_arrival_min, 1)} menit tetapi biaya naik ${rp(+best[0].cost_rp - +best[1].cost_rp)} per hari. Pengelola SPPG bisa memilih bobot sesuai prioritasnya.`);
  }

  // ============================================================ 13. rute terbaik
  {
    const s = content("Hasil", "Rute terbaik di peta");
    image(s, routePng, M, 1.35, 5.6, 5.55);
    const perYear = (g.cost_rp - sol.cost_rp) * 200;
    const stats = [
      [rp(sol.cost_rp), `bensin per hari (${fmt(sol.km, 1)} km, ${sol.n_vehicles} Granmax)`],
      [`${fmt(sol.mean_arrival_min, 1)} mnt`, `rata-rata makanan tiba; terakhir ${fmt(sol.makespan_min, 0)} mnt`],
      [`−${rp(g.cost_rp - sol.cost_rp)}`, "per hari dibanding Greedy"],
      [`±${rp(perYear)}`, `per tahun (asumsi 200 hari sekolah) untuk ${CONFIG.instances[BIG].n_schools} sekolah`],
    ];
    stats.forEach(([v, l], i) => {
      const x = 6.75 + (i % 2) * 3.05, y = 1.55 + Math.floor(i / 2) * 2.05;
      statCard(s, x, y, 2.9, 1.8, v, l, 24);
    });
    txt(s, "Demo interaktif: results/<instance>/peta_rute_terbaik.html (rute per Granmax, jam tiba tiap sekolah).",
      { x: 6.75, y: 5.75, w: 5.98, h: 0.9, fontSize: 14, color: C.text1 });
    s.addNotes(`Rute (±45 detik). Solusi terbaik ditemukan oleh ${top} + rute optimal. Warna menunjukkan SPPG asal, angka urutan kunjungan, garis mengikuti jalan asli. Bila waktu memungkinkan, buka peta interaktif.`);
  }

  // ============================================================ 14. sensitivitas
  {
    const s = content("Hasil", "Sensitivitas: kapasitas penting, batas 3 jam tidak");
    const qs = [1, 2, 3, 4];
    s.addChart(pres.charts.LINE, [{ name: "Biaya bensin (ribu Rp)", labels: qs.map((q) => `${q}`), values: qs.map((q) => +(sv("kapasitas", q, "cost_rp") / 1000).toFixed(1)) }], {
      x: M, y: 1.45, w: 5.9, h: 4.2, chartColors: [T.accent2], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 9,
      showValue: true, dataLabelPosition: "t", dataLabelFormatCode: "0", showLegend: false, showTitle: true,
      title: "Biaya bensin (ribu Rp) vs maks sekolah per Granmax", valAxisMinVal: 0, ...chartBase,
    });
    s.addChart(pres.charts.LINE, [
      { name: "Sekolah terakhir tiba (mnt)", labels: TF.map((v) => `${v}×`), values: TF.map((v) => +sv("macet", v, "makespan_min").toFixed(0)) },
      { name: "Batas 3 jam", labels: TF.map((v) => `${v}×`), values: TF.map(() => CONFIG.problem.max_delivery_time_min) },
    ], {
      x: 6.83, y: 1.45, w: 5.9, h: 4.2, chartColors: [T.accent3, "C0392B"], lineSize: 2, lineDataSymbol: "circle",
      lineDataSymbolSize: 8, showLegend: true, legendPos: "b", showTitle: true, title: "Waktu tiba terakhir vs faktor kemacetan",
      valAxisMinVal: 0, valAxisMaxVal: 200, ...chartBase,
    });
    const q1 = sv("kapasitas", 1, "cost_rp"), q3 = sv("kapasitas", 3, "cost_rp");
    txt(s, `Jika 1 Granmax hanya ke 1 sekolah, biaya naik ${fmt((q1 / q3 - 1) * 100, 0)}%. Bahkan dengan macet ${TF[TF.length - 1]}× (±${fmt(SPEED / TF[TF.length - 1], 0)} km/jam), sekolah terakhir tiba dalam ${fmt(sv("macet", TF[TF.length - 1], "makespan_min"), 0)} menit.`,
      { x: M, y: 5.9, w: W - 2 * M, h: 0.85, fontSize: 16 });
    s.addNotes(`Sensitivitas (±45 detik). Konsumsi 10 km/L menaikkan biaya sekitar ${fmt((sv("km_per_liter", 10, "cost_rp") / sv("km_per_liter", 14, "cost_rp") - 1) * 100, 0)}% tanpa mengubah rute. Batas 3 jam tidak aktif; bila diperketat ke 2 jam (anjuran WHO), batas mulai terlampaui saat waktu tempuh sekitar ${F120 || ">" + TF[TF.length - 1]} kali kondisi lancar.`);
  }

  // ============================================================ 15. kesimpulan
  section("Penutup");
  {
    const s = pres.addSlide({ masterName: "DARK", sectionTitle: "Penutup" });
    txt(s, "Kesimpulan", { x: M, y: 0.55, w: 8, h: 0.8, fontSize: 36, bold: true, color: "FFFFFF", fontFace: "Cambria" });
    const pts = [
      ["Dekomposisi eksak: pembagian sekolah (pencarian lokal) + rute per SPPG (algoritma pencarian).", fa.FaSitemap],
      [`Bagian A: UCS, A*, DFS-B&B optimal; BFS/IDS +${fmt(RA.BFS.gap, 0)}%, GBFS +${fmt(RA.GBFS.gap, 0)}%. Heuristik h2: ${fmt(ratioUA, 0)}× lebih sedikit node.`, fa.FaRoute],
      [`Bagian B: HC biasa terjebak; mekanisme keluar (RR-HC, EHC, SA, GA, random walk) yang menentukan. Terbaik: ${rB.slice(0, 3).join(" ≈ ")}${top3ns ? " (tidak beda signifikan)" : ""}.`, fa.FaMountain],
      [`Lebih baik dari metaheuristik terintegrasi; bensin −${fmt(savePct, 0)}% vs Greedy. Batas 3 jam tidak aktif.`, fa.FaTrophy],
    ];
    for (let i = 0; i < pts.length; i++) {
      const y = 1.55 + i * 1.1;
      await circleIcon(s, pts[i][1], M, y, 0.72, "2E6B55");
      txt(s, pts[i][0], { x: M + 1.0, y: y - 0.04, w: 11.1, h: 0.82, fontSize: 18, color: "FFFFFF", valign: "middle" });
    }
    await circleIcon(s, fa.FaGithub, M, 6.15, 0.6, "FFFFFF", T.dk2);
    txt(s, GITHUB, { x: M + 0.8, y: 6.17, w: 6, h: 0.55, fontSize: 18, bold: true, color: "9FD3B9", valign: "middle",
      hyperlink: { url: "https://" + GITHUB } });
    txt(s, "Terima kasih · Pertanyaan?", { x: 7.5, y: 6.17, w: 5.23, h: 0.55, fontSize: 18, color: "D7E7DF", align: "right", valign: "middle" });
    s.addNotes("Kesimpulan (±45 detik). Tutup dengan empat temuan, sebutkan repositori GitHub, lalu buka sesi tanya jawab.");
  }

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("->", OUT);
}

// Tulis warna THEME ke ppt/theme/theme1.xml (pptxgenjs selalu menulis palet Office).
async function applyTheme(file, theme) {
  const JSZip = require(require.resolve("jszip", { paths: [require.resolve("pptxgenjs")] }));
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const part = "ppt/theme/theme1.xml";
  const slots = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];
  const scheme = `<a:clrScheme name="${theme.name}">` + slots.map((k) => `<a:${k}><a:srgbClr val="${theme.colors[k]}"/></a:${k}>`).join("") + "</a:clrScheme>";
  const xml = (await zip.file(part).async("string"))
    .replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, h) => `${h}${theme.name}"`);
  zip.file(part, xml);
  for (const name of Object.keys(zip.files)) {
    if (!name.endsWith(".xml")) continue;
    const bad = (await zip.file(name).async("string")).match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/);
    if (bad) throw new Error(`${name}: warna tidak valid "${bad[1]}" (scheme color di opsi yang hanya menerima hex)`);
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

main().catch((e) => { console.error(e); process.exit(1); });
