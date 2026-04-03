"""
Anna math engine — deterministic quantitative layer for analysis (signal vs noise).

All numeric claims that ground the LLM should come from here or other code paths,
not from model fluency. The local LLM explains what these facts mean; when the engine
marks small samples or missing data, the prompt still instructs honest uncertainty.

Paper cohort + market tick + training quant metrics (Sharpe/Sortino-style proxies, drawdown, VaR/CVaR).
"""
from __future__ import annotations

import math
import os
import re
from typing import Any

MATH_ENGINE_VERSION = "3"


def wilson_score_interval_95(wins: int, n: int) -> tuple[float, float]:
    """Wilson score interval for binomial proportion (95% nominal). Empty sample → [0,1]."""
    if n <= 0:
        return (0.0, 1.0)
    z = 1.96
    z2 = z * z
    p = wins / n
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return (max(0.0, center - margin), min(1.0, center + margin))


def spread_bps_of_mid(price: float, spread: float) -> float | None:
    """Spread as basis points of mid (same convention as risk.build_market_context)."""
    if price is None or spread is None or price <= 0:
        return None
    return (spread / price) * 10000.0


def relative_mid_spread_pct(primary: float | None, comparator: float | None) -> float | None:
    """Signed relative spread vs mid, matching market_data.strategy_eval convention."""
    if primary is None or comparator is None:
        return None
    mid = (primary + comparator) / 2.0
    if mid == 0:
        return None
    return (primary - comparator) / mid


