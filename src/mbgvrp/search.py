"""Bagian A — routing di dalam satu SPPG dengan algoritma pencarian (Kuliah 2 & 3).

Sub-masalah: SPPG d melayani himpunan sekolah S dengan <= V Granmax, tiap Granmax
<= Q sekolah, semuanya berangkat bersamaan di t = 0.

Keadaan (state) = (sisa, posisi, muatan, t, dipakai, pembuka)
  sisa    : bitmask sekolah yang belum dilayani (bit b = sekolah lokal b, node b+1)
  posisi  : node lokal saat ini (0 = SPPG, 1..k = sekolah)
  muatan  : jumlah sekolah yang sudah dilayani Granmax yang sedang jalan
  t       : waktu siap berangkat dari posisi (menit, sudah termasuk drop 15 menit)
  dipakai : jumlah Granmax yang sudah diberangkatkan
  pembuka : sekolah pertama Granmax terakhir. Pemecah simetri: Granmax berikutnya
            harus dibuka sekolah bernomor lebih besar, jadi himpunan rute yang sama
            tidak muncul dalam 3! urutan Granmax yang berbeda.
Aksi:
  kunjungi(s) : antar ke sekolah s (dari SPPG = memberangkatkan Granmax baru)
  pulang      : Granmax kembali ke SPPG
Goal: sisa kosong dan posisi = SPPG.

Biaya langkah memakai fungsi objektif masalah penuh:
  w * Rp(jarak) / ref_cost + (1 - w) * waktu_tiba / (n * ref_time)
sehingga biaya jalur = kontribusi SPPG ini ke fitness total. Anak yang tiba lewat
batas 3 jam, atau yang sisanya tidak mungkin terangkut Granmax tersisa, dipangkas.
"""
import heapq
import math
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

PULANG = 0  # aksi pulang = menuju node 0 (SPPG)


@dataclass
class SearchResult:
    algorithm: str
    status: str            # "ok", "gagal" (ruang habis), "batas" (melewati batas node)
    cost: float            # biaya jalur (inf jika tidak ketemu)
    routes: list           # [(depot, [sekolah global, ...]), ...]
    expanded: int          # node yang diekspansi
    generated: int         # node yang dibangkitkan
    max_stored: int        # node terbanyak yang disimpan bersamaan (proksi memori)
    runtime_s: float
    extra: dict = field(default_factory=dict)


class _Node:
    __slots__ = ("state", "g", "parent", "action", "depth")

    def __init__(self, state, g=0.0, parent=None, action=None):
        self.state, self.g, self.parent, self.action = state, g, parent, action
        self.depth = parent.depth + 1 if parent else 0


class _Limit(Exception):
    pass


