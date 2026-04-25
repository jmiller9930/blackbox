"""
Directive D8 — Memory semantics honesty.

Student learning retrieval v1 is **exact** ``signature_key`` match — not approximate “same pattern”
similarity. Product language must not claim chart repetition from this matcher alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    list_student_learning_records_by_signature_key,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    SCHEMA_MEMORY_SEMANTICS_ANNOTATION_V1,
    _signature_key_for_trade_v1,
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.tests.test_cross_run_retrieval_v1 import _learning_row
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def test_d8_operator_audit_exact_key_mode(tmp_path: Path) -> None:
    db = tmp_path / "d8.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "st.jsonl"
    o = OutcomeRecord(
        trade_id="t8",
        symbol="TESTUSDT",
        direction="long",
        entry_time=6_000_000,
        exit_time=6_100_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=2.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="tp",
    )
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[
            {
                "ok": True,
                "scenario_id": "sc",
                "replay_outcomes_json": [outcome_record_to_jsonable(o)],
            }
        ],
        run_id="run_d8",
        db_path=db,
        store_path=store,
    )
    ms = audit.get("memory_semantics_annotation_v1")
    assert isinstance(ms, dict)
    assert ms.get("schema") == SCHEMA_MEMORY_SEMANTICS_ANNOTATION_V1
    assert ms.get("directive") == "D8"
    assert ms.get("student_retrieval_match_mode_v1") == "exact_signature_key"
    assert ms.get("same_chart_pattern_repeat_claim_supported_v1") is False
    assert ms.get("approximate_similarity_matching_student_store_v1") is False
    assert "{symbol}:{entry_time}" in str(ms.get("retrieval_signature_key_format_v1"))


def test_d8_skipped_seam_memory_annotation_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LOOP_SEAM", "0")
    audit = student_loop_seam_after_parallel_batch_v1(results=[], run_id="x")
    ms = audit.get("memory_semantics_annotation_v1")
    assert ms.get("student_retrieval_match_mode_v1") is None


def test_d8_store_retrieval_is_exact_signature_only(tmp_path: Path) -> None:
    store = tmp_path / "sx.jsonl"
    k_alpha = "student_entry_v1:TESTUSDT:6000000"
    k_other = "student_entry_v1:TESTUSDT:7000000"
    append_student_learning_record_v1(
        store, _learning_row(rid="r1", run_id="a", sig=k_alpha, trade="t1")
    )
    append_student_learning_record_v1(
        store, _learning_row(rid="r2", run_id="b", sig=k_other, trade="t2")
    )
    m_alpha = list_student_learning_records_by_signature_key(store, k_alpha)
    m_other = list_student_learning_records_by_signature_key(store, k_other)
    assert len(m_alpha) == 1 and m_alpha[0].get("record_id") == "r1"
    assert len(m_other) == 1
    assert list_student_learning_records_by_signature_key(store, "student_entry_v1:TESTUSDT:5000000") == []


def test_d8_signature_key_matches_trade_tuple() -> None:
    o = OutcomeRecord(
        trade_id="z",
        symbol="SOLUSDT",
        direction="short",
        entry_time=1_234_000,
        exit_time=2_000_000,
        entry_price=1.0,
        exit_price=1.1,
        pnl=-1.0,
        mae=0.1,
        mfe=0.2,
        exit_reason="x",
    )
    assert _signature_key_for_trade_v1(o, candle_timeframe_minutes=5) == "student_entry_v1:SOLUSDT:1234000:5"
