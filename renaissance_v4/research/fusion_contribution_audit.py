"""
fusion_contribution_audit.py — read-only instrumentation for fusion contribution math.

Computes legacy (product) vs proposed (geometric mean) directional contributions
across the full bar set. Does not modify fusion_engine.
"""

from __future__ import annotations

import io
import statistics
import sys
from collections import Counter, defaultdict
from contextlib import redirect_stdout

from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.core.fusion_engine import _directional_contribution as fusion_directional_contribution
from renaissance_v4.core.signal_weights import get_signal_weight
from renaissance_v4.signals.breakout_expansion import BreakoutExpansionSignal
from renaissance_v4.signals.mean_reversion_fade import MeanReversionFadeSignal
from renaissance_v4.signals.pullback_continuation import PullbackContinuationSignal
from renaissance_v4.signals.signal_result import SignalResult
from renaissance_v4.signals.trend_continuation import TrendContinuationSignal
from renaissance_v4.utils.db import get_connection

MIN_ROWS = 50


def _bucket(name: str) -> str:
    if name in {"trend_continuation", "pullback_continuation"}:
        return "trend_family"
    if name == "breakout_expansion":
        return "breakout_family"
    if name == "mean_reversion_fade":
        return "mean_reversion_family"
    return "other"


def _legacy_contribution(r: SignalResult) -> float:
    if not r.active or r.direction not in {"long", "short"}:
        return 0.0
    w = get_signal_weight(r.signal_name)
    return (
        r.confidence
        * max(r.expected_edge, 0.0)
        * max(r.regime_fit, 0.0)
        * max(r.stability_score, 0.0)
        * w
    )


def _percentiles(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {"n": 0.0}
    xs = sorted(xs)
    n = len(xs)

    def p(q: float) -> float:
        if n == 1:
            return xs[0]
        idx = int(q * (n - 1))
        return xs[idx]

    return {
        "n": float(n),
        "min": xs[0],
        "p50": p(0.50),
        "p75": p(0.75),
        "p90": p(0.90),
        "p95": p(0.95),
        "p99": p(0.99),
        "max": xs[-1],
        "mean": float(statistics.mean(xs)),
    }


def run_audit() -> dict:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m ORDER BY open_time ASC
        """
    ).fetchall()
    if len(rows) < MIN_ROWS:
        raise SystemExit("not enough bars")

    signals = [
        TrendContinuationSignal(),
        PullbackContinuationSignal(),
        BreakoutExpansionSignal(),
        MeanReversionFadeSignal(),
    ]
    buf = io.StringIO()
    steps = 0
    gross_zero = 0
    starvation = Counter()
    legacy_contribs_by_signal: dict[str, list[float]] = defaultdict(list)
    gm_contribs_by_signal: dict[str, list[float]] = defaultdict(list)
    legacy_winning: list[float] = []
    gm_winning: list[float] = []
    overlap_events = 0

    for index in range(MIN_ROWS, len(rows) + 1):
        window = rows[:index]
        with redirect_stdout(buf):
            state = build_market_state(window)
            features = build_feature_set(state)
            regime = classify_regime(features)
            srs = [s.evaluate(state, features, regime) for s in signals]

        any_active = any(r.active for r in srs)
        any_active_ls = [r for r in srs if r.active and r.direction in {"long", "short"}]
        if not any_active_ls:
            if not any_active:
                starvation["no_active_signals"] += 1
            else:
                starvation["active_but_direction_neutral_only"] += 1
            gross_zero += 1
            steps += 1
            continue

        ll = ss = 0.0
        ll_gm = ss_gm = 0.0
        for r in srs:
            if r.active and r.direction in {"long", "short"}:
                lg = _legacy_contribution(r)
                gg = fusion_directional_contribution(r)
                legacy_contribs_by_signal[r.signal_name].append(lg)
                gm_contribs_by_signal[r.signal_name].append(gg)
                if r.direction == "long":
                    ll += lg
                    ll_gm += gg
                else:
                    ss += lg
                    ss_gm += gg

        g = ll + ss
        if g <= 0:
            starvation["active_long_short_but_legacy_contribution_zero"] += 1
            gross_zero += 1
            steps += 1
            continue

        lw = max(ll, ss)
        lw_gm = max(ll_gm, ss_gm)
        legacy_winning.append(lw)
        gm_winning.append(lw_gm)
        buckets = [_bucket(r.signal_name) for r in any_active_ls]
        bc = Counter(buckets)
        if any(c > 2 for c in bc.values()):
            overlap_events += 1

        steps += 1

    return {
        "steps": steps,
        "gross_zero_bars": gross_zero,
        "starvation": dict(starvation),
        "legacy_winning": _percentiles(legacy_winning),
        "gm_winning": _percentiles(gm_winning),
        "legacy_by_signal": {k: _percentiles(v) for k, v in legacy_contribs_by_signal.items()},
        "gm_by_signal": {k: _percentiles(v) for k, v in gm_contribs_by_signal.items()},
        "overlap_bars_gt2_same_bucket": overlap_events,
    }


def main() -> None:
    a = run_audit()
    import json

    print(json.dumps(a, indent=2))


if __name__ == "__main__":
    main()
