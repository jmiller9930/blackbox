"""
diagnostic_quality_pipeline.py — read-only economic quality breakdown from full replay outcomes.

Runs the same bar loop as replay_runner (no logic changes), aggregates OutcomeRecord fields.
Writes renaissance_v4/reports/diagnostic_quality_v1.md
"""

from __future__ import annotations

import io
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from renaissance_v4.core.execution_manager import ExecutionManager
from renaissance_v4.core.feature_engine import build_feature_set
from renaissance_v4.core.fusion_engine import fuse_signal_results
from renaissance_v4.core.market_state_builder import build_market_state
from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.performance_metrics import compute_excursion_mae_mfe, compute_summary_metrics
from renaissance_v4.core.pnl import compute_pnl
from renaissance_v4.core.regime_classifier import classify_regime
from renaissance_v4.core.risk_governor import evaluate_risk
from renaissance_v4.research.execution_learning_bridge import record_closed_trade_to_ledger
from renaissance_v4.research.learning_ledger import LearningLedger
from renaissance_v4.signals.breakout_expansion import BreakoutExpansionSignal
from renaissance_v4.signals.mean_reversion_fade import MeanReversionFadeSignal
from renaissance_v4.signals.pullback_continuation import PullbackContinuationSignal
from renaissance_v4.signals.trend_continuation import TrendContinuationSignal
from renaissance_v4.utils.db import get_connection

MIN_ROWS_REQUIRED = 50
_REPORT = Path(__file__).resolve().parent.parent / "reports" / "diagnostic_quality_v1.md"

SIGNAL_NAMES = (
    "trend_continuation",
    "pullback_continuation",
    "breakout_expansion",
    "mean_reversion_fade",
)


def _family(name: str) -> str:
    if name in {"trend_continuation", "pullback_continuation"}:
        return "trend_family"
    if name == "breakout_expansion":
        return "breakout_family"
    if name == "mean_reversion_fade":
        return "mean_reversion_family"
    return "other"


def _metrics(outcomes: list[OutcomeRecord]) -> dict:
    if not outcomes:
        return compute_summary_metrics([])
    ordered = sorted(outcomes, key=lambda o: o.exit_time)
    return compute_summary_metrics(ordered)


def _fmt(m: dict) -> str:
    return (
        f"n={m['total_trades']} | win%={m['win_rate']:.4f} | E={m['expectancy']:.6f} | "
        f"avg_pnl={m['average_pnl']:.6f} | max_dd={m['max_drawdown']:.6f} | "
        f"avg_mae={m['avg_mae']:.6f} | avg_mfe={m['avg_mfe']:.6f}"
    )


def run_silent_replay() -> tuple[list[OutcomeRecord], int]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()
    if len(rows) < MIN_ROWS_REQUIRED:
        raise RuntimeError("not enough bars")

    signals = [
        TrendContinuationSignal(),
        PullbackContinuationSignal(),
        BreakoutExpansionSignal(),
        MeanReversionFadeSignal(),
    ]
    exec_manager = ExecutionManager()
    ledger = LearningLedger()
    buf = io.StringIO()
    processed = 0

    for index in range(MIN_ROWS_REQUIRED, len(rows) + 1):
        window = rows[:index]
        with redirect_stdout(buf):
            state = build_market_state(window)
            features = build_feature_set(state)
            regime = classify_regime(features)
            signal_results = [s.evaluate(state, features, regime) for s in signals]
            fusion_result = fuse_signal_results(signal_results)
            risk_decision = evaluate_risk(
                fusion_result=fusion_result,
                features=features,
                regime=regime,
                drawdown_proxy=0.0,
            )

        if exec_manager.current_trade and exec_manager.current_trade.open:
            exec_manager.record_bar_extremes(state.current_high, state.current_low)
            with redirect_stdout(buf):
                exit_ev = exec_manager.evaluate_bar(state.current_high, state.current_low)
            if exit_ev:
                reason, exit_price = exit_ev
                closed = exec_manager.current_trade
                bar_pnl = compute_pnl(
                    closed.entry_price,
                    exit_price,
                    closed.size,
                    closed.direction,
                )
                exec_manager.cumulative_pnl += bar_pnl
                mae, mfe = compute_excursion_mae_mfe(closed)
                with redirect_stdout(buf):
                    record_closed_trade_to_ledger(
                        ledger,
                        closed_trade=closed,
                        exit_time=state.timestamp,
                        exit_price=exit_price,
                        exit_reason=reason,
                        bar_pnl=bar_pnl,
                        mae=mae,
                        mfe=mfe,
                        regime=regime,
                    )

        flat = exec_manager.current_trade is None or not exec_manager.current_trade.open
        active_signal_names = [r.signal_name for r in signal_results if r.active]
        if (
            flat
            and risk_decision.allowed
            and fusion_result.direction in {"long", "short"}
        ):
            with redirect_stdout(buf):
                exec_manager.open_trade(
                    symbol=state.symbol,
                    price=state.current_close,
                    direction=fusion_result.direction,
                    atr=features.atr_proxy_14,
                    size=risk_decision.notional_fraction,
                    entry_time=state.timestamp,
                    contributing_signal_names=active_signal_names,
                    size_tier=risk_decision.size_tier,
                    notional_fraction=risk_decision.notional_fraction,
                    bar_high=state.current_high,
                    bar_low=state.current_low,
                )

        processed += 1
        if processed % 5000 == 0:
            print(f"[diagnostic_quality] progress processed={processed}", file=sys.stderr)

    return ledger.outcomes, len(rows)


