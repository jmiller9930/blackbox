"""
fusion_engine.py

Purpose:
Fuse active signal outputs into one directional decision for RenaissanceV4.

Usage:
Used by the replay runner after all signal modules have been evaluated.

Version:
v1.0

Change History:
- v1.0 Initial Phase 4 implementation.
- v1.1 DV-ARCH-CORRECTION-009: geometric-mean contribution; MIN_FUSION_SCORE 0.35 from measured scale.
"""

from __future__ import annotations

from collections import Counter

from renaissance_v4.core.fusion_result import FusionResult
from renaissance_v4.core.signal_weights import get_signal_weight
from renaissance_v4.signals.signal_result import SignalResult

# DV-ARCH-CORRECTION-009: threshold aligned to measured GM contribution scale (see correction_v1.md).
# Legacy product form produced winning-side scores ~0.01 typical / ~0.11 max — unreachable vs 0.55.
MIN_FUSION_SCORE = 0.35
MAX_CONFLICT_SCORE = 0.45
MAX_OVERLAP_BUCKET_COUNT = 2
OVERLAP_PENALTY_PER_EXTRA_SIGNAL = 0.08

_EPS = 1e-12


def _geometric_mean_four(conf: float, edge: float, regime_fit: float, stability: float) -> float:
    """Fourth root of four factors in [0,1] (with epsilon floors); preserves ordering, avoids product collapse."""
    c = max(conf, _EPS)
    e = max(edge, _EPS)
    rf = max(regime_fit, _EPS)
    st = max(stability, _EPS)
    return (c * e * rf * st) ** 0.25


def _directional_contribution(signal: SignalResult) -> float:
    """
    Weighted directional contribution before overlap adjustments.

    Uses **geometric mean** of confidence, expected_edge, regime_fit, stability (times signal weight).
    The prior **product** form collapsed typical scores to ~1e-2 while MIN_FUSION_SCORE was 0.55, so fusion
    never emitted long/short on full history (diagnostic_v1.md).
    """
    if not signal.active or signal.direction not in {"long", "short"}:
        return 0.0

    base_weight = get_signal_weight(signal.signal_name)
    gm = _geometric_mean_four(
        max(signal.confidence, 0.0),
        max(signal.expected_edge, 0.0),
        max(signal.regime_fit, 0.0),
        max(signal.stability_score, 0.0),
    )
    return gm * base_weight


def _signal_bucket(signal_name: str) -> str:
    """
    Collapse signal names into coarse buckets so similar hypotheses can be overlap-penalized.
    """
    if signal_name in {"trend_continuation", "pullback_continuation"}:
        return "trend_family"
    if signal_name == "breakout_expansion":
        return "breakout_family"
    if signal_name == "mean_reversion_fade":
        return "mean_reversion_family"
    return "other"


def fuse_signal_results(
    signal_results: list[SignalResult],
    *,
    min_fusion_score: float | None = None,
    max_conflict_score: float | None = None,
    overlap_penalty_per_extra_signal: float | None = None,
) -> FusionResult:
    """
    Fuse active signal results into one directional output.
    Prefers no_trade whenever evidence is weak, conflicted, or overly redundant.

    Optional overrides (from manifest / memory bundle) default to module constants when None.
    """
    min_fs = MIN_FUSION_SCORE if min_fusion_score is None else float(min_fusion_score)
    max_cf = MAX_CONFLICT_SCORE if max_conflict_score is None else float(max_conflict_score)
    pen = (
        OVERLAP_PENALTY_PER_EXTRA_SIGNAL
        if overlap_penalty_per_extra_signal is None
        else float(overlap_penalty_per_extra_signal)
    )

    long_score = 0.0
    short_score = 0.0
    contributing_signals: list[str] = []
    suppressed_signals: list[str] = []
    active_buckets: list[str] = []

    for result in signal_results:
        if result.active and result.direction in {"long", "short"}:
            contribution = _directional_contribution(result)
            contributing_signals.append(f"{result.signal_name}:{result.direction}:{contribution:.4f}")
            active_buckets.append(_signal_bucket(result.signal_name))

            if result.direction == "long":
                long_score += contribution
            elif result.direction == "short":
                short_score += contribution
        else:
            suppressed_signals.append(f"{result.signal_name}:{result.suppression_reason}")

    gross_score = long_score + short_score

    conflict_score = 0.0
    if gross_score > 0:
        conflict_score = min(long_score, short_score) / gross_score

    bucket_counts = Counter(active_buckets)
    overlap_penalty = 0.0
    for bucket_name, count in bucket_counts.items():
        if count > MAX_OVERLAP_BUCKET_COUNT:
            extra = count - MAX_OVERLAP_BUCKET_COUNT
            penalty = extra * pen
            overlap_penalty += penalty
            print(
                f"[fusion_engine] Overlap penalty applied bucket={bucket_name} "
                f"count={count} penalty={penalty:.4f}"
            )

    raw_winning_score = max(long_score, short_score)
    fusion_score = max(0.0, raw_winning_score - overlap_penalty)

    direction = "no_trade"
    threshold_passed = False

    if gross_score == 0:
        direction = "no_trade"
    elif conflict_score > max_cf:
        direction = "no_trade"
    elif fusion_score >= min_fs:
        direction = "long" if long_score > short_score else "short"
        threshold_passed = True
    else:
        direction = "no_trade"

    result = FusionResult(
        direction=direction,
        fusion_score=fusion_score,
        long_score=long_score,
        short_score=short_score,
        gross_score=gross_score,
        conflict_score=conflict_score,
        overlap_penalty=overlap_penalty,
        threshold_passed=threshold_passed,
        contributing_signals=contributing_signals,
        suppressed_signals=suppressed_signals,
        debug_trace={
            "min_fusion_score": min_fs,
            "max_conflict_score": max_cf,
            "bucket_counts": dict(bucket_counts),
        },
    )

    print(
        "[fusion_engine] Fused decision "
        f"direction={result.direction} fusion_score={result.fusion_score:.4f} "
        f"long_score={result.long_score:.4f} short_score={result.short_score:.4f} "
        f"conflict_score={result.conflict_score:.4f} overlap_penalty={result.overlap_penalty:.4f}"
    )

    return result
