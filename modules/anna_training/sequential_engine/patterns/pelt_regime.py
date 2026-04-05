"""PELT changepoint detection (ruptures) — structural regime boundaries."""

from __future__ import annotations

from typing import Any

import numpy as np


def run_pelt_changepoints(
    series: np.ndarray,
    *,
    penalty: float,
    model: str = "l2",
) -> dict[str, Any]:
    """
    PELT on a 1-D series (e.g. log returns).

    ``model`` is passed to ruptures (e.g. ``l2``, ``rbf``).
    """
    import ruptures as rpt

    x = np.asarray(series, dtype=float).ravel()
    if x.size < 3:
        raise ValueError("series must have length >= 3 for PELT")
    algo = rpt.Pelt(model=model).fit(x.reshape(-1, 1))
    bkps = algo.predict(pen=penalty)
    # ruptures returns last index = n; strip
    edges = [int(b) for b in bkps if b < len(x)]
    return {
        "method": "PELT",
        "ruptures_version": getattr(rpt, "__version__", "unknown"),
        "model": model,
        "penalty": float(penalty),
        "n": int(x.size),
        "changepoints_end_exclusive": edges,
        "pattern_spec_hash_inputs": {
            "method": "PELT",
            "penalty": float(penalty),
            "model": model,
            "ruptures_version": getattr(rpt, "__version__", "unknown"),
        },
    }