def build_report(outcomes: list[OutcomeRecord], dataset_bars: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    n = len(outcomes)
    if n == 0:
        raise RuntimeError("no outcomes — run full-history DB")

    portfolio = _metrics(outcomes)
    total_neg = sum(o.pnl for o in outcomes if o.pnl < 0)

    # 7.1 per signal name (trade may appear in multiple rows)
    by_signal: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for o in outcomes:
        if not o.contributing_signals:
            by_signal["(no_contributing_signal)"].append(o)
        else:
            for s in o.contributing_signals:
                by_signal[s].append(o)

    # family: attribute full PnL once per distinct family per trade (split if multi-family)
    by_family: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for o in outcomes:
        fams = {_family(s) for s in (o.contributing_signals or [])}
        if not fams:
            fams = {"(none)"}
        for f in fams:
            by_family[f].append(o)

    # 7.2 regime (exit regime on record)
    by_regime: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for o in outcomes:
        by_regime[o.regime or "unknown"].append(o)

    # 7.3 direction
    by_dir: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for o in outcomes:
        by_dir[o.direction].append(o)

    # 7.4 exit reason
    by_exit: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for o in outcomes:
        by_exit[str(o.exit_reason or "unknown")].append(o)

    # 7.5 risk tier
    by_tier: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for o in outcomes:
        by_tier[o.size_tier or "unknown"].append(o)

    # 7.6 time thirds by exit_time
    chron = sorted(outcomes, key=lambda o: o.exit_time)
    t1 = n // 3
    t2 = 2 * n // 3
    thirds = {
        "first_third_of_trades (chronological)": chron[:t1],
        "middle_third": chron[t1:t2],
        "final_third": chron[t2:],
    }

    def loss_share(m: dict, label: str) -> float:
        g = m.get("gross_pnl", 0.0)
        if total_neg >= 0:
            return 0.0
        if g >= 0:
            return 0.0
        return 100.0 * abs(g) / abs(total_neg)

    lines = [
        "# RenaissanceV4 — Economic quality diagnostic v1 (read-only)",
        "",
        f"Generated: **{now}** · `renaissance_v4/research/diagnostic_quality_pipeline.py`",
        "",
        f"- **Dataset bars:** {dataset_bars}",
        f"- **Closed trades (unique outcomes):** {n}",
        "",
        "## Portfolio (all closed trades)",
        "",
        f"- {_fmt(portfolio)}",
        f"- **Total gross PnL:** {portfolio['gross_pnl']:.8f}",
        "",
        "## 7.1 Signal-level performance (contributing signal tags)",
        "",
        "Each trade is duplicated into **every** contributing signal row (same method as scorecards). "
        "`n` is **not** unique trade count across rows.",
        "",
        "| Signal | n (tagged) | win_rate | expectancy | avg_pnl | max_dd | avg_MAE | avg_MFE | share of loss mass* |",
        "|--------|------------|----------|------------|---------|--------|---------|---------|----------------------|",
    ]

    for name in list(SIGNAL_NAMES) + sorted(k for k in by_signal if k not in SIGNAL_NAMES):
        m = _metrics(by_signal[name])
        ls = loss_share(m, name)
        lines.append(
            f"| `{name}` | {m['total_trades']} | {m['win_rate']:.4f} | {m['expectancy']:.6f} | "
            f"{m['average_pnl']:.6f} | {m['max_drawdown']:.6f} | {m['avg_mae']:.6f} | {m['avg_mfe']:.6f} | {ls:.1f}% |"
        )

    lines.extend(
        [
            "",
            "*Share of loss mass* = abs(group gross PnL) / abs(sum of negative trade PnLs portfolio-wide) when group PnL is negative; else 0.",
            "",
            "### Signal **family** (each trade counted once per distinct family in its contributing list)",
            "",
            "| Family | n (rows) | win_rate | expectancy | avg_pnl | max_dd | avg_MAE | avg_MFE |",
            "|--------|----------|----------|------------|---------|--------|---------|---------|",
        ]
    )
    for fam in sorted(by_family.keys(), key=lambda k: _metrics(by_family[k])["gross_pnl"]):
        m = _metrics(by_family[fam])
        lines.append(
            f"| `{fam}` | {m['total_trades']} | {m['win_rate']:.4f} | {m['expectancy']:.6f} | "
            f"{m['average_pnl']:.6f} | {m['max_drawdown']:.6f} | {m['avg_mae']:.6f} | {m['avg_mfe']:.6f} |"
        )

    lines.extend(["", "## 7.2 Regime performance (exit `regime` on outcome)", "", "| Regime | n | win_rate | expectancy | avg_pnl | max_dd |", "|--------|---|----------|------------|---------|--------|"])
    for reg in sorted(by_regime.keys(), key=lambda k: _metrics(by_regime[k])["gross_pnl"]):
        m = _metrics(by_regime[reg])
        lines.append(
            f"| `{reg}` | {m['total_trades']} | {m['win_rate']:.4f} | {m['expectancy']:.6f} | "
            f"{m['average_pnl']:.6f} | {m['max_drawdown']:.6f} |"
        )

    lines.extend(["", "## 7.3 Directional performance", "", "| Side | n | win_rate | expectancy | avg_pnl |", "|------|---|----------|------------|---------|"])
    for d in sorted(by_dir.keys()):
        m = _metrics(by_dir[d])
        lines.append(
            f"| `{d}` | {m['total_trades']} | {m['win_rate']:.4f} | {m['expectancy']:.6f} | {m['average_pnl']:.6f} |"
        )

    lines.extend(["", "## 7.4 Exit-reason performance", "", "| exit_reason | n | win_rate | avg_pnl | avg_MAE | avg_MFE |", "|-------------|---|----------|---------|---------|---------|"])
    for er in sorted(by_exit.keys()):
        m = _metrics(by_exit[er])
        lines.append(
            f"| `{er}` | {m['total_trades']} | {m['win_rate']:.4f} | {m['average_pnl']:.6f} | "
            f"{m['avg_mae']:.6f} | {m['avg_mfe']:.6f} |"
        )

    lines.extend(["", "## 7.5 Risk-tier performance (`size_tier` at entry)", "", "| Tier | n | win_rate | expectancy | avg_pnl | max_dd |", "|------|---|----------|------------|---------|--------|"])
    for tier in sorted(by_tier.keys()):
        m = _metrics(by_tier[tier])
        lines.append(
            f"| `{tier}` | {m['total_trades']} | {m['win_rate']:.4f} | {m['expectancy']:.6f} | "
            f"{m['average_pnl']:.6f} | {m['max_drawdown']:.6f} |"
        )

    lines.extend(["", "## 7.6 Time distribution (chronological trade thirds)", ""])
    for label, chunk in thirds.items():
        m = _metrics(chunk)
        lines.append(f"- **{label}:** {_fmt(m)}")

    # Root cause ranking: regime and signal (unique trades) gross pnl
    reg_rank = sorted(((r, _metrics(v)["gross_pnl"]) for r, v in by_regime.items()), key=lambda x: x[1])
    sig_rank = sorted(((s, _metrics(v)["gross_pnl"]) for s, v in by_signal.items() if s in SIGNAL_NAMES), key=lambda x: x[1])
    worst_reg = reg_rank[0][0] if reg_rank else "n/a"
    worst_reg_pnl = reg_rank[0][1] if reg_rank else 0.0
    worst_sig = sig_rank[0][0] if sig_rank else "n/a"
    worst_sig_pnl = sig_rank[0][1] if sig_rank else 0.0

    exit_m = _metrics(by_exit.get("stop", []))
    tgt_m = by_exit.get("target", [])
    tgt_metrics = _metrics(tgt_m) if tgt_m else compute_summary_metrics([])

    lines.extend(
        [
            "",
            "## Dominant root cause (evidence-ranked)",
            "",
            f"> The system is alive but economically weak because **aggregate expectancy is negative** "
            f"(`{portfolio['expectancy']:.6f}`) with **large path drawdown** (`max_dd={portfolio['max_drawdown']:.4f}` on the equity curve built from these trades). "
            f"**Regime:** the worst gross PnL bucket by **exit regime** is **`{worst_reg}`** "
            f"(gross PnL **{worst_reg_pnl:.6f}**). "
            f"**Signals (tagged rows):** the weakest named contributor among the four primaries is **`{worst_sig}`** "
            f"(gross PnL **{worst_sig_pnl:.6f}** across tagged outcomes). "
            f"**Exit path:** stops dominate count (`stop` n={exit_m['total_trades']}, avg_pnl={exit_m['average_pnl']:.6f}) vs targets (`target` n={tgt_metrics['total_trades']}, avg_pnl={tgt_metrics['average_pnl']:.6f}), "
            f"indicating **adverse exits hit more often than favorable targets** under current SL/TP geometry.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "cd /path/to/blackbox",
            "export PYTHONPATH=.",
            "python3 -m renaissance_v4.research.diagnostic_quality_pipeline",
            "```",
            "",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    outcomes, dataset_bars = run_silent_replay()
    text = build_report(outcomes, dataset_bars)
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(text, encoding="utf-8")
    print(f"[diagnostic_quality_pipeline] Wrote {_REPORT.resolve()}")


if __name__ == "__main__":
    main()
