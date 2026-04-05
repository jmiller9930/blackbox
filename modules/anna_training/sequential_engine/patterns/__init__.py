"""Approved pattern detectors only — each returns a versioned pattern_spec dict."""

from __future__ import annotations

from modules.anna_training.sequential_engine.patterns.cusum_shift import run_cusum_monitor
from modules.anna_training.sequential_engine.patterns.matrix_profile_motif import run_matrix_profile_top_motif
from modules.anna_training.sequential_engine.patterns.pelt_regime import run_pelt_changepoints
from modules.anna_training.sequential_engine.patterns.rsi_divergence import run_rsi_divergence_scan

__all__ = [
    "run_cusum_monitor",
    "run_matrix_profile_top_motif",
    "run_pelt_changepoints",
    "run_rsi_divergence_scan",
]
