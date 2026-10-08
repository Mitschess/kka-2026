"""Algoritma yang dibandingkan.

Single-objective (weighted sum, bobot w):
  - Greedy            : baseline konstruktif (cheapest append)
  - Simulated Annealing : representasi langsung (permutasi + pemisah kendaraan)
  - Genetic Algorithm   : representasi urutan sekolah + decoder greedy
  - Ant Colony Optimization (MAX-MIN Ant System) : konstruktif probabilistik
Multi-objective:
  - NSGA-II : urutan sekolah + gen bobot decoder, langsung mencari Pareto front
              (biaya bensin vs rata-rata waktu tiba)

Semua metaheuristik diberi anggaran jumlah evaluasi solusi yang sama (budget)
agar perbandingannya adil.

Parameter opsional trace(event, **data) hanya dipakai make_animation.py untuk merekam
jalannya algoritma. Callback tidak memakai rng, jadi hasil run tetap sama persis.
"""
import math
import time
from dataclasses import dataclass, field

import numpy as np

from . import encoding as enc
from .construct import construct, decode_order, greedy


@dataclass
class Result:
    algorithm: str
    routes: list
    evaluation: object
    fitness: float
    runtime_s: float
    n_evals: int
    history: list = field(default_factory=list)  # [(evals, best fitness)]


class _Objective:
    """Membungkus evaluasi skalar + menghitung jumlah evaluasi + mencatat best."""

    def __init__(self, inst, w, penalty, log_every=200):
        self.inst, self.w, self.penalty = inst, w, penalty
        self.evals = 0
        self.best_f = math.inf
        self.best_routes = None
        self.history = []
        self.log_every = log_every

    def routes(self, routes):
        ev = self.inst.evaluate(routes)
        f = self.inst.scalarize(ev, self.w, self.penalty)
        self.evals += 1
        if f < self.best_f:
            self.best_f, self.best_routes = f, routes
        if self.evals % self.log_every == 0:
            self.history.append((self.evals, self.best_f))
        return f

    def perm(self, perm):
        return self.routes(enc.decode(self.inst, perm))

    def result(self, name, start):
        ev = self.inst.evaluate(self.best_routes)
        self.history.append((self.evals, self.best_f))
        return Result(name, [(d, list(s)) for d, s in self.best_routes if s], ev, self.best_f,
                      time.perf_counter() - start, self.evals, self.history)


# ============================================================================ Greedy
def run_greedy(inst, w, penalty, trace=None, **_):
    start = time.perf_counter()
    obj = _Objective(inst, w, penalty)
    obj.routes(greedy(inst, w, trace))
    return obj.result("Greedy", start)


# =============================================================== Simulated Annealing
def run_sa(inst, w, penalty, budget, rng, accept_prob_init=0.8, final_temp_ratio=1e-4,
           trace=None, **_):
    start = time.perf_counter()
    obj = _Objective(inst, w, penalty)
    x = enc.random_solution(inst, rng)
    fx = obj.perm(x)

    # suhu awal: kenaikan objektif rata-rata (TANPA penalti, karena penalti solusi
    # acak sangat besar dan membuat T0 meledak) diterima dengan peluang p0
    ups = []
    f_plain = inst.scalarize(inst.evaluate(enc.decode(inst, x)), w, 0.0)
    for _ in range(100):
        y_routes = enc.decode(inst, enc.neighbor(x, rng))
        obj.routes(y_routes)
        d = inst.scalarize(inst.evaluate(y_routes), w, 0.0) - f_plain
        if d > 0:
            ups.append(d)
    T0 = -np.mean(ups) / math.log(accept_prob_init) if ups else 1.0
    steps = budget - obj.evals
    cooling = final_temp_ratio ** (1.0 / steps)  # pendinginan geometrik
    temp = T0
    if trace:
        trace("sa_init", x=x, fx=fx, T0=T0, steps=steps, cooling=cooling)

    for it in range(steps):
        y = enc.neighbor(x, rng)
        fy = obj.perm(y)
        accepted = fy <= fx or rng.random() < math.exp(-(fy - fx) / temp)
        if trace:
            trace("sa_step", it=it + 1, x=x, y=y, fx=fx, fy=fy, temp=temp, accepted=accepted,
                  best_f=obj.best_f, best_routes=obj.best_routes)
        if accepted:
            x, fx = y, fy
        temp *= cooling
    return obj.result("SA", start)


