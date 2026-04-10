"""T2 decision_trace — structured, persisted, replayable steps per (market_event_id, strategy_id)."""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, ensure_execution_ledger_schema
from modules.anna_training.store import utc_now_iso

TRACE_SCHEMA_VERSION = "decision_trace_v1"
LEARNING_PROOF_SCHEMA = "learning_proof_v1"
RATIONALE_MAX_LEN = 512

STEP_NAMES = frozenset({"ingest", "feature_calc", "policy_check", "decision", "execution"})


def _pnl_close(a: float, b: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and abs(float(a) - float(b)) <= 1e-6


def _clamp_rationale(s: str | None) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    if len(t) > RATIONALE_MAX_LEN:
        return t[: RATIONALE_MAX_LEN - 3] + "..."
    return t


def _validate_steps(steps: list[dict[str, Any]], *, market_event_id: str) -> None:
    if not steps:
        raise ValueError("decision_trace.steps must be non-empty")
    mid = (market_event_id or "").strip()
    for i, st in enumerate(steps):
        if not isinstance(st, dict):
            raise ValueError(f"steps[{i}] must be an object")
        sn = str(st.get("step_name") or "").strip()
        if sn not in STEP_NAMES:
            raise ValueError(f"steps[{i}].step_name invalid: {sn!r}")
        if not str(st.get("timestamp") or "").strip():
            raise ValueError(f"steps[{i}].timestamp required")
        refs = st.get("input_refs")
        if not isinstance(refs, dict):
            raise ValueError(f"steps[{i}].input_refs must be an object")
        ir_mid = str(refs.get("market_event_id") or "").strip()
        if ir_mid != mid:
            raise ValueError(
                f"steps[{i}].input_refs.market_event_id must match trace market_event_id"
            )
        if not str(refs.get("bar_id") or "").strip():
            raise ValueError(f"steps[{i}].input_refs.bar_id required (grounding)")
        out = st.get("output")
        if not isinstance(out, dict):
            raise ValueError(f"steps[{i}].output must be a structured object")
        rat = st.get("rationale")
        if rat is not None:
            _clamp_rationale(str(rat))


def build_input_refs(
    *,
    market_event_id: str,
    bar_id: str | int,
    snapshot_id: str | None = None,
    ledger_ref: str | None = None,
) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "market_event_id": (market_event_id or "").strip(),
        "bar_id": str(bar_id).strip(),
    }
    if snapshot_id:
        refs["snapshot_id"] = str(snapshot_id).strip()
    if ledger_ref:
        refs["ledger_ref"] = str(ledger_ref).strip()
    return refs


def build_parallel_anna_paper_stub_steps(
    *,
    market_event_id: str,
    strategy_id: str,
    bar: dict[str, Any],
    stub_result: str,
    stub_pnl_usd: float,
    trade_id: str,
    trace_id: str,
    runner: str = "parallel_strategy_runner_v1",
) -> list[dict[str, Any]]:
    """Ordered steps for Anna lane paper_stub parallel harness (full structure, explicit stub marking)."""
    mid = (market_event_id or "").strip()
    bar_id = bar.get("id")
    if bar_id is None:
        bar_id = mid
    sym = str(bar.get("canonical_symbol") or "")
    tf = str(bar.get("timeframe") or "")
    base_refs = build_input_refs(market_event_id=mid, bar_id=bar_id)

    def _ts() -> str:
        return utc_now_iso()

    steps: list[dict[str, Any]] = [
        {
            "step_name": "ingest",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "source": "market_bars_5m",
                "canonical_symbol": sym,
                "timeframe": tf,
                "candle_open_utc": bar.get("candle_open_utc"),
                "candle_close_utc": bar.get("candle_close_utc"),
            },
            "rationale": _clamp_rationale("Canonical bar row read for latest closed candle."),
        },
        {
            "step_name": "feature_calc",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "ohlc": {
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                },
                "fields": ["open", "high", "low", "close"],
            },
        },
        {
            "step_name": "policy_check",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "anna_lane_allowed": True,
                "parallel_runner": runner,
                "paper_stub_explicit": True,
            },
        },
        {
            "step_name": "decision",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "mode": "paper_stub",
                "classification": stub_result,
                "stub_pnl_usd": stub_pnl_usd,
                "trade_id_planned": trade_id,
            },
            "rationale": _clamp_rationale(
                "Deterministic stub classification from strategy_id+market_event_id hash (not venue truth)."
            ),
        },
        {
            "step_name": "execution",
            "timestamp": _ts(),
            "input_refs": build_input_refs(
                market_event_id=mid,
                bar_id=bar_id,
                ledger_ref="execution_trades",
            ),
            "output": {
                "status": "written",
                "trade_id": trade_id,
                "trace_id": trace_id,
                "lane": "anna",
                "mode": "paper_stub",
            },
        },
    ]
    _validate_steps(steps, market_event_id=mid)
    return steps


