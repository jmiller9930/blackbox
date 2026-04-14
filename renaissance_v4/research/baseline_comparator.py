"""
Compare deterministic and Monte Carlo summaries: candidate vs locked baseline reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ComparisonResult:
    baseline_tag: str
    candidate_label: str
    deterministic: dict[str, Any]
    monte_carlo_baseline_by_mode: dict[str, dict[str, Any]]
    monte_carlo_candidate_by_mode: dict[str, dict[str, Any]]
    notes: list[str]


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def compare_summaries(
    *,
    baseline_tag: str,
    candidate_label: str,
    det_baseline: dict[str, Any],
    det_candidate: dict[str, Any],
    mc_baseline_by_mode: dict[str, dict[str, Any]],
    mc_candidate_by_mode: dict[str, dict[str, Any]],
) -> ComparisonResult:
    notes: list[str] = []
    # Cross-check trade counts
    tb, tc = int(det_baseline.get("total_trades", 0)), int(det_candidate.get("total_trades", 0))
    if tb == 0:
        notes.append("baseline deterministic trade count is zero — invalid comparison.")
    if tc == 0:
        notes.append("candidate deterministic trade count is zero — invalid comparison.")
    return ComparisonResult(
        baseline_tag=baseline_tag,
        candidate_label=candidate_label,
        deterministic={
            "baseline": det_baseline,
            "candidate": det_candidate,
            "delta_expectancy": _f(det_candidate.get("expectancy")) - _f(det_baseline.get("expectancy")),
            "delta_max_drawdown": _f(det_candidate.get("max_drawdown")) - _f(det_baseline.get("max_drawdown")),
            "delta_total_trades": tc - tb,
        },
        monte_carlo_baseline_by_mode=mc_baseline_by_mode,
        monte_carlo_candidate_by_mode=mc_candidate_by_mode,
        notes=notes,
    )
