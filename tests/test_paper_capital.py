"""Paper capital journal — contributed capital vs trading PnL."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_anna_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    (tmp_path / "state.json").write_text(
        json.dumps({"paper_wallet": {"starting_usd": 100.0}}),
        encoding="utf-8",
    )
    return tmp_path


def test_journal_seeds_initial_and_deposit(isolated_anna_dir: Path) -> None:
    from modules.anna_training.paper_capital import append_flow, build_paper_capital_summary
    from modules.anna_training.store import load_state

    s = build_paper_capital_summary(training_state=load_state())
    assert s["starting_capital"] == 100.0
    assert s["capital_added"] == 0.0
    assert s["net_contributed_capital"] == 100.0

    r = append_flow(event_type="deposit", amount_usd=25.0, note="add")
    assert r.get("ok") is True
    s2 = build_paper_capital_summary(training_state=load_state())
    assert s2["capital_added"] == 25.0
    assert s2["net_contributed_capital"] == 125.0


def test_withdrawal_reduces_net(isolated_anna_dir: Path) -> None:
    from modules.anna_training.paper_capital import append_flow, build_paper_capital_summary
    from modules.anna_training.store import load_state

    build_paper_capital_summary(training_state=load_state())
    assert append_flow(event_type="withdrawal", amount_usd=10.0, note="wd").get("ok") is True
    s = build_paper_capital_summary(training_state=load_state())
    assert s["capital_withdrawn"] == 10.0
    assert s["net_contributed_capital"] == 90.0


def test_net_contributed_used_by_resolve_bankroll(isolated_anna_dir: Path) -> None:
    from modules.anna_training.paper_wallet import resolve_paper_bankroll_start_usd
    from modules.anna_training.store import load_state

    st = load_state()
    assert resolve_paper_bankroll_start_usd(st) == 100.0
    from modules.anna_training.paper_capital import append_flow

    assert append_flow(event_type="deposit", amount_usd=50.0, note="").get("ok") is True
    st2 = load_state()
    assert resolve_paper_bankroll_start_usd(st2) == 150.0
