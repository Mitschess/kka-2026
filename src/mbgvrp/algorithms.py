"""Algoritma yang dibandingkan.

Hanya algoritma dari slide kuliah (weighted sum, bobot w):
  - Greedy              : baseline konstruktif (cheapest append)
  - Hill Climbing       : random-restart, representasi permutasi + pemisah kendaraan
  - Simulated Annealing : representasi permutasi + pemisah kendaraan
  - Genetic Algorithm   : representasi urutan sekolah + decoder greedy

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
from .construct import decode_order, greedy


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


# ============================================================ Random-Restart Hill Climbing
def run_hc(inst, w, penalty, budget, rng, n_neighbors=50, trace=None, **_):
    """Hill climbing: tiap langkah ambil n_neighbors tetangga acak, pindah ke yang terbaik
    kalau lebih baik dari solusi sekarang. Tak ada yang lebih baik = local optimum, lalu
    restart dari solusi acak baru. Solusi terbaik dari semua restart dikembalikan."""
    start = time.perf_counter()
    obj = _Objective(inst, w, penalty)
    restarts = 0
    x = enc.random_solution(inst, rng)
    fx = obj.perm(x)
    if trace:
        trace("hc_start", x=x, fx=fx)
    while obj.evals + n_neighbors + 1 <= budget:
        cands = [enc.neighbor(x, rng) for _ in range(n_neighbors)]
        fits = [obj.perm(c) for c in cands]
        k = int(np.argmin(fits))
        improved = fits[k] < fx
        if trace:
            trace("hc_step", x=x, fx=fx, y=cands[k], fy=fits[k], improved=improved,
                  restarts=restarts, best_f=obj.best_f, best_routes=obj.best_routes,
                  evals=obj.evals)
        if improved:
            x, fx = cands[k], fits[k]
            continue
        restarts += 1
        x = enc.random_solution(inst, rng)
        fx = obj.perm(x)
    return obj.result("HC", start)
