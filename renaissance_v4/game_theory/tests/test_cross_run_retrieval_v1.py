"""
Directive 06 — Cross-run retrieval into legal decision packets.
"""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1,
    SCHEMA_STUDENT_RETRIEVAL_SLICE_V1,
    validate_pre_reveal_bundle_v1,
)
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
    project_student_learning_record_to_retrieval_slice_v1,
)
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import build_reveal_v1_from_outcome_and_student
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    validate_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    build_student_learning_record_v1_from_reveal,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def _learning_row(*, rid: str, run_id: str, sig: str, trade: str) -> dict:
    o = OutcomeRecord(
        trade_id=trade,
        symbol="TESTUSDT",
        direction="long",
        entry_time=4_000_000,
        exit_time=5_000_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=3.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="x",
    )
    so = {
        "schema": "student_output_v1",
        "contract_version": 1,
        "graded_unit_type": "closed_trade",
        "graded_unit_id": trade,
        "decision_at_ms": o.entry_time,
        "act": True,
        "direction": "long",
        "pattern_recipe_ids": ["p1"],
        "confidence_01": 0.7,
        "reasoning_text": None,
        "student_decision_ref": "650e8400-e29b-41d4-a716-446655440000",
    }
    rev, e = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=o)
    assert not e and rev
    row, br = build_student_learning_record_v1_from_reveal(
        rev,
        run_id=run_id,
        record_id=rid,
        context_signature_v1={"schema": "context_signature_v1", "signature_key": sig},
    )
    assert not br and row
    return row


def test_retrieval_slices_injected_into_legal_packet(tmp_path: Path) -> None:
    store = tmp_path / "sl.jsonl"
    append_student_learning_record_v1(
        store, _learning_row(rid="lr1", run_id="run_a", sig="key_alpha", trade="t_a")
    )
    append_student_learning_record_v1(
        store, _learning_row(rid="lr2", run_id="run_b", sig="key_alpha", trade="t_b")
    )

    db = tmp_path / "m.sqlite3"
    _mk_synthetic_db(db)

    pkt, err = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000,
        store_path=store,
        retrieval_signature_key="key_alpha",
        max_retrieval_slices=8,
    )
    assert err is None and pkt is not None
    assert validate_student_decision_packet_v1(pkt) == []
    exp = pkt.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
    assert isinstance(exp, list) and len(exp) == 2
    assert exp[0]["schema"] == SCHEMA_STUDENT_RETRIEVAL_SLICE_V1
    blob = json.dumps(pkt)
    assert '"pnl"' not in blob, "forbidden outcome keys must not appear in pre-reveal packet"


def test_wrong_signature_yields_empty_retrieval(tmp_path: Path) -> None:
    store = tmp_path / "sl2.jsonl"
    append_student_learning_record_v1(
        store, _learning_row(rid="lr3", run_id="r1", sig="only_k", trade="tx")
    )
    db = tmp_path / "m2.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=6_000_000,
        store_path=store,
        retrieval_signature_key="other",
    )
    assert err is None and pkt is not None
    assert pkt[FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1] == []


def test_projection_drops_referee_pnl_branch() -> None:
    row = _learning_row(rid="lr4", run_id="r2", sig="sk", trade="ty")
    sl, errs = project_student_learning_record_to_retrieval_slice_v1(row)
    assert not errs and sl
    assert "referee_outcome_subset" not in sl
    assert "referee_truth" not in json.dumps(sl)
    assert validate_pre_reveal_bundle_v1(sl) == []


def test_execution_stack_no_cross_run_import() -> None:
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
                assert "cross_run_retrieval_v1" not in t, py
        else:
            assert "cross_run_retrieval_v1" not in rel.read_text(encoding="utf-8")
