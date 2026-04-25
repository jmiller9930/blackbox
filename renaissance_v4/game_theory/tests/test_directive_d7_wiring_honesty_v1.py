"""
Directive D7 — Wiring honesty (as-built Student path vs “full” trading context).

Marketing and operators must not claim full indicator/regime panels on the Student pre-reveal path
until annex buckets are attached **and** tested. The operator seam audit exposes an explicit
``wiring_honesty_annotation_v1`` block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1,
    FIELD_STUDENT_CONTEXT_ANNEX_V1,
    legal_example_student_context_annex_v1,
)
from renaissance_v4.game_theory.student_proctor import student_proctor_operator_runtime_v1 as operator_rt
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    attach_student_context_annex_v1,
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    SCHEMA_WIRING_HONESTY_ANNOTATION_V1,
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def test_d7_default_builder_packet_has_no_context_annex(tmp_path: Path) -> None:
    db = tmp_path / "w.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000,
        candle_timeframe_minutes=5,
        max_bars_in_packet=500,
    )
    assert err is None and pkt
    assert FIELD_STUDENT_CONTEXT_ANNEX_V1 not in pkt


def test_d7_wiring_audit_default_seam_rejects_full_context_claim(tmp_path: Path) -> None:
    db = tmp_path / "d7.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "st.jsonl"
    o = OutcomeRecord(
        trade_id="t_d7",
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
                "scenario_id": "sc",
                "replay_outcomes_json": [outcome_record_to_jsonable(o)],
            }
        ],
        run_id="run_d7",
        db_path=db,
        store_path=store,
    )
    wh = audit.get("wiring_honesty_annotation_v1")
    assert isinstance(wh, dict)
    assert wh.get("schema") == SCHEMA_WIRING_HONESTY_ANNOTATION_V1
    assert wh.get("directive") == "D7"
    assert wh.get("full_structured_trading_context_baseline_claim_supported_v1") is False
    assert isinstance(wh.get("as_built_student_pre_reveal_wiring_v1"), str)
    assert wh.get("student_context_annex_v1_present_on_first_packet") is False


def test_d7_skipped_seam_wiring_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LOOP_SEAM", "0")
    audit = student_loop_seam_after_parallel_batch_v1(
        results=[], run_id="x"
    )
    wh = audit.get("wiring_honesty_annotation_v1")
    assert isinstance(wh, dict)
    assert wh.get("as_built_student_pre_reveal_wiring_v1") is None


def test_d7_annex_flag_when_operator_uses_augmented_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patch cross-run builder on the operator module so the first packet includes an annex."""

    def wrapped(**kwargs):
        from renaissance_v4.game_theory.student_proctor import cross_run_retrieval_v1 as cr

        pkt, err = cr.build_student_decision_packet_v1_with_cross_run_retrieval(**kwargs)
        if err or pkt is None:
            return None, err
        merged, merr = attach_student_context_annex_v1(pkt, legal_example_student_context_annex_v1())
        if merr or merged is None:
            return None, merr
        merged[FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1] = []
        return merged, None

    monkeypatch.setattr(
        operator_rt,
        "build_student_decision_packet_v1_with_cross_run_retrieval",
        wrapped,
    )

    db = tmp_path / "db.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "st.jsonl"
    o = OutcomeRecord(
        trade_id="t_annex",
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
                "scenario_id": "sc",
                "replay_outcomes_json": [outcome_record_to_jsonable(o)],
            }
        ],
        run_id="run_annex",
        db_path=db,
        store_path=store,
    )
    wh = audit.get("wiring_honesty_annotation_v1")
    assert wh.get("student_context_annex_v1_present_on_first_packet") is True
    assert wh.get("full_structured_trading_context_baseline_claim_supported_v1") is False
