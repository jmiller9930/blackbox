"""Runtime driver, persistence, calibration — end-to-end sequential learning loop."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from modules.anna_training.execution_ledger import append_execution_trade
from modules.anna_training.sequential_engine.calibration_report import CalibrationReport
from modules.anna_training.sequential_engine.calibration_factory import load_and_validate_calibration, write_calibration_from_template
from modules.anna_training.sequential_engine.runtime_driver import run_sequential_learning_driver
from modules.anna_training.sequential_engine.sequential_persistence import (
    ensure_strategy_registered,
    list_sequential_runs_for_test,
    persist_sequential_decision_run,
)
from tests.test_sequential_engine import _mk_market_db


def _append_pair(
    *,
    db: Path,
    market_event_id: str,
    candidate_strategy_id: str,
    baseline_exit: float,
    candidate_exit: float,
) -> None:
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
        market_event_id=market_event_id,
        db_path=db,
        **common,
        exit_price=baseline_exit,
    )
    append_execution_trade(
        strategy_id=candidate_strategy_id,
        lane="anna",
        mode="paper",
        market_event_id=market_event_id,
        db_path=db,
        **common,
        exit_price=candidate_exit,
    )


def test_persist_three_decision_types(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    ensure_strategy_registered("s_test", db_path=db)
    for d in ("CONTINUE", "PROMOTE", "KILL"):
        persist_sequential_decision_run(
            test_id="t_persist",
            strategy_id="s_test",
            sprt_decision=d,
            eligible_n=10,
            win_n=5,
            wilson={"wins": 5, "eligible_n": 10},
            sprt_snapshot={"log_likelihood_ratio": 0.1},
            shadow_tier={"tier": "baseline_only", "mode": "shadow"},
            hypothesis_hash=None,
            pattern_spec_hash=None,
            manifest_content_hash="abc",
            db_path=db,
        )
    conn = __import__("sqlite3").connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM anna_sequential_decision_runs").fetchone()[0]
    finally:
        conn.close()
    assert n == 3
    rows = list_sequential_runs_for_test("t_persist", db_path=db, limit=10)
    assert {r["sprt_decision"] for r in rows} == {"CONTINUE", "PROMOTE", "KILL"}


def test_driver_e2e_manifest_sprt_restart(tmp_path: Path) -> Path:
    os.environ.pop("ANNA_STRICT_TRADE_IDENTITY", None)
    db = tmp_path / "ledger.db"
    mdb = _mk_market_db(tmp_path)
    strat = "anna_seq_e2e"
    _append_pair(db=db, market_event_id="me1", candidate_strategy_id=strat, baseline_exit=102.0, candidate_exit=101.0)
    _append_pair(db=db, market_event_id="me2", candidate_strategy_id=strat, baseline_exit=102.0, candidate_exit=103.0)

    cal_path = tmp_path / "calibration_report.json"
    write_calibration_from_template(cal_path, protocol_id="e2e_protocol_v1")
    raw = json.loads(cal_path.read_text(encoding="utf-8"))
    raw["n_min"] = 2
    raw["batch_size"] = 2
    raw["p0"] = 0.4
    raw["p1"] = 0.55
    cal_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    cal = load_and_validate_calibration(cal_path)

    art = tmp_path / "art"
    ev = tmp_path / "events.txt"
    ev.write_text("me1\nme2\n", encoding="utf-8")

    hyp = {"test": "hypothesis", "v": 1}
    pat = {"method": "CUSUM", "k": 0.5}

    r1 = run_sequential_learning_driver(
        test_id="e2e_test",
        strategy_id=strat,
        calibration=cal,
        market_event_ids=["me1", "me2"],
        ledger_db_path=db,
        market_db_path=mdb,
        artifacts_dir=art,
        hypothesis=hyp,
        pattern_spec=pat,
    )
    assert r1["ok"] is True
    assert (art / "e2e_test" / "outcome_manifest.jsonl").is_file()
    lines = (art / "e2e_test" / "outcome_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert (art / "e2e_test" / "hypothesis_bundle.json").is_file()

    runs = list_sequential_runs_for_test("e2e_test", db_path=db, limit=5)
    assert len(runs) >= 1
    assert runs[0]["sprt_decision"] in ("CONTINUE", "PROMOTE", "KILL")

    r2 = run_sequential_learning_driver(
        test_id="e2e_test",
        strategy_id=strat,
        calibration=cal,
        market_event_ids=["me1", "me2"],
        ledger_db_path=db,
        market_db_path=mdb,
        artifacts_dir=art,
        hypothesis=hyp,
        pattern_spec=pat,
    )
    assert r2["events_processed"] == 2
    assert all(x["append"]["status"] == "duplicate_noop" for x in r2["results"])
    dup_lines = (art / "e2e_test" / "duplicate_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(dup_lines) == 2

    st_path = art / "e2e_test" / "sequential_state.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    assert st["schema_version"] == "sequential_state_v1"
    assert "sprt" in st


def test_calibration_validation_rejects_bad_mae() -> None:
    from modules.anna_training.sequential_engine.calibration_factory import validate_calibration_for_run

    bad = CalibrationReport(
        protocol_id="x",
        p0=0.1,
        p1=0.2,
        alpha=0.05,
        beta=0.1,
        n_min=1,
        batch_size=1,
        epsilon=0.0,
        mae_protocol_id="wrong",
    )
    with pytest.raises(ValueError, match="mae_protocol_id"):
        validate_calibration_for_run(bad)