# ================================================================= Genetic Algorithm
def run_ga(inst, w, penalty, budget, rng, pop_size=100, tournament_k=3, p_crossover=0.9,
           p_mutation=0.3, n_elite=2, trace=None, **_):
    start = time.perf_counter()
    """Kromosom = urutan sekolah (permutasi 0..n-1). decode_order menempatkan tiap
    sekolah secara greedy -> GA mencari urutan penempatan terbaik."""
    obj = _Objective(inst, w, penalty)
    fitness = lambda order: obj.routes(decode_order(inst, order.tolist(), w))  # noqa: E731
    pop = [rng.permutation(inst.n) for _ in range(pop_size)]
    fit = np.array([fitness(p) for p in pop])
    if trace:
        trace("ga_gen", gen=0, pop=pop, fit=fit, evals=obj.evals)

    def tournament():
        idx = rng.choice(pop_size, tournament_k, replace=False)
        return pop[idx[np.argmin(fit[idx])]]

    gen = 0
    while obj.evals + pop_size - n_elite <= budget:
        gen += 1
        elite = np.argsort(fit)[:n_elite]
        new_pop = [pop[i] for i in elite]
        new_fit = [fit[i] for i in elite]
        while len(new_pop) < pop_size:
            p1, p2 = tournament(), tournament()
            crossed = rng.random() < p_crossover
            child = enc.order_crossover(p1, p2, rng) if crossed else p1.copy()
            mutated = rng.random() < p_mutation
            if mutated:
                child = enc.neighbor(child, rng)
            new_pop.append(child)
            new_fit.append(fitness(child))
            if trace:
                trace("ga_child", gen=gen, p1=p1, p2=p2, child=child, child_f=new_fit[-1],
                      crossed=crossed, mutated=mutated)
        pop, fit = new_pop, np.array(new_fit)
        if trace:
            trace("ga_gen", gen=gen, pop=pop, fit=fit, evals=obj.evals)
    return obj.result("GA", start)


# ========================================================== Ant Colony Optimization
def run_aco(inst, w, penalty, budget, rng, n_ants=20, alpha=1.0, beta=3.0, rho=0.1,
            trace=None, **_):
    """MAX-MIN Ant System: hanya semut terbaik yang menaruh feromon, tau dibatasi."""
    start = time.perf_counter()
    obj = _Objective(inst, w, penalty)
    n_nodes = inst.m + inst.n

    f_greedy = inst.scalarize(inst.evaluate(greedy(inst, w)), w, penalty)
    tau_max = 1.0 / (rho * f_greedy)
    tau_min = tau_max / (2.0 * inst.n)
    tau = np.full((n_nodes, n_nodes), tau_max)

    it = 0
    best_routes, best_f = None, math.inf
    while obj.evals + n_ants <= budget:
        it_best_routes, it_best_f = None, math.inf
        for k in range(n_ants):
            routes = construct(inst, w, rng=rng, tau=tau, alpha=alpha, beta=beta)
            f = obj.routes(routes)
            if trace:
                trace("aco_ant", it=it, ant=k, routes=routes, f=f)
            if f < it_best_f:
                it_best_routes, it_best_f = routes, f
        if it_best_f < best_f:
            best_routes, best_f = it_best_routes, it_best_f
            tau_max = 1.0 / (rho * best_f)
            tau_min = tau_max / (2.0 * inst.n)

        # penguapan + deposit (iteration-best, tiap 5 iterasi pakai best-so-far)
        tau *= (1 - rho)
        dep_routes, dep_f = (best_routes, best_f) if it % 5 == 4 else (it_best_routes, it_best_f)
        for d, seq in dep_routes:
            path = [d] + [s + inst.m for s in seq] + [d]
            for a, b in zip(path[:-1], path[1:]):
                tau[a, b] += 1.0 / dep_f
        np.clip(tau, tau_min, tau_max, out=tau)
        if trace:
            trace("aco_iter", it=it, it_best_routes=it_best_routes, it_best_f=it_best_f,
                  best_routes=best_routes, best_f=best_f, deposit_best=it % 5 == 4,
                  tau=tau, tau_min=tau_min, tau_max=tau_max, evals=obj.evals)
        it += 1
    return obj.result("ACO", start)


# =========================================================================== NSGA-II
@dataclass
class ParetoResult:
    algorithm: str
    front: list          # [(routes, Evaluation)] solusi feasible non-dominated
    runtime_s: float
    n_evals: int
    snapshots: list      # [(evals, [objektif ternormalisasi front feasible])]


