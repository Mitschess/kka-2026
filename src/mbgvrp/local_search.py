"""Bagian B — penugasan sekolah ke SPPG dengan pencarian lokal (Kuliah 6).

Representasi: x[s] = nomor SPPG yang melayani sekolah s (vektor bilangan bulat).
Fitness F(x) = jumlah biaya rute optimal tiap SPPG untuk sekolah-sekolah miliknya
(Router, setara UCS/A* Bagian A) + penalti (Granmax melebihi armada, tiba > 3 jam).
F sama persis dengan fungsi objektif skalar masalah penuh (problem.scalarize), jadi
hasilnya bisa dibandingkan langsung dengan metaheuristik terintegrasi (algorithms.py).

Tetangga:
  pindah(s, b) : sekolah s dipindah ke SPPG b
  tukar(s, u)  : dua sekolah dari SPPG berbeda bertukar SPPG
Algoritma (semua diberi anggaran evaluasi F yang sama, mulai dari penugasan acak):
  HC              steepest-ascent, berhenti di optimum lokal
  HC-Sideways     seperti HC, tetapi boleh langkah datar (dF = 0) maks. 100x berturut-turut
  Stochastic HC   pilih acak di antara semua langkah yang memperbaiki
  Random-Walk HC  dengan peluang p langkah acak, selain itu langkah terbaik
  RR-HC           HC diulang dari penugasan acak baru sampai anggaran habis
  EHC             Enforced HC: BFS dari keadaan sekarang sampai ketemu yang lebih baik
  SA              terima langkah lebih buruk dengan peluang e^(-dF/T)
  GA              kromosom = SPPG tiap sekolah, fitness = 1/F, turnamen, crossover uniform
"""
import math
import time
from dataclasses import dataclass, field

from .router import Router

EPS = 1e-12


@dataclass
class LSResult:
    algorithm: str
    routes: list
    evaluation: object
    fitness: float
    runtime_s: float
    n_evals: int
    history: list = field(default_factory=list)   # [(evaluasi, F terbaik)]
    assignment: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


class _Budget(Exception):
    pass


class AssignmentProblem:
    def __init__(self, inst, w, penalty):
        self.inst, self.w, self.penalty = inst, w, penalty
        self.router = Router(inst, w, penalty)
        self.n, self.m = inst.n, inst.m
        self.cap = [v * inst.Q for v in inst.vehicles_per_depot]

    def random_assignment(self, rng):
        """Penugasan acak yang menghormati kapasitas SPPG (armada x Q sekolah)."""
        x, count = [0] * self.n, [0] * self.m
        for s in rng.permutation(self.n).tolist():
            free = [d for d in range(self.m) if count[d] < self.cap[d]] or list(range(self.m))
            d = free[int(rng.integers(len(free)))]
            x[s] = d
            count[d] += 1
        return x

    def masks(self, x):
        mk = [0] * self.m
        for s, d in enumerate(x):
            mk[d] |= 1 << s
        return mk

    def fitness_of_masks(self, masks):
        return sum(self.router.cost(d, mk) for d, mk in enumerate(masks))


class _State:
    """Penugasan + bitmask & biaya rute per SPPG, untuk evaluasi tetangga inkremental."""
    __slots__ = ("x", "masks", "costs", "F")

    def __init__(self, prob, x):
        self.x = list(x)
        self.masks = prob.masks(x)
        self.costs = [prob.router.cost(d, mk) for d, mk in enumerate(self.masks)]
        self.F = sum(self.costs)

    def copy(self):
        st = _State.__new__(_State)
        st.x, st.masks, st.costs, st.F = list(self.x), list(self.masks), list(self.costs), self.F
        return st


