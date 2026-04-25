"""
Directive 05 — Student learning store: append, retrieve, schema, isolation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_learning_record_v1 as legal_learning_row,
    validate_student_learning_record_v1,
)
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import build_reveal_v1_from_outcome_and_student
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    build_student_learning_record_v1_from_reveal,
    default_student_learning_store_path_v1,
    get_student_learning_record_by_id,
    list_student_learning_records_by_graded_unit_id,
    list_student_learning_records_by_run_id,
    list_student_learning_records_by_signature_key,
    load_student_learning_records_v1,
)


def test_append_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "learn.jsonl"
    rec = legal_learning_row()
    rec["record_id"] = "r1-directive-05"
    rec["run_id"] = "run_proof_a"
    append_student_learning_record_v1(p, rec)
    rows = load_student_learning_records_v1(p)
    assert len(rows) == 1
    assert rows[0]["record_id"] == "r1-directive-05"
    got = get_student_learning_record_by_id(p, "r1-directive-05")
    assert got is not None
    assert got["graded_unit_id"] == rec["graded_unit_id"]


def test_append_rejects_invalid_record(tmp_path: Path) -> None:
    p = tmp_path / "x.jsonl"
    bad = dict(legal_learning_row())
    bad["alignment_flags_v1"] = []  # must be dict
    with pytest.raises(ValueError, match="invalid student_learning_record_v1"):
        append_student_learning_record_v1(p, bad)


def test_duplicate_record_id_forbidden(tmp_path: Path) -> None:
    p = tmp_path / "dup.jsonl"
    r = legal_learning_row()
    r["record_id"] = "same-id"
    r["run_id"] = "run1"
    append_student_learning_record_v1(p, r)
    with pytest.raises(ValueError, match="record_id already present"):
        append_student_learning_record_v1(p, r)


def test_persistence_new_process_simulated_by_fresh_read(tmp_path: Path) -> None:
    """After write, reading path again yields same canonical data (disk-backed)."""
    p = tmp_path / "persist.jsonl"
    r = legal_learning_row()
    r["record_id"] = "persist-uuid-1"
    r["run_id"] = "run_z"
    append_student_learning_record_v1(p, r)
    p2 = tmp_path / "persist.jsonl"
    assert p2 == p
    again = load_student_learning_records_v1(Path(str(p2)))
    assert len(again) == 1
    assert again[0]["record_id"] == "persist-uuid-1"


def test_query_by_run_graded_unit_signature(tmp_path: Path) -> None:
    p = tmp_path / "q.jsonl"
    a = legal_learning_row()
    a["record_id"] = "q1"
    a["run_id"] = "run_shared"
    a["graded_unit_id"] = "trade_alpha"
    a["context_signature_v1"] = {"schema": "context_signature_v1", "signature_key": "sig_a"}
    b = legal_learning_row()
    b["record_id"] = "q2"
    b["run_id"] = "run_other"
    b["graded_unit_id"] = "trade_beta"
    b["context_signature_v1"] = {"schema": "context_signature_v1", "signature_key": "sig_b"}
    append_student_learning_record_v1(p, a)
    append_student_learning_record_v1(p, b)

    assert len(list_student_learning_records_by_run_id(p, "run_shared")) == 1
    assert len(list_student_learning_records_by_graded_unit_id(p, "trade_beta")) == 1
    assert len(list_student_learning_records_by_signature_key(p, "sig_a")) == 1


def test_build_from_reveal_and_store(tmp_path: Path) -> None:
    o = OutcomeRecord(
        trade_id="sto_trade",
        symbol="SOLUSDT",
        direction="long",
        entry_time=1_700_000_000_000,
        exit_time=1_700_000_300_000,
        entry_price=99.0,
        exit_price=100.0,
        pnl=5.0,
        mae=0.1,
        mfe=1.0,
        exit_reason="tp",
    )
    so = {
        "schema": "student_output_v1",
        "contract_version": 1,
        "graded_unit_type": "closed_trade",
        "graded_unit_id": "sto_trade",
        "decision_at_ms": o.entry_time,
        "act": True,
        "direction": "long",
        "pattern_recipe_ids": ["x"],
        "confidence_01": 0.6,
        "reasoning_text": None,
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
    }
    rev, err = build_reveal_v1_from_outcome_and_student(
        student_output=so, outcome=o, revealed_at_utc="2026-04-21T10:00:00Z"
    )
    assert not err and rev
    row, br = build_student_learning_record_v1_from_reveal(
        rev,
        run_id="run_d05",
        record_id="learn-row-99",
        context_signature_v1={"schema": "context_signature_v1", "signature_key": "k9"},
        candle_timeframe_minutes=5,
        strategy_id="test_strategy",
    )
    assert not br and row
    assert validate_student_learning_record_v1(row) == []

    p = tmp_path / "from_reveal.jsonl"
    append_student_learning_record_v1(p, row)
    assert get_student_learning_record_by_id(p, "learn-row-99") is not None


def test_malformed_jsonl_line_skipped_on_load(tmp_path: Path) -> None:
    p = tmp_path / "badline.jsonl"
    rec = legal_learning_row()
    rec["record_id"] = "ok-row"
    append_student_learning_record_v1(p, rec)
    with p.open("a", encoding="utf-8") as fh:
        fh.write("not json\n")
    loaded = load_student_learning_records_v1(p)
    assert len(loaded) == 1


def _imports_student_learning_store_module(py_source: str) -> bool:
    """
    True when the file imports the ``student_learning_store_v1`` **module**.

    Ignores identifiers that merely contain the substring (e.g. ``clear_student_learning_store_v1``).
    """
    if re.search(
        r"(?:^|\n)\s*from\s+renaissance_v4\.game_theory\.student_proctor\.student_learning_store_v1\s+import",
        py_source,
    ):
        return True
    if re.search(r"(?:^|\n)\s*from\s+\.student_learning_store_v1\s+import", py_source):
        return True
    return False


def test_execution_stack_does_not_import_learning_store() -> None:
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
                assert not _imports_student_learning_store_module(t), py
        else:
            t = rel.read_text(encoding="utf-8")
            assert not _imports_student_learning_store_module(t), rel


def test_default_store_path_is_under_runtime() -> None:
    d = default_student_learning_store_path_v1()
    assert d.name == "student_learning_records_v1.jsonl"
    assert d.parent.name == "student_learning"