def _dominates(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and (a[0] < b[0] or a[1] < b[1])


def _constrained_dominates(oa, va, ob, vb):
    """Aturan Deb: feasible > infeasible; sesama infeasible -> violation kecil menang."""
    if va == 0 and vb == 0:
        return _dominates(oa, ob)
    if va == 0:
        return True
    if vb == 0:
        return False
    return va < vb


def _fast_nondominated_sort(objs, viol):
    N = len(objs)
    S = [[] for _ in range(N)]
    count = np.zeros(N, dtype=int)
    fronts = [[]]
    for p in range(N):
        for q in range(p + 1, N):
            if _constrained_dominates(objs[p], viol[p], objs[q], viol[q]):
                S[p].append(q)
                count[q] += 1
            elif _constrained_dominates(objs[q], viol[q], objs[p], viol[p]):
                S[q].append(p)
                count[p] += 1
    fronts[0] = [p for p in range(N) if count[p] == 0]
    i = 0
    while fronts[i]:
        nxt = []
        for p in fronts[i]:
            for q in S[p]:
                count[q] -= 1
                if count[q] == 0:
                    nxt.append(q)
        i += 1
        fronts.append(nxt)
    return fronts[:-1]


def _crowding(objs, front):
    dist = {p: 0.0 for p in front}
    if len(front) <= 2:
        return {p: math.inf for p in front}
    for k in range(2):
        srt = sorted(front, key=lambda p: objs[p][k])
        lo, hi = objs[srt[0]][k], objs[srt[-1]][k]
        dist[srt[0]] = dist[srt[-1]] = math.inf
        if hi == lo:
            continue
        for a, b, c in zip(srt[:-2], srt[1:-1], srt[2:]):
            dist[b] += (objs[c][k] - objs[a][k]) / (hi - lo)
    return dist


def run_nsga2(inst, budget, rng, pop_size=100, p_crossover=0.9, p_mutation=0.3,
              snapshot_every=None, trace=None, **_):
    """Individu = (urutan sekolah, gen bobot wg in [0,1]). Gen wg mengatur decoder
    (decode_order) lebih hemat bensin atau lebih cepat, sehingga populasi bisa
    menyebar sepanjang Pareto front. snapshot_every: simpan front tiap k generasi."""
    start = time.perf_counter()
    evals = 0

    def evaluate(ind):
        nonlocal evals
        evals += 1
        ev = inst.evaluate(decode_order(inst, ind[0].tolist(), ind[1]))
        return (ev.cost / inst.ref_cost, ev.mean_arrival / inst.ref_time), ev.violation

    def crossover(p1, p2):
        order = enc.order_crossover(p1[0], p2[0], rng)
        a = rng.random()
        return order, a * p1[1] + (1 - a) * p2[1]

    def mutate(ind):
        order = enc.neighbor(ind[0], rng)
        return order, float(np.clip(ind[1] + rng.normal(0, 0.1), 0.0, 1.0))

    pop = [(rng.permutation(inst.n), float(rng.random())) for _ in range(pop_size)]
    scored = [evaluate(p) for p in pop]
    objs = [s[0] for s in scored]
    viol = [s[1] for s in scored]

    def rank_and_crowd(objs, viol):
        fronts = _fast_nondominated_sort(objs, viol)
        rank, crowd = {}, {}
        for r, fr in enumerate(fronts):
            crowd.update(_crowding(objs, fr))
            for p in fr:
                rank[p] = r
        return fronts, rank, crowd

    fronts, rank, crowd = rank_and_crowd(objs, viol)
    if trace:
        trace("nsga_gen", gen=0, pop=pop, objs=objs, viol=viol, fronts=fronts, evals=evals)
    snapshots = []
    gen = 0
    while evals + pop_size <= budget:
        def tournament():
            a, b = rng.choice(pop_size, 2, replace=False)
            if rank[a] != rank[b]:
                return pop[a] if rank[a] < rank[b] else pop[b]
            return pop[a] if crowd[a] >= crowd[b] else pop[b]

        children = []
        while len(children) < pop_size:
            p1, p2 = tournament(), tournament()
            child = crossover(p1, p2) if rng.random() < p_crossover else (p1[0].copy(), p1[1])
            if rng.random() < p_mutation:
                child = mutate(child)
            children.append(child)
        c_scored = [evaluate(c) for c in children]

        # seleksi elitis (mu + lambda)
        all_pop = pop + children
        all_objs = objs + [s[0] for s in c_scored]
        all_viol = viol + [s[1] for s in c_scored]
        fronts_all, _, _ = rank_and_crowd(all_objs, all_viol)
        chosen = []
        for fr in fronts_all:
            if len(chosen) + len(fr) <= pop_size:
                chosen.extend(fr)
            else:
                cd = _crowding(all_objs, fr)
                chosen.extend(sorted(fr, key=lambda p: -cd[p])[:pop_size - len(chosen)])
                break
        pop = [all_pop[i] for i in chosen]
        objs = [all_objs[i] for i in chosen]
        viol = [all_viol[i] for i in chosen]
        fronts, rank, crowd = rank_and_crowd(objs, viol)
        gen += 1
        if trace:
            trace("nsga_gen", gen=gen, pop=pop, objs=objs, viol=viol, fronts=fronts, evals=evals)
        if snapshot_every and gen % snapshot_every == 0:
            snapshots.append((evals, [objs[i] for i in fronts[0] if viol[i] == 0]))

    # front akhir: solusi feasible non-dominated, tanpa duplikat nilai objektif
    seen, front = set(), []
    for i in fronts[0]:
        if viol[i] != 0:
            continue
        key = (round(objs[i][0], 9), round(objs[i][1], 9))
        if key in seen:
            continue
        seen.add(key)
        routes = decode_order(inst, pop[i][0].tolist(), pop[i][1])
        front.append((routes, inst.evaluate(routes)))
    front.sort(key=lambda x: x[1].cost)
    return ParetoResult("NSGA-II", front, time.perf_counter() - start, evals, snapshots)