def build_parallel_anna_paper_steps(
    *,
    market_event_id: str,
    strategy_id: str,
    bar: dict[str, Any],
    trade_id: str,
    trace_id: str,
    entry_price: float,
    exit_price: float,
    size: float,
    side: str,
    runner: str = "parallel_strategy_runner_v1",
    signal_reason_code: str | None = None,
) -> list[dict[str, Any]]:
    """Ordered steps for Anna lane **economic paper** parallel harness (PnL derived in ledger)."""
    from modules.anna_training.execution_ledger import compute_pnl_usd

    mid = (market_event_id or "").strip()
    bar_id = bar.get("id")
    if bar_id is None:
        bar_id = mid
    sym = str(bar.get("canonical_symbol") or "")
    tf = str(bar.get("timeframe") or "")
    base_refs = build_input_refs(market_event_id=mid, bar_id=bar_id)
    pnl_preview = compute_pnl_usd(
        entry_price=float(entry_price),
        exit_price=float(exit_price),
        size=float(size),
        side=str(side).strip().lower(),
    )

    def _ts() -> str:
        return utc_now_iso()

    steps: list[dict[str, Any]] = [
        {
            "step_name": "ingest",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "source": "market_bars_5m",
                "canonical_symbol": sym,
                "timeframe": tf,
                "candle_open_utc": bar.get("candle_open_utc"),
                "candle_close_utc": bar.get("candle_close_utc"),
            },
            "rationale": _clamp_rationale("Canonical bar row for parallel economic paper harness."),
        },
        {
            "step_name": "feature_calc",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "ohlc": {
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                },
                "entry_price": entry_price,
                "exit_price": exit_price,
                "size": size,
                "side": side,
            },
        },
        {
            "step_name": "policy_check",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "anna_lane_allowed": True,
                "parallel_runner": runner,
                "economic_paper": True,
                "sean_jupiter_v1": True,
                "policy_engine": "jupiter_2",
                "signal_reason_code": signal_reason_code,
            },
        },
        {
            "step_name": "decision",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "mode": "paper",
                "trade_id_planned": trade_id,
                "derived_pnl_usd_preview": round(pnl_preview, 8),
            },
            "rationale": _clamp_rationale(
                f"Open→close {side} on canonical bar (Jupiter_2 policy fired"
                + (f", {signal_reason_code}" if signal_reason_code else "")
                + "); parallel Anna measurement vs baseline on same market_event_id."
            ),
        },
        {
            "step_name": "execution",
            "timestamp": _ts(),
            "input_refs": build_input_refs(
                market_event_id=mid,
                bar_id=bar_id,
                ledger_ref="execution_trades",
            ),
            "output": {
                "status": "written",
                "trade_id": trade_id,
                "trace_id": trace_id,
                "lane": "anna",
                "mode": "paper",
            },
        },
    ]
    _validate_steps(steps, market_event_id=mid)
    return steps