def merge_authoritative_fact_layers(
    base: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Concatenate facts_for_prompt; merge structured (extra keys win on conflict)."""
    bf = list(base.get("facts_for_prompt") or [])
    ef = list(extra.get("facts_for_prompt") or [])
    bs = dict(base.get("structured") or {})
    es = dict(extra.get("structured") or {})
    merged_struct = {**bs, **es}
    return {
        "facts_for_prompt": bf + ef,
        "structured": merged_struct,
    }


def _load_paper_trades_safe() -> list[dict[str, Any]]:
    try:
        from modules.anna_training.paper_trades import load_paper_trades_for_gates

        return load_paper_trades_for_gates()
    except Exception:
        return []


def _full_stack_facts(trades: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    """ARIMA/GARCH/WFO/MC/ML/Kalman — requires deps; gated by ANNA_MATH_ENGINE_FULL=1."""
    try:
        from modules.anna_training.math_engine_full.stack import (
            full_stack_fact_lines,
            run_full_math_stack,
            training_full_stack_env_enabled,
        )
    except Exception:
        return [], {}
    if not training_full_stack_env_enabled():
        return [], {}
    try:
        result = run_full_math_stack(trades, aux=None)
        lines = full_stack_fact_lines(result)
        return lines, {"full_stack": result}
    except Exception:
        return [], {"full_stack_error": "runtime_or_dependency"}


def _paper_quant_extended_facts(trades: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    """Risk-style metrics on ordered paper P&L (training quant layer)."""
    try:
        from modules.anna_training.quant_metrics import (
            compute_paper_quant_metrics,
            quant_metrics_fact_lines,
        )
    except Exception:
        return [], {}
    qm = compute_paper_quant_metrics(trades)
    lines = quant_metrics_fact_lines(qm)
    return lines, qm


def _float_or_none(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _paper_cohort_facts(trades: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    lines: list[str] = []
    wins = losses = breakeven = abstain = 0
    pnl_sum = 0.0
    for t in trades:
        pnl_sum += float(t.get("pnl_usd") or 0)
        r = str(t.get("result") or "")
        if r == "won":
            wins += 1
        elif r == "lost":
            losses += 1
        elif r == "breakeven":
            breakeven += 1
        else:
            abstain += 1
    decisive = wins + losses
    structured: dict[str, Any] = {
        "paper_trade_count": len(trades),
        "decisive_trades": decisive,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "abstain": abstain,
        "total_pnl_usd": round(pnl_sum, 6),
    }
    if decisive == 0:
        lines.append(
            "FACT (math engine): No decisive paper trades (won+lost) logged yet — "
            "no cohort win rate; do not infer edge from P&L narrative alone."
        )
        structured["win_rate"] = None
        structured["wilson_95"] = None
        structured["sample_adequacy"] = "no_decisive"
        return lines, structured

    wr = wins / decisive
    lo, hi = wilson_score_interval_95(wins, decisive)
    structured["win_rate"] = round(wr, 6)
    structured["wilson_95"] = {"low": round(lo, 6), "high": round(hi, 6)}
    lines.append(
        f"FACT (math engine): Paper cohort decisive n={decisive} "
        f"(wins={wins}, losses={losses}); point win rate={wr:.4f}; "
        f"95% Wilson interval≈[{lo:.4f}, {hi:.4f}]."
    )
    lines.append(f"FACT (math engine): Sum of logged paper P&L (USD)={pnl_sum:.4f} (descriptive).")

    if decisive < 5:
        structured["sample_adequacy"] = "small"
        lines.append(
            "FACT (math engine): Decisive n is small — treat win rate as descriptive only; "
            "separating signal from luck requires more data. Use LLM to discuss uncertainty, "
            "not to invent precision."
        )
    elif decisive < 30:
        structured["sample_adequacy"] = "moderate"
        lines.append(
            "FACT (math engine): Moderate sample — intervals are wide; avoid overconfidence in edge claims."
        )
    else:
        structured["sample_adequacy"] = "usable_for_gate_style_metrics"

    return lines, structured


def _tick_math_facts(tick: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    if not tick or not isinstance(tick, dict):
        return [], {}
    lines: list[str] = []
    st: dict[str, Any] = {}
    primary = _float_or_none(tick.get("primary_price"))
    comp = _float_or_none(tick.get("comparator_price"))
    rsp = relative_mid_spread_pct(primary, comp)
    if rsp is not None:
        st["relative_spread_pct"] = round(rsp, 8)
        lines.append(
            f"FACT (math engine): Primary vs comparator relative spread vs mid = {rsp:.6f} "
            f"(deterministic from stored tick)."
        )
    gs = str(tick.get("gate_state") or "")
    if gs in ("blocked", "degraded"):
        st["gate_state"] = gs
        lines.append(
            f"FACT (math engine): Market tick gate_state={gs} — numeric spread above is "
            f"not a clean quality signal until gates are healthy."
        )
    return lines, st


def _snapshot_math_facts(market: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    if not market or not isinstance(market, dict):
        return [], {}
    price = _float_or_none(market.get("price"))
    spread = _float_or_none(market.get("spread"))
    bps = spread_bps_of_mid(price, spread) if price is not None and spread is not None else None
    if bps is None:
        return [], {}
    return (
        [
            f"FACT (math engine): Snapshot spread ≈ {bps:.2f} bps of mid (deterministic).",
        ],
        {"snapshot_spread_bps": round(bps, 6)},
    )


_RE_NUMERIC_ASK = re.compile(
    r"\b(win\s*rate|statistics|statistic|probability|sample|cohort|edge|p&l|pnl|"
    r"performance|variance|std|deviation|confidence|interval|noise|signal)\b",
    re.IGNORECASE,
)


def compute_math_engine_facts(
    input_text: str,
    human_intent: dict[str, Any],
    *,
    market: dict[str, Any] | None = None,
    market_data_tick: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Deterministic math facts for Anna → merged with rule_facts before the LLM.

    Always attaches cohort + tick/snapshot math when data exists (bounded token cost).
    When the user is clearly asking a numeric question, facts are still the same —
    the engine is the single quantitative source of truth for those inputs.
    """
    _ = human_intent  # reserved for intent-gated extensions
    lines: list[str] = []
    structured: dict[str, Any] = {
        "math_engine": {
            "version": MATH_ENGINE_VERSION,
            "numeric_question_likely": bool(_RE_NUMERIC_ASK.search(input_text or "")),
        }
    }

    trades = _load_paper_trades_safe()
    pc_lines, pc_st = _paper_cohort_facts(trades)
    lines.extend(pc_lines)
    structured["math_engine"]["paper_cohort"] = pc_st

    q_lines, q_struct = _paper_quant_extended_facts(trades)
    lines.extend(q_lines)
    if q_struct:
        structured["math_engine"]["paper_quant"] = q_struct

    fs_lines, fs_struct = _full_stack_facts(trades)
    lines.extend(fs_lines)
    if fs_struct:
        structured["math_engine"].update(fs_struct)

    sn_lines, sn_st = _snapshot_math_facts(market)
    lines.extend(sn_lines)
    if sn_st:
        structured["math_engine"]["snapshot"] = sn_st

    tk_lines, tk_st = _tick_math_facts(market_data_tick)
    lines.extend(tk_lines)
    if tk_st:
        structured["math_engine"]["phase5_tick"] = tk_st

    return {
        "facts_for_prompt": lines,
        "structured": structured,
    }
