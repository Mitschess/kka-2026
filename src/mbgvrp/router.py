"""Evaluator rute optimal per SPPG untuk Bagian B (penugasan sekolah -> SPPG).

Untuk himpunan sekolah S milik SPPG d, rute optimalnya adalah partisi S menjadi
trip Granmax (<= Q sekolah per trip, urutan terbaik di dalam trip) dengan jumlah
biaya trip terkecil. Ini masalah yang sama dengan Bagian A (search.py) dan
hasilnya identik dengan UCS / A* (dicek di run_search.py), tetapi dihitung dengan
enumerasi lengkap supaya cukup cepat dipanggil ratusan ribu kali oleh algoritma
pencarian lokal:
  1. biaya tiap trip (himpunan <= Q sekolah) = urutan terbaik dari semua permutasi
     (maks. 3! = 6), disimpan di cache;
  2. semua partisi S menjadi <= V trip disiapkan sekali per ukuran |S| (template),
     lalu biaya semua partisi dijumlahkan sekaligus dengan numpy dan diambil minimum.
Kalau |S| > V*Q (SPPG kelebihan sekolah), dipakai jumlah Granmax minimum
ceil(|S|/Q) dan tiap Granmax di luar armada kena penalti. Keterlambatan di atas
batas 3 jam juga kena penalti. Semua biaya memakai skala fungsi objektif.
"""
import math
from itertools import combinations, permutations

import numpy as np

MAX_TEMPLATE = 60_000     # partisi terbanyak per template; di atas itu pakai DP rekursif
MAX_CACHE = 400_000       # batas entri cache biaya per SPPG (hemat RAM)


def _partitions(k, Q, min_b, max_b):
    """Semua partisi {0..k-1} menjadi min_b..max_b blok berukuran <= Q.
    Blok pertama selalu memuat elemen terkecil yang tersisa (tanpa duplikat)."""
    out = []

    def rec(rest, blocks):
        if not rest:
            if len(blocks) >= min_b:
                out.append(list(blocks))
            return
        if len(blocks) + -(-len(rest) // Q) > max_b or len(out) > MAX_TEMPLATE:
            return
        first, others = rest[0], rest[1:]
        for size in range(min(Q, len(rest))):
            for combo in combinations(others, size):
                left = [x for x in others if x not in combo]
                rec(left, blocks + [(first,) + combo])

    rec(list(range(k)), [])
    return out if len(out) <= MAX_TEMPLATE else None


class Router:
    def __init__(self, inst, w, penalty):
        self.inst, self.w, self.penalty = inst, w, penalty
        self.m, self.Q = inst.m, inst.Q
        self.V = list(inst.vehicles_per_depot)
        self.wc = w * inst.cost_per_km / inst.ref_cost
        self.wt = (1 - w) / (inst.n * inst.ref_time)
        self._trip = [{} for _ in range(inst.m)]   # bitmask trip -> (biaya, urutan)
        self._cost = [{} for _ in range(inst.m)]   # bitmask SPPG -> biaya rute optimal
        self._tpl = {}                             # (|S|, V) -> template partisi
        self.calls = 0                             # sub-masalah yang benar-benar dihitung

    # ------------------------------------------------------------------- trip
    def trip(self, d, tmask):
        hit = self._trip[d].get(tmask)
        if hit is not None:
            return hit
        inst, m = self.inst, self.m
        D, T = inst._D, inst._T
        schools = [b for b in range(inst.n) if tmask >> b & 1]
        best = (math.inf, None)
        for order in permutations(schools):
            prev, t, km, arr_sum, late = d, 0.0, 0.0, 0.0, 0.0
            for s in order:
                j = m + s
                t += T[prev][j]
                km += D[prev][j]
                arr_sum += t
                if t > inst.max_time:
                    late += t - inst.max_time
                t += inst.service
                prev = j
            if inst.return_to_depot:
                km += D[prev][d]
            c = self.wc * km + self.wt * arr_sum + self.penalty * late / 10.0
            if c < best[0]:
                best = (c, order)
        self._trip[d][tmask] = best
        return best

    # --------------------------------------------------------------- template
    def _template(self, k, V):
        key = (k, V)
        if key not in self._tpl:
            Q = self.Q
            need = -(-k // Q)
            parts = _partitions(k, Q, need, min(V, k)) if k <= V * Q else _partitions(k, Q, need, need)
            if parts is None:
                self._tpl[key] = None
            else:
                blocks = sorted({b for p in parts for b in p}, key=lambda b: (len(b), b))
                pos = {b: i for i, b in enumerate(blocks)}
                width = max(len(p) for p in parts)
                arr = np.full((len(parts), width), len(blocks), dtype=np.int32)  # kolom kosong -> 0
                for i, p in enumerate(parts):
                    arr[i, :len(p)] = [pos[b] for b in p]
                extra = np.array([self.penalty * max(0, len(p) - V) for p in parts])
                self._tpl[key] = (blocks, arr, extra)
        return self._tpl[key]

    # ------------------------------------------------------------- per SPPG
    def cost(self, d, mask):
        cache = self._cost[d]
        hit = cache.get(mask)
        if hit is None:
            hit = self._best(d, mask)[0]
            if len(cache) >= MAX_CACHE:
                cache.clear()
            cache[mask] = hit
        return hit

    def _best(self, d, mask):
        """(biaya optimal, daftar bitmask trip) untuk SPPG d dan himpunan mask."""
        if not mask:
            return 0.0, []
        self.calls += 1
        bits = []
        x = mask
        while x:
            low = x & -x
            bits.append(low)
            x ^= low
        tpl = self._template(len(bits), self.V[d])
        if tpl is None:
            return self._dp(d, bits)
        blocks, arr, extra = tpl
        costs = np.empty(len(blocks) + 1)
        costs[-1] = 0.0
        for i, b in enumerate(blocks):
            t = 0
            for j in b:
                t |= bits[j]
            costs[i] = self.trip(d, t)[0]
        total = costs[arr].sum(axis=1) + extra
        i = int(total.argmin())
        trips = [sum(bits[j] for j in blocks[c]) for c in arr[i] if c < len(blocks)]
        return float(total[i]), trips

    def _dp(self, d, bits):
        """Cadangan untuk |S| sangat besar: rekursi partisi + memo lokal."""
        memo = {}
        Q, V = self.Q, self.V[d]

        def solve(mask, r):
            if not mask:
                return 0.0, []
            key = (mask, r)
            if key not in memo:
                bs = [b for b in bits if mask & b]
                low, rest = bs[0], bs[1:]
                best = (math.inf, [])
                for size in range(min(Q, len(bs))):
                    for combo in combinations(rest, size):
                        t = low | sum(combo)
                        sub = solve(mask ^ t, max(r - 1, 0))
                        c = self.trip(d, t)[0] + (0.0 if r > 0 else self.penalty) + sub[0]
                        if c < best[0]:
                            best = (c, [t] + sub[1])
                memo[key] = best
            return memo[key]

        return solve(sum(bits), V)

    def routes(self, d, mask):
        """Rute optimal SPPG d: [(d, [sekolah, ...]), ...]."""
        return [(d, list(self.trip(d, t)[1])) for t in self._best(d, mask)[1]]

    def all_routes(self, masks):
        return [rt for d, mk in enumerate(masks) for rt in self.routes(d, mk)]
