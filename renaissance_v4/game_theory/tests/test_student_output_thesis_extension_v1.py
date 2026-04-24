"""§1.0 optional directional-thesis fields on ``student_output_v1`` (parallel seam)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_output_v1,
    legal_example_student_output_with_thesis_v1,
    validate_student_output_directional_thesis_required_for_llm_profile_v1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import (
    build_reveal_v1_from_outcome_and_student,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    build_student_learning_record_v1_from_reveal,
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


def test_llm_thesis_required_full_document() -> None:
    doc = legal_example_student_output_with_thesis_v1()
    assert validate_student_output_v1(doc) == []
    assert validate_student_output_directional_thesis_required_for_llm_profile_v1(doc) == []


def test_llm_thesis_required_missing_band() -> None:
    doc = copy.deepcopy(legal_example_student_output_with_thesis_v1())
    del doc["confidence_band"]
    assert validate_student_output_directional_thesis_required_for_llm_profile_v1(doc)


def test_stub_core_output_fails_llm_thesis_required() -> None:
    """Deterministic stub has no thesis bundle — must not satisfy LLM-profile requirement."""
    assert validate_student_output_directional_thesis_required_for_llm_profile_v1(
        legal_example_student_output_v1()
    )


def test_fixture_incomplete_fails_llm_thesis_required() -> None:
    p = Path(__file__).resolve().parent / "fixtures" / "student_output_thesis_llm_incomplete_v1.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert validate_student_output_v1(doc) == []
    assert validate_student_output_directional_thesis_required_for_llm_profile_v1(doc)


def test_thesis_persists_via_learning_record() -> None:
    o = OutcomeRecord(
        trade_id="trade_thesis_fixture_valid",
        symbol="TESTUSDT",
        direction="long",
        entry_time=4_000_000,
        exit_time=5_000_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=1.0,
        mae=0.1,
        mfe=0.5,
        exit_reason="tp",
    )
    p = Path(__file__).resolve().parent / "fixtures" / "student_output_thesis_llm_valid_v1.json"
    so = json.loads(p.read_text(encoding="utf-8"))
    rev, re = build_reveal_v1_from_outcome_and_student(student_output=so, outcome=o)
    assert not re and rev
    lr, le = build_student_learning_record_v1_from_reveal(
        rev,
        run_id="run_fixture_thesis",
        record_id="660e8400-e29b-41d4-a716-446655440099",
        context_signature_v1={"schema": "context_signature_v1", "signature_key": "k"},
        strategy_id="s",
    )
    assert not le and lr
    embed = lr["student_output"]
    assert embed.get("confidence_band") == "high"
    assert embed.get("student_action_v1") == "enter_long"
    assert isinstance(embed.get("supporting_indicators"), list)
