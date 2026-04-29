"""
GT_DIRECTIVE_038 — mandatory 10-scenario registry + DB-backed window resolution.

Evaluation-only: selects ``decision_open_time_ms`` and symbols from ``market_bars_5m``;
does not alter RM, pattern memory math, EV, promotion, or execution.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.candle_timeframe_runtime import (
    is_allowed_candle_timeframe_minutes_v1,
    rollup_5m_rows_to_candle_timeframe,
)
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    build_indicator_context_eval_v1,
)
from renaissance_v4.game_theory.exam.student_reasoning_exam_gt041_v1 import (
    GT041_STYLE_EXAM_IDS_V1,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    fetch_all_5m_for_symbol_asc,
)


def _closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b.get("close") or 0.0) for b in bars]


def _indicator_tail(rolled: list[dict[str, Any]], idx: int, tail_max: int = 400) -> dict[str, Any]:
    chunk = rolled[: idx + 1]
    tail = chunk[-tail_max:] if len(chunk) > tail_max else chunk
    ic, _, _ = build_indicator_context_eval_v1(tail)
    return ic if isinstance(ic, dict) else {}


def _fake_breakout_score(rolled: list[dict[str, Any]], idx: int) -> float:
    """Higher = more like spike-and-fade within recent window (proxy for trap)."""
    start = max(0, idx - 24)
    win = rolled[start : idx + 1]
    if len(win) < 8:
        return 0.0
    ranges = [float(b["high"]) - float(b["low"]) for b in win]
    avg_r = sum(ranges[:-3]) / max(1, len(ranges) - 3)
    last3 = ranges[-3:]
    spike = max(last3) / avg_r if avg_r > 1e-12 else 0.0
    # fade if last close back toward middle of recent range
    last = win[-1]
    lo = min(float(b["low"]) for b in win[-8:])
    hi = max(float(b["high"]) for b in win[-8:])
    mid = 0.5 * (lo + hi)
    c = float(last["close"])
    fade = 1.0 - abs(c - mid) / max(1e-12, hi - lo)
    return spike * max(0.0, fade)


def _real_breakout_score(rolled: list[dict[str, Any]], idx: int) -> float:
    """Higher = expansion break with directional close."""
    start = max(0, idx - 48)
    win = rolled[start : idx + 1]
    if len(win) < 12:
        return 0.0
    prior_hi = max(float(b["high"]) for b in win[:-4])
    last4 = win[-4:]
    hi4 = max(float(b["high"]) for b in last4)
    c = float(win[-1]["close"])
    if hi4 <= prior_hi:
        return 0.0
    stretch = (hi4 - prior_hi) / max(1e-12, float(win[-5]["close"]))
    dir_bias = 1.0 if c >= float(win[-2]["close"]) else 0.3
    return stretch * dir_bias


def pick_dense_symbol_v1(db_path: Path) -> str | None:
    p = Path(db_path)
    if not p.is_file():
        return None
    try:
        with sqlite3.connect(str(p)) as conn:
            cur = conn.execute(
                """
                SELECT symbol, COUNT(*) AS n
                FROM market_bars_5m
                WHERE symbol IS NOT NULL AND TRIM(symbol) != ''
                GROUP BY symbol
                ORDER BY n DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0]).strip()
    except (OSError, sqlite3.Error):
        return None
    return None


def _rollup_symbol(
    db_path: Path,
    symbol: str,
    candle_timeframe_minutes: int,
) -> tuple[list[dict[str, Any]], str | None]:
    all_5m, err = fetch_all_5m_for_symbol_asc(db_path=db_path, symbol=symbol)
    if err:
        return [], err
    if not all_5m:
        return [], "no 5m rows for symbol"
    tf = int(candle_timeframe_minutes)
    if tf == 5:
        return all_5m, None
    rolled, _audit = rollup_5m_rows_to_candle_timeframe(list(all_5m), target_minutes=tf)
    return rolled, None


