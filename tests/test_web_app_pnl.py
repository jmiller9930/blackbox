"""Pattern game web_app batch PnL summary."""

from __future__ import annotations

from renaissance_v4.game_theory.pattern_game import PATTERN_GAME_STARTING_EQUITY_USD_SPEC
from renaissance_v4.game_theory.web_app import _batch_pnl_summary


def test_batch_pnl_summary_sums_ok_rows() -> None:
    start = float(PATTERN_GAME_STARTING_EQUITY_USD_SPEC)
    s = _batch_pnl_summary(
        [
            {"ok": True, "cumulative_pnl": 10.0},
            {"ok": False, "cumulative_pnl": 999.0},
            {"ok": True, "cumulative_pnl": -5.5},
        ]
    )
    assert s["batch_total_pnl_usd"] == 4.5
    assert s["ending_equity_usd"] == start + 4.5
    assert "note" in s
