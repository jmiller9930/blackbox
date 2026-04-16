"""DV-067 — Breakeven mechanics: exit at entry after ratchet yields zero gross PnL (before fees)."""

from __future__ import annotations

from modules.anna_training.jupiter_2_baseline_lifecycle import apply_breakeven, evaluate_exit_ohlc


def test_breakeven_long_moves_stop_to_entry_then_exit_is_neutral_gross() -> None:
    """After +0.2% favorable move, stop ratchets to entry; exit at that stop → fill at entry → 0 PnL."""
    entry = 100.0
    stop0 = 95.0
    high_favorable = 100.3  # >0.2% above 100
    nsl, fired = apply_breakeven(
        side="long",
        entry=entry,
        stop_loss=stop0,
        high=high_favorable,
        low=99.0,
        breakeven_applied=False,
    )
    assert fired is True
    assert abs(nsl - entry) < 1e-9

    ex = evaluate_exit_ohlc(
        side="long",
        stop_loss=nsl,
        take_profit=110.0,
        open_=100.0,
        high=100.1,
        low=99.5,
        close=99.8,
    )
    assert ex is not None
    reason, fill = ex
    assert reason == "STOP_LOSS"
    assert abs(float(fill) - entry) < 1e-9


def test_breakeven_not_applied_without_favorable_move() -> None:
    nsl, fired = apply_breakeven(
        side="long",
        entry=100.0,
        stop_loss=95.0,
        high=100.1,
        low=99.0,
        breakeven_applied=False,
    )
    assert fired is False
    assert nsl == 95.0
