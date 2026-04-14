"""
diagnostic_pipeline.py

Read-only pass: replay the same bar loop as replay_runner and aggregate counts
at signal → fusion → risk stages. Does not modify thresholds or production logic.

DV-ARCH-DIAGNOSTIC-008 — write renaissance_v4/reports/diagnostic_v1.md
"""

from __future__ import annotations

import io
import sys
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.fusion_engine import MAX_CONFLICT_SCORE, MIN_FUSION_SCORE, fuse_signal_results
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.core.risk_governor import evaluate_risk
from renaissance_v4.signals.breakout_expansion import BreakoutExpansionSignal
from renaissance_v4.signals.mean_reversion_fade import MeanReversionFadeSignal
from renaissance_v4.signals.pullback_continuation import PullbackContinuationSignal
from renaissance_v4.signals.trend_continuation import TrendContinuationSignal
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50

_REPORT_DEFAULT = Path(__file__).resolve().parent.parent / "reports" / "diagnostic_v1.md"


def _classify_fusion_no_trade(fr) -> str:
    """Why fusion returned no_trade (uses same structure as fusion_engine)."""
    if fr.gross_score <= 0.0:
        return "no_gross_directional_score (no active long/short contributions)"
    if fr.conflict_score > MAX_CONFLICT_SCORE:
        return f"conflict_score>{MAX_CONFLICT_SCORE}"
    return f"fusion_score<{MIN_FUSION_SCORE} (after overlap) or tie"


def run_diagnostic() -> dict:
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()

    dataset_bars = len(rows)
    if dataset_bars < MIN_ROWS_REQUIRED:
        raise RuntimeError(f"[diagnostic] Need at least {MIN_ROWS_REQUIRED} bars, found {dataset_bars}")

    signals = [
        TrendContinuationSignal(),
        PullbackContinuationSignal(),
        BreakoutExpansionSignal(),
        MeanReversionFadeSignal(),
    ]
    signal_names = [s.signal_name for s in signals]

    per_signal: dict[str, dict[str, int]] = {
        n: {"active": 0, "long": 0, "short": 0, "neutral": 0} for n in signal_names
    }
    bars_any_signal_active = 0

    fusion_long = fusion_short = fusion_no_trade = 0
    fusion_no_trade_reasons: Counter[str] = Counter()

    risk_allowed_total = 0
    risk_blocked_total = 0
    risk_allowed_on_directional = 0
    risk_blocked_on_directional = 0
    veto_when_directional_blocked: Counter[str] = Counter()
    size_tier_when_allowed: Counter[str] = Counter()

    regime_counts: Counter[str] = Counter()

    # Pipeline: hypothetical entries (same gate as replay when flat & no position)
    hypothetical_entries = 0

    decision_steps = 0
    expected_steps = max(0, len(rows) - MIN_ROWS_REQUIRED + 1)

    buf = io.StringIO()
    for index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:index]
        with redirect_stdout(buf):
            state = build_market_state(window)
            features = build_feature_set(state)
            regime = classify_regime(features)

        regime_counts[regime] += 1

        signal_results = []
        with redirect_stdout(buf):
            for signal in signals:
                signal_results.append(signal.evaluate(state, features, regime))

        any_active = False
        for r in signal_results:
            name = r.signal_name
            if r.active:
                per_signal[name]["active"] += 1
                any_active = True
            d = (r.direction or "").lower()
            if d == "long":
                per_signal[name]["long"] += 1
            elif d == "short":
                per_signal[name]["short"] += 1
            else:
                per_signal[name]["neutral"] += 1
        if any_active:
            bars_any_signal_active += 1

        with redirect_stdout(buf):
            fusion_result = fuse_signal_results(signal_results)

        active_signal_names = [r.signal_name for r in signal_results if r.active]

        if fusion_result.direction == "long":
            fusion_long += 1
        elif fusion_result.direction == "short":
            fusion_short += 1
        else:
            fusion_no_trade += 1
            fusion_no_trade_reasons[_classify_fusion_no_trade(fusion_result)] += 1

        drawdown_proxy = 0.0
        with redirect_stdout(buf):
            risk_decision = evaluate_risk(
                fusion_result=fusion_result,
                features=features,
                regime=regime,
                drawdown_proxy=drawdown_proxy,
                active_signal_names=active_signal_names,
            )

        if risk_decision.allowed:
            risk_allowed_total += 1
            size_tier_when_allowed[risk_decision.size_tier] += 1
        else:
            risk_blocked_total += 1

        if fusion_result.direction in {"long", "short"}:
            if risk_decision.allowed:
                risk_allowed_on_directional += 1
                hypothetical_entries += 1
            else:
                risk_blocked_on_directional += 1
                for vr in risk_decision.veto_reasons or []:
                    veto_when_directional_blocked[str(vr)] += 1

        decision_steps += 1
        if decision_steps % 25000 == 0:
            print(f"[diagnostic] progress steps={decision_steps}/{expected_steps}", file=sys.stderr)

    return {
        "dataset_bars": dataset_bars,
        "decision_steps": decision_steps,
        "signal_names": signal_names,
        "per_signal": per_signal,
        "fusion_long": fusion_long,
        "fusion_short": fusion_short,
        "fusion_no_trade": fusion_no_trade,
        "fusion_no_trade_reasons": fusion_no_trade_reasons,
        "risk_allowed_total": risk_allowed_total,
        "risk_blocked_total": risk_blocked_total,
        "risk_allowed_on_directional": risk_allowed_on_directional,
        "risk_blocked_on_directional": risk_blocked_on_directional,
        "veto_when_directional_blocked": veto_when_directional_blocked,
        "size_tier_when_allowed": size_tier_when_allowed,
        "regime_counts": regime_counts,
        "hypothetical_entries": hypothetical_entries,
        "bars_any_signal_active": bars_any_signal_active,
    }


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return 100.0 * float(part) / float(whole)