def scenario_templates_v1() -> list[dict[str, Any]]:
    """Exactly ten directive scenarios (metadata + grading hints)."""
    return [
        {
            "scenario_id": "d6_s01_strong_trend_long",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "strong_trend_long",
            "memory_injection_v1": None,
            "expected_state": "bullish_trend_or_aligned_structure",
            "expected_behavior": "Trend continuation long is plausible; RM long bias acceptable.",
            "allowed_actions": ["enter_long", "no_trade"],
            "disallowed_actions": ["enter_short"],
            "required_signals": ["indicator_context_eval_v1", "decision_synthesis_v1", "expected_value_risk_cost_v1"],
            "grade_primary_action_v1": "long",
        },
        {
            "scenario_id": "d6_s02_strong_trend_short",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "strong_trend_short",
            "memory_injection_v1": None,
            "expected_state": "bearish_trend_or_aligned_structure",
            "expected_behavior": "Trend continuation short is plausible; RM short bias acceptable.",
            "allowed_actions": ["enter_short", "no_trade"],
            "disallowed_actions": ["enter_long"],
            "required_signals": ["indicator_context_eval_v1", "decision_synthesis_v1", "expected_value_risk_cost_v1"],
            "grade_primary_action_v1": "short",
        },
        {
            "scenario_id": "d6_s03_sideways_chop",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "sideways_chop",
            "memory_injection_v1": None,
            "expected_state": "range_or_neutral_trend",
            "expected_behavior": "NO_TRADE expected — chop / no clean edge.",
            "allowed_actions": ["no_trade"],
            "disallowed_actions": ["enter_long", "enter_short"],
            "required_signals": ["indicator_context_eval_v1", "decision_synthesis_v1"],
            "grade_primary_action_v1": "no_trade",
        },
        {
            "scenario_id": "d6_s04_fake_breakout_trap",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "fake_breakout",
            "memory_injection_v1": None,
            "expected_state": "trap_or_mean_reversion_risk",
            "expected_behavior": "Avoid directional chase; NO_TRADE or fade-aware stance.",
            "allowed_actions": ["no_trade"],
            "disallowed_actions": [],
            "required_signals": ["risk_inputs_v1", "decision_synthesis_v1"],
            "grade_primary_action_v1": "no_trade",
        },
        {
            "scenario_id": "d6_s05_real_breakout",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "real_breakout",
            "memory_injection_v1": None,
            "expected_state": "breakout_expansion",
            "expected_behavior": "Directional trade may be justified with EV/risk acknowledgement.",
            "allowed_actions": ["enter_long", "enter_short", "no_trade"],
            "disallowed_actions": [],
            "required_signals": ["indicator_context_eval_v1", "expected_value_risk_cost_v1"],
            "grade_primary_action_v1": "contextual",
        },
        {
            "scenario_id": "d6_s06_overextended_long",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "overextended_long",
            "memory_injection_v1": None,
            "expected_state": "rsi_exhaustion_or_late_long",
            "expected_behavior": "Mean-reversion / exhaustion risk must be acknowledged; NO_TRADE often correct.",
            "allowed_actions": ["no_trade", "enter_short"],
            "disallowed_actions": ["enter_long"],
            "required_signals": ["indicator_context_eval_v1", "risk_inputs_v1"],
            "grade_primary_action_v1": "no_trade",
        },
        {
            "scenario_id": "d6_s07_overextended_short",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "overextended_short",
            "memory_injection_v1": None,
            "expected_state": "rsi_oversold_or_late_short",
            "expected_behavior": "Cover / reversal risk — NO_TRADE or cautious long only with acknowledgement.",
            "allowed_actions": ["no_trade", "enter_long"],
            "disallowed_actions": ["enter_short"],
            "required_signals": ["indicator_context_eval_v1", "risk_inputs_v1"],
            "grade_primary_action_v1": "no_trade",
        },
        {
            "scenario_id": "d6_s08_high_volatility_danger",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "high_volatility",
            "memory_injection_v1": None,
            "expected_state": "high_atr_volatility",
            "expected_behavior": "Risk/vol must be acknowledged; NO_TRADE acceptable.",
            "allowed_actions": ["no_trade", "enter_long", "enter_short"],
            "disallowed_actions": [],
            "required_signals": ["indicator_context_eval_v1", "risk_inputs_v1", "expected_value_risk_cost_v1"],
            "grade_primary_action_v1": "risk_ack",
        },
        {
            "scenario_id": "d6_s09_memory_supported_trade",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "neutral_for_memory",
            "memory_injection_v1": "positive",
            "expected_state": "memory_positive_prior_pnls",
            "expected_behavior": "Decision should not ignore positive cross-run memory when EV/memory align.",
            "allowed_actions": ["enter_long", "enter_short", "no_trade"],
            "disallowed_actions": [],
            "required_signals": ["memory_context_eval_v1", "prior_outcome_eval_v1"],
            "grade_primary_action_v1": "memory_obey",
        },
        {
            "scenario_id": "d6_s10_memory_warning_trade",
            "symbol": "SOLUSDT",
            "timeframe_minutes": 240,
            "kind": "neutral_for_memory",
            "memory_injection_v1": "negative",
            "expected_state": "memory_conflict_or_negative_pnls",
            "expected_behavior": "Aggressive entry against negative memory should fail grading.",
            "allowed_actions": ["no_trade"],
            "disallowed_actions": [],
            "required_signals": ["memory_context_eval_v1", "prior_outcome_eval_v1"],
            "grade_primary_action_v1": "memory_conflict",
        },
    ]