class _Search:
    """Kerangka bersama: hitung evaluasi, catat solusi terbaik & riwayat konvergensi."""

    def __init__(self, prob, budget, rng, log_every=500):
        self.prob, self.budget, self.rng = prob, budget, rng
        self.R = prob.router
        self.evals = 0
        self.best_F, self.best_x = math.inf, None
        self.history, self.log_every = [], log_every
        self.extra = {}

    # ------------------------------------------------------------- evaluasi
    def _count(self, F, make_x):
        if self.evals >= self.budget:
            raise _Budget
        self.evals += 1
        if F < self.best_F - EPS:
            self.best_F, self.best_x = F, make_x()
            self.extra["evals_to_best"] = self.evals
        if self.evals % self.log_every == 0 or self.evals == 1:
            self.history.append((self.evals, self.best_F))

    def new_state(self, x):
        st = _State(self.prob, x)
        self._count(st.F, lambda: list(st.x))
        return st

    def delta(self, st, move):
        """Selisih F jika langkah diterapkan (dihitung sebagai satu evaluasi)."""
        R, kind, s, v = self.R, move[0], move[1], move[2]
        a = st.x[s]
        if kind == 0:   # pindah s -> SPPG v
            na = R.cost(a, st.masks[a] ^ (1 << s))
            nb = R.cost(v, st.masks[v] | (1 << s))
            dF = na + nb - st.costs[a] - st.costs[v]
        else:           # tukar s <-> v
            b = st.x[v]
            bs, bv = 1 << s, 1 << v
            na = R.cost(a, st.masks[a] ^ bs | bv)
            nb = R.cost(b, st.masks[b] ^ bv | bs)
            dF = na + nb - st.costs[a] - st.costs[b]
        self._count(st.F + dF, lambda: self._applied_x(st, move))
        return dF

    @staticmethod
    def _applied_x(st, move):
        x = list(st.x)
        if move[0] == 0:
            x[move[1]] = move[2]
        else:
            x[move[1]], x[move[2]] = x[move[2]], x[move[1]]
        return x

    def apply(self, st, move):
        R, s, v = self.R, move[1], move[2]
        a = st.x[s]
        if move[0] == 0:
            touched = (a, v)
            st.x[s] = v
            st.masks[a] ^= 1 << s
            st.masks[v] |= 1 << s
        else:
            b = st.x[v]
            touched = (a, b)
            st.x[s], st.x[v] = b, a
            st.masks[a] ^= (1 << s) | (1 << v)
            st.masks[b] ^= (1 << s) | (1 << v)
        for d in touched:
            st.costs[d] = R.cost(d, st.masks[d])
        st.F = sum(st.costs)

    # ------------------------------------------------------------- tetangga
    def moves(self, st):
        """Semua langkah pindah & tukar, urutan diacak (pemecah seri yang adil)."""
        m, x = self.prob.m, st.x
        out = [(0, s, b) for s in range(len(x)) for b in range(m) if b != x[s]]
        out += [(1, s, u) for s in range(len(x)) for u in range(s + 1, len(x)) if x[s] != x[u]]
        order = self.rng.permutation(len(out)).tolist()
        return [out[i] for i in order]

    def random_move(self, st):
        x, n = st.x, len(st.x)
        if self.rng.random() < 0.5:
            s = int(self.rng.integers(n))
            b = int(self.rng.integers(self.prob.m - 1))
            return (0, s, b + (b >= x[s]))
        while True:
            s, u = (int(v) for v in self.rng.choice(n, 2, replace=False))
            if x[s] != x[u]:
                return (1, min(s, u), max(s, u))

    def scan(self, st):
        """Evaluasi seluruh tetangga: [(dF, langkah)]."""
        return [(self.delta(st, mv), mv) for mv in self.moves(st)]

    def climb(self, st, sideways=0):
        """Steepest-ascent hill climbing dari st sampai optimum lokal."""
        flat = 0
        while True:
            scored = self.scan(st)
            best = min(d for d, _ in scored)
            if best < -EPS:
                flat = 0
            elif best <= EPS and flat < sideways:
                flat += 1
                self.extra["sideways"] = self.extra.get("sideways", 0) + 1
            else:
                return st
            ties = [mv for d, mv in scored if d <= best + EPS]
            self.apply(st, ties[int(self.rng.integers(len(ties)))])
            self.extra["steps"] = self.extra.get("steps", 0) + 1


# ======================================================================== varian HC
def _hc(S, sideways=0, **_):
    S.climb(S.new_state(S.prob.random_assignment(S.rng)), sideways)


def _hc_sideways(S, max_sideways=100, **_):
    _hc(S, sideways=max_sideways)


def _stochastic_hc(S, **_):
    st = S.new_state(S.prob.random_assignment(S.rng))
    while True:
        up = [mv for d, mv in S.scan(st) if d < -EPS]
        if not up:
            return
        S.apply(st, up[int(S.rng.integers(len(up)))])
        S.extra["steps"] = S.extra.get("steps", 0) + 1


def _random_walk_hc(S, p_walk=0.2, **_):
    st = S.new_state(S.prob.random_assignment(S.rng))
    while True:
        if S.rng.random() < p_walk:
            mv = S.random_move(st)
            S.delta(st, mv)
            S.apply(st, mv)
            S.extra["random_steps"] = S.extra.get("random_steps", 0) + 1
            continue
        best_d, best_mv = min(S.scan(st))
        if best_d >= -EPS:   # optimum lokal: paksa satu langkah acak
            best_mv = S.random_move(st)
            S.delta(st, best_mv)
            S.extra["random_steps"] = S.extra.get("random_steps", 0) + 1
        S.apply(st, best_mv)


def _random_restart_hc(S, **_):
    while True:
        S.climb(S.new_state(S.prob.random_assignment(S.rng)))
        S.extra["restarts"] = S.extra.get("restarts", 0) + 1