def _root_cause_statement(stats: dict) -> str:
    steps = stats["decision_steps"]
    fn = stats["fusion_no_trade"]
    fl = stats["fusion_long"]
    fs = stats["fusion_short"]
    hyp = stats["hypothetical_entries"]
    r_dir_block = stats["risk_blocked_on_directional"]
    reasons = stats["fusion_no_trade_reasons"]

    if hyp > 0:
        return (
            f"Fusion and risk produced **{hyp}** bars where execution would open a new trade (flat book); "
            "zero closed trades then implies execution/exit simulation or position logic — re-check replay_runner "
            "vs this diagnostic (unexpected if counts disagree)."
        )

    if fl == 0 and fs == 0 and fn >= steps * 0.99:
        g0 = reasons.get("no_gross_directional_score (no active long/short contributions)", 0)
        low = reasons.get("fusion_score<0.55 (after overlap) or tie", 0)
        cf = reasons.get(f"conflict_score>{MAX_CONFLICT_SCORE}", 0)
        p0 = _pct(g0, steps)
        p1 = _pct(low, steps)
        return (
            f"**Fusion never emitted `long` or `short` (0 / {steps} decision steps).** "
            f"**{p0:.2f}%** of steps had **no gross directional score** ({g0} bars); "
            f"**{p1:.2f}%** had non-zero gross but **fused score stayed below MIN_FUSION_SCORE** ({low} bars). "
            f"Conflict bucket: {cf}. "
            "**Risk** never sized a directional trade (`no_trade_from_fusion`); **execution received 0 opens**."
        )

    if (fl + fs) > 0 and r_dir_block == (fl + fs):
        top = stats["veto_when_directional_blocked"].most_common(3)
        top_s = ", ".join(f"`{k}` ({v})" for k, v in top) if top else "(no veto tags)"
        return (
            f"Fusion produced **{fl + fs}** directional bars, but **risk blocked execution on every one** "
            f"(vetoes: {top_s}). Size collapsed to zero via regime/volatility/persistence/compression rules."
        )

    return (
        "Fusion produced some directional bars and risk allowed some — see tables; zero trades may indicate "
        "a mismatch between this diagnostic and replay execution path (investigate)."
    )


