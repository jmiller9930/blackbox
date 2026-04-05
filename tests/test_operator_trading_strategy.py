"""Operator-designated trading strategy (state) — promote/demote + cookie jar."""

from __future__ import annotations

import pytest

from modules.anna_training.catalog import default_state


@pytest.fixture()
def isolated_state(monkeypatch: pytest.MonkeyPatch) -> dict:
    from modules.anna_training import operator_trading_strategy as ots

    st = default_state()

    def load_state() -> dict:
        return st

    def save_state(new_st: dict) -> None:
        # Snapshot before clear — production save writes JSON; in-memory mock must not
        # clear the same dict reference that load_state() returned.
        snap = dict(new_st)
        st.clear()
        st.update(snap)

    monkeypatch.setattr(ots, "load_state", load_state)
    monkeypatch.setattr(ots, "save_state", save_state)
    monkeypatch.setattr(
        ots,
        "list_sustained_strategy_ids_from_ledger",
        lambda _db=None: ["alpha", "beta", "gamma"],
    )
    monkeypatch.setattr(
        ots,
        "build_operator_trading_bundle_part",
        lambda _db=None: {**ots.get_operator_trading_payload(), "eligible_strategy_ids": ["alpha", "beta", "gamma"]},
    )
    return st


def test_promote_then_replace_previous_goes_to_jar(isolated_state: dict) -> None:
    from modules.anna_training import operator_trading_strategy as ots

    r1 = ots.promote_designated_strategy(strategy_id="alpha")
    assert r1["ok"] is True
    assert isolated_state["operator_trading"]["designated_strategy_id"] == "alpha"
    r2 = ots.promote_designated_strategy(strategy_id="beta")
    assert r2["ok"] is True
    assert isolated_state["operator_trading"]["designated_strategy_id"] == "beta"
    jar = isolated_state["operator_trading"]["cookie_jar"]
    assert any(e.get("strategy_id") == "alpha" and e.get("action") == "replaced_by_promote" for e in jar)


def test_demote_requires_replacement(isolated_state: dict) -> None:
    from modules.anna_training import operator_trading_strategy as ots

    ots.promote_designated_strategy(strategy_id="alpha")
    r = ots.demote_designated_strategy(strategy_id="alpha", replacement_strategy_id="")
    assert r["ok"] is False
    assert r.get("reason_code") == "missing_replacement"


def test_demote_switches_and_jars_demoted(isolated_state: dict) -> None:
    from modules.anna_training import operator_trading_strategy as ots

    ots.promote_designated_strategy(strategy_id="alpha")
    r = ots.demote_designated_strategy(strategy_id="alpha", replacement_strategy_id="gamma")
    assert r["ok"] is True
    assert isolated_state["operator_trading"]["designated_strategy_id"] == "gamma"
    jar = isolated_state["operator_trading"]["cookie_jar"]
    assert any(e.get("strategy_id") == "alpha" and e.get("action") == "demoted" for e in jar)


def test_cannot_promote_baseline_lane(isolated_state: dict) -> None:
    from modules.anna_training.execution_ledger import RESERVED_STRATEGY_BASELINE
    from modules.anna_training import operator_trading_strategy as ots

    r = ots.promote_designated_strategy(strategy_id=RESERVED_STRATEGY_BASELINE)
    assert r["ok"] is False
    assert r.get("reason_code") == "baseline_reserved"


def test_promote_rejects_not_sustained_in_registry(isolated_state: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.anna_training import operator_trading_strategy as ots

    monkeypatch.setattr(ots, "list_sustained_strategy_ids_from_ledger", lambda _db=None: ["alpha"])
    r = ots.promote_designated_strategy(strategy_id="zzz")
    assert r["ok"] is False
    assert r.get("reason_code") == "not_sustained_in_registry"


def test_demote_to_baseline_default_system(isolated_state: dict) -> None:
    from modules.anna_training import operator_trading_strategy as ots

    ots.promote_designated_strategy(strategy_id="alpha")
    r = ots.demote_designated_strategy(strategy_id="alpha", replacement_strategy_id="baseline")
    assert r["ok"] is True
    assert isolated_state["operator_trading"]["designated_strategy_id"] is None
