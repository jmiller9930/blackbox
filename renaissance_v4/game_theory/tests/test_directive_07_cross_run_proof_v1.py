"""
Directive 07 — Automated cross-run proof: prior learning changes observable Student output; reset restores.
"""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import build_reveal_v1_from_outcome_and_student
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    build_student_learning_record_v1_from_reveal,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db

SIG = "directive_07_proof_key"


def _make_and_store_prior_run(store: Path) -> None:
    o = OutcomeRecord(
        trade_id="prior_trade_d07",
        symbol="TESTUSDT",
        direction="long",
        entry_time=3_000_000,
        exit_time=4_000_000,
        entry_price=100.0,
        exit_price=102.0,
        pnl=5.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="demo",
    )
    so = {
        "schema": "student_output_v1",
        "contract_version": 1,
        "graded_unit_type": "closed_trade",
        "graded_unit_id": "prior_trade_d07",
        "decision_at_ms": o.entry_time,
        "act": True,
        "direction": "long",
        "pattern_recipe_ids": ["prior_run_marker_v1"],
        "confidence_01": 0.72,
        "reasoning_text": None,
        "student_decision_ref": "750e8400-e29b-41d4-a716-446655440000",
    }
    rev, e = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=o)
    assert not e and rev
    row, br = build_student_learning_record_v1_from_reveal(
        rev,
        run_id="run_1_d07",
        record_id="learning_row_d07_prior",
        context_signature_v1={"schema": "context_signature_v1", "signature_key": SIG},
    )
    assert not br and row
    append_student_learning_record_v1(store, row)


def test_run2_student_output_differs_when_learning_loaded_vs_baseline(tmp_path: Path) -> None:
    """
    Run 1: persist a learning record.

    Run 2a (baseline): same causal decision point — packet **without** retrieval → shadow output O0.

    Run 2b (informed): same DB/time/symbol — packet **with** retrieval → shadow output O1.

    Assert O1 differs from O0 on decision-relevant fields (recipe ids / confidence / reasoning / ref).

    Reset: informed build with a non-matching retrieval key → empty slices → O2 matches O0.
    """
    store = tmp_path / "d07.jsonl"
    _make_and_store_prior_run(store)

    db = tmp_path / "bars.sqlite3"
    _mk_synthetic_db(db)
    t_ms = 6_000_000
    gid = "later_trade_d07"

    pkt0, e0 = build_student_decision_packet_v1(
        db_path=db, symbol="TESTUSDT", decision_open_time_ms=t_ms
    )
    assert not e0 and pkt0
    o0, _ = emit_shadow_stub_student_output_v1(pkt0, graded_unit_id=gid, decision_at_ms=t_ms)
    assert o0

    pkt1, e1 = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=t_ms,
        store_path=store,
        retrieval_signature_key=SIG,
    )
    assert not e1 and pkt1
    o1, _ = emit_shadow_stub_student_output_v1(pkt1, graded_unit_id=gid, decision_at_ms=t_ms)
    assert o1

    assert o0["pattern_recipe_ids"] != o1["pattern_recipe_ids"]
    assert o0["confidence_01"] != o1["confidence_01"]
    assert o0["student_decision_ref"] != o1["student_decision_ref"]
    assert "Directive 07" not in (o0.get("reasoning_text") or "")
    assert "Directive 07" in (o1.get("reasoning_text") or "")

    pkt_reset, er = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=t_ms,
        store_path=store,
        retrieval_signature_key="no_such_records",
    )
    assert not er and pkt_reset
    o2, _ = emit_shadow_stub_student_output_v1(pkt_reset, graded_unit_id=gid, decision_at_ms=t_ms)
    assert o2
    assert o2["pattern_recipe_ids"] == o0["pattern_recipe_ids"]
    assert o2["confidence_01"] == o0["confidence_01"]
    assert o2["student_decision_ref"] == o0["student_decision_ref"]


def test_replay_runner_does_not_import_student_path() -> None:
    """Cross-run / shadow proof remains off the Referee hot path."""
    root = Path(__file__).resolve().parents[2]
    rr = (root / "research" / "replay_runner.py").read_text(encoding="utf-8")
    assert "shadow_student_v1" not in rr
    assert "cross_run_retrieval_v1" not in rr
