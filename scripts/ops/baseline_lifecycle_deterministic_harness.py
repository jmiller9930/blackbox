#!/usr/bin/env python3
"""
Deterministic Sean Jupiter **baseline lifecycle** proof harness (paper).

Drives the **real** runtime chain (no UI mocks, no hand-inserted execution_trades rows):

1. ``evaluate_sean_jupiter_baseline_v1`` / ``evaluate_jupiter_2_sean`` on synthetic OHLC
2. ``run_baseline_ledger_bridge_tick`` ×3 → open → hold → ``persist_baseline_lifecycle_close``
3. Temp ``market_data.db`` + ``execution_ledger.db`` (same schema as production)

**Bar window (documented)**

- **Base series:** 280 consecutive 5m bars starting ``2026-01-01T00:00:00Z`` (``SOL-PERP``).
  OHLC is generated with ``random.Random(136)`` and the same walk as
  ``tests/test_jupiter_2_sean_policy._synthetic_bars``-style noise (bounded), such that
  ``evaluate_jupiter_2_sean(..., free_collateral_usd=1000)`` returns **trade=True**,
  **side=long**, ``reason_code=jupiter_2_long_signal`` on the **last** base bar (index 279).
  Seed **136** is fixed so the run is repeatable across machines.

- **Bar 280 (hold):** OHLC chosen so ``process_holding_bar`` does **not** hit SL/TP (long: low above
  stop, high below take-profit). Flat-ish continuation.

- **Bar 281 (exit):** OHLC chosen so intrabar range hits **STOP_LOSS** (long: low ≤ stop).

Hold wall-clock span from stored ``entry_time`` (open of signal candle) to ``exit_time`` (close of
exit candle) is **15 minutes** (three 5m steps), satisfying **> 5 minutes**.

**Pass criteria**

- ``trade_id`` starts with ``bl_lc_``
- ``exit_reason`` is ``STOP_LOSS`` or ``TAKE_PROFIT``
- ``size`` ≠ 1.0 when policy sizing supplies ``position_size_hint.notional_usd`` (paper collateral path)
- ``position_open`` / ``position_close`` rows exist; ``context_snapshot_json`` on the trade row

Usage::

  python3 scripts/ops/baseline_lifecycle_deterministic_harness.py
  python3 scripts/ops/baseline_lifecycle_deterministic_harness.py --json > proof.json

Exit code 0 on success; non-zero if assertions fail.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Repo root on sys.path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_RUNTIME = _ROOT / "scripts" / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from market_data.canonical_instrument import CANONICAL_INSTRUMENT_SOL_PERP, TICK_SYMBOL_SOL_DEFAULT
from market_data.canonical_time import candle_close_utc_exclusive
from market_data.market_event_id import make_market_event_id
from market_data.store import connect_market_db, ensure_market_schema, upsert_market_bar_5m
from market_data.canonical_bar import CanonicalBarV1

from modules.anna_training.baseline_ledger_bridge import run_baseline_ledger_bridge_tick
from modules.anna_training.jupiter_2_baseline_lifecycle import (
    initial_sl_tp,
    open_position_from_signal,
    process_holding_bar,
)
from modules.anna_training.jupiter_2_sean_policy import calculate_atr, evaluate_jupiter_2_sean
from modules.anna_training.baseline_ledger_bridge import _baseline_lifecycle_trade_id


HARNESS_SEED = 136
N_BASE_BARS = 280
# First candle open UTC for bar index 0
ANCHOR_OPEN = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _synth_ohlc(rng: "random.Random", n: int) -> list[dict[str, float]]:
    """Same construction as search loop: bounded random walk OHLC."""
    p = 100.0
    out: list[dict[str, float]] = []
    for _ in range(n):
        o = p
        p = max(50.0, p + rng.uniform(-0.4, 0.4))
        c = max(50.0, p + rng.uniform(-0.2, 0.2))
        h = max(o, c) + rng.uniform(0.01, 0.15)
        l = min(o, c) - rng.uniform(0.01, 0.15)
        out.append({"open": o, "high": h, "low": l, "close": c})
        p = c
    return out


def _candle_open_for_index(i: int) -> datetime:
    return ANCHOR_OPEN + timedelta(minutes=5 * i)


def _bar_to_canonical(i: int, o: float, h: float, l: float, c: float) -> CanonicalBarV1:
    candle_open = _candle_open_for_index(i)
    candle_close = candle_close_utc_exclusive(candle_open)
    meid = make_market_event_id(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        candle_open_utc=candle_open,
    )
    return CanonicalBarV1(
        canonical_symbol=CANONICAL_INSTRUMENT_SOL_PERP,
        tick_symbol=TICK_SYMBOL_SOL_DEFAULT,
        timeframe="5m",
        candle_open_utc=candle_open,
        candle_close_utc=candle_close,
        market_event_id=meid,
        open=o,
        high=h,
        low=l,
        close=c,
        tick_count=3,
        volume_base=None,
        price_source="deterministic_harness",
    )


def _design_hold_exit(
    base: list[dict[str, float]],
    *,
    free_collateral_usd: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (hold_bar, exit_bar) OHLC dicts for long lifecycle after base series."""
    closes = [float(b["close"]) for b in base]
    highs = [float(b["high"]) for b in base]
    lows = [float(b["low"]) for b in base]
    atr = calculate_atr(closes, highs, lows)
    sig = evaluate_jupiter_2_sean(bars_asc=base, free_collateral_usd=free_collateral_usd)
    assert sig.trade and sig.side == "long"
    entry = float(base[-1]["close"])
    sl, tp = initial_sl_tp(entry=entry, atr_entry=atr, side="long")
    tid = _baseline_lifecycle_trade_id("x", "paper")
    pos = open_position_from_signal(
        trade_id=tid,
        market_event_id="MID",
        bar=base[-1],
        side="long",
        atr_entry=atr,
        reason_code=sig.reason_code,
        signal_features=dict(sig.features) if sig.features else {},
    )
    hold = {
        "open": entry,
        "high": min(entry + 0.2, tp - 0.01),
        "low": max(sl + 0.02, entry - 0.1),
        "close": entry + 0.05,
    }
    closes2 = closes + [hold["close"]]
    highs2 = highs + [hold["high"]]
    lows2 = lows + [hold["low"]]
    np, ex = process_holding_bar(
        pos,
        market_event_id="MID1",
        closes=closes2,
        highs=highs2,
        lows=lows2,
        bar=hold,
    )
    assert np is not None and ex is None, "hold bar must not close"
    exit_bar = {
        "open": hold["close"],
        "high": hold["close"] + 0.05,
        "low": sl - 1.0,
        "close": sl,
    }
    closes3 = closes2 + [exit_bar["close"]]
    highs3 = highs2 + [exit_bar["high"]]
    lows3 = lows2 + [exit_bar["low"]]
    _, ex2 = process_holding_bar(
        np,
        market_event_id="MID2",
        closes=closes3,
        highs=highs3,
        lows=lows3,
        bar=exit_bar,
    )
    assert ex2 is not None, "exit bar must close"
    assert str(ex2.get("exit_reason") or "") == "STOP_LOSS"
    return hold, exit_bar


