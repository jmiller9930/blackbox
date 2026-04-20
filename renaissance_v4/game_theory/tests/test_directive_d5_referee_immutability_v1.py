"""
Directive 05 — Referee immutability.

Students do not authorize ledger writes or alter Referee economics. ``reveal_v1`` joins a validated
``student_output_v1`` snapshot to Referee truth taken **only** from :class:`OutcomeRecord``.
``student_learning_record_v1`` persists a Referee **subset** projected from that reveal, not from
Student-authored outcome fields.
"""

from __future__ import annotations

from copy import deepcopy

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import validate_student_output_v1
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import (
    build_reveal_v1_from_outcome_and_student,
    outcome_record_to_referee_truth_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    build_student_learning_record_v1_from_reveal,
)


def _outcome(*, tid: str = "d5_tr", direction: str = "short", pnl: float = -2.5) -> OutcomeRecord:
    return OutcomeRecord(
        trade_id=tid,
        symbol="TESTUSDT",
        direction=direction,
        entry_time=4_000_000,
        exit_time=5_000_000,
        entry_price=100.0,
        exit_price=99.0,
        pnl=pnl,
        mae=0.1,
        mfe=0.2,
        exit_reason="stop",
    )


def _student(tid: str, direction: str) -> dict:
    return {
        "schema": "student_output_v1",
        "contract_version": 1,
        "graded_unit_type": "closed_trade",
        "graded_unit_id": tid,
        "decision_at_ms": 4_000_000,
        "act": True,
        "direction": direction,
        "pattern_recipe_ids": ["stub"],
        "confidence_01": 0.5,
        "reasoning_text": None,
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
    }


def test_d5_referee_truth_is_deterministic_outcome_projection() -> None:
    o = _outcome()
    rt_expected = outcome_record_to_referee_truth_v1(o)
    rev, errs = build_reveal_v1_from_outcome_and_student(
        student_output=_student(o.trade_id, "long"),
        outcome=o,
        revealed_at_utc="2026-04-20T20:00:00Z",
    )
    assert not errs and rev
    assert rev["referee_truth_v1"] == rt_expected


def test_d5_student_direction_does_not_override_referee_fields() -> None:
    o = _outcome(direction="short", pnl=-1.0)
    so = _student(o.trade_id, direction="long")
    rev, errs = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=o)
    assert not errs and rev
    assert rev["referee_truth_v1"]["direction"] == "short"
    assert rev["student_output"]["direction"] == "long"
    assert rev["comparison_v1"]["direction_match"] is False


def test_d5_rebuild_reveal_referee_unchanged_when_student_scalar_changes() -> None:
    o = _outcome()
    so1 = _student(o.trade_id, "long")
    so2 = deepcopy(so1)
    so2["confidence_01"] = 0.99
    so2["reasoning_text"] = "student changed mind"
    r1, e1 = build_reveal_v1_from_outcome_and_student(student_output=so1, outcome=o)
    r2, e2 = build_reveal_v1_from_outcome_and_student(student_output=so2, outcome=o)
    assert not e1 and not e2 and r1 and r2
    assert r1["referee_truth_v1"] == r2["referee_truth_v1"]


def test_d5_learning_row_referee_subset_matches_referee_truth_from_reveal() -> None:
    o = _outcome(pnl=7.25)
    rev, errs = build_reveal_v1_from_outcome_and_student(
        student_output=_student(o.trade_id, "short"),
        outcome=o,
        revealed_at_utc="2026-04-20T20:00:00Z",
    )
    assert not errs and rev
    lr, lre = build_student_learning_record_v1_from_reveal(
        rev,
        run_id="run_d5",
        record_id="660e8400-e29b-41d4-a716-446655440099",
        context_signature_v1={"schema": "context_signature_v1", "signature_key": "k"},
    )
    assert not lre and lr
    subset = lr["referee_outcome_subset"]
    rt = rev["referee_truth_v1"]
    assert subset["trade_id"] == rt["trade_id"]
    assert subset["symbol"] == rt["symbol"]
    assert subset["pnl"] == rt["pnl"]
    assert subset["exit_reason"] == rt["exit_reason"]


def test_d5_student_output_rejects_smuggled_referee_truth_key() -> None:
    so = _student("t", "long")
    so["referee_truth"] = {"pnl": 999.0}
    assert validate_student_output_v1(so)