def build_baseline_bridge_steps(
    *,
    market_event_id: str,
    strategy_id: str,
    bar: dict[str, Any],
    mode: str,
    trade_id: str,
    trace_id: str,
    pnl_usd: float,
    side: str = "long",
    economic_basis: str = "canonical_bar_open_to_close_long_1unit",
    signal_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Baseline lane: same bar grounding; economic PnL from open→close 1 unit (long or short)."""
    mid = (market_event_id or "").strip()
    bar_id = bar.get("id")
    if bar_id is None:
        bar_id = mid

    def _ts() -> str:
        return utc_now_iso()

    base_refs = build_input_refs(market_event_id=mid, bar_id=bar_id)
    o = bar.get("open")
    c = bar.get("close")
    sd = (side or "long").strip().lower()
    if sd not in ("long", "short"):
        sd = "long"
    sig = signal_snapshot if isinstance(signal_snapshot, dict) else {}
    steps: list[dict[str, Any]] = [
        {
            "step_name": "ingest",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "source": "market_bars_5m",
                "bridge": "baseline_ledger_bridge_v1",
            },
        },
        {
            "step_name": "feature_calc",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "ohlc": {
                    "open": o,
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": c,
                },
                "economic_basis": economic_basis,
                "jupiter_policy_signal": sig,
            },
        },
        {
            "step_name": "policy_check",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {"baseline_lane": True, "mode": mode, "trade_policy": "jupiter_perps_sean_rules_v1"},
        },
        {
            "step_name": "decision",
            "timestamp": _ts(),
            "input_refs": dict(base_refs),
            "output": {
                "side": sd,
                "size": 1.0,
                "entry_price": float(o) if o is not None else None,
                "exit_price": float(c) if c is not None else None,
                "derived_pnl_usd": pnl_usd,
            },
        },
        {
            "step_name": "execution",
            "timestamp": _ts(),
            "input_refs": build_input_refs(
                market_event_id=mid,
                bar_id=bar_id,
                ledger_ref="execution_trades",
            ),
            "output": {
                "status": "written",
                "trade_id": trade_id,
                "trace_id": trace_id,
                "lane": "baseline",
                "mode": mode,
            },
        },
    ]
    _validate_steps(steps, market_event_id=mid)
    return steps


def _json_obj_or_none(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def insert_decision_trace(
    conn: sqlite3.Connection,
    *,
    trace_id: str,
    market_event_id: str,
    strategy_id: str,
    lane: str,
    mode: str,
    paper_stub: bool,
    timestamp_start_utc: str,
    timestamp_end_utc: str,
    steps: list[dict[str, Any]],
    trade_id: str | None,
    retrieved_memory_ids: list[str] | None = None,
    memory_used: bool = False,
    decision_summary: str | None = None,
    baseline_action_json: dict[str, Any] | None = None,
    anna_action_json: dict[str, Any] | None = None,
    memory_ablation_off: bool = False,
) -> None:
    _validate_steps(steps, market_event_id=market_event_id)
    lane_n = (lane or "").strip().lower()
    if lane_n not in ("baseline", "anna"):
        raise ValueError("lane must be baseline or anna")
    mode_n = (mode or "").strip().lower()
    rids = list(retrieved_memory_ids or [])
    conn.execute(
        """
        INSERT INTO decision_traces (
          trace_id, market_event_id, strategy_id, lane, mode, paper_stub,
          timestamp_start_utc, timestamp_end_utc, steps_json, trade_id, schema_version, created_at_utc,
          retrieved_memory_ids_json, memory_used, decision_summary, baseline_action_json, anna_action_json,
          memory_ablation_off, learning_proof_schema
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trace_id.strip(),
            market_event_id.strip(),
            strategy_id.strip(),
            lane_n,
            mode_n,
            1 if paper_stub else 0,
            timestamp_start_utc,
            timestamp_end_utc,
            json.dumps(steps, ensure_ascii=False),
            (trade_id or "").strip() or None,
            TRACE_SCHEMA_VERSION,
            utc_now_iso(),
            json.dumps(rids, ensure_ascii=False),
            1 if memory_used else 0,
            _clamp_rationale(decision_summary),
            _json_obj_or_none(baseline_action_json),
            _json_obj_or_none(anna_action_json),
            1 if memory_ablation_off else 0,
            LEARNING_PROOF_SCHEMA,
        ),
    )


