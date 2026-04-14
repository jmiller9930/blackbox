"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run directly after database initialization and validation to confirm replay can process the dataset.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.utils.db import get_connection


def main() -> None:
    """
    Iterate through historical bars in strict chronological order.
    For Phase 1, generate a placeholder no-trade decision object per bar to prove the replay path works.
    """
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()

    print(f"[replay] Loaded {len(rows)} bars")

    if not rows:
        raise RuntimeError("[replay] No historical bars found")

    for index, row in enumerate(rows, start=1):
        decision = DecisionContract(
            decision_id=str(uuid.uuid4()),
            symbol=row["symbol"],
            timestamp=row["open_time"],
            market_regime="unknown",
            direction="no_trade",
            fusion_score=0.0,
            confidence_score=0.0,
            edge_score=0.0,
            risk_budget=0.0,
            execution_allowed=False,
            reason_trace={
                "phase": "phase_1_foundation",
                "note": "Replay pipeline shell only; no signal logic yet",
                "close": row["close"],
                "volume": row["volume"],
            },
        )

        if index % 5000 == 0:
            print(
                "[replay] Progress: "
                f"processed={index} symbol={decision.symbol} "
                f"timestamp={decision.timestamp} direction={decision.direction}"
            )

    print("[replay] Replay completed successfully")


if __name__ == "__main__":
    main()
