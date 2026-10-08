"""Representasi permutasi-dengan-pemisah (dipakai SA, GA, NSGA-II).

Kromosom = permutasi token 0..n+R-2:
  token < n   -> sekolah
  token >= n  -> pemisah antar kendaraan (ada R-1 pemisah, R = total kendaraan)
Segmen ke-k (di antara pemisah) adalah urutan kunjungan kendaraan ke-k, yang
berangkat dari SPPG vehicle_depot[k]. Segmen kosong = kendaraan tidak dipakai.

Contoh n=4 sekolah, R=3 kendaraan:  [2, 0, 4, 5, 3, 1]
  kendaraan 0: sekolah 2 -> 0, kendaraan 1: (kosong), kendaraan 2: sekolah 3 -> 1
"""
import numpy as np


def random_solution(inst, rng):
    return rng.permutation(inst.n + inst.R - 1)


def decode(inst, perm):
    n = inst.n
    routes = [[] for _ in range(inst.R)]
    k = 0
    for g in perm.tolist():
        if g >= n:
            k += 1
        else:
            routes[k].append(g)
    return [(inst.vehicle_depot[k], seq) for k, seq in enumerate(routes)]


def encode(inst, routes):
    """Kebalikan decode: rute (depot, seq) -> permutasi. Dipakai untuk inisialisasi."""
    slots = {d: [k for k in range(inst.R) if inst.vehicle_depot[k] == d] for d in range(inst.m)}
    per_vehicle = [[] for _ in range(inst.R)]
    for d, seq in routes:
        if seq:
            per_vehicle[slots[d].pop(0)] = list(seq)
    perm, sep = [], inst.n
    for k, seq in enumerate(per_vehicle):
        perm.extend(seq)
        if k < inst.R - 1:
            perm.append(sep)
            sep += 1
    return np.array(perm)


# ----------------------------------------------------------------- operator mutasi
def swap(perm, rng):
    y = perm.copy()
    i, j = rng.choice(len(y), 2, replace=False)
    y[i], y[j] = y[j], y[i]
    return y


def insert(perm, rng):
    i, j = rng.choice(len(perm), 2, replace=False)
    y = np.delete(perm, i)
    return np.insert(y, j, perm[i])


def inversion(perm, rng):
    i, j = sorted(rng.choice(len(perm) + 1, 2, replace=False))
    y = perm.copy()
    y[i:j] = y[i:j][::-1]
    return y


MOVES = (swap, insert, inversion)


def neighbor(perm, rng):
    return MOVES[rng.integers(len(MOVES))](perm, rng)


# ---------------------------------------------------------------- operator crossover
def order_crossover(p1, p2, rng):
    """Order Crossover (OX): salin potongan p1, sisanya diisi urutan dari p2."""
    size = len(p1)
    i, j = sorted(rng.choice(size + 1, 2, replace=False))
    child = np.full(size, -1)
    child[i:j] = p1[i:j]
    taken = np.zeros(size, dtype=bool)
    taken[p1[i:j]] = True
    fill = [g for g in np.concatenate([p2[j:], p2[:j]]) if not taken[g]]
    positions = list(range(j, size)) + list(range(0, i))
    child[positions] = fill
    return child
