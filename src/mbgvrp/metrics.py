"""Metrik evaluasi multi-objective."""


def nondominated(points):
    """Ambil titik non-dominated (minimasi kedua objektif) dari list (f1, f2)."""
    pts = sorted(set(points))
    front, best_f2 = [], float("inf")
    for f1, f2 in pts:
        if f2 < best_f2:
            front.append((f1, f2))
            best_f2 = f2
    return front


def hypervolume_2d(points, ref):
    """Luas daerah yang didominasi front dan dibatasi titik referensi ref (minimasi)."""
    front = [p for p in nondominated(points) if p[0] < ref[0] and p[1] < ref[1]]
    hv, prev_f2 = 0.0, ref[1]
    for f1, f2 in front:  # terurut f1 naik, f2 turun
        hv += (ref[0] - f1) * (prev_f2 - f2)
        prev_f2 = f2
    return hv