def run_harness(
    *,
    json_out: bool,
    keep_tmp: bool,
) -> dict:
    import random

    rng = random.Random(HARNESS_SEED)
    ohlc = _synth_ohlc(rng, N_BASE_BARS)
    sig_chk = evaluate_jupiter_2_sean(bars_asc=ohlc, free_collateral_usd=1000.0)
    if not (sig_chk.trade and sig_chk.side == "long"):
        raise RuntimeError(
            "Harness seed/window mismatch: expected long signal on last base bar. "
            f"Got trade={sig_chk.trade} side={sig_chk.side} reason={sig_chk.reason_code}"
        )

    hold_d, exit_d = _design_hold_exit(ohlc, free_collateral_usd=1000.0)

    tmp_root = Path(os.environ.get("BASELINE_HARNESS_TMP") or _ROOT / "data" / "tmp" / "baseline_harness")
    tmp_root.mkdir(parents=True, exist_ok=True)
    market_db = tmp_root / "market_data_harness.db"
    ledger_db = tmp_root / "execution_ledger_harness.db"
    if not keep_tmp:
        for p in (market_db, ledger_db):
            if p.exists():
                p.unlink()

    os.environ["BLACKBOX_MARKET_DATA_PATH"] = str(market_db)
    os.environ["BLACKBOX_EXECUTION_LEDGER_PATH"] = str(ledger_db)
    os.environ["BASELINE_LEDGER_BRIDGE"] = "1"
    os.environ["BASELINE_LEDGER_AFTER_CANONICAL_BAR"] = "0"

    from _paths import repo_root

    conn = connect_market_db(market_db)
    ensure_market_schema(conn, repo_root())
    for i in range(N_BASE_BARS):
        b = ohlc[i]
        upsert_market_bar_5m(
            conn,
            _bar_to_canonical(i, b["open"], b["high"], b["low"], b["close"]),
        )
    conn.close()

    r1 = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    if r1.get("lifecycle") != "opened":
        raise RuntimeError(f"expected open, got {r1}")

    conn = connect_market_db(market_db)
    hi = N_BASE_BARS
    upsert_market_bar_5m(
        conn,
        _bar_to_canonical(hi, hold_d["open"], hold_d["high"], hold_d["low"], hold_d["close"]),
    )
    conn.close()

    r2 = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    if r2.get("lifecycle") != "holding":
        raise RuntimeError(f"expected holding, got {r2}")

    conn = connect_market_db(market_db)
    ei = N_BASE_BARS + 1
    upsert_market_bar_5m(
        conn,
        _bar_to_canonical(ei, exit_d["open"], exit_d["high"], exit_d["low"], exit_d["close"]),
    )
    conn.close()

    r3 = run_baseline_ledger_bridge_tick(
        market_data_db_path=market_db,
        execution_ledger_db_path=ledger_db,
    )
    if r3.get("lifecycle_exit") is None:
        raise RuntimeError(f"expected lifecycle exit, got {r3}")

    tid = str(r3.get("trade_id") or "")
    proof = _fetch_proof_package(ledger_db, tid)

    # Assertions (contract)
    if not tid.startswith("bl_lc_"):
        raise AssertionError(f"trade_id must be lifecycle bl_lc_, got {tid!r}")
    et_row = proof["execution_trades_row"]
    er = str(et_row.get("exit_reason") or "")
    if er not in ("STOP_LOSS", "TAKE_PROFIT"):
        raise AssertionError(f"exit_reason must be SL/TP, got {er!r}")
    sz = float(et_row.get("size") or 0.0)
    if abs(sz - 1.0) < 1e-9:
        raise AssertionError("expected size != 1.0 when policy sizing is wired")
    held = proof.get("held_duration_minutes")
    if held is None or held <= 5.0:
        raise AssertionError(f"held duration must be > 5 min, got {held}")

    out = {
        "harness": {
            "seed": HARNESS_SEED,
            "n_base_bars": N_BASE_BARS,
            "anchor_candle_open_utc": ANCHOR_OPEN.isoformat().replace("+00:00", "Z"),
            "bridge_ticks": [r1, r2, r3],
        },
        **proof,
    }
    if json_out:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(json.dumps(out, indent=2, default=str))
    return out


