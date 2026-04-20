"""
Directive 01 — **complete contract + leakage proof** for architect acceptance.

Requires:
  - One valid + one invalid per schema (structure-enforced failures).
  - Pre-reveal leakage boundary proof.
"""

from __future__ import annotations

from renaissance_v4.game_theory.student_proctor.contract_proof_fixtures_v1 import (
    reveal_v1_invalid_proof_structure,
    reveal_v1_valid_proof,
    student_learning_record_v1_invalid_proof_structure,
    student_learning_record_v1_valid_proof,
    student_output_v1_invalid_proof_structure,
    student_output_v1_valid_proof,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    illegal_pre_reveal_bundle_example_v1,
    legal_example_student_output_v1,
    validate_pre_reveal_bundle_v1,
    validate_reveal_v1,
    validate_student_learning_record_v1,
    validate_student_output_v1,
)


# --- student_output_v1 ---


def test_proof_student_output_v1_valid_passes() -> None:
    doc = student_output_v1_valid_proof()
    errs = validate_student_output_v1(doc)
    assert errs == [], f"errors: {errs}"


def test_proof_student_output_v1_invalid_contract_version_fails() -> None:
    doc = student_output_v1_invalid_proof_structure()
    errs = validate_student_output_v1(doc)
    assert errs, "must reject wrong contract_version"
    assert any("contract_version" in e for e in errs), f"unexpected errors: {errs}"


# --- reveal_v1 ---


def test_proof_reveal_v1_valid_passes() -> None:
    doc = reveal_v1_valid_proof()
    errs = validate_reveal_v1(doc)
    assert errs == [], f"errors: {errs}"


def test_proof_reveal_v1_invalid_missing_referee_pnl_fails() -> None:
    doc = reveal_v1_invalid_proof_structure()
    errs = validate_reveal_v1(doc)
    assert errs, "must reject referee_truth without required keys"
    assert any("pnl" in e for e in errs), f"unexpected errors: {errs}"


# --- student_learning_record_v1 ---


def test_proof_student_learning_record_v1_valid_passes() -> None:
    doc = student_learning_record_v1_valid_proof()
    errs = validate_student_learning_record_v1(doc)
    assert errs == [], f"errors: {errs}"


def test_proof_student_learning_record_v1_invalid_alignment_flags_type_fails() -> None:
    doc = student_learning_record_v1_invalid_proof_structure()
    errs = validate_student_learning_record_v1(doc)
    assert errs, "must reject non-dict alignment_flags_v1"
    assert any("alignment_flags" in e.lower() for e in errs), f"unexpected errors: {errs}"


# --- Leakage: pre-reveal boundary ---


def test_proof_leakage_top_level_pnl_rejected() -> None:
    bad = illegal_pre_reveal_bundle_example_v1()
    errs = validate_pre_reveal_bundle_v1(bad)
    assert errs and any("pnl" in e for e in errs)


def test_proof_leakage_nested_forbidden_key_rejected() -> None:
    bundle = {"context": {"nested": {"mae": 3.0}}}
    errs = validate_pre_reveal_bundle_v1(bundle)
    assert errs and any("mae" in e for e in errs)


def test_proof_leakage_student_output_cannot_smuggle_flashcard_fields() -> None:
    doc = dict(legal_example_student_output_v1())
    doc["win_rate"] = 0.5
    errs = validate_student_output_v1(doc)
    assert errs and any("win_rate" in e.lower() or "forbidden" in e.lower() for e in errs)


def test_proof_leakage_legal_pre_reveal_style_packet_accepted() -> None:
    ok = {
        "schema": "pre_reveal_decision_packet_v1",
        "graded_unit_id": "trade_1",
        "bars_up_to_t": [{"t": 1, "c": 100.0}],
        "indicator_snapshots": {"rsi": 44.2},
    }
    assert validate_pre_reveal_bundle_v1(ok) == []
