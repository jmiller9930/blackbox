"""Matrix Profile (STOMP) — top motif discovery."""

from __future__ import annotations

from typing import Any

import numpy as np


def run_matrix_profile_top_motif(
    series: np.ndarray,
    *,
    window: int,
) -> dict[str, Any]:
    """
    STOMP matrix profile; returns global minimum distance motif index (start).
    """
    import stumpy

    x = np.asarray(series, dtype=float).ravel()
    m = int(window)
    if m < 3 or len(x) < m * 2:
        raise ValueError("series too short for window")
    mp = stumpy.stump(x, m=m)
    profile = mp[:, 0].astype(float)
    idx = int(np.argmin(profile))
    return {
        "method": "matrix_profile_stomp",
        "stumpy_version": getattr(stumpy, "__version__", "unknown"),
        "window": m,
        "n": int(x.size),
        "motif_start_index": idx,
        "matrix_profile_min": float(profile[idx]),
        "pattern_spec_hash_inputs": {
            "method": "matrix_profile_stomp",
            "window": m,
            "stumpy_version": getattr(stumpy, "__version__", "unknown"),
        },
    }