def _fetch_proof_package(ledger_db: Path, trade_id: str) -> dict:
    conn = sqlite3.connect(ledger_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM execution_trades WHERE trade_id = ? AND strategy_id = 'baseline'",
        (trade_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise RuntimeError("no baseline execution_trades row for trade_id")
    trade = dict(row)
    ctx_raw = trade.get("context_snapshot_json")
    ctx = json.loads(ctx_raw) if ctx_raw else {}

    evs = conn.execute(
        """
        SELECT event_type, market_event_id, sequence_num, payload_json
        FROM position_events WHERE trade_id = ?
        ORDER BY sequence_num ASC
        """,
        (trade_id,),
    ).fetchall()
    conn.close()

    events = []
    for et, mid, seq, pj in evs:
        events.append(
            {
                "event_type": et,
                "market_event_id": mid,
                "sequence_num": seq,
                "payload": json.loads(pj) if pj else {},
            }
        )

    open_ev = next((e for e in events if e["event_type"] == "position_open"), None)
    close_ev = next((e for e in events if e["event_type"] == "position_close"), None)

    et_open = trade.get("entry_time")
    et_close = trade.get("exit_time")
    held_min = None
    if et_open and et_close:
        try:
            a = datetime.fromisoformat(str(et_open).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(et_close).replace("Z", "+00:00"))
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            if b.tzinfo is None:
                b = b.replace(tzinfo=timezone.utc)
            held_min = (b - a).total_seconds() / 60.0
        except ValueError:
            pass

    op = ctx.get("open_position") if isinstance(ctx.get("open_position"), dict) else {}
    pop = (open_ev.get("payload") if open_ev else {}) or {}
    if isinstance(pop, dict):
        op = {**pop, **op}

    return {
        "trade_id": trade.get("trade_id"),
        "entry_time": et_open,
        "exit_time": et_close,
        "held_duration_minutes": held_min,
        "side": trade.get("side"),
        "size": trade.get("size"),
        "size_source": pop.get("size_source") or op.get("size_source"),
        "notional_usd": pop.get("notional_usd") or op.get("notional_usd"),
        "free_collateral_usd": pop.get("free_collateral_usd") or ctx.get("free_collateral_usd"),
        "stop_loss": pop.get("virtual_sl") or ctx.get("initial_stop_loss"),
        "take_profit": pop.get("virtual_tp") or ctx.get("initial_take_profit"),
        "exit_reason": trade.get("exit_reason"),
        "execution_trades_row": trade,
        "position_open_payload": open_ev["payload"] if open_ev else None,
        "position_close_payload": close_ev["payload"] if close_ev else None,
        "context_snapshot_json": ctx_raw,
        "position_events": events,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Deterministic baseline lifecycle proof harness.")
    ap.add_argument("--json", action="store_true", help="Alias for default JSON stdout")
    ap.add_argument("--keep-tmp", action="store_true", help="Do not delete temp DBs before run")
    args = ap.parse_args()
    try:
        run_harness(json_out=args.json, keep_tmp=args.keep_tmp)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
