"""Directive 01 — contract freeze: schemas, samples, leakage tests."""

from __future__ import annotations

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    GRADED_UNIT_TYPE_V1,
    illegal_pre_reveal_bundle_example_v1,
    legal_example_reveal_v1,
    legal_example_student_learning_record_v1,
    legal_example_student_output_v1,
    validate_pre_reveal_bundle_v1,
    validate_reveal_v1,
    validate_student_learning_record_v1,
    validate_student_output_v1,
)


def test_graded_unit_v1_is_closed_trade() -> None:
    assert GRADED_UNIT_TYPE_V1 == "closed_trade"


def test_legal_student_output_v1_validates() -> None:
    doc = legal_example_student_output_v1()
    assert validate_student_output_v1(doc) == []


def test_legal_reveal_v1_validates() -> None:
    doc = legal_example_reveal_v1()
    assert validate_reveal_v1(doc) == []


def test_legal_student_learning_record_v1_validates() -> None:
    doc = legal_example_student_learning_record_v1()
    assert validate_student_learning_record_v1(doc) == []


def test_illegal_pre_reveal_rejected() -> None:
    bad = illegal_pre_reveal_bundle_example_v1()
    errs = validate_pre_reveal_bundle_v1(bad)
    assert errs, "expected leakage violations"
    assert any("pnl" in e.lower() for e in errs)


def test_student_output_with_smuggled_pnl_invalid() -> None:
    doc = legal_example_student_output_v1()
    doc = dict(doc)
    doc["pnl"] = 99.0
    errs = validate_student_output_v1(doc)
    assert errs


def test_pre_reveal_nested_forbidden_key() -> None:
    bundle = {
        "window": {"open": 1, "mfe": 5.0},
    }
    errs = validate_pre_reveal_bundle_v1(bundle)
    assert errs, "mfe must be forbidden in pre_reveal tree"