def persist_parallel_anna_stub_trade_with_trace(
    *,
    market_event_id: str,
    strategy_id: str,
    bar: dict[str, Any],
    stub_result: str,
    stub_pnl_usd: float,
    trade_id: str,
    context_snapshot: dict[str, Any],
    notes: str | None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Single transaction: ``decision_traces`` row then ``execution_trades`` with matching ``trace_id``.
    """
    from modules.anna_training.execution_ledger import append_execution_trade
    from modules.anna_training.learning_proof import compute_learning_proof_attachment

    trace_id = str(uuid.uuid4())
    ts_start = utc_now_iso()
    steps = build_parallel_anna_paper_stub_steps(
        market_event_id=market_event_id,
        strategy_id=strategy_id,
        bar=bar,
        stub_result=stub_result,
        stub_pnl_usd=stub_pnl_usd,
        trade_id=trade_id,
        trace_id=trace_id,
    )
    ts_end = utc_now_iso()
    lp = compute_learning_proof_attachment(
        strategy_id=strategy_id,
        market_event_id=market_event_id,
        bar=bar,
        mode="paper_stub",
    )
    ctx = dict(context_snapshot or {})
    ctx["learning_proof"] = lp

    close_px = bar.get("close")
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        insert_decision_trace(
            conn,
            trace_id=trace_id,
            market_event_id=market_event_id,
            strategy_id=strategy_id,
            lane="anna",
            mode="paper_stub",
            paper_stub=True,
            timestamp_start_utc=ts_start,
            timestamp_end_utc=ts_end,
            steps=steps,
            trade_id=trade_id,
            retrieved_memory_ids=lp["retrieved_memory_ids"],
            memory_used=bool(lp["memory_used"]),
            decision_summary=str(lp.get("decision_summary") or ""),
            baseline_action_json=lp.get("baseline_action_json"),
            anna_action_json=lp.get("anna_action_json"),
            memory_ablation_off=bool(lp.get("memory_ablation_off")),
        )
        row = append_execution_trade(
            trade_id=trade_id,
            strategy_id=strategy_id,
            lane="anna",
            mode="paper_stub",
            market_event_id=market_event_id,
            symbol="SOL-PERP",
            timeframe="5m",
            trace_id=trace_id,
            side="long",
            entry_time=bar.get("candle_open_utc"),
            entry_price=float(close_px) if close_px is not None else None,
            size=1.0,
            exit_time=bar.get("candle_close_utc"),
            exit_price=float(close_px) if close_px is not None else None,
            exit_reason="CLOSE",
            context_snapshot=ctx,
            notes=notes,
            db_path=db_path,
            conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "trace_id": trace_id,
        "trade_id": trade_id,
        "market_event_id": market_event_id,
        "strategy_id": strategy_id,
        "lane": "anna",
        "mode": "paper_stub",
        "paper_stub": True,
        "timestamp_start_utc": ts_start,
        "timestamp_end_utc": ts_end,
        "steps": steps,
        "execution_trade": row,
        "learning_proof": lp,
    }


def persist_parallel_anna_paper_trade_with_trace(
    *,
    market_event_id: str,
    strategy_id: str,
    bar: dict[str, Any],
    trade_id: str,
    context_snapshot: dict[str, Any],
    notes: str | None,
    db_path: Path | None = None,
    side: str = "long",
    signal_reason_code: str | None = None,
) -> dict[str, Any]:
    """
    Parallel harness: **economic** Anna lane ``paper`` row (PnL derived from OHLC).

    Uses open→close in ``side`` (``long`` or ``short``), size **1.0**, matching Sean Jupiter v1
    when the parallel runner only calls this after ``evaluate_sean_jupiter_baseline_v1().trade``.
    Does not affect baseline headline book (lane=anna).
    """
    from modules.anna_training.execution_ledger import append_execution_trade
    from modules.anna_training.learning_proof import compute_learning_proof_attachment

    trace_id = str(uuid.uuid4())
    ts_start = utc_now_iso()
    close_px = bar.get("close")
    open_px = bar.get("open")
    try:
        ep = float(open_px) if open_px is not None else float(close_px) if close_px is not None else None
        xp = float(close_px) if close_px is not None else None
    except (TypeError, ValueError):
        ep = xp = None
    if ep is None or xp is None:
        raise ValueError("parallel Anna paper requires bar open and close for entry/exit prices")
    size = 1.0
    sd = (side or "long").strip().lower()
    if sd not in ("long", "short"):
        sd = "long"
    sym = str(bar.get("canonical_symbol") or "SOL-PERP").strip() or "SOL-PERP"
    tf = str(bar.get("timeframe") or "5m").strip() or "5m"
    steps = build_parallel_anna_paper_steps(
        market_event_id=market_event_id,
        strategy_id=strategy_id,
        bar=bar,
        trade_id=trade_id,
        trace_id=trace_id,
        entry_price=ep,
        exit_price=xp,
        size=size,
        side=sd,
        signal_reason_code=signal_reason_code,
    )
    ts_end = utc_now_iso()
    lp = compute_learning_proof_attachment(
        strategy_id=strategy_id,
        market_event_id=market_event_id,
        bar=bar,
        mode="paper",
    )
    ctx = dict(context_snapshot or {})
    ctx.setdefault("economic_parallel_paper", True)
    ctx["learning_proof"] = lp

    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        insert_decision_trace(
            conn,
            trace_id=trace_id,
            market_event_id=market_event_id,
            strategy_id=strategy_id,
            lane="anna",
            mode="paper",
            paper_stub=False,
            timestamp_start_utc=ts_start,
            timestamp_end_utc=ts_end,
            steps=steps,
            trade_id=trade_id,
            retrieved_memory_ids=lp["retrieved_memory_ids"],
            memory_used=bool(lp["memory_used"]),
            decision_summary=str(lp.get("decision_summary") or ""),
            baseline_action_json=lp.get("baseline_action_json"),
            anna_action_json=lp.get("anna_action_json"),
            memory_ablation_off=bool(lp.get("memory_ablation_off")),
        )
        row = append_execution_trade(
            trade_id=trade_id,
            strategy_id=strategy_id,
            lane="anna",
            mode="paper",
            market_event_id=market_event_id,
            symbol=sym,
            timeframe=tf,
            trace_id=trace_id,
            side=sd,
            entry_time=bar.get("candle_open_utc"),
            entry_price=ep,
            size=size,
            exit_time=bar.get("candle_close_utc"),
            exit_price=xp,
            exit_reason="CLOSE",
            context_snapshot=ctx,
            notes=notes,
            db_path=db_path,
            conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "trace_id": trace_id,
        "trade_id": trade_id,
        "market_event_id": market_event_id,
        "strategy_id": strategy_id,
        "lane": "anna",
        "mode": "paper",
        "paper_stub": False,
        "timestamp_start_utc": ts_start,
        "timestamp_end_utc": ts_end,
        "steps": steps,
        "execution_trade": row,
        "learning_proof": lp,
    }


def persist_baseline_trade_with_trace(
    *,
    market_event_id: str,
    bar: dict[str, Any],
    mode: str,
    trade_id: str,
    pnl_usd: float,
    context_snapshot: dict[str, Any],
    notes: str | None,
    db_path: Path | None = None,
    side: str = "long",
    economic_basis: str = "canonical_bar_open_to_close_long_1unit",
    signal_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from modules.anna_training.execution_ledger import RESERVED_STRATEGY_BASELINE, append_execution_trade

    from modules.anna_training.execution_ledger import compute_pnl_usd

    trace_id = str(uuid.uuid4())
    ts_start = utc_now_iso()
    o = bar.get("open")
    c = bar.get("close")
    if o is None or c is None:
        raise ValueError("bar_missing_ohlc")
    sd = (side or "long").strip().lower()
    if sd not in ("long", "short"):
        sd = "long"
    pnl = compute_pnl_usd(entry_price=float(o), exit_price=float(c), size=1.0, side=sd)
    if not _pnl_close(pnl, float(pnl_usd)):
        raise ValueError("pnl_usd mismatch for baseline trace")
    steps = build_baseline_bridge_steps(
        market_event_id=market_event_id,
        strategy_id=RESERVED_STRATEGY_BASELINE,
        bar=bar,
        mode=mode,
        trade_id=trade_id,
        trace_id=trace_id,
        pnl_usd=pnl,
        side=sd,
        economic_basis=economic_basis,
        signal_snapshot=signal_snapshot,
    )
    ts_end = utc_now_iso()

    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        insert_decision_trace(
            conn,
            trace_id=trace_id,
            market_event_id=market_event_id,
            strategy_id=RESERVED_STRATEGY_BASELINE,
            lane="baseline",
            mode=mode,
            paper_stub=False,
            timestamp_start_utc=ts_start,
            timestamp_end_utc=ts_end,
            steps=steps,
            trade_id=trade_id,
            retrieved_memory_ids=[],
            memory_used=False,
            decision_summary="Baseline lane — no Anna memory attribution.",
            baseline_action_json=None,
            anna_action_json=None,
            memory_ablation_off=False,
        )
        trade_row = append_execution_trade(
            trade_id=trade_id,
            strategy_id=RESERVED_STRATEGY_BASELINE,
            lane="baseline",
            mode=mode,
            market_event_id=market_event_id,
            symbol=str(bar.get("canonical_symbol") or "SOL-PERP"),
            timeframe=str(bar.get("timeframe") or "5m"),
            trace_id=trace_id,
            side=sd,
            entry_time=str(bar.get("candle_open_utc") or ""),
            entry_price=float(o),
            size=1.0,
            exit_time=str(bar.get("candle_close_utc") or ""),
            exit_price=float(c),
            exit_reason="CLOSE",
            context_snapshot=context_snapshot,
            notes=notes,
            db_path=db_path,
            conn=conn,
        )
        from modules.anna_training.execution_ledger import insert_baseline_paper_lifecycle_events

        insert_baseline_paper_lifecycle_events(
            conn,
            trade_id=trade_id,
            market_event_id=market_event_id,
            bar=bar,
            side=sd,
            pnl_usd=float(pnl),
            mode=mode,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "trace_id": trace_id,
        "trade_id": trade_id,
        "market_event_id": market_event_id,
        "strategy_id": RESERVED_STRATEGY_BASELINE,
        "lane": "baseline",
        "mode": mode,
        "paper_stub": False,
        "timestamp_start_utc": ts_start,
        "timestamp_end_utc": ts_end,
        "steps": steps,
        "execution_trade": trade_row,
    }


def _parse_json_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x) for x in data if str(x).strip()]
        except json.JSONDecodeError:
            return []
    return []


def _parse_json_obj(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def row_to_api_dict(row: dict[str, Any]) -> dict[str, Any]:
    steps = json.loads(row["steps_json"]) if row.get("steps_json") else []
    rj = row.get("retrieved_memory_ids_json")
    mem_ids = _parse_json_list(rj)
    return {
        "trace_id": row.get("trace_id"),
        "market_event_id": row.get("market_event_id"),
        "strategy_id": row.get("strategy_id"),
        "lane": row.get("lane"),
        "mode": row.get("mode"),
        "paper_stub": bool(row.get("paper_stub")),
        "timestamp_start_utc": row.get("timestamp_start_utc"),
        "timestamp_end_utc": row.get("timestamp_end_utc"),
        "steps": steps,
        "trade_id": row.get("trade_id"),
        "schema_version": row.get("schema_version"),
        "created_at_utc": row.get("created_at_utc"),
        "retrieved_memory_ids": mem_ids,
        "memory_used": bool(row.get("memory_used")),
        "decision_summary": row.get("decision_summary"),
        "baseline_action_json": _parse_json_obj(row.get("baseline_action_json")),
        "anna_action_json": _parse_json_obj(row.get("anna_action_json")),
        "memory_ablation_off": bool(row.get("memory_ablation_off")),
        "learning_proof_schema": row.get("learning_proof_schema") or LEARNING_PROOF_SCHEMA,
    }


def query_trace_by_trade_id(
    trade_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    tid = (trade_id or "").strip()
    if not tid:
        return None
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            "SELECT * FROM decision_traces WHERE trade_id = ? LIMIT 1",
            (tid,),
        )
        r = cur.fetchone()
        if not r:
            return None
        cols = [d[0] for d in cur.description]
        return row_to_api_dict(dict(zip(cols, r)))
    finally:
        conn.close()


def query_traces_by_market_event_id(
    market_event_id: str,
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    mid = (market_event_id or "").strip()
    if not mid:
        return []
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT * FROM decision_traces
            WHERE market_event_id = ?
            ORDER BY timestamp_start_utc ASC, trace_id ASC
            """,
            (mid,),
        )
        cols = [d[0] for d in cur.description]
        return [row_to_api_dict(dict(zip(cols, r))) for r in cur.fetchall()]
    finally:
        conn.close()


def query_traces_by_strategy_id(
    strategy_id: str,
    *,
    limit: int = 200,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    sid = (strategy_id or "").strip()
    if not sid:
        return []
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT * FROM decision_traces
            WHERE strategy_id = ?
            ORDER BY timestamp_start_utc DESC, trace_id DESC
            LIMIT ?
            """,
            (sid, int(limit)),
        )
        cols = [d[0] for d in cur.description]
        return [row_to_api_dict(dict(zip(cols, r))) for r in cur.fetchall()]
    finally:
        conn.close()


def query_trace_by_trace_id(
    trace_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    tid = (trace_id or "").strip()
    if not tid:
        return None
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            "SELECT * FROM decision_traces WHERE trace_id = ? LIMIT 1",
            (tid,),
        )
        r = cur.fetchone()
        if not r:
            return None
        cols = [d[0] for d in cur.description]
        return row_to_api_dict(dict(zip(cols, r)))
    finally:
        conn.close()