def scenario_templates_gt041_memory_ev_v1() -> list[dict[str, Any]]:
    """
    GT_DIRECTIVE_041 — ten spread windows; lanes drive seeded PnL / proof expectations.

    Resolver uses ``kind`` = ``gt041_spread`` + ``gt041_slot`` 0..9 across rolled bars.
    """
    lanes = (
        "memory_positive",
        "memory_positive",
        "memory_positive",
        "memory_negative",
        "memory_negative",
        "memory_negative",
        "ev_positive",
        "ev_positive",
        "ev_negative",
        "ev_negative",
    )
    out: list[dict[str, Any]] = []
    for slot in range(10):
        lane = lanes[slot]
        out.append(
            {
                "scenario_id": f"d6_gt041_{lane}_{slot:02d}",
                "symbol": "SOLUSDT",
                # Use 5m so modest SQLite fixtures (hundreds of 5m rows) yield ≥80 rolled candles.
                "timeframe_minutes": 5,
                "kind": "gt041_spread",
                "gt041_slot": slot,
                "gt041_lane_v1": lane,
                "memory_injection_v1": None,
                "expected_state": f"gt041_{lane}",
                "expected_behavior": "Pattern-memory store + EV proof — see GT_DIRECTIVE_041.",
                "allowed_actions": ["enter_long", "enter_short", "no_trade"],
                "disallowed_actions": [],
                "required_signals": [
                    "indicator_context_eval_v1",
                    "decision_synthesis_v1",
                    "pattern_memory_eval_v1",
                    "expected_value_risk_cost_v1",
                ],
                "grade_primary_action_v1": "contextual",
            }
        )
    return out


