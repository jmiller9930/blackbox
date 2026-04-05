"""Page CUSUM for mean shift — sequential monitoring statistic."""

from __future__ import annotations

from typing import Any

import numpy as np


def run_cusum_monitor(
    series: np.ndarray,
    *,
    reference_mean: float,
    sigma: float,
    k: float,
    h: float,
) -> dict[str, Any]:
    """
    Standard normal CUSUM: cumulative sums with allowance ``k`` and threshold ``h``.

    ``sigma`` scales residuals (series - reference_mean) / sigma.
    """
    x = np.asarray(series, dtype=float).ravel()
    if x.size < 2:
        raise ValueError("series must have length >= 2")
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    z = (x - reference_mean) / sigma
    gp = np.zeros_like(z)
    gn = np.zeros_like(z)
    for i in range(len(z)):
        gp[i] = max(0.0, gp[i - 1] + z[i] - k) if i else max(0.0, z[i] - k)
        gn[i] = max(0.0, gn[i - 1] - z[i] - k) if i else max(0.0, -z[i] - k)
    crossed = bool(np.max(gp) >= h or np.max(gn) >= h)
    return {
        "method": "CUSUM",
        "reference_mean": float(reference_mean),
        "sigma": float(sigma),
        "k": float(k),
        "h": float(h),
        "n": int(x.size),
        "cusum_pos_max": float(np.max(gp)),
        "cusum_neg_max": float(np.max(gn)),
        "threshold_crossed": crossed,
        "pattern_spec_hash_inputs": {
            "method": "CUSUM",
            "reference_mean": float(reference_mean),
            "sigma": float(sigma),
            "k": float(k),
            "h": float(h),
        },
    }