class RoutingProblem:
    def __init__(self, inst, depot, schools, w, vehicles=None):
        self.inst, self.depot = inst, depot
        self.schools = list(schools)
        self.k = len(self.schools)
        nodes = [depot] + [inst.m + s for s in self.schools]
        self.D = [[float(inst.D[i, j]) for j in nodes] for i in nodes]
        self.T = [[float(inst.T[i, j]) for j in nodes] for i in nodes]
        self.V = inst.vehicles_per_depot[depot] if vehicles is None else vehicles
        self.Q, self.service, self.max_time = inst.Q, inst.service, inst.max_time
        self.ret = inst.return_to_depot
        self.wc = w * inst.cost_per_km / inst.ref_cost
        self.wt = (1 - w) / (inst.n * inst.ref_time)
        self.initial = ((1 << self.k) - 1, 0, 0, 0.0, 0, 0)

    # ------------------------------------------------------------- model masalah
    def is_goal(self, st):
        return st[0] == 0 and st[1] == 0

    def key(self, st):
        """Kunci deteksi duplikat. t hanya memengaruhi masa depan selama Granmax
        masih bisa menambah sekolah, jadi di luar itu diabaikan."""
        rem, pos, load, t, used, opener = st
        return (rem, pos, load, t if 0 < load < self.Q else 0.0, used, opener)

    def successors(self, st):
        """Daftar (aksi, state_anak, biaya_langkah)."""
        rem, pos, load, t, used, opener = st
        Q, V, D, T = self.Q, self.V, self.D, self.T
        out = []
        if pos:
            if rem.bit_count() <= (V - used) * Q:
                out.append((PULANG, (rem, 0, 0, 0.0, used, opener),
                            self.wc * D[pos][0] if self.ret else 0.0))
            if load == Q:
                return out
        elif used == V:
            return out
        r = rem
        while r:
            low = r & -r
            r ^= low
            i = low.bit_length()
            if not pos and i <= opener:
                continue
            arr = t + T[pos][i]
            if arr > self.max_time:
                continue
            rem2 = rem ^ low
            if pos:
                load2, used2, opener2 = load + 1, used, opener
            else:
                load2, used2, opener2 = 1, used + 1, i
            if rem2.bit_count() > (Q - load2) + (V - used2) * Q:
                continue
            out.append((i, (rem2, i, load2, arr + self.service, used2, opener2),
                        self.wc * D[pos][i] + self.wt * arr))
        return out

    @staticmethod
    def _nodes(rem):
        idx = []
        while rem:
            low = rem & -rem
            rem ^= low
            idx.append(low.bit_length())
        return idx

    def h(self, st):
        """Heuristik admissible h2 (relaksasi penugasan slot). Tiap sekolah tersisa
        harus menempati satu slot = (Granmax, urutan ke-p). Untuk tiap jenis slot
        dihitung batas bawah jarak masuk & waktu tiba sekolah s di slot itu:
          Granmax baru, urutan 1     : dari SPPG langsung
          Granmax baru, urutan p >= 2: lewat p-1 sekolah tersisa lain (+ drop 15 menit)
          Granmax berjalan, urutan q : lanjut dari posisi sekarang
        Tiap urutan hanya punya satu slot per Granmax, jadi tidak semua sekolah bisa
        dihitung "langsung dari SPPG". Penugasan sekolah -> slot dengan biaya total
        minimum (algoritma Hungaria) <= biaya sebenarnya. Ditambah jalan pulang:
        minimal satu per Granmax yang masih harus berangkat/pulang."""
        rem, pos, load, t, used, _ = st
        D, T, svc, Q = self.D, self.T, self.service, self.Q
        if not rem:
            return self.wc * D[pos][0] if pos and self.ret else 0.0
        idx = self._nodes(rem)
        k_new = self.V - used
        cont = pos and load < Q
        din = [min((D[x][s] for x in idx if x != s), default=math.inf) for s in idx]
        cols = []

        def chain(arr, fuel, n_pos, copies):
            cols.extend([[self.wc * f + self.wt * a for f, a in zip(fuel, arr)]] * copies)
            for _ in range(n_pos - 1):
                arr = [min((arr[j] + svc + T[x][s] for j, x in enumerate(idx) if x != s),
                           default=math.inf) for s in idx]
                cols.extend([[self.wc * f + self.wt * a for f, a in zip(din, arr)]] * copies)

        if k_new > 0:
            chain([T[0][s] for s in idx], [D[0][s] for s in idx], Q, min(k_new, len(idx)))
        if cont:
            chain([t + T[pos][s] for s in idx], [D[pos][s] for s in idx], Q - load, 1)
        C = np.array(cols).T
        C[~np.isfinite(C)] = 1e9
        rows, cs = linear_sum_assignment(C)
        val = float(C[rows, cs].sum())
        if self.ret:
            n_new = max(0, -(-(len(idx) - (Q - load if cont else 0)) // Q))
            ends = sorted(D[s][0] for s in idx)
            if pos and load == Q:
                val += self.wc * (D[pos][0] + sum(ends[:n_new]))
            elif pos:
                val += self.wc * sum(sorted(ends + [D[pos][0]])[:n_new + 1])
            else:
                val += self.wc * sum(ends[:n_new])
        return val

    def h_nearest(self, st):
        """Heuristik admissible h1 (sederhana): tiap sekolah tersisa butuh satu jalan
        masuk dan satu waktu tiba; ambil yang termurah dari semua kemungkinan
        asalnya (SPPG = Granmax baru, posisi sekarang, atau sekolah tersisa
        terdekat), ditambah minimal satu jalan pulang ke SPPG."""
        rem, pos, load, t, used, _ = st
        D, T, svc = self.D, self.T, self.service
        if not rem:
            return self.wc * D[pos][0] if pos and self.ret else 0.0
        idx = self._nodes(rem)
        new_ok = used < self.V
        cont = pos and load < self.Q
        # batas bawah waktu tiba "langsung" (tanpa lewat sekolah tersisa lain)
        direct = {}
        for s in idx:
            a = T[0][s] if new_ok else math.inf
            if cont:
                a = min(a, t + T[pos][s])
            direct[s] = a
        lb = {s: min(direct[s], min((svc + T[x][s] for x in idx if x != s), default=math.inf))
              for s in idx}
        fuel = tsum = 0.0
        for s in idx:
            dmin = D[0][s] if new_ok else math.inf
            if cont:
                dmin = min(dmin, D[pos][s])
            amin = direct[s]
            for x in idx:
                if x != s:
                    if D[x][s] < dmin:
                        dmin = D[x][s]
                    a = lb[x] + svc + T[x][s]
                    if a < amin:
                        amin = a
            fuel += dmin
            tsum += amin
        if self.ret:
            fuel += min(D[s][0] for s in idx)
            if pos and load == self.Q:
                fuel += D[pos][0]
        return self.wc * fuel + self.wt * tsum

    # ------------------------------------------------------------------ utilitas
    def routes_of(self, node):
        actions = []
        while node.parent is not None:
            actions.append(node.action)
            node = node.parent
        routes, cur = [], None
        for a in reversed(actions):
            if a == PULANG:
                cur = None
            else:
                if cur is None:
                    cur = []
                    routes.append((self.depot, cur))
                cur.append(self.schools[a - 1])
        return routes

    def _result(self, name, node, stats, start, status=None, extra=None):
        found = node is not None
        return SearchResult(name, status or ("ok" if found else "gagal"),
                            node.g if found else math.inf,
                            self.routes_of(node) if found else [],
                            stats["expanded"], stats["generated"], stats["max_stored"],
                            time.perf_counter() - start, extra or {})


def _children(problem, node, stats, max_nodes):
    kids = [_Node(st, node.g + c, node, a) for a, st, c in problem.successors(node.state)]
    stats["generated"] += len(kids)
    if stats["generated"] > max_nodes:
        raise _Limit
    return kids


def _new_stats():
    return {"expanded": 0, "generated": 1, "max_stored": 1}


# ============================================================== pencarian buta
def breadth_first(problem, max_nodes=2_000_000, trace=None):
    """BFS (graph search, goal test saat dibangkitkan): menemukan solusi dengan
    jumlah langkah paling sedikit = Granmax paling sedikit, bukan yang termurah.

    `trace(event, **data)` opsional, hanya dipakai make_animation.py untuk merekam
    jalannya algoritma. Tidak memakai rng, jadi hasil run tidak berubah."""
    start, stats = time.perf_counter(), _new_stats()
    root = _Node(problem.initial)
    if trace:
        trace("start", node=root)
    if problem.is_goal(root.state):
        return problem._result("BFS", root, stats, start)
    frontier, reached = deque([root]), {problem.key(root.state)}
    try:
        while frontier:
            node = frontier.popleft()
            stats["expanded"] += 1
            if trace:
                trace("expand", node=node, frontier=len(frontier))
            for child in _children(problem, node, stats, max_nodes):
                if problem.is_goal(child.state):
                    if trace:
                        trace("goal", node=child)
                    return problem._result("BFS", child, stats, start)
                k = problem.key(child.state)
                kept = k not in reached
                if kept:
                    reached.add(k)
                    frontier.append(child)
                if trace:
                    trace("child", parent=node, child=child, kept=kept)
            stats["max_stored"] = max(stats["max_stored"], len(reached))
    except _Limit:
        return problem._result("BFS", None, stats, start, "batas")
    return problem._result("BFS", None, stats, start)


def iterative_deepening(problem, max_nodes=20_000_000):
    """IDS: depth-limited DFS dengan batas kedalaman 0, 1, 2, ... (tree search).
    Hasilnya sama dengan BFS (solusi terdangkal), memorinya seperti DFS."""
    start, stats = time.perf_counter(), _new_stats()
    try:
        for limit in range(problem.k + problem.V + 1):
            stack, cutoff = [_Node(problem.initial)], False
            while stack:
                node = stack.pop()
                if problem.is_goal(node.state):
                    return problem._result("IDS", node, stats, start, extra={"depth": limit})
                if node.depth == limit:
                    cutoff = True
                    continue
                stats["expanded"] += 1
                stack.extend(reversed(_children(problem, node, stats, max_nodes)))
                stats["max_stored"] = max(stats["max_stored"], len(stack))
            if not cutoff:
                break
    except _Limit:
        return problem._result("IDS", None, stats, start, "batas")
    return problem._result("IDS", None, stats, start)


def dfs_branch_and_bound(problem, max_nodes=20_000_000, trace=None):
    """DFS + Branch and Bound: telusuri dalam-dulu (anak termurah dulu), simpan
    solusi terbaik sejauh ini, pangkas cabang yang biayanya sudah >= solusi itu."""
    start, stats = time.perf_counter(), _new_stats()
    best, n_sol = None, 0
    stack = [_Node(problem.initial)]
    if trace:
        trace("start", node=stack[0])
    try:
        while stack:
            node = stack.pop()
            if best is not None and node.g >= best.g:
                if trace:
                    trace("prune", node=node, best=best)
                continue
            if problem.is_goal(node.state):
                best, n_sol = node, n_sol + 1
                if trace:
                    trace("incumbent", node=node)
                continue
            stats["expanded"] += 1
            if trace:
                trace("expand", node=node, frontier=len(stack))
            kids = _children(problem, node, stats, max_nodes)
            kids.sort(key=lambda c: -c.g)   # termurah paling atas tumpukan
            stack.extend(c for c in kids if best is None or c.g < best.g)
            if trace:
                for c in kids:
                    trace("child", parent=node, child=c, kept=(best is None or c.g < best.g))
            stats["max_stored"] = max(stats["max_stored"], len(stack))
    except _Limit:
        return problem._result("DFS-B&B", best, stats, start, "batas", {"incumbents": n_sol})
    return problem._result("DFS-B&B", best, stats, start, extra={"incumbents": n_sol})


# ======================================================== best-first search
def _best_first(problem, name, f, max_nodes, trace=None):
    """Best-first graph search (AIMA): ambil node dengan f terkecil; jalur yang
    lebih murah ke keadaan yang sama menggantikan jalur lama."""
    start, stats = time.perf_counter(), _new_stats()
    root = _Node(problem.initial)
    reached = {problem.key(root.state): root}
    frontier, tie = [(f(root), 0, root)], 1
    if trace:
        trace("start", node=root)
    try:
        while frontier:
            _, _, node = heapq.heappop(frontier)
            if reached.get(problem.key(node.state)) is not node:
                continue   # sudah ada jalur lebih murah ke keadaan ini
            if problem.is_goal(node.state):
                if trace:
                    trace("goal", node=node)
                return problem._result(name, node, stats, start)
            stats["expanded"] += 1
            if trace:
                trace("expand", node=node, frontier=len(frontier))
            for child in _children(problem, node, stats, max_nodes):
                k = problem.key(child.state)
                old = reached.get(k)
                kept = old is None or child.g < old.g
                if kept:
                    reached[k] = child
                    heapq.heappush(frontier, (f(child), tie, child))
                    tie += 1
                if trace:
                    trace("child", parent=node, child=child, kept=kept)
            stats["max_stored"] = max(stats["max_stored"], len(reached))
    except _Limit:
        return problem._result(name, None, stats, start, "batas")
    return problem._result(name, None, stats, start)


def uniform_cost(problem, max_nodes=5_000_000, trace=None):
    """UCS: f(n) = g(n), biaya jalur sejauh ini. Optimal."""
    return _best_first(problem, "UCS", lambda n: n.g, max_nodes, trace)


def astar(problem, max_nodes=5_000_000, trace=None):
    """A*: f(n) = g(n) + h(n), h admissible -> optimal dengan ekspansi lebih sedikit."""
    return _best_first(problem, "A*", lambda n: n.g + problem.h(n.state), max_nodes, trace)


def astar_h1(problem, max_nodes=5_000_000, trace=None):
    """A* dengan heuristik sederhana h1 (pembanding kekuatan heuristik)."""
    return _best_first(problem, "A* (h1)", lambda n: n.g + problem.h_nearest(n.state), max_nodes, trace)


def greedy_best_first(problem, max_nodes=5_000_000, trace=None):
    """Greedy best-first: f(n) = h(n) saja. Cepat, tidak menjamin optimal."""
    return _best_first(problem, "GBFS", lambda n: problem.h(n.state), max_nodes, trace)


SEARCHES = {
    "BFS": breadth_first,
    "IDS": iterative_deepening,
    "DFS-B&B": dfs_branch_and_bound,
    "UCS": uniform_cost,
    "A* (h1)": astar_h1,
    "A*": astar,
    "GBFS": greedy_best_first,
}
