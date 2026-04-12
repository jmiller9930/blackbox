#!/usr/bin/env python3
"""
Operational snapshot: first baseline execution_trades row at/after a cutoff, with position_events.

Use after deploy to prove Sean Jupiter lifecycle persistence (bl_lc_…, SL/TP exit, etc.).

  BASELINE_PROOF_LEDGER_PATH — default: repo data/sqlite/execution_ledger.db
  BASELINE_PROOF_CUTOFF_UTC — ISO Zulu, e.g. 2026-04-12T21:31:00Z (rows with created_at_utc > cutoff)

Exit 0 always; prints JSON to stdout. If no rows, prints {"post_cutoff_baseline_closes": 0}.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ledger_path() -> Path:
    raw = (os.environ.get("BASELINE_PROOF_LEDGER_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _repo_root() / "data" / "sqlite" / "execution_ledger.db"


def _minutes_between(entry_s: str | None, exit_s: str | None) -> float | None:
    if not entry_s or not exit_s:
        return None
    try:
        a = datetime.fromisoformat(str(entry_s).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(exit_s).replace("Z", "+00:00"))
        if a.tzinfo is None:
            a = a.replace(tzinfo=timezone.utc)
        if b.tzinfo is None:
            b = b.replace(tzinfo=timezone.utc)
        return (b - a).total_seconds() / 60.0
    except ValueError:
        return None


def main() -> None:
    cutoff = (os.environ.get("BASELINE_PROOF_CUTOFF_UTC") or "").strip()
    if not cutoff:
        print(
            "Set BASELINE_PROOF_CUTOFF_UTC to the deploy time (ISO Zulu), e.g. 2026-04-12T21:31:00Z",
            file=sys.stderr,
        )
        sys.exit(2)
    ledger = _ledger_path()
    if not ledger.is_file():
        print(json.dumps({"error": "ledger_not_found", "path": str(ledger)}))
        return

    conn = sqlite3.connect(ledger)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM execution_trades
        WHERE strategy_id = 'baseline' AND created_at_utc > ?
        ORDER BY created_at_utc ASC LIMIT 1
        """,
        (cutoff,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        print(json.dumps({"post_cutoff_baseline_closes": 0, "cutoff_utc": cutoff, "ledger": str(ledger)}))
        return

    trade = dict(row)
    tid = str(trade.get("trade_id") or "")
    ctx_raw = trade.get("context_snapshot_json")
    ctx: dict | None
    try:
        ctx = json.loads(ctx_raw) if ctx_raw else None
    except json.JSONDecodeError:
        ctx = {"_parse_error": True, "raw": ctx_raw}

    pe_rows = cur.execute(
        """
        SELECT event_type, market_event_id, sequence_num, payload_json
        FROM position_events
        WHERE trade_id = ?
        ORDER BY sequence_num ASC
        """,
        (tid,),
    ).fetchall()
    events = []
    for et, mid, seq, pj in pe_rows:
        payload = json.loads(pj) if pj else {}
        events.append(
            {
                "event_type": et,
                "market_event_id": mid,
                "sequence_num": seq,
                "payload": payload,
            }
        )
    conn.close()

    er = (ctx or {}).get("exit_record") if isinstance(ctx, dict) else None
    held_min = None
    if isinstance(er, dict):
        try:
            held_min = float(er["hold_duration_minutes"])
        except (KeyError, TypeError, ValueError):
            held_min = None
    if held_min is None:
        held_min = _minutes_between(trade.get("entry_time"), trade.get("exit_time"))

    op = (ctx or {}).get("open_position") if isinstance(ctx, dict) else None
    if not isinstance(op, dict):
        op = {}

    out = {
        "proof_for_trade_id": tid,
        "cutoff_utc": cutoff,
        "ledger": str(ledger),
        "execution_trade": {
            "trade_id": trade.get("trade_id"),
            "entry_time": trade.get("entry_time"),
            "exit_time": trade.get("exit_time"),
            "held_duration_minutes": held_min,
            "exit_reason": trade.get("exit_reason"),
            "size": trade.get("size"),
            "size_source": op.get("size_source"),
            "notional_usd": op.get("notional_usd"),
            "free_collateral_usd": (ctx or {}).get("free_collateral_usd") if isinstance(ctx, dict) else None,
            "stop_loss_at_exit": (er or {}).get("stop_at_exit") if isinstance(er, dict) else None,
            "take_profit_at_exit": (er or {}).get("take_profit_at_exit") if isinstance(er, dict) else None,
            "initial_stop_loss": (ctx or {}).get("initial_stop_loss") if isinstance(ctx, dict) else None,
            "initial_take_profit": (ctx or {}).get("initial_take_profit") if isinstance(ctx, dict) else None,
            "created_at_utc": trade.get("created_at_utc"),
        },
        "context_snapshot": ctx,
        "position_events": events,
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
