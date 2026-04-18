"""Single-silo indicator context quality (tide metaphor, not raw numbers alone)."""

from __future__ import annotations

from renaissance_v4.game_theory.context_memory import (
    CONTEXT_SILO_ID,
    assess_indicator_context,
)


def test_missing_context_is_flagged() -> None:
    q = assess_indicator_context(None)
    assert q["level"] == "missing"
    assert q["silo"] == CONTEXT_SILO_ID


def test_rich_context() -> None:
    q = assess_indicator_context(
        {"regime": "range", "direction": "long", "transition": "fade", "rsi": 55}
    )
    assert q["level"] == "rich"
    assert "regime" in q["matched_signal_keys"]


def test_noise_risk_raw_number_only() -> None:
    q = assess_indicator_context({"rsi": 55, "macd": 0.1})
    assert q["level"] == "noise_risk"
