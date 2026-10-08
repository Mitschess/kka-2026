"""Konstruksi solusi langkah demi langkah (dipakai Greedy dan ACO).

Di setiap langkah, opsi yang tersedia untuk tiap sekolah j yang belum dilayani:
  (a) tambahkan j di ujung rute yang masih punya kapasitas (< Q sekolah), atau
  (b) buka rute baru dari SPPG d yang masih punya Granmax menganggur.
Biaya inkremental opsi = w * dBiaya/ref_cost + (1-w) * waktu_tiba_j/(n*ref_time),
sehingga konsisten dengan fungsi objektif skalar.

Greedy memilih opsi dengan biaya inkremental terkecil (deterministik).
ACO memilih secara probabilistik dengan bobot tau^alpha * eta^beta, eta = 1/biaya.
"""
import numpy as np


def construct(inst, w, rng=None, tau=None, alpha=1.0, beta=1.0, trace=None):
    """trace: callback opsional trace(event, **data) untuk animasi (tidak mengubah hasil)."""
    m, n, Q = inst.m, inst.n, inst.Q
    D, T = inst.D, inst.T
    ret = inst.return_to_depot
    wc = w * inst.cost_per_km / inst.ref_cost
    wt = (1 - w) / (n * inst.ref_time)

    unvisited = np.ones(n, dtype=bool)
    spare = list(inst.vehicles_per_depot)
    routes = []          # [depot, [sekolah...]]
    last = []            # node terakhir tiap rute
    ready = []           # waktu siap berangkat dari node terakhir

    for _ in range(n):
        U = np.flatnonzero(unvisited)
        Unodes = U + m

        # baris opsi: rute terbuka yang belum penuh, lalu SPPG dengan Granmax tersisa
        open_r = [r for r in range(len(routes)) if len(routes[r][1]) < Q]
        new_d = [d for d in range(m) if spare[d] > 0]
        if not open_r and not new_d:  # armada habis: terpaksa melanggar kapasitas
            open_r = list(range(len(routes)))
        frm = np.array([last[r] for r in open_r] + new_d, dtype=int)
        dep = np.array([routes[r][0] for r in open_r] + new_d, dtype=int)
        t0 = np.array([ready[r] for r in open_r] + [0.0] * len(new_d))

        arrive = t0[:, None] + T[frm[:, None], Unodes[None, :]]
        ddist = D[frm[:, None], Unodes[None, :]]
        if ret:
            ddist = ddist + D[Unodes[None, :], dep[:, None]] - D[frm, dep][:, None]
        delta = wc * ddist + wt * arrive

        ok = arrive <= inst.max_time
        if not ok.any():
            ok[:] = True

        if tau is None:  # greedy
            flat = np.where(ok, delta, np.inf).argmin()
        else:
            tau_sub = tau[frm[:, None], Unodes[None, :]]
            if alpha != 1.0:
                tau_sub = tau_sub ** alpha
            weight = (tau_sub * (delta + 1e-9) ** -beta * ok).ravel()
            cum = np.cumsum(weight)  # roulette wheel (lebih cepat dari rng.choice(p=...))
            flat = min(int(np.searchsorted(cum, rng.random() * cum[-1], side="right")),
                       weight.size - 1)
        row, col = divmod(int(flat), U.size)
        s = int(U[col])

        if row < len(open_r):
            r = open_r[row]
        else:
            d = new_d[row - len(open_r)]
            spare[d] -= 1
            routes.append([d, []])
            last.append(d)
            ready.append(0.0)
            r = len(routes) - 1
        routes[r][1].append(s)
        ready[r] = arrive[row, col] + inst.service
        last[r] = s + m
        unvisited[s] = False
        if trace is not None:
            trace("construct_step", routes=[(d, list(seq)) for d, seq in routes], school=s,
                  new_route=row >= len(open_r), arrive=float(arrive[row, col]),
                  delta=float(delta[row, col]), n_options=int(ok.sum()))

    return [(d, seq) for d, seq in routes]


def greedy(inst, w, trace=None):
    return construct(inst, w, trace=trace)


def decode_order(inst, order, w):
    """Decoder GA: sekolah diproses sesuai urutan kromosom, tiap sekolah ditaruh
    pada opsi (tambah di ujung rute / rute baru) dengan biaya inkremental terkecil."""
    m, Q, service, max_time = inst.m, inst.Q, inst.service, inst.max_time
    D, T = inst._D, inst._T
    ret = inst.return_to_depot
    wc = w * inst.cost_per_km / inst.ref_cost
    wt = (1 - w) / (inst.n * inst.ref_time)

    spare = list(inst.vehicles_per_depot)
    depot, seqs, last, ready = [], [], [], []
    for s in order:
        j = m + s
        best = (False, float("inf"), None, 0.0)   # (feasible, delta, opsi, waktu tiba)
        for r in range(len(seqs)):
            if len(seqs[r]) >= Q:
                continue
            i, d = last[r], depot[r]
            arr = ready[r] + T[i][j]
            dd = D[i][j] + (D[j][d] - D[i][d] if ret else 0.0)
            cand = (arr <= max_time, wc * dd + wt * arr, r, arr)
            if (cand[0], -cand[1]) > (best[0], -best[1]):
                best = cand
        for d in range(m):
            if spare[d] == 0:
                continue
            arr = T[d][j]
            dd = D[d][j] + (D[j][d] if ret else 0.0)
            cand = (arr <= max_time, wc * dd + wt * arr, -1 - d, arr)
            if (cand[0], -cand[1]) > (best[0], -best[1]):
                best = cand
        _, _, opt, arr = best
        if opt is None:  # armada & kapasitas habis: paksa ke rute pertama (melanggar)
            opt, arr = 0, ready[0] + T[last[0]][j]
        if opt < 0:
            d = -1 - opt
            spare[d] -= 1
            depot.append(d)
            seqs.append([])
            last.append(d)
            ready.append(0.0)
            opt = len(seqs) - 1
        seqs[opt].append(s)
        last[opt] = j
        ready[opt] = arr + service
    return list(zip(depot, seqs))
