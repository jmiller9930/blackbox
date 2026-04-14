"""
Rules-based recommendation: improve / degrade / inconclusive.

Does not auto-promote code — advisory only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Recommendation = Literal["improve", "degrade", "inconclusive"]


@dataclass
class RecommendationResult:
    label: Recommendation
    reasons: list[str]


def recommend(
    *,
    det_baseline: dict[str, Any],
    det_candidate: dict[str, Any],
    mc_mode: str,
    mc_baseline: dict[str, Any],
    mc_candidate: dict[str, Any],
    min_trades: int = 200,
    expectancy_epsilon: float = 1e-4,
    dd_tolerance_ratio: float = 1.15,
) -> RecommendationResult:
    """
    Version-1 rules:
    - degrade if candidate expectancy materially worse OR median Monte Carlo terminal worse with worse DD
    - improve if expectancy not worse, drawdown not materially worse, Monte Carlo median terminal >= baseline, p95 DD not worse
    - else inconclusive
    """
    reasons: list[str] = []
    tb = int(det_baseline.get("total_trades", 0))
    tc = int(det_candidate.get("total_trades", 0))
    eb = float(det_baseline.get("expectancy", 0.0))
    ec = float(det_candidate.get("expectancy", 0.0))
    ddb = float(det_baseline.get("max_drawdown", 0.0))
    ddc = float(det_candidate.get("max_drawdown", 0.0))

    if tc < min_trades:
        reasons.append(f"candidate trade count {tc} below minimum heuristic {min_trades}")
        return RecommendationResult("inconclusive", reasons)

    if ec < eb - expectancy_epsilon:
        reasons.append(f"deterministic expectancy degraded ({ec:.6f} vs baseline {eb:.6f})")
        if ddc > ddb * dd_tolerance_ratio:
            reasons.append(
                f"max drawdown worse by >{int((dd_tolerance_ratio - 1) * 100)}% ({ddc:.4f} vs {ddb:.4f})"
            )
        return RecommendationResult("degrade", reasons)

    mb = float(mc_baseline.get("median_terminal_pnl", 0.0))
    mc = float(mc_candidate.get("median_terminal_pnl", 0.0))
    ddb_mc = float(mc_baseline.get("median_max_drawdown", 0.0))
    ddc_mc = float(mc_candidate.get("median_max_drawdown", 0.0))
    fb = float(mc_baseline.get("fraction_terminal_negative", 0.0))
    fc = float(mc_candidate.get("fraction_terminal_negative", 0.0))

    worse_mc = mc < mb - abs(mb) * 0.05 - 1e-9 if mb != 0 else mc < mb
    worse_dd_mc = ddc_mc > ddb_mc * dd_tolerance_ratio
    worse_neg = fc > fb + 0.02

    if worse_mc and (worse_dd_mc or worse_neg):
        reasons.append(
            f"Monte Carlo ({mc_mode}): median terminal {mc:.6f} vs baseline {mb:.6f}; "
            f"median DD {ddc_mc:.4f} vs {ddb_mc:.4f}; negative-finish fraction {fc:.3f} vs {fb:.3f}"
        )
        return RecommendationResult("degrade", reasons)

    if ec >= eb - expectancy_epsilon and ddc <= ddb * dd_tolerance_ratio and mc >= mb - abs(mb) * 0.02 and not worse_dd_mc:
        reasons.append(
            f"deterministic expectancy maintained ({ec:.6f}), Monte Carlo median terminal {mc:.6f} vs {mb:.6f} on mode {mc_mode}"
        )
        return RecommendationResult("improve", reasons)

    reasons.append("mixed signals — use full Monte Carlo tables and deterministic deltas")
    return RecommendationResult("inconclusive", reasons)
