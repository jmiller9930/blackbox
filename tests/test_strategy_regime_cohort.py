"""Strategy label + regime cohort stats and catalog validation."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_compute_strategy_regime_stats_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_STRATEGY_STATS_MIN_N", "2")
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.strategy_stats import compute_strategy_regime_stats

    append_paper_trade(
        symbol="S",
        side="long",
        result="won",
        pnl_usd=1.0,
        timeframe="5m",
        strategy_label="jupiter_supertrend_ema_rsi_atr_v1",
        regime="nominal",
    )
    append_paper_trade(
        symbol="S",
        side="long",
        result="lost",
        pnl_usd=-0.5,
        timeframe="5m",
        strategy_label="jupiter_supertrend_ema_rsi_atr_v1",
        regime="nominal",
    )
    rows = compute_strategy_regime_stats()
    assert len(rows) == 1
    assert rows[0]["strategy_label"] == "jupiter_supertrend_ema_rsi_atr_v1"
    assert rows[0]["regime"] == "nominal"
    assert rows[0]["meets_min_n"] is True
    assert rows[0]["decisive_trades"] == 2


def test_strict_strategy_label_rejects_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_STRICT_STRATEGY_LABELS", "1")
    from modules.anna_training.paper_trades import append_paper_trade

    with pytest.raises(ValueError, match="strategy_label_not_in_catalog"):
        append_paper_trade(
            symbol="S",
            side="long",
            result="won",
            pnl_usd=1.0,
            timeframe="5m",
            strategy_label="not_in_catalog_xyz",
        )


def test_regime_signal_file_merged_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    sig = {
        "schema": "trading_core_signal_v1",
        "ts_utc": "2026-01-01T00:00:00Z",
        "long_ok": True,
        "short_ok": False,
        "filters_pass": True,
        "bar_ts": "2026-01-01T00:00:00Z",
    }
    (tmp_path / "trading_core_signal.json").write_text(__import__("json").dumps(sig), encoding="utf-8")
    from modules.anna_training.regime_signal import load_trading_core_signal, signal_allows_execution_path

    loaded = load_trading_core_signal()
    assert loaded is not None
    assert signal_allows_execution_path(loaded) is True
