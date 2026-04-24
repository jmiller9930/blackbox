"""GT_DIRECTIVE_018 — learning loop governance: retrieval cap env + newest-first order."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import build_reveal_v1_from_outcome_and_student
from renaissance_v4.game_theory.student_proctor.student_learning_loop_governance_v1 import (
    resolved_max_retrieval_slices_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    build_student_learning_record_v1_from_reveal,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.tests.test_cross_run_retrieval_v1 import _learning_row
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


def test_resolved_max_retrieval_slices_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES", "3")
    assert resolved_max_retrieval_slices_v1(5) == 5
    assert resolved_max_retrieval_slices_v1(None) == 3


def test_resolved_max_retrieval_slices_env_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES", "999")
    assert resolved_max_retrieval_slices_v1(None) == 128
    monkeypatch.setenv("PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES", "not_int")
    assert resolved_max_retrieval_slices_v1(None) == 8


def test_env_cap_limits_slices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES", "2")
    store = tmp_path / "cap.jsonl"
    for i in range(5):
        append_student_learning_record_v1(
            store,
            _learning_row(rid=f"r{i}", run_id=f"run{i}", sig="sig_x", trade=f"t{i}"),
        )
    db = tmp_path / "c.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=db,
        symbol="TESTUSDT",
        decision_open_time_ms=5_000_000,
        store_path=store,
        retrieval_signature_key="sig_x",
        max_retrieval_slices=None,
    )
    assert err is None and pkt is not None
    rx = pkt[FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1]
    assert len(rx) == 2
    assert {x["source_record_id"] for x in rx} == {"r4", "r3"}


def test_seam_audit_includes_learning_loop_governance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES", "4")
    db = tmp_path / "gov.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "gov.jsonl"
    o = OutcomeRecord(
        trade_id="tg",
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
    sk = f"student_entry_v1:{o.symbol}:{o.entry_time}"
    so = {
        "schema": "student_output_v1",
        "contract_version": 1,
        "graded_unit_type": "closed_trade",
        "graded_unit_id": "tg",
        "decision_at_ms": o.entry_time,
        "act": True,
        "direction": "long",
        "pattern_recipe_ids": ["p1"],
        "confidence_01": 0.5,
        "reasoning_text": None,
        "student_decision_ref": "750e8400-e29b-41d4-a716-446655440001",
    }
    rev, e = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=o)
    assert not e and rev
    row, br = build_student_learning_record_v1_from_reveal(
        rev,
        run_id="run_gov",
        record_id="rec_gov",
        context_signature_v1={"schema": "context_signature_v1", "signature_key": sk},
    )
    assert not br and row
    append_student_learning_record_v1(store, row)

    results = [
        {
            "ok": True,
            "scenario_id": "s_gov",
            "replay_outcomes_json": [
                {
                    "trade_id": "tg",
                    "symbol": "TESTUSDT",
                    "direction": "long",
                    "entry_time": 6_000_000,
                    "exit_time": 6_100_000,
                    "entry_price": 100.0,
                    "exit_price": 101.0,
                    "pnl": 1.0,
                    "mae": 0.0,
                    "mfe": 0.5,
                    "exit_reason": "tp",
                    "metadata": {},
                }
            ],
        }
    ]
    audit = student_loop_seam_after_parallel_batch_v1(
        results=results,
        run_id="jid_gov",
        db_path=db,
        store_path=store,
        strategy_id="pattern_learning",
    )
    g = audit.get("learning_loop_governance_v1")
    assert isinstance(g, dict)
    assert g.get("schema") == "student_learning_loop_governance_v1"
    assert g.get("max_retrieval_slices_resolved") == 4
    assert g.get("retrieval_attachment_order_v1") == "newest_first"
