"""
Directive D6 — Phased honesty (process order vs causal pre-reveal packet).

The operator seam runs **after** parallel replay has produced ``OutcomeRecord`` payloads in batch
results; strict “exam blind” **process** order is therefore **not** satisfied, while the **Student
decision packet** remains causal (bars through entry only).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    SCHEMA_PHASED_HONESTY_ANNOTATION_V1,
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def test_d6_seam_audit_flags_not_exam_blind_when_trade_processed(tmp_path: Path) -> None:
    db = tmp_path / "d6.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "lr.jsonl"
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
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[
            {
                "ok": True,
                "scenario_id": "s_d6",
                "replay_outcomes_json": [outcome_record_to_jsonable(o)],
            }
        ],
        run_id="run_d6",
        db_path=db,
        store_path=store,
    )
    ph = audit.get("phased_honesty_annotation_v1")
    assert isinstance(ph, dict)
    assert ph.get("schema") == SCHEMA_PHASED_HONESTY_ANNOTATION_V1
    assert ph.get("directive") == "D6"
    assert ph.get("strict_exam_blind_process_order") is False
    assert ph.get("replay_outcomes_supplied_before_shadow_emit") is True
    assert ph.get("pre_reveal_student_inputs_are_causal_only") is True
    assert ph.get("student_shadow_emit_occurred") is True
    assert int(ph.get("trades_seen_by_seam") or 0) >= 1


def test_d6_skipped_seam_phased_honesty_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LOOP_SEAM", "0")
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[{"ok": True, "scenario_id": "x", "replay_outcomes_json": []}],
        run_id="skip",
    )
    ph = audit.get("phased_honesty_annotation_v1")
    assert isinstance(ph, dict)
    assert ph.get("strict_exam_blind_process_order") is None


def test_d6_web_app_batch_handler_runs_seam_after_parallel_results(tmp_path: Path) -> None:
    """Static guard: Flask batch path must not reorder seam before ``run_scenarios_parallel``."""
    root = Path(__file__).resolve().parents[1]
    web = root / "web_app.py"
    text = web.read_text(encoding="utf-8")
    i_parallel = text.find("results = run_scenarios_parallel(")
    i_seam = text.find(
        "seam_audit, seam_timed_out = _run_student_loop_seam_after_parallel_with_timeout_v1("
    )
    assert i_parallel != -1 and i_seam != -1 and i_parallel < i_seam
