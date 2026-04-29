"""Directive 09 — operator runtime seam (parallel batch → learning store)."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import (
    OutcomeRecord,
    outcome_record_from_jsonable,
    outcome_record_to_jsonable,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def test_outcome_record_json_roundtrip() -> None:
    o = OutcomeRecord(
        trade_id="t1",
        symbol="SOLUSDT",
        direction="long",
        entry_time=1_700_000_000_000,
        exit_time=1_700_000_300_000,
        entry_price=99.0,
        exit_price=100.0,
        pnl=1.0,
        mae=0.1,
        mfe=0.5,
        exit_reason="tp",
    )
    d = outcome_record_to_jsonable(o)
    o2 = outcome_record_from_jsonable(d)
    assert o2 == o


def test_seam_skipped_when_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LOOP_SEAM", "0")
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[{"ok": True, "scenario_id": "s1", "replay_outcomes_json": []}],
        run_id="run_x",
    )
    assert audit.get("skipped") is True
    assert audit.get("student_seam_stop_reason_v1") == "skipped_seam_disabled_v1"
    assert audit.get("replay_closed_trades_total_v1") == 0
    assert int(audit.get("student_learning_rows_appended") or 0) == 0
    assert int(audit.get("student_retrieval_matches") or 0) == 0
    assert audit.get("student_output_fingerprint") is None
    assert audit.get("shadow_student_enabled") is False


def test_seam_processes_trade_with_synthetic_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "bars.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "learn.jsonl"

    def _l3_ok(
        jid: str,
        tid: str,
        *,
        provisional_student_learning_record_v1: dict | None = None,
        **_kw: object,
    ) -> dict:
        return {
            "ok": True,
            "data_gaps": [],
            "decision_record_v1": {"ok": True},
            "job_id": jid,
            "trade_id": tid,
        }

    monkeypatch.setattr(
        "renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1"
        ".build_student_panel_l3_payload_v1",
        _l3_ok,
    )

    o = OutcomeRecord(
        trade_id="sto_trade",
        symbol="TESTUSDT",
        direction="long",
        entry_time=6_000_000,
        exit_time=6_100_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=3.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="tp",
    )
    results = [
        {
            "ok": True,
            "scenario_id": "row_a",
            "replay_outcomes_json": [outcome_record_to_jsonable(o)],
        }
    ]
    audit = student_loop_seam_after_parallel_batch_v1(
        results=results,
        run_id="run_demo_09",
        db_path=db,
        store_path=store,
        strategy_id="pattern_learning",
    )
    assert int(audit.get("student_learning_rows_appended") or 0) >= 1
    assert int(audit.get("replay_closed_trades_total_v1") or 0) == 1
    assert audit.get("student_seam_stop_reason_v1") == "completed_all_trades_v1"
    assert int(audit.get("trades_considered") or 0) == 1
    assert audit.get("shadow_student_enabled") is True
    assert isinstance(audit.get("student_retrieval_matches"), int)
    fp = audit.get("student_output_fingerprint")
    assert isinstance(fp, str) and len(fp) == 64
    assert store.is_file()
    assert store.read_text(encoding="utf-8").strip()
