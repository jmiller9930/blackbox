"""
Baseline chain validation harness — market vs policy vs ledger for a 5m bar (JUPv3 / JUPv2).

Contract (JUPv3): ``binance_strategy_bars_5m`` (market truth), ``policy_evaluations`` (decision),
``execution_trades`` (recorded). Join key: ``market_event_id``.

Does not re-run policy; compares stored rows only.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import (
    BASELINE_POLICY_SLOT_JUP_V2,
    BASELINE_POLICY_SLOT_JUP_V3,
    RESERVED_STRATEGY_BASELINE,
    connect_ledger,
    default_execution_ledger_path,
    ensure_execution_ledger_schema,
    fetch_policy_evaluation_for_market_event,
    signal_mode_for_baseline_policy_slot,
)
from modules.anna_training.store import utc_now_iso

SCHEMA_VERSION = "baseline_chain_validate_v1"

# Verdict strings (operator-facing; plain English).
V_ALIGNED_NO_TRADE = "ALIGNED — NO TRADE"
V_ALIGNED_TRADE = "ALIGNED — TRADE"
V_MISALIGNED_MISSED = "MISALIGNED — MISSED TRADE"
V_MISALIGNED_EXEC = "MISALIGNED — EXECUTION OR RECORDING FAILURE"
V_INCOMPLETE = "INCOMPLETE DATA"

MAX_LAST_N = 96
MAX_RANGE_BARS = 96


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_market_db_path() -> Path | None:
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or os.environ.get("BLACKBOX_MARKET_DATA_DB") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_file() else None
    repo = _repo_root()
    for candidate in (
        repo / "data" / "sqlite" / "market_data.db",
        repo / "data" / "sqlite" / "market_data.sqlite",
    ):
        if candidate.is_file():
            return candidate
    return None


def _ensure_runtime_for_market_imports() -> None:
    rt = _repo_root() / "scripts" / "runtime"
    s = str(rt)
    import sys

    if s not in sys.path:
        sys.path.insert(0, s)


def _canonical_symbol() -> str:
    return (os.environ.get("BLACKBOX_TRADE_CHAIN_CANONICAL_SYMBOL") or "").strip() or "SOL-PERP"


def normalize_policy_slot(raw: str | None) -> str:
    s = (raw or BASELINE_POLICY_SLOT_JUP_V3).strip().lower()
    if s in (BASELINE_POLICY_SLOT_JUP_V2, "jupiter_2", "v2"):
        return BASELINE_POLICY_SLOT_JUP_V2
    return BASELINE_POLICY_SLOT_JUP_V3


def _market_table_for_slot(policy_slot: str) -> str:
    return "binance_strategy_bars_5m" if policy_slot == BASELINE_POLICY_SLOT_JUP_V3 else "market_bars_5m"


def resolve_market_event_id(
    *,
    candle_open_utc_iso: str,
    canonical_symbol: str | None = None,
) -> str:
    _ensure_runtime_for_market_imports()
    from market_data.canonical_instrument import TIMEFRAME_5M
    from market_data.canonical_time import parse_iso_zulu_to_utc
    from market_data.market_event_id import make_market_event_id

    sym = (canonical_symbol or _canonical_symbol()).strip()
    op = parse_iso_zulu_to_utc((candle_open_utc_iso or "").strip())
    if op is None:
        raise ValueError("candle_open_utc must be ISO Zulu (e.g. 2026-04-14T01:05:00Z)")
    return make_market_event_id(canonical_symbol=sym, candle_open_utc=op, timeframe=TIMEFRAME_5M)


_ALLOWED_MARKET_TABLES = frozenset({"binance_strategy_bars_5m", "market_bars_5m"})


def _fetch_market_row(
    conn: sqlite3.Connection,
    *,
    table: str,
    market_event_id: str,
) -> dict[str, Any] | None:
    if table not in _ALLOWED_MARKET_TABLES:
        raise ValueError("invalid market table")
    mid = (market_event_id or "").strip()
    if not mid:
        return None
    row = conn.execute(
        f"SELECT * FROM {table} WHERE market_event_id = ? LIMIT 1",
        (mid,),
    ).fetchone()
    if not row:
        return None
    cols = [d[0] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return dict(zip(cols, row))


def _fetch_baseline_ledger_rows(conn: sqlite3.Connection, market_event_id: str) -> list[dict[str, Any]]:
    mid = (market_event_id or "").strip()
    if not mid:
        return []
    cur = conn.execute(
        """
        SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
               side, entry_time, exit_time, exit_reason, pnl_usd, created_at_utc
        FROM execution_trades
        WHERE market_event_id = ? AND lane = ? AND strategy_id = ?
        ORDER BY created_at_utc ASC
        """,
        (mid, RESERVED_STRATEGY_BASELINE, RESERVED_STRATEGY_BASELINE),
    )
    keys = [
        "trade_id",
        "strategy_id",
        "lane",
        "mode",
        "market_event_id",
        "symbol",
        "timeframe",
        "side",
        "entry_time",
        "exit_time",
        "exit_reason",
        "pnl_usd",
        "created_at_utc",
    ]
    return [dict(zip(keys, r)) for r in cur.fetchall()]


@dataclass
class BarValidation:
    candle_open_utc: str
    market_event_id: str
    market_present: bool
    policy_present: bool
    decision_trade: bool | None
    reason_code: str | None
    signal_mode: str | None
    recorded: bool
    trade_ids: list[str]
    verdict: str
    verdict_code: str


def _verdict_from_layers(
    *,
    market_present: bool,
    policy_present: bool,
    decision_trade: bool | None,
    recorded: bool,
) -> tuple[str, str]:
    if not market_present or not policy_present or decision_trade is None:
        return V_INCOMPLETE, "incomplete_data"
    if decision_trade:
        if recorded:
            return V_ALIGNED_TRADE, "aligned_trade"
        return V_MISALIGNED_MISSED, "misaligned_missed_trade"
    if recorded:
        return V_MISALIGNED_EXEC, "misaligned_execution_or_recording"
    return V_ALIGNED_NO_TRADE, "aligned_no_trade"


def validate_bar(
    candle_open_utc_iso: str,
    policy_slot: str | None = None,
    *,
    market_db_path: Path | None = None,
    ledger_db_path: Path | None = None,
    canonical_symbol: str | None = None,
) -> dict[str, Any]:
    """
    Validate one closed 5m bar: market row, policy row (for selected slot's signal_mode), baseline ledger rows.

    Returns a dict with ``plain_english``, ``structured``, and per-bar fields for API/CLI.
    """
    slot = normalize_policy_slot(policy_slot)
    sm = signal_mode_for_baseline_policy_slot(slot)
    mpath = market_db_path if market_db_path is not None else default_market_db_path()
    lpath = ledger_db_path if ledger_db_path is not None else default_execution_ledger_path()
    sym = (canonical_symbol or _canonical_symbol()).strip()
    mid = resolve_market_event_id(candle_open_utc_iso=candle_open_utc_iso, canonical_symbol=sym)
    table = _market_table_for_slot(slot)

    market_present = False
    policy_present = False
    decision_trade: bool | None = None
    reason_code: str | None = None
    market_row: dict[str, Any] | None = None

    if not mpath or not mpath.is_file():
        out = BarValidation(
            candle_open_utc=(candle_open_utc_iso or "").strip(),
            market_event_id=mid,
            market_present=False,
            policy_present=False,
            decision_trade=None,
            reason_code=None,
            signal_mode=sm,
            recorded=False,
            trade_ids=[],
            verdict=V_INCOMPLETE,
            verdict_code="incomplete_data",
        )
        return _bar_result_to_payload(out, policy_slot=slot, market_row=None, policy_row=None, ledger_rows=[])

    _ensure_runtime_for_market_imports()
    from market_data.store import connect_market_db, ensure_market_schema

    mconn = connect_market_db(mpath)
    try:
        ensure_market_schema(mconn)
        market_row = _fetch_market_row(mconn, table=table, market_event_id=mid)
        market_present = market_row is not None
    finally:
        mconn.close()

    if not lpath.is_file():
        out = BarValidation(
            candle_open_utc=(candle_open_utc_iso or "").strip(),
            market_event_id=mid,
            market_present=market_present,
            policy_present=False,
            decision_trade=None,
            reason_code=None,
            signal_mode=sm,
            recorded=False,
            trade_ids=[],
            verdict=V_INCOMPLETE,
            verdict_code="incomplete_data",
        )
        return _bar_result_to_payload(out, policy_slot=slot, market_row=market_row, policy_row=None, ledger_rows=[])

    pol: dict[str, Any] | None = None
    lconn = connect_ledger(lpath)
    try:
        ensure_execution_ledger_schema(lconn)
        pol = fetch_policy_evaluation_for_market_event(
            lconn,
            mid,
            lane=RESERVED_STRATEGY_BASELINE,
            strategy_id=RESERVED_STRATEGY_BASELINE,
            signal_mode=sm,
        )
        policy_present = pol is not None
        if pol:
            decision_trade = bool(pol.get("trade"))
            reason_code = str(pol.get("reason_code") or "") or None
        ledger_rows = _fetch_baseline_ledger_rows(lconn, mid)
    finally:
        lconn.close()

    recorded = len(ledger_rows) > 0
    trade_ids = [str(r.get("trade_id") or "") for r in ledger_rows if r.get("trade_id")]
    verdict, vcode = _verdict_from_layers(
        market_present=market_present,
        policy_present=policy_present,
        decision_trade=decision_trade,
        recorded=recorded,
    )
    out = BarValidation(
        candle_open_utc=(candle_open_utc_iso or "").strip(),
        market_event_id=mid,
        market_present=market_present,
        policy_present=policy_present,
        decision_trade=decision_trade,
        reason_code=reason_code,
        signal_mode=sm,
        recorded=recorded,
        trade_ids=trade_ids,
        verdict=verdict,
        verdict_code=vcode,
    )
    return _bar_result_to_payload(
        out,
        policy_slot=slot,
        market_row=market_row,
        policy_row=pol if policy_present else None,
        ledger_rows=ledger_rows,
    )


def _bar_result_to_payload(
    out: BarValidation,
    *,
    policy_slot: str,
    market_row: dict[str, Any] | None,
    policy_row: dict[str, Any] | None,
    ledger_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    exp = "NO TRADE"
    dec = "NO TRADE"
    rec = "NONE"
    if out.decision_trade is True:
        exp = dec = "TRADE"
    elif out.decision_trade is False:
        exp = dec = "NO TRADE"
    else:
        exp = dec = "UNKNOWN"
    if out.recorded and out.trade_ids:
        rec = ", ".join(out.trade_ids[:3])
        if len(out.trade_ids) > 3:
            rec += f" (+{len(out.trade_ids) - 3} more)"
    elif out.recorded:
        rec = "(rows present)"

    plain_lines = [
        f"BAR: {out.candle_open_utc}",
        f"market_event_id: {out.market_event_id}",
        "",
        f"EXPECTED: {exp}",
        f"DECISION: {dec}",
        f"RECORDED: {rec}",
        "",
        f"RESULT: {out.verdict}",
    ]

    structured = {
        "candle_open_utc": out.candle_open_utc,
        "market_event_id": out.market_event_id,
        "policy_slot": policy_slot,
        "signal_mode": out.signal_mode,
        "market_table": _market_table_for_slot(policy_slot),
        "market_present": out.market_present,
        "policy_present": out.policy_present,
        "decision_trade": out.decision_trade,
        "reason_code": out.reason_code,
        "recorded": out.recorded,
        "trade_ids": out.trade_ids,
        "verdict": out.verdict,
        "verdict_code": out.verdict_code,
        "expected_label": exp,
        "decision_label": dec,
        "recorded_label": rec,
        "market_row": market_row,
        "policy_row": policy_row,
        "ledger_rows": ledger_rows,
    }
    return {
        "schema": SCHEMA_VERSION,
        "ok": True,
        "plain_english": "\n".join(plain_lines),
        "structured": structured,
    }


def _list_candle_opens_for_last_n(
    market_db_path: Path,
    *,
    policy_slot: str,
    canonical_symbol: str,
    last_n: int,
) -> list[str]:
    table = _market_table_for_slot(policy_slot)
    if table not in _ALLOWED_MARKET_TABLES:
        raise ValueError("invalid market table")
    n = max(1, min(MAX_LAST_N, int(last_n)))
    _ensure_runtime_for_market_imports()
    from market_data.store import connect_market_db, ensure_market_schema

    conn = connect_market_db(market_db_path)
    try:
        ensure_market_schema(conn)
        cur = conn.execute(
            f"""
            SELECT candle_open_utc FROM {table}
            WHERE canonical_symbol = ?
            ORDER BY candle_open_utc DESC
            LIMIT ?
            """,
            (canonical_symbol, n),
        )
        rows = [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()
    return list(reversed(rows))


def _list_candle_opens_in_range(
    market_db_path: Path,
    *,
    policy_slot: str,
    canonical_symbol: str,
    from_utc_iso: str,
    to_utc_iso: str,
) -> list[str]:
    table = _market_table_for_slot(policy_slot)
    if table not in _ALLOWED_MARKET_TABLES:
        raise ValueError("invalid market table")
    _ensure_runtime_for_market_imports()
    from market_data.store import connect_market_db, ensure_market_schema

    conn = connect_market_db(market_db_path)
    try:
        ensure_market_schema(conn)
        cur = conn.execute(
            f"""
            SELECT candle_open_utc FROM {table}
            WHERE canonical_symbol = ?
              AND candle_open_utc >= ?
              AND candle_open_utc <= ?
            ORDER BY candle_open_utc ASC
            LIMIT ?
            """,
            (canonical_symbol, from_utc_iso.strip(), to_utc_iso.strip(), MAX_RANGE_BARS + 1),
        )
        rows = [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()
    if len(rows) > MAX_RANGE_BARS:
        raise ValueError(f"range exceeds {MAX_RANGE_BARS} bars; narrow from/to")
    return rows


def validate_range(
    *,
    mode: str,
    policy_slot: str | None = None,
    candle_open_utc_iso: str | None = None,
    last_n: int | None = None,
    from_utc_iso: str | None = None,
    to_utc_iso: str | None = None,
    market_db_path: Path | None = None,
    ledger_db_path: Path | None = None,
    canonical_symbol: str | None = None,
) -> dict[str, Any]:
    """
    Validate multiple bars. Aggregation: any incomplete → INCOMPLETE; any misaligned → MISALIGNED; else ALIGNED.
    """
    slot = normalize_policy_slot(policy_slot)
    mpath = market_db_path if market_db_path is not None else default_market_db_path()
    sym = (canonical_symbol or _canonical_symbol()).strip()
    mode_l = (mode or "single").strip().lower()

    if mode_l == "single":
        co = (candle_open_utc_iso or "").strip()
        if not co:
            raise ValueError("candle_open_utc required for mode=single")
        one = validate_bar(co, policy_slot=slot, market_db_path=mpath, ledger_db_path=ledger_db_path, canonical_symbol=sym)
        s = one.get("structured") or {}
        agg = _aggregate_verdicts([str(s.get("verdict_code") or "")])
        one["aggregate"] = agg
        one["bars"] = [s]
        return one

    if not mpath or not mpath.is_file():
        return {
            "schema": SCHEMA_VERSION,
            "ok": False,
            "error": "market_db_missing",
            "plain_english": "INCOMPLETE DATA — market database not found.",
            "aggregate": {"verdict": "INCOMPLETE DATA", "verdict_code": "incomplete_data"},
            "bars": [],
        }

    if mode_l == "last_n":
        ln = last_n if last_n is not None else 12
        opens = _list_candle_opens_for_last_n(mpath, policy_slot=slot, canonical_symbol=sym, last_n=ln)
    elif mode_l == "range":
        fu = (from_utc_iso or "").strip()
        tu = (to_utc_iso or "").strip()
        if not fu or not tu:
            raise ValueError("from_utc and to_utc required for mode=range")
        opens = _list_candle_opens_in_range(mpath, policy_slot=slot, canonical_symbol=sym, from_utc_iso=fu, to_utc_iso=tu)
    else:
        raise ValueError("mode must be single, last_n, or range")

    if not opens:
        return {
            "schema": SCHEMA_VERSION,
            "ok": True,
            "plain_english": "No bars in the selected window (check range / market data).",
            "aggregate": {"verdict": "INCOMPLETE DATA", "verdict_code": "incomplete_data"},
            "bars": [],
            "structured": {"policy_slot": slot, "bar_count": 0, "generated_at_utc": utc_now_iso()},
        }

    bars_struct: list[dict[str, Any]] = []
    plain_chunks: list[str] = []
    codes: list[str] = []

    for i, co in enumerate(opens):
        one = validate_bar(co, policy_slot=slot, market_db_path=mpath, ledger_db_path=ledger_db_path, canonical_symbol=sym)
        st = one.get("structured") or {}
        bars_struct.append(st)
        codes.append(str(st.get("verdict_code") or ""))
        plain_chunks.append(one.get("plain_english") or "")
        if i < len(opens) - 1:
            plain_chunks.append("—")

    agg = _aggregate_verdicts(codes)
    overall_plain = (
        f"RANGE: {len(opens)} bar(s)\n"
        f"policy_slot: {slot}\n\n"
        + "\n\n".join(plain_chunks)
        + f"\n\nOVERALL: {agg['verdict']}"
    )
    return {
        "schema": SCHEMA_VERSION,
        "ok": True,
        "plain_english": overall_plain,
        "aggregate": agg,
        "bars": bars_struct,
        "structured": {"policy_slot": slot, "bar_count": len(opens), "generated_at_utc": utc_now_iso()},
    }


def _aggregate_verdicts(codes: list[str]) -> dict[str, Any]:
    if not codes:
        return {"verdict": "INCOMPLETE DATA", "verdict_code": "incomplete_data"}
    if any(c == "incomplete_data" for c in codes):
        return {"verdict": "INCOMPLETE DATA", "verdict_code": "incomplete_data"}
    if any(c.startswith("misaligned") for c in codes):
        return {"verdict": "MISALIGNED", "verdict_code": "misaligned"}
    return {"verdict": "ALIGNED", "verdict_code": "aligned"}


def parse_request_body(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize API POST body into validate_range kwargs."""
    mode = str(body.get("mode") or "single").strip().lower()
    policy_slot = body.get("policy_slot")
    co = body.get("candle_open_utc") or body.get("candle_open")
    last_n = body.get("last_n")
    from_u = body.get("from_utc") or body.get("from")
    to_u = body.get("to_utc") or body.get("to")
    mpath = body.get("market_db_path")
    lpath = body.get("ledger_db_path")
    cs = body.get("canonical_symbol")

    kwargs: dict[str, Any] = {
        "mode": mode,
        "policy_slot": str(policy_slot).strip() if policy_slot else None,
        "candle_open_utc_iso": str(co).strip() if co else None,
        "last_n": int(last_n) if last_n is not None and str(last_n).strip() else None,
        "from_utc_iso": str(from_u).strip() if from_u else None,
        "to_utc_iso": str(to_u).strip() if to_u else None,
        "market_db_path": Path(str(mpath)) if mpath else None,
        "ledger_db_path": Path(str(lpath)) if lpath else None,
        "canonical_symbol": str(cs).strip() if cs else None,
    }
    return kwargs


def main_cli() -> None:
    import argparse
    import json

    p = argparse.ArgumentParser(description="Baseline chain validation harness")
    p.add_argument("--policy-slot", default="jup_v3", help="jup_v2 or jup_v3")
    p.add_argument("--mode", choices=("single", "last_n", "range"), default="single")
    p.add_argument("--candle-open-utc", help="Bar open ISO Zulu")
    p.add_argument("--last-n", type=int, default=12)
    p.add_argument("--from-utc")
    p.add_argument("--to-utc")
    args = p.parse_args()
    out = validate_range(
        mode=args.mode,
        policy_slot=args.policy_slot,
        candle_open_utc_iso=args.candle_open_utc,
        last_n=args.last_n,
        from_utc_iso=args.from_utc,
        to_utc_iso=args.to_utc,
    )
    print(out.get("plain_english") or json.dumps(out, indent=2))
    if out.get("aggregate"):
        print("\n--- JSON (aggregate + bars) ---\n")
        print(json.dumps({"aggregate": out.get("aggregate"), "bars": out.get("bars")}, indent=2, default=str))


if __name__ == "__main__":
    main_cli()