def resolve_scenario_windows_v1(
    *,
    db_path: Path | str,
    symbol_override: str | None = None,
    timeframe_override: int | None = None,
    exam_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Returns enriched scenario rows: each includes resolved ``symbol``, ``candle_timeframe_minutes``,
    ``decision_open_time_ms``, ``bars_window_note``, ``window_resolution_v1``.
    """
    p = Path(db_path)
    eid = str(exam_id or "").strip()
    if eid in GT041_STYLE_EXAM_IDS_V1:
        templates = scenario_templates_gt041_memory_ev_v1()
    else:
        templates = scenario_templates_v1()
    sym = (symbol_override or "").strip() or pick_dense_symbol_v1(p)
    if not sym:
        return [], "could not resolve symbol from database"

    tf = int(timeframe_override) if timeframe_override is not None else int(templates[0]["timeframe_minutes"])
    if not is_allowed_candle_timeframe_minutes_v1(tf):
        return [], f"invalid timeframe_minutes: {tf}"

    rolled, err = _rollup_symbol(p, sym, tf)
    if err:
        return [], err
    min_bars = 80
    if len(rolled) < min_bars:
        return [], f"insufficient rolled bars for {sym}@{tf}m (need >= {min_bars}, got {len(rolled)})"

    # Scan indices (leave margin for causal packet).
    idx_lo = 120 if len(rolled) >= 200 else max(40, min_bars // 2)
    indices = range(idx_lo, len(rolled) - 2, 3)
    idx_list = list(indices)

    def best_match(tmpl: dict[str, Any]) -> tuple[int | None, str]:
        kind = str(tmpl.get("kind") or "")
        best_i: int | None = None
        best_score = -1.0
        note = ""
        if kind == "gt041_spread":
            slot = int(tmpl.get("gt041_slot") or 0)
            slot = max(0, min(slot, 9))
            if not idx_list:
                return None, "no_gt041_indices"
            # Spread decisions across the scan range so signatures diverge.
            stride = max(1, len(idx_list) // 11)
            off = min(slot * stride + (slot % 3), len(idx_list) - 1)
            picked = int(idx_list[off])
            return picked, f"gt041_spread slot={slot} off={off}"

        if kind == "strong_trend_long":
            for i in indices:
                ic = _indicator_tail(rolled, i)
                ema_t = str(ic.get("ema_trend") or "")
                rsi_s = str(ic.get("rsi_state") or "")
                flags = ic.get("support_flags_v1") if isinstance(ic.get("support_flags_v1"), dict) else {}
                long_ok = bool(flags.get("long")) if flags else False
                if ema_t == "bullish_trend" and long_ok and rsi_s != "exhaustion_risk":
                    return i, "matched bullish_trend + long flag"
                # score fallback
                tail = rolled[: i + 1][-80:]
                cc = _closes(tail)
                if len(cc) < 40:
                    continue
                mom = (cc[-1] - cc[-40]) / max(1e-12, abs(cc[-40]))
                score = mom
                if score > best_score:
                    best_score = score
                    best_i = i
                    note = f"fallback momentum score={score:.4f}"
            return best_i, note or "fallback momentum"

        if kind == "strong_trend_short":
            for i in indices:
                ic = _indicator_tail(rolled, i)
                ema_t = str(ic.get("ema_trend") or "")
                flags = ic.get("support_flags_v1") if isinstance(ic.get("support_flags_v1"), dict) else {}
                short_ok = bool(flags.get("short")) if flags else False
                if ema_t == "bearish_trend" and short_ok:
                    return i, "matched bearish_trend + short flag"
                tail = rolled[: i + 1][-80:]
                cc = _closes(tail)
                if len(cc) < 40:
                    continue
                mom = (cc[-1] - cc[-40]) / max(1e-12, abs(cc[-40]))
                score = -mom
                if score > best_score:
                    best_score = score
                    best_i = i
                    note = f"fallback downside momentum score={score:.4f}"
            return best_i, note or "fallback downside momentum"

        if kind == "sideways_chop":
            for i in indices:
                ic = _indicator_tail(rolled, i)
                ema_t = str(ic.get("ema_trend") or "")
                atr_st = str(ic.get("atr_volume_state") or "")
                tail = rolled[: i + 1][-60:]
                cc = _closes(tail)
                if len(cc) < 40:
                    continue
                drift = abs(cc[-1] - cc[-40]) / max(1e-12, abs(cc[-40]))
                if ema_t == "neutral_trend" and drift < 0.012 and atr_st in ("low_volatility", "normal_volatility"):
                    return i, "matched neutral_trend + low drift"
            return None, "no ideal chop window"

        if kind == "fake_breakout":
            for i in indices:
                sc = _fake_breakout_score(rolled, i)
                if sc > 1.35:
                    return i, f"trap proxy score={sc:.3f}"
            # weakest directional chase windows often near traps — take best score
            best_i2: int | None = None
            best_sc = -1.0
            for i in indices:
                sc = _fake_breakout_score(rolled, i)
                if sc > best_sc:
                    best_sc = sc
                    best_i2 = i
            return best_i2, f"best_effort trap proxy score={best_sc:.3f}"

        if kind == "real_breakout":
            for i in indices:
                sc = _real_breakout_score(rolled, i)
                if sc > 0.008:
                    return i, f"breakout proxy score={sc:.5f}"
            best_i2: int | None = None
            best_sc = -1.0
            for i in indices:
                sc = _real_breakout_score(rolled, i)
                if sc > best_sc:
                    best_sc = sc
                    best_i2 = i
            return best_i2, f"best_effort breakout proxy score={best_sc:.5f}"

        if kind == "overextended_long":
            for i in indices:
                ic = _indicator_tail(rolled, i)
                rsi_s = str(ic.get("rsi_state") or "")
                ema_t = str(ic.get("ema_trend") or "")
                if ema_t == "bullish_trend" and rsi_s in ("continuation_pressure", "overbought"):
                    return i, "matched bullish_trend + rsi heat"
            return None, "no rsi heat window"

        if kind == "overextended_short":
            for i in indices:
                ic = _indicator_tail(rolled, i)
                rsi_s = str(ic.get("rsi_state") or "")
                ema_t = str(ic.get("ema_trend") or "")
                if ema_t == "bearish_trend" and rsi_s in ("continuation_weakness", "oversold"):
                    return i, "matched bearish_trend + rsi stretched"
            return None, "no rsi stretched short window"

        if kind == "high_volatility":
            for i in indices:
                ic = _indicator_tail(rolled, i)
                if str(ic.get("atr_volume_state") or "") == "high_volatility":
                    return i, "matched atr high_volatility"
            return None, "no high_volatility window in scan"

        if kind == "neutral_for_memory":
            # Mid-history stable window — memory injection dominates interpretation.
            i = min(indices[len(indices) // 2], len(rolled) - 5)
            return i, "neutral anchor for memory injection"

        return None, f"unknown kind {kind!r}"

    out: list[dict[str, Any]] = []
    fallback_ms = int(rolled[-40]["open_time"])

    for tmpl in templates:
        kind = str(tmpl["kind"])
        idx, note = best_match(tmpl)
        if idx is None:
            idx = min(indices[len(indices) // 2], len(rolled) - 5)
            note = (note + "; " if note else "") + "used_mid_series_fallback"
        decision_open_time_ms = int(rolled[idx]["open_time"])
        row = {
            **tmpl,
            "symbol": sym,
            "candle_timeframe_minutes": tf,
            "decision_open_time_ms": decision_open_time_ms,
            "bars_window_note": f"rolled[{kind}] idx={idx} open_time_ms={decision_open_time_ms}",
            "window_resolution_v1": {
                "resolved_index_v1": idx,
                "resolution_note_v1": note,
                "fallback_time_used_v1": decision_open_time_ms == fallback_ms,
            },
        }
        out.append(row)

    return out, None


def synthetic_retrieved_experience_v1(
    *,
    candle_timeframe_minutes: int,
    injection: str | None,
) -> list[dict[str, Any]]:
    """Minimal retrieval-shaped rows for memory scenarios (passed to entry reasoning as ``rse``)."""
    if injection is None:
        return []
    tf = int(candle_timeframe_minutes)
    base = {
        "record_id": "gt038_exam_memory_probe_positive_v1"
        if injection == "positive"
        else "gt038_exam_memory_probe_negative_v1",
        "candle_timeframe_minutes": tf,
        "referee_outcome_subset": {"pnl": 420.0}
        if injection == "positive"
        else {"pnl": -880.0},
    }
    return [base]


__all__ = [
    "GT041_STYLE_EXAM_IDS_V1",
    "pick_dense_symbol_v1",
    "resolve_scenario_windows_v1",
    "scenario_templates_gt041_memory_ev_v1",
    "scenario_templates_v1",
    "synthetic_retrieved_experience_v1",
]
