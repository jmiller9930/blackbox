#!/usr/bin/env python3
"""One-time fixtures for WebUI control HTTP verification (operator paths use these paths in the form)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from modules.anna_training.execution_ledger import append_execution_trade
from modules.anna_training.sequential_engine.calibration_factory import write_calibration_from_template

PROOF = Path(__file__).resolve().parent
TEST_ID = "proof_verify_run"
STRAT = "proof_verify_strat"


def _mk_market_db(path: Path, mids: tuple[str, ...]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE market_bars_5m (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          canonical_symbol TEXT NOT NULL,
          tick_symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL DEFAULT '5m',
          candle_open_utc TEXT NOT NULL,
          candle_close_utc TEXT NOT NULL,
          market_event_id TEXT NOT NULL UNIQUE,
          open REAL, high REAL, low REAL, close REAL,
          tick_count INTEGER NOT NULL DEFAULT 0,
          volume_base REAL,
          price_source TEXT NOT NULL DEFAULT 'pyth_primary',
          bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
          computed_at TEXT NOT NULL
        );
        """
    )
    sym = "SOL-PERP"
    for i, mid in enumerate(mids):
        co = f"2025-01-0{i+1}T10:00:00+00:00"
        cc = f"2025-01-0{i+1}T10:05:00+00:00"
        conn.execute(
            """
            INSERT INTO market_bars_5m (
              canonical_symbol, tick_symbol, candle_open_utc, candle_close_utc,
              market_event_id, open, high, low, close, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 't')
            """,
            (sym, sym, co, cc, mid, 100.0 + i, 103.0 + i, 99.0 + i, 101.0 + i),
        )
    conn.commit()
    conn.close()


def _append_pair(db: Path, mid: str) -> None:
    common = {
        "symbol": "SOL-PERP",
        "timeframe": "5m",
        "side": "long",
        "entry_time": "2025-01-01T10:00:00+00:00",
        "entry_price": 100.0,
        "size": 1.0,
        "exit_time": "2025-01-01T10:12:00+00:00",
        "exit_reason": "test",
    }
    append_execution_trade(
        strategy_id="baseline",
        lane="baseline",
        mode="paper",
        market_event_id=mid,
        db_path=db,
        **common,
        exit_price=102.0,
    )
    append_execution_trade(
        strategy_id=STRAT,
        lane="anna",
        mode="paper",
        market_event_id=mid,
        db_path=db,
        **common,
        exit_price=101.0,
    )


def main() -> None:
    PROOF.mkdir(parents=True, exist_ok=True)
    cal = PROOF / "calibration_valid.json"
    write_calibration_from_template(cal, protocol_id="proof_verify_v1")
    raw = json.loads(cal.read_text(encoding="utf-8"))
    raw["n_min"] = 1
    raw["batch_size"] = 1
    cal.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    bad = PROOF / "calibration_bad_mae.json"
    bad_raw = json.loads(cal.read_text(encoding="utf-8"))
    bad_raw["mae_protocol_id"] = "INVALID_MAE"
    bad.write_text(json.dumps(bad_raw, indent=2), encoding="utf-8")

    mids = ("proof_mid1", "proof_mid2")
    (PROOF / "events.txt").write_text("\n".join(mids) + "\n", encoding="utf-8")

    ledger = PROOF / "ledger.db"
    _mk_market_db(PROOF / "market.db", mids)
    for m in mids:
        _append_pair(ledger, m)

    empty_ledger = PROOF / "ledger_empty.db"
    # minimal schema for empty ledger - use append to create schema
    append_execution_trade(
        strategy_id="baseline",
        lane="baseline",
        mode="paper",
        market_event_id="orphan",
        db_path=empty_ledger,
        symbol="SOL-PERP",
        timeframe="5m",
        side="long",
        entry_time="2025-01-01T10:00:00+00:00",
        entry_price=100.0,
        size=1.0,
        exit_time="2025-01-01T10:12:00+00:00",
        exit_price=101.0,
        exit_reason="test",
    )

    print(json.dumps({"proof_dir": str(PROOF), "calibration_valid": str(cal), "ledger": str(ledger), "test_id": TEST_ID, "strategy_id": STRAT}, indent=2))


if __name__ == "__main__":
    main()
