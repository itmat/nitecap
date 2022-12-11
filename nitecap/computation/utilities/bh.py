import numpy as np

def bh(P):
    """Benjamini-Hochberg FDR control"""

    P = np.array(P)
    (indices_of_finite_values,) = np.where(np.isfinite(P))

    p = P[indices_of_finite_values]

    sort_order = np.argsort(p)

    q = np.empty(p.size)
    q[sort_order] = p[sort_order] * p.size / np.arange(1, p.size + 1)

    running_minimum = 1
    for i in reversed(sort_order):
        q[i] = running_minimum = min(q[i], running_minimum)

    Q = np.full(P.size, np.nan)
    Q.put(indices_of_finite_values, q)

    return Q
