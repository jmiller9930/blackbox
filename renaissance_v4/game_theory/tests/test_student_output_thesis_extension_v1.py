"""§1.0 optional directional-thesis fields on ``student_output_v1`` (parallel seam)."""

from __future__ import annotations

import copy

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_output_v1,
    legal_example_student_output_with_thesis_v1,
    validate_student_output_v1,
)


def test_thesis_extension_valid_passes() -> None:
    doc = legal_example_student_output_with_thesis_v1()
    assert validate_student_output_v1(doc) == []


def test_thesis_bad_confidence_band() -> None:
    doc = copy.deepcopy(legal_example_student_output_with_thesis_v1())
    doc["confidence_band"] = "extreme"
    errs = validate_student_output_v1(doc)
    assert any("confidence_band" in e for e in errs)


def test_thesis_student_action_mismatch_enter_long() -> None:
    doc = copy.deepcopy(legal_example_student_output_with_thesis_v1())
    doc["act"] = False
    doc["student_action_v1"] = "enter_long"
    errs = validate_student_output_v1(doc)
    assert any("enter_long" in e for e in errs)


def test_thesis_no_trade_requires_act_false() -> None:
    doc = copy.deepcopy(legal_example_student_output_v1())
    doc["student_action_v1"] = "no_trade"
    doc["act"] = True
    errs = validate_student_output_v1(doc)
    assert any("no_trade" in e for e in errs)


def test_minimal_output_still_valid_without_thesis() -> None:
    assert validate_student_output_v1(legal_example_student_output_v1()) == []
