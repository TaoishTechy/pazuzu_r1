#!/usr/bin/env python3
"""Dependency-free paired statistics for the Pazuzu 1.0-R1 verification suite.

Implements exactly what blueprint §4.5 requires for P1/P2 recomputation:

  * means, standard deviations,
  * a paired t-test with an exact two-sided p-value via the regularized
    incomplete beta function (continued-fraction evaluation — Numerical
    Recipes §6.4),
  * a seeded paired permutation test as a distribution-free cross-check.

No third-party dependencies: the suite stays runnable on a bare CPython
install (blueprint §8 reproducibility goal; audit items 62/63).
"""
from __future__ import annotations

import math
import random
from statistics import fmean

__all__ = [
    "betainc", "student_t_two_sided_p", "paired_ttest",
    "permutation_paired_p", "summarize_pairs",
]

_EPS = 3.0e-14
_MAX_ITER = 300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    else:
        raise ArithmeticError("betacf failed to converge")
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b), 0 <= x <= 1."""
    if not 0.0 <= x <= 1.0:
        raise ValueError("x outside [0, 1]")
    if x == 0.0 or x == 1.0:
        return x
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided_p(t: float, df: float) -> float:
    """Exact two-sided p-value for Student-t with df degrees of freedom."""
    if df <= 0:
        raise ValueError("df must be positive")
    t = abs(float(t))
    if math.isinf(t):
        return 0.0
    return betainc(0.5 * df, 0.5, df / (df + t * t))


def paired_ttest(differences) -> dict:
    """Paired t-test on the sequence of per-pair differences.

    Returns {"n", "mean", "stdev", "t", "df", "p_two_sided"}.
    Requires n >= 2 and non-zero variance (else p = 1.0 by convention with
    t = 0.0 — recorded explicitly rather than silently).
    """
    d = [float(v) for v in differences]
    n = len(d)
    if n < 2:
        raise ValueError("paired t-test needs at least 2 pairs")
    mean = fmean(d)
    var = sum((v - mean) ** 2 for v in d) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0.0:
        if mean == 0.0:
            return {"n": n, "mean": 0.0, "stdev": 0.0, "t": 0.0,
                    "df": n - 1, "p_two_sided": 1.0, "degenerate": "zero variance"}
        return {"n": n, "mean": mean, "stdev": 0.0, "t": math.inf,
                "df": n - 1, "p_two_sided": 0.0, "degenerate": "zero variance"}
    t = mean / (sd / math.sqrt(n))
    return {"n": n, "mean": mean, "stdev": sd, "t": t,
            "df": n - 1, "p_two_sided": student_t_two_sided_p(t, n - 1)}


def permutation_paired_p(differences, n_perm: int = 10_000,
                         seed: int = 13) -> float:
    """Seeded paired permutation test (sign-flip) two-sided p-value.

    Deterministic for a given (data, n_perm, seed). Uses the |mean| statistic.
    """
    d = [float(v) for v in differences]
    n = len(d)
    if n < 2:
        raise ValueError("permutation test needs at least 2 pairs")
    observed = abs(fmean(d))
    if all(v == 0.0 for v in d):
        return 1.0
    rng = random.Random(seed)
    count = 0
    for _ in range(n_perm):
        s = 0.0
        for v in d:
            s += v if rng.random() < 0.5 else -v
        if abs(s / n) >= observed - 1e-15:
            count += 1
    return (count + 1) / (n_perm + 1)          # add-one correction


def summarize_pairs(pairs) -> dict:
    """Summarize paired (forcing, greedy) observations.

    `pairs` is an iterable of (forcing_value, greedy_value) tuples.
    Returns means, standard deviations (sample, n-1), mean difference and the
    paired t-test — exactly the statistics blueprint §4.5 requires recomputing
    from the raw CSV.
    """
    f = [float(p[0]) for p in pairs]
    g = [float(p[1]) for p in pairs]
    if len(f) != len(g):
        raise ValueError("paired vectors must have equal length")
    n = len(f)
    if n < 2:
        raise ValueError("need at least 2 pairs")

    def sd(vals, mean):
        return math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))

    mf, mg = fmean(f), fmean(g)
    diffs = [a - b for a, b in zip(f, g)]
    res = paired_ttest(diffs)
    return {
        "n": n,
        "forcing_mean": mf, "forcing_sd": sd(f, mf),
        "greedy_mean": mg, "greedy_sd": sd(g, mg),
        "mean_difference": res["mean"],
        "difference_sd": res["stdev"],
        "t": res["t"], "df": res["df"],
        "p_two_sided": res["p_two_sided"],
    }
