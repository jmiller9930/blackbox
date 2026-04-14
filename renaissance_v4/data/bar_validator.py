"""
bar_validator.py

Purpose:
Validate historical 5-minute Binance bars stored in SQLite.

Usage:
Run after ingestion to detect gaps, duplicates, or ordering problems.

Version:
v1.0

Change History:
- v1.0 Initial implementation scaffold.
"""

from __future__ import annotations

from renaissance_v4.utils.db import get_connection

EXPECTED_SPACING_MS = 5 * 60 * 1000
SYMBOL = "SOLUSDT"


def main() -> None:
    """
    Validate that all bars are strictly increasing and evenly spaced.
    """
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT open_time
        FROM market_bars_5m
        WHERE symbol = ?
        ORDER BY open_time ASC
        """,
        (SYMBOL,),
    ).fetchall()

    print(f"[validator] Loaded {len(rows)} bars for symbol {SYMBOL}")

    if not rows:
        raise RuntimeError("[validator] No bars found to validate")

    gap_count = 0
    for index in range(1, len(rows)):
        previous_open = rows[index - 1]["open_time"]
        current_open = rows[index]["open_time"]
        delta = current_open - previous_open

        if delta != EXPECTED_SPACING_MS:
            gap_count += 1
            print(
                "[validator] Gap detected: "
                f"index={index} previous_open={previous_open} current_open={current_open} delta={delta}"
            )

    if gap_count > 0:
        raise RuntimeError(f"[validator] Validation failed with {gap_count} spacing issues")

    print("[validator] Validation passed with no spacing issues")


if __name__ == "__main__":
    main()
