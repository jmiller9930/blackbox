"""
Directive 04 — ``reveal_v1`` join: schema, mismatch guards, pre- vs post-reveal separation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    SCHEMA_REVEAL_V1,
    validate_pre_reveal_bundle_v1,
    validate_reveal_v1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import (
    build_comparison_v1,
    build_reveal_v1_from_outcome_and_student,
    outcome_record_to_referee_truth_v1,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import (
    emit_shadow_stub_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


@pytest.fixture()
def synthetic_db(tmp_path: Path) -> Path:
    p = tmp_path / "reveal_t.sqlite3"
    _mk_synthetic_db(p)
    return p


def _sample_outcome(trade_id: str = "tr_reveal_01") -> OutcomeRecord:
    return OutcomeRecord(
        trade_id=trade_id,
        symbol="TESTUSDT",
        direction="long",
        entry_time=4_000_000,
        exit_time=5_000_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=12.5,
        mae=0.5,
        mfe=2.0,
        exit_reason="take_profit",
    )


def _minimal_valid_student_output(graded_unit_id: str, entry_ms: int) -> dict:
    return {
        "schema": "student_output_v1",
        "contract_version": 1,
        "graded_unit_type": "closed_trade",
        "graded_unit_id": graded_unit_id,
        "decision_at_ms": entry_ms,
        "act": True,
        "direction": "long",
        "pattern_recipe_ids": ["x"],
        "confidence_01": 0.5,
        "reasoning_text": None,
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
    }


def test_referee_truth_maps_outcome_fields() -> None:
    o = _sample_outcome()
    rt = outcome_record_to_referee_truth_v1(o)
    assert rt["trade_id"] == o.trade_id
    assert rt["symbol"] == o.symbol
    assert rt["pnl"] == o.pnl
    assert rt["direction"] == o.direction


def test_build_reveal_validates_and_joins() -> None:
    o = _sample_outcome()
    so = _minimal_valid_student_output(o.trade_id, o.entry_time)
    assert validate_student_output_v1(so) == []

    rev, errs = build_reveal_v1_from_outcome_and_student(
        student_output=so,
        outcome=o,
        revealed_at_utc="2026-04-20T12:00:00Z",
    )
    assert not errs and rev
    assert validate_reveal_v1(rev) == []
    assert rev["schema"] == SCHEMA_REVEAL_V1
    assert rev["student_output"]["graded_unit_id"] == o.trade_id
    assert rev["referee_truth_v1"]["pnl"] == o.pnl
    assert rev["comparison_v1"]["direction_match"] is True


def test_mismatched_graded_unit_fails() -> None:
    o = _sample_outcome()
    so = _minimal_valid_student_output("other_trade_id", o.entry_time)
    rev, errs = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=o)
    assert rev is None
    assert errs


def test_reveal_is_not_a_pre_reveal_packet() -> None:
    """
    ``validate_pre_reveal_bundle_v1`` rejects nested forbidden keys such as ``pnl`` anywhere.
    A valid ``reveal_v1`` embeds Referee ``pnl`` — it must **not** be mistaken for pre-reveal.
    """
    o = _sample_outcome("tr_sep")
    so = _minimal_valid_student_output(o.trade_id, o.entry_time)
    rev, errs = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=o)
    assert not errs and rev
    assert validate_reveal_v1(rev) == []
    pre = validate_pre_reveal_bundle_v1(rev)
    assert pre, "expected recursive pre-reveal guard to fire on reveal (referee pnl keys)"


def test_comparison_direction_match_false_when_student_differs() -> None:
    o = _sample_outcome()
    o2 = OutcomeRecord(
        trade_id=o.trade_id,
        symbol=o.symbol,
        direction="short",
        entry_time=o.entry_time,
        exit_time=o.exit_time,
        entry_price=o.entry_price,
        exit_price=o.exit_price,
        pnl=-1.0,
        mae=o.mae,
        mfe=o.mfe,
        exit_reason=o.exit_reason,
    )
    so = _minimal_valid_student_output(o2.trade_id, o2.entry_time)
    so["direction"] = "long"
    rt = outcome_record_to_referee_truth_v1(o2)
    comp = build_comparison_v1(so, rt)
    assert comp["direction_match"] is False


def test_e2e_packet_shadow_reveal_chain(synthetic_db: Path) -> None:
    """Decision packet → shadow student_output → OutcomeRecord → reveal_v1 (full join story)."""
    tid = "e2e_tr"
    pkt, perr = build_student_decision_packet_v1(
        db_path=synthetic_db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000, candle_timeframe_minutes=5
    )
    assert not perr and pkt
    so, serr = emit_shadow_stub_student_output_v1(pkt, graded_unit_id=tid, decision_at_ms=5_000_000)
    assert not serr and so

    outcome = OutcomeRecord(
        trade_id=tid,
        symbol="TESTUSDT",
        direction="long",
        entry_time=5_000_000,
        exit_time=6_000_000,
        entry_price=100.0,
        exit_price=100.0,
        pnl=0.0,
        mae=0.0,
        mfe=0.0,
        exit_reason="test",
    )
    rev, rerr = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=outcome)
    assert not rerr and rev
    assert validate_reveal_v1(rev) == []


def test_execution_stack_does_not_import_reveal_layer() -> None:
    root = Path(__file__).resolve().parents[2]
    for rel in (
        root / "core",
        root / "research" / "replay_runner.py",
        root / "game_theory" / "pattern_game.py",
        root / "game_theory" / "web_app.py",
    ):
        if rel.is_dir():
            for py in rel.rglob("*.py"):
                t = py.read_text(encoding="utf-8")
                assert "reveal_layer_v1" not in t, py
                assert "build_reveal_v1_from_outcome_and_student" not in t, py
        else:
            t = rel.read_text(encoding="utf-8")
            assert "reveal_layer_v1" not in t
            assert "build_reveal_v1_from_outcome_and_student" not in t


def test_examples_reveal_v1_layer_built_json_validates() -> None:
    p = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "reveal_v1_layer_built_example.json"
    )
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert validate_reveal_v1(doc) == []


def test_committed_example_built_reveal_roundtrip(tmp_path: Path, synthetic_db: Path) -> None:
    """Optional: write minimal reveal json via builder for doc parity (in-memory check)."""
    o = _sample_outcome("doc_tr")
    so = _minimal_valid_student_output(o.trade_id, o.entry_time)
    rev, errs = build_reveal_v1_from_outcome_and_student(
        student_output=so,
        outcome=o,
        revealed_at_utc="2026-04-20T18:00:00Z",
    )
    assert not errs and rev
    p = tmp_path / "reveal.json"
    p.write_text(json.dumps(rev, indent=2), encoding="utf-8")
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert validate_reveal_v1(loaded) == []
