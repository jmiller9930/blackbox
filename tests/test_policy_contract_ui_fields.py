"""Policy contract summary and session WIN/LOSS for parallel results / API."""

from __future__ import annotations

from renaissance_v4.game_theory.scenario_contract import (
    extract_policy_contract_summary,
    referee_session_outcome,
)


def test_extract_policy_contract_summary_minimal() -> None:
    m = {
        "strategy_id": "s1",
        "symbol": "SOLUSDT",
        "timeframe": "5m",
        "signal_modules": ["a", "b"],
        "regime_module": "regime_v1_default",
        "risk_model": "risk_governor_v1_default",
        "fusion_module": "fusion_geometric_v1",
        "execution_template": "execution_manager_v1_default",
    }
    s = extract_policy_contract_summary(m)
    assert s["signal_modules"] == ["a", "b"]
    assert s["fusion_module"] == "fusion_geometric_v1"


def test_referee_session_outcome() -> None:
    assert referee_session_outcome(False, {"cumulative_pnl": 100}) == "ERROR"
    assert referee_session_outcome(True, {"cumulative_pnl": 0.01}) == "WIN"
    assert referee_session_outcome(True, {"cumulative_pnl": 0.0}) == "LOSS"
    assert referee_session_outcome(True, {"cumulative_pnl": -1.0}) == "LOSS"