def _enforced_hc(S, max_depth=2, **_):
    """EHC (Hoffmann & Nebel 2001): dari keadaan sekarang lakukan BFS di graf tetangga
    sampai menemukan keadaan yang lebih baik, pindah ke sana, ulangi. Anak tiap level
    dibuka mulai dari yang paling menjanjikan (dF terkecil)."""
    st = S.new_state(S.prob.random_assignment(S.rng))
    while True:
        level = [(0.0, st, [])]    # (dF kumulatif, keadaan, jalur langkah)
        found = None
        for depth in range(1, max_depth + 1):
            nxt = []
            for d0, parent, path in sorted(level, key=lambda e: e[0]):
                base = parent
                if depth > 1:   # keadaan anak baru dibangun saat akan dibuka
                    base = parent.copy()
                    S.apply(base, path[-1])
                for mv in S.moves(base):
                    d1 = d0 + S.delta(base, mv)
                    if d1 < -EPS:
                        found = path + [mv]
                        break
                    if depth < max_depth:
                        nxt.append((d1, base, path + [mv]))
                if found:
                    break
            if found:
                S.extra["depth_%d" % depth] = S.extra.get("depth_%d" % depth, 0) + 1
                break
            level = nxt
        if not found:
            return     # BFS habis tanpa perbaikan: EHC gagal (berhenti)
        for mv in found:
            S.apply(st, mv)


def _simulated_annealing(S, accept_prob_init=0.8, final_temp_ratio=1e-4, **_):
    st = S.new_state(S.prob.random_assignment(S.rng))
    # suhu awal: langkah memburuk rata-rata diterima dengan peluang accept_prob_init
    ups = [d for d in (S.delta(st, S.random_move(st)) for _ in range(100)) if d > EPS]
    T0 = -(sum(ups) / len(ups)) / math.log(accept_prob_init) if ups else 1e-3
    remaining = max(1, S.budget - S.evals)
    alpha = final_temp_ratio ** (1.0 / remaining)
    T = T0
    while True:
        mv = S.random_move(st)
        dF = S.delta(st, mv)
        if dF < 0 or S.rng.random() < math.exp(-dF / T):
            S.apply(st, mv)
        T *= alpha


def _genetic(S, pop_size=100, tournament_k=3, p_crossover=0.9, n_elite=2, **_):
    prob, rng = S.prob, S.rng
    n, m = prob.n, prob.m
    p_gene = 1.0 / n

    def evaluate(x):
        F = prob.fitness_of_masks(prob.masks(x))
        S._count(F, lambda: list(x))
        return F

    pop = [prob.random_assignment(rng) for _ in range(pop_size)]
    fit = [evaluate(x) for x in pop]

    def tournament():
        idx = rng.choice(pop_size, tournament_k, replace=False)
        return pop[min(idx, key=lambda i: fit[i])]   # fitness 1/F terbesar = F terkecil

    while True:
        order = sorted(range(pop_size), key=lambda i: fit[i])
        new_pop = [pop[i] for i in order[:n_elite]]
        new_fit = [fit[i] for i in order[:n_elite]]
        while len(new_pop) < pop_size:
            p1, p2 = tournament(), tournament()
            if rng.random() < p_crossover:
                pick = rng.random(n) < 0.5
                child = [a if c else b for a, b, c in zip(p1, p2, pick)]
            else:
                child = list(p1)
            for s in range(n):
                if rng.random() < p_gene:
                    b = int(rng.integers(m - 1))
                    child[s] = b + (b >= child[s])
            new_pop.append(child)
            new_fit.append(evaluate(child))
        pop, fit = new_pop, new_fit
        S.extra["generations"] = S.extra.get("generations", 0) + 1


ALGORITHMS = {
    "HC": _hc,
    "HC-Sideways": _hc_sideways,
    "Stochastic HC": _stochastic_hc,
    "Random-Walk HC": _random_walk_hc,
    "RR-HC": _random_restart_hc,
    "EHC": _enforced_hc,
    "SA": _simulated_annealing,
    "GA": _genetic,
}


def run(name, inst, w, penalty, budget, rng, log_every=500, **params):
    """Jalankan satu algoritma Bagian B. Berhenti saat anggaran evaluasi habis atau
    (untuk varian HC tanpa restart) saat terjebak di optimum lokal."""
    start = time.perf_counter()
    prob = AssignmentProblem(inst, w, penalty)
    S = _Search(prob, budget, rng, log_every)
    try:
        ALGORITHMS[name](S, **params)
        S.extra["stopped"] = "optimum lokal"
    except _Budget:
        S.extra["stopped"] = "anggaran habis"
    S.history.append((S.evals, S.best_F))
    masks = prob.masks(S.best_x)
    routes = prob.router.all_routes(masks)
    ev = inst.evaluate(routes)
    check = inst.scalarize(ev, w, penalty)
    assert abs(check - S.best_F) < 1e-7, f"{name}: F {S.best_F} != evaluasi rute {check}"
    S.extra["router_subproblems"] = prob.router.calls
    return LSResult(name, routes, ev, S.best_F, time.perf_counter() - start, S.evals,
                    S.history, list(S.best_x), S.extra)
