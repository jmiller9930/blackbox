"""
Directive D9 — Deliverable vocabulary (**trade** §0.2, **learned behavior** §0.3).

Operator and release language must not equate Referee fills with Student **trade** intent or claim
**learned behavior** from metrics without a declared baseline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    SCHEMA_STUDENT_OUTPUT_V1,
    legal_example_student_output_v1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    SCHEMA_DELIVERABLE_VOCABULARY_ANNOTATION_V1,
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def _ladder_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "student_proctor"
        / "ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md"
    )


def test_d9_architecture_file_defines_trade_and_learned_behavior() -> None:
    text = _ladder_path().read_text(encoding="utf-8")
    assert "### 0.2 What a **trade** is" in text
    assert "### 0.3 What **learned behavior** is" in text
    assert "student_output_v1" in text
    assert "baseline" in text.lower()


def test_d9_trade_artifact_is_student_output_schema() -> None:
    so = legal_example_student_output_v1()
    assert so.get("schema") == SCHEMA_STUDENT_OUTPUT_V1
    assert validate_student_output_v1(so) == []


def test_d9_operator_audit_vocabulary_flags(tmp_path: Path) -> None:
    db = tmp_path / "d9.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "st.jsonl"
    o = OutcomeRecord(
        trade_id="td9",
        symbol="TESTUSDT",
        direction="long",
        entry_time=6_000_000,
        exit_time=6_100_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=1.0,
        mae=0.0,
        mfe=0.5,
        exit_reason="tp",
    )
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[
            {
                "ok": True,
                "scenario_id": "s",
                "replay_outcomes_json": [outcome_record_to_jsonable(o)],
            }
        ],
        run_id="r9",
        db_path=db,
        store_path=store,
    )
    dv = audit.get("deliverable_vocabulary_annotation_v1")
    assert isinstance(dv, dict)
    assert dv.get("schema") == SCHEMA_DELIVERABLE_VOCABULARY_ANNOTATION_V1
    assert dv.get("directive") == "D9"
    assert dv.get("trade_is_contract_student_output_pre_reveal_v1") is True
    assert dv.get("referee_fill_not_trade_definition_v1") is True
    assert dv.get("learned_behavior_requires_baseline_v1") is True
    assert "§0.2" in str(dv.get("authoritative_doc_anchor_v1"))


def test_d9_skipped_seam_vocabulary_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LOOP_SEAM", "0")
    audit = student_loop_seam_after_parallel_batch_v1(results=[], run_id="z")
    dv = audit.get("deliverable_vocabulary_annotation_v1")
    assert dv.get("trade_is_contract_student_output_pre_reveal_v1") is None