def write_diagnostic_report(path: Path | None = None) -> Path:
    stats = run_diagnostic()
    out = path or _REPORT_DEFAULT
    out.parent.mkdir(parents=True, exist_ok=True)

    steps = stats["decision_steps"]
    ds = stats["dataset_bars"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# RenaissanceV4 — Pipeline diagnostic v1 (read-only)",
        "",
        f"Generated: **{now}** by `renaissance_v4/research/diagnostic_pipeline.py` (DV-ARCH-DIAGNOSTIC-008).",
        "",
        "**No thresholds, weights, or signal/fusion/risk logic were modified.** This pass only counts outcomes ",
        "using the **same** `evaluate` → `fuse_signal_results` → `evaluate_risk` sequence as `replay_runner.py`.",
        "",
        "## Dataset",
        "",
        f"- **Rows in `market_bars_5m`:** {ds}",
        f"- **Decision steps (bars processed after {MIN_ROWS_REQUIRED}-bar warmup):** {steps}",
        "",
        "## 5.1 Signal layer",
        "",
        "Per signal, counts are **per decision bar** (same bar may increment multiple counters).",
        "",
        "| Signal | `active` | direction `long` | direction `short` | direction `neutral` |",
        "|--------|----------|--------------------|--------------------|---------------------|",
    ]

    for name in stats["signal_names"]:
        p = stats["per_signal"][name]
        lines.append(
            f"| `{name}` | {p['active']} | {p['long']} | {p['short']} | {p['neutral']} |"
        )

    lines.extend(
        [
            "",
            f"- **Decision bars with ≥1 signal `active`:** {stats['bars_any_signal_active']} "
            f"({_pct(stats['bars_any_signal_active'], steps):.4f}% of steps).",
            "",
            "## 5.2 Fusion layer",
            "",
            f"- **Fusion `long`:** {stats['fusion_long']} ({_pct(stats['fusion_long'], steps):.4f}% of decision steps)",
            f"- **Fusion `short`:** {stats['fusion_short']} ({_pct(stats['fusion_short'], steps):.4f}%)",
            f"- **Fusion `no_trade`:** {stats['fusion_no_trade']} ({_pct(stats['fusion_no_trade'], steps):.4f}%)",
            "",
            "**`no_trade` breakdown (mutually exclusive buckets):**",
            "",
            "| Reason bucket | Count | % of decision steps |",
            "|---------------|-------|---------------------|",
        ]
    )

    for reason, cnt in stats["fusion_no_trade_reasons"].most_common():
        lines.append(f"| {reason} | {cnt} | {_pct(cnt, steps):.4f}% |")

    lines.extend(
        [
            "",
            "## 5.3 Risk layer",
            "",
            f"- **Risk `allowed` (all fusion outputs):** {stats['risk_allowed_total']} ({_pct(stats['risk_allowed_total'], steps):.4f}%)",
            f"- **Risk `blocked` (all fusion outputs):** {stats['risk_blocked_total']} ({_pct(stats['risk_blocked_total'], steps):.4f}%)",
            "",
            "When fusion was **directional** (`long` or `short`):",
            "",
            f"- **Risk allowed:** {stats['risk_allowed_on_directional']}",
            f"- **Risk blocked:** {stats['risk_blocked_on_directional']}",
            "",
            "**Veto reason counts (only when fusion was directional and risk blocked):**",
            "",
            "| Veto reason | Count |",
            "|-------------|-------|",
        ]
    )

    for vr, cnt in stats["veto_when_directional_blocked"].most_common(30):
        lines.append(f"| `{vr}` | {cnt} |")

    if not stats["veto_when_directional_blocked"]:
        lines.append("| *(none — fusion rarely directional or risk never blocked directional)* | 0 |")

    lines.extend(
        [
            "",
            "**Size tier when risk allowed (any fusion output):**",
            "",
            "| Size tier | Count |",
            "|-----------|-------|",
        ]
    )
    for tier, cnt in stats["size_tier_when_allowed"].most_common():
        lines.append(f"| `{tier}` | {cnt} |")

    lines.extend(
        [
            "",
            "## 5.4 Pipeline breakdown (Signal → Fusion → Risk → Execution gate)",
            "",
            f"- **Hypothetical new entries (flat book, same gate as replay):** `{stats['hypothetical_entries']}`",
            "  (count of bars where `fusion ∈ {{long,short}}` **and** `risk_decision.allowed`).",
            "",
            "If this count is **0**, execution never receives an open instruction — **closed trades stay 0**.",
            "",
            "## Regime distribution (informational)",
            "",
            "| Regime | Bars | % of steps |",
            "|--------|------|------------|",
        ]
    )

    for reg, cnt in stats["regime_counts"].most_common():
        lines.append(f"| `{reg}` | {cnt} | {_pct(cnt, steps):.4f}% |")

    lines.extend(
        [
            "",
            "## 7. Root cause analysis (data-backed)",
            "",
            "The system produced zero closed trades because:",
            "",
            f"> {_root_cause_statement(stats)}",
            "",
            "## 8. Reproduce",
            "",
            "```bash",
            "cd /path/to/blackbox",
            "export PYTHONPATH=.",
            "python3 -m renaissance_v4.research.diagnostic_pipeline",
            "```",
            "",
            "Writes this file by default to `renaissance_v4/reports/diagnostic_v1.md`.",
            "",
        ]
    )

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[diagnostic_pipeline] Wrote {out.resolve()}")
    return out


def main() -> None:
    write_diagnostic_report()


if __name__ == "__main__":
    main()
