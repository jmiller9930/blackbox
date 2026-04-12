#!/usr/bin/env python3
"""Print full accounting for one baseline Jupiter_2 lifecycle trade (read-only).

Uses execution_ledger.db: execution_trades, position_events, policy_evaluations.
Example (repo root):

  BLACKBOX_EXECUTION_LEDGER_PATH=/path/to/execution_ledger.db \\
    python3 scripts/runtime/baseline_trade_accounting.py --trade-id 'bl_lc_...'

See docs/trading/jupiter_2_baseline_operator_rules.md — "Full accounting".
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.anna_training.execution_ledger import RESERVED_STRATEGY_BASELINE, compute_pnl_usd

LANE = "baseline"
STRATEGY = RESERVED_STRATEGY_BASELINE
SIGNAL_MODE = "sean_jupiter_v1"
RC_HOLD = "jupiter_2_baseline_holding"
RC_EXIT = "jupiter_2_baseline_exit"


def _default_db() -> Path:
    raw = (os.environ.get("BLACKBOX_EXECUTION_LEDGER_PATH") or "").strip()
    if raw:
        return Path(raw)
    return ROOT / "data" / "sqlite" / "execution_ledger.db"


def _parse_json_obj(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        o = json.loads(raw)
        return o if isinstance(o, dict) else {}
    except json.JSONDecodeError:
        return {}


def _fetch_policy_rows(
    conn: sqlite3.Connection,
    trade_id: str,
    entry_mid: str,
    exit_mid: str,
) -> list[sqlite3.Row]:
    """Rows for this trade: entry + exit by id, held rows via open_position.trade_id in JSON."""
    like = '%"trade_id": "' + trade_id.replace("%", "\\%") + '"%'
    cur = conn.execute(
        """
        SELECT id, market_event_id, trade, reason_code, features_json, evaluated_at_utc, pnl_usd
        FROM policy_evaluations
        WHERE lane = ? AND strategy_id = ? AND signal_mode = ?
          AND (
            market_event_id IN (?, ?)
            OR features_json LIKE ?
          )
        ORDER BY evaluated_at_utc ASC, id ASC
        """,
        (LANE, STRATEGY, SIGNAL_MODE, entry_mid, exit_mid, like),
    )
    return list(cur.fetchall())


def _phase_label(
    *,
    tid: str,
    trade_i: int,
    rc: str,
    mid: str,
    entry_mid: str,
    exit_mid: str,
    feat: dict[str, object],
) -> str:
    if mid == entry_mid and trade_i == 1:
        return "open"
    if rc == RC_HOLD:
        return "held"
    if rc == RC_EXIT and mid == exit_mid:
        return "closed (exit policy)"
    op = feat.get("open_position")
    if isinstance(op, dict) and str(op.get("trade_id") or "") == tid:
        return "held"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser(description="Baseline lifecycle trade accounting (read-only).")
    ap.add_argument("--db", type=Path, default=None, help="execution_ledger.db path")
    ap.add_argument("--trade-id", required=True, help="execution_trades.trade_id (e.g. bl_lc_...)")
    args = ap.parse_args()
    trade_id = str(args.trade_id).strip()
    db_path = args.db or _default_db()
    if not db_path.is_file():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ex = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, created_at_utc
            FROM execution_trades
            WHERE trade_id = ? AND lane = ?
            """,
            (trade_id, LANE),
        ).fetchone()
        if not ex:
            print(f"No baseline execution_trades row for trade_id={trade_id!r}", file=sys.stderr)
            print("Hint: list recent closes with:", file=sys.stderr)
            print(
                "  sqlite3 ... \"SELECT trade_id, market_event_id, pnl_usd, exit_reason "
                "FROM execution_trades WHERE lane='baseline' ORDER BY created_at_utc DESC LIMIT 10;\"",
                file=sys.stderr,
            )
            return 1

        ctx = _parse_json_obj(str(ex["context_snapshot_json"] or ""))
        entry_mid = str(ctx.get("entry_market_event_id") or "").strip()
        exit_mid = str(ex["market_event_id"] or "").strip()

        print("=== execution_trades (closed) ===")
        for k in ex.keys():
            if k == "context_snapshot_json":
                print(f"  {k}: <json, {len(str(ex[k] or ''))} chars>")
                continue
            print(f"  {k}: {ex[k]}")

        pnl_row = float(ex["pnl_usd"])
        ep = float(ex["entry_price"])
        xp = float(ex["exit_price"])
        sz = float(ex["size"])
        side = str(ex["side"] or "long").strip().lower()
        pnl_re = compute_pnl_usd(entry_price=ep, exit_price=xp, size=sz, side=side)
        print("\n=== PnL check (compute_pnl_usd vs execution_trades.pnl_usd) ===")
        print(f"  recomputed: {pnl_re:.8f}")
        print(f"  ledger:     {pnl_row:.8f}")
        if abs(pnl_re - pnl_row) > 1e-6:
            print("  WARNING: mismatch above float tolerance")
        else:
            print("  OK")

        print("\n=== position_events (sequence) ===")
        pe = conn.execute(
            """
            SELECT trade_id, market_event_id, sequence_num, event_type, payload_json, created_at_utc
            FROM position_events
            WHERE trade_id = ?
            ORDER BY sequence_num ASC
            """,
            (trade_id,),
        ).fetchall()
        if not pe:
            print("  (none)")
        for r in pe:
            print(
                f"  seq={r['sequence_num']} {r['event_type']} mid={r['market_event_id']} "
                f"at {r['created_at_utc']}"
            )
            pj = _parse_json_obj(str(r["payload_json"] or ""))
            if pj:
                print(f"    payload: {json.dumps(pj, default=str)[:500]}")

        if not entry_mid:
            print(
                "\nWARNING: context_snapshot_json missing entry_market_event_id; "
                "cannot select policy rows by entry bar.",
                file=sys.stderr,
            )

        print("\n=== policy_evaluations (open → held → closed) ===")
        if entry_mid and exit_mid:
            rows = _fetch_policy_rows(conn, trade_id, entry_mid, exit_mid)
        else:
            rows = []

        if not rows:
            print("  No matching rows (check entry_mid/exit_mid and signal_mode).")
        for r in rows:
            feat = _parse_json_obj(str(r["features_json"] or ""))
            ph = _phase_label(
                tid=trade_id,
                trade_i=int(r["trade"]),
                rc=str(r["reason_code"] or ""),
                mid=str(r["market_event_id"]),
                entry_mid=entry_mid,
                exit_mid=exit_mid,
                feat=feat,
            )
            print(
                f"\n  [{ph}] id={r['id']} mid={r['market_event_id']} "
                f"trade={r['trade']} rc={r['reason_code']} at={r['evaluated_at_utc']}"
            )
            if ph == "open":
                print("    (entry bar: signal features; no open_position in this upsert)")
            if ph == "held" or str(r["reason_code"]) == RC_HOLD:
                op = feat.get("open_position")
                ur = feat.get("unrealized_pnl_usd")
                print(f"    unrealized_pnl_usd (stored): {ur}")
                if isinstance(op, dict):
                    e = float(op.get("entry_price") or 0)
                    # Mark is bar close on that evaluation (bridge); not duplicated in open_position — full unrealized check needs OHLC
                    side_o = str(op.get("side") or "long").strip().lower()
                    sz_o = float(op.get("size") or 1.0)
                    print(
                        f"    open_position: entry={e} side={side_o} size={sz_o} "
                        f"sl={op.get('stop_loss')} tp={op.get('take_profit')}"
                    )
            if ph == "closed (exit policy)" or str(r["reason_code"]) == RC_EXIT:
                exx = feat.get("exit")
                print(f"    exit feature: {json.dumps(exx, default=str) if exx is not None else 'null'}")

        print("\n=== summary ===")
        print(f"  entry_market_event_id: {entry_mid or '(missing)'}")
        print(f"  exit_market_event_id:  {exit_mid}")
        print(f"  trade_id:              {trade_id}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
