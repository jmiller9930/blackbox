"""
bar_validator.py

Purpose:
Validate that historical Binance 5-minute bars in SQLite are evenly spaced and ordered.

Usage:
Run after ingestion to catch missing bars or timestamp problems before replay work begins.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

from renaissance_v4.utils.db import get_connection

SYMBOL = "SOLUSDT"
EXPECTED_SPACING_MS = 5 * 60 * 1000


def main() -> None:
    """
    Verify that each adjacent bar is exactly 5 minutes apart.
    Prints any gap to the screen and fails loudly if issues are found.
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

    print(f"[validator] Loaded {len(rows)} bars for {SYMBOL}")

    if not rows:
        raise RuntimeError("[validator] No bars found to validate")

    issues = 0

    for index in range(1, len(rows)):
        previous_open = rows[index - 1]["open_time"]
        current_open = rows[index]["open_time"]
        delta = current_open - previous_open

        if delta != EXPECTED_SPACING_MS:
            issues += 1
            print(
                "[validator] Spacing issue detected: "
                f"index={index} previous_open={previous_open} current_open={current_open} delta={delta}"
            )

    if issues:
        raise RuntimeError(f"[validator] Validation failed with {issues} spacing issues")

    print("[validator] Validation passed with no spacing issues")


if __name__ == "__main__":
    main()
