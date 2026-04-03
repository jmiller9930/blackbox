"""Engle-Granger cointegration test; simple Kalman local-level filter."""
from __future__ import annotations

from typing import Any

import numpy as np


def engle_granger_coint(
    a: list[float] | np.ndarray,
    b: list[float] | np.ndarray,
) -> dict[str, Any]:
    """Two integrated series; returns test stat and p-value (statsmodels)."""
    try:
        from statsmodels.tsa.stattools import coint
    except ImportError as e:
        return {"ok": False, "error": str(e)}
    aa = np.asarray(a, dtype=float).ravel()
    bb = np.asarray(b, dtype=float).ravel()
    n = min(len(aa), len(bb))
    if n < 20:
        return {"ok": False, "skipped": True, "reason": "need_two_series_len>=20"}
    aa, bb = aa[:n], bb[:n]
    try:
        out = coint(aa, bb)
        stat, pvalue = float(out[0]), float(out[1])
        crit = out[2] if len(out) > 2 else {}
        crit_flat = {str(k): float(v) for k, v in crit.items()} if isinstance(crit, dict) else {}
        return {
            "ok": True,
            "n": n,
            "statistic": stat,
            "pvalue": pvalue,
            "critical_values": crit_flat,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def kalman_local_level(
    y: np.ndarray | list[float],
    *,
    q: float = 1e-4,
    r: float = 1.0,
) -> dict[str, Any]:
    """
    Univariate local-level model: x_t = x_{t-1}+w, y_t = x_t+v.
    Simple forward filter (numpy); returns smoothed level at last step.
    """
    obs = np.asarray(y, dtype=float).ravel()
    obs = obs[np.isfinite(obs)]
    n = len(obs)
    if n < 3:
        return {"ok": False, "skipped": True, "reason": "insufficient_obs"}
    x = np.zeros(n)
    p = np.zeros(n)
    x[0] = obs[0]
    p[0] = 1.0
    for t in range(1, n):
        p_pred = p[t - 1] + q
        k = p_pred / (p_pred + r)
        x[t] = x[t - 1] + k * (obs[t] - x[t - 1])
        p[t] = (1 - k) * p_pred
    return {
        "ok": True,
        "n": n,
        "level_last": float(x[-1]),
        "q": q,
        "r": r,
    }
