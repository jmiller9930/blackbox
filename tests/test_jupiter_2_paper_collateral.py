"""Jupiter_2 paper bankroll resolver — no hardcoded 10k stub."""

from __future__ import annotations

import pytest

from modules.anna_training.jupiter_2_paper_collateral import (
    resolve_free_collateral_usd_for_jupiter_policy,
)


def test_resolve_explicit_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUPITER_BASELINE_FREE_COLLATERAL_USD", "500")
    usd, meta = resolve_free_collateral_usd_for_jupiter_policy(training_state={})
    assert usd == 500.0
    assert meta.get("source") == "env:JUPITER_BASELINE_FREE_COLLATERAL_USD"
