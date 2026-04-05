"""Sequential learning WebUI control plane — state machine + auditable transitions."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import append_execution_trade
from modules.anna_training.sequential_engine.calibration_factory import load_and_validate_calibration, write_calibration_from_template
from modules.anna_training.sequential_engine import ui_control as uc
from tests.test_sequential_engine import _mk_market_db


def _cal_and_events(tmp_path: Path) -> tuple[Path, Path, Path]:
    cal_path = tmp_path / "calibration_report.json"
    write_calibration_from_template(cal_path, protocol_id="ui_ctl_v1")
    raw = json.loads(cal_path.read_text(encoding="utf-8"))
    raw["n_min"] = 1
    raw["batch_size"] = 1
    cal_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    ev = tmp_path / "events.txt"
    ev.write_text("me1\nme2\n", encoding="utf-8")
    return cal_path, ev, tmp_path / "state.json"


def _append_pair(db: Path, mid: str, strat: str) -> None:
    common = {
        "symbol": "SOL-PERP",
        "timeframe": "5m",
        "side": "long",
        "entry_time": "2025-01-01T10:00:00+00:00",
        "entry_price": 100.0,
        "size": 1.0,
        "exit_time": "2025-01-01T10:12:00+00:00",
        "exit_reason": "test",
    }
    append_execution_trade(
        strategy_id="baseline",
        lane="baseline",
        mode="paper",
        market_event_id=mid,
        db_path=db,
        **common,
        exit_price=102.0,
    )
    append_execution_trade(
        strategy_id=strat,
        lane="anna",
        mode="paper",
        market_event_id=mid,
        db_path=db,
        **common,
        exit_price=101.0,
    )


def test_state_machine_transitions_and_audit_log(tmp_path: Path) -> None:
    os.environ.pop("ANNA_STRICT_TRADE_IDENTITY", None)
    cal_path, ev_path, state_path = _cal_and_events(tmp_path)
    art = tmp_path / "artifacts"
    db = tmp_path / "ledger.db"
    mdb = _mk_market_db(tmp_path)
    strat = "ui_ctl_strat"
    _append_pair(db, "me1", strat)
    _append_pair(db, "me2", strat)

    assert uc.load_control_state(state_path)["ui_state"] == "idle"

    r = uc.control_start(
        start_mode="new_run",
        test_id="t1",
        strategy_id=strat,
        calibration_path=str(cal_path),
        events_file_path=str(ev_path),
        ledger_db_path=str(db),
        market_db_path=str(mdb),
        artifacts_dir=str(art),
        state_path=state_path,
    )
    assert r["ok"] is True
    st = uc.load_control_state(state_path)
    assert st["ui_state"] == "running"
    log_len_1 = len(st["transition_log"])

    assert uc.control_pause(state_path=state_path)["ok"] is True
    assert uc.load_control_state(state_path)["ui_state"] == "paused"

    r_resume = uc.control_start(
        start_mode="resume",
        test_id="t1",
        strategy_id=strat,
        calibration_path=str(cal_path),
        events_file_path=str(ev_path),
        ledger_db_path=str(db),
        market_db_path=str(mdb),
        artifacts_dir=str(art),
        state_path=state_path,
    )
    assert r_resume["ok"] is True
    assert uc.load_control_state(state_path)["ui_state"] == "running"

    assert uc.control_stop(state_path=state_path)["ok"] is True
    assert uc.load_control_state(state_path)["ui_state"] == "stopped"

    r2 = uc.control_start(
        start_mode="resume",
        test_id="t1",
        strategy_id=strat,
        calibration_path=str(cal_path),
        events_file_path=str(ev_path),
        ledger_db_path=str(db),
        market_db_path=str(mdb),
        artifacts_dir=str(art),
        state_path=state_path,
    )
    assert r2["ok"] is True
    uc.control_stop(state_path=state_path)

    rr = uc.control_reset(archive=True, new_test_id="t2", state_path=state_path)
    assert rr["ok"] is True
    st_final = uc.load_control_state(state_path)
    assert st_final["ui_state"] == "idle"
    assert st_final["test_id"] == "t2"
    assert len(st_final["transition_log"]) >= log_len_1
    for entry in st_final["transition_log"]:
        assert "trace_id" in entry
        assert entry["from"] and entry["to"] and entry["action"]


def test_new_run_rejects_nonempty_artifact_dir(tmp_path: Path) -> None:
    cal_path, ev_path, state_path = _cal_and_events(tmp_path)
    art = tmp_path / "artifacts"
    tid = "blocked"
    (art / tid).mkdir(parents=True)
    (art / tid / "x.txt").write_text("x", encoding="utf-8")

    r = uc.control_start(
        start_mode="new_run",
        test_id=tid,
        strategy_id="s",
        calibration_path=str(cal_path),
        events_file_path=str(ev_path),
        artifacts_dir=str(art),
        state_path=state_path,
    )
    assert r["ok"] is False
    assert r["reason_code"] == "artifacts_exist_for_test_id"


def test_reset_rejects_while_running(tmp_path: Path) -> None:
    cal_path, ev_path, state_path = _cal_and_events(tmp_path)
    uc.control_start(
        start_mode="new_run",
        test_id="run",
        strategy_id="s",
        calibration_path=str(cal_path),
        events_file_path=str(ev_path),
        state_path=state_path,
    )
    r = uc.control_reset(state_path=state_path)
    assert r["ok"] is False
    assert r["reason_code"] == "must_stop_before_reset"


def test_pause_halts_tick(tmp_path: Path) -> None:
    os.environ.pop("ANNA_STRICT_TRADE_IDENTITY", None)
    cal_path, ev_path, state_path = _cal_and_events(tmp_path)
    art = tmp_path / "artifacts"
    db = tmp_path / "ledger.db"
    mdb = _mk_market_db(tmp_path)
    strat = "ui_tick"
    _append_pair(db, "me1", strat)
    _append_pair(db, "me2", strat)

    uc.control_start(
        start_mode="new_run",
        test_id="tick_t",
        strategy_id=strat,
        calibration_path=str(cal_path),
        events_file_path=str(ev_path),
        ledger_db_path=str(db),
        market_db_path=str(mdb),
        artifacts_dir=str(art),
        state_path=state_path,
    )
    uc.control_pause(state_path=state_path)
    tr = uc.control_tick(state_path=state_path)
    assert tr["ok"] is False
    assert tr["reason_code"] == "not_running_tick_skipped"


def test_operator_status_includes_sprt_decision_key(tmp_path: Path) -> None:
    cal_path, ev_path, state_path = _cal_and_events(tmp_path)
    uc.control_start(
        start_mode="new_run",
        test_id="st",
        strategy_id="s",
        calibration_path=str(cal_path),
        events_file_path=str(ev_path),
        state_path=state_path,
    )
    out = uc.build_operator_status(state_path=state_path)
    assert out["schema"] == "sequential_operator_status_v1"
    assert "last_sprt_decision" in out
    assert "sequential_state_snapshot" in out
