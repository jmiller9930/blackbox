"""Ollama path: directional thesis required for LLM profile (precondition for GT_DIRECTIVE_017)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    legal_example_student_output_protocol_no_trade_v1,
    legal_example_student_output_protocol_short_v1,
    legal_example_student_output_with_thesis_v1,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    emit_student_output_via_ollama_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.game_theory.tests.test_student_context_builder_v1 import _mk_synthetic_db


@pytest.fixture()
def decision_packet(tmp_path: Path) -> dict:
    db = tmp_path / "ollama_thesis.sqlite3"
    _mk_synthetic_db(db)
    pkt, err = build_student_decision_packet_v1(
        db_path=db, symbol="TESTUSDT", decision_open_time_ms=5_000_000, candle_timeframe_minutes=5
    )
    assert err is None and isinstance(pkt, dict)
    return pkt


def test_ollama_rejects_json_missing_decision_protocol_fields(decision_packet: dict) -> None:
    """Legacy thesis-only JSON without context/hypothesis must fail LLM-profile gate."""
    legacy_thesis_only = {
        "act": True,
        "direction": "long",
        "confidence_01": 0.5,
        "pattern_recipe_ids": ["x"],
        "reasoning_text": "has old thesis keys only",
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
        "confidence_band": "medium",
        "supporting_indicators": ["a"],
        "conflicting_indicators": ["b"],
        "context_fit": "trend",
        "invalidation_text": "inv",
        "student_action_v1": "enter_long",
    }

    def fake_once(**_kwargs: object) -> tuple[str, str | None]:
        return json.dumps(legacy_thesis_only), None

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        fake_once,
    ):
        out, err = emit_student_output_via_ollama_v1(
            decision_packet,
            graded_unit_id="tr_ollama_protocol_legacy",
            decision_at_ms=5_000_000,
            llm_model="stub-model",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_pv",
            require_directional_thesis_v1=True,
        )
    assert out is None
    assert err and any("thesis" in e.lower() or "llm_profile" in e.lower() for e in err)


def test_ollama_rejects_json_missing_thesis(decision_packet: dict) -> None:
    minimal = {
        "act": True,
        "direction": "long",
        "confidence_01": 0.5,
        "pattern_recipe_ids": ["x"],
        "reasoning_text": "no thesis keys",
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
    }

    def fake_once(**_kwargs: object) -> tuple[str, str | None]:
        return json.dumps(minimal), None

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        fake_once,
    ):
        out, err = emit_student_output_via_ollama_v1(
            decision_packet,
            graded_unit_id="tr_ollama_thesis_1",
            decision_at_ms=5_000_000,
            llm_model="stub-model",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_pv",
            require_directional_thesis_v1=True,
        )
    assert out is None
    assert err and any("thesis" in e.lower() for e in err)


def test_ollama_accepts_full_thesis_json(decision_packet: dict) -> None:
    full = dict(legal_example_student_output_with_thesis_v1())
    full.pop("schema", None)
    full.pop("contract_version", None)
    full.pop("graded_unit_type", None)
    full.pop("graded_unit_id", None)
    full.pop("decision_at_ms", None)

    def fake_once(**_kwargs: object) -> tuple[str, str | None]:
        return json.dumps(full), None

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        fake_once,
    ):
        out, err = emit_student_output_via_ollama_v1(
            decision_packet,
            graded_unit_id="tr_ollama_thesis_2",
            decision_at_ms=5_000_000,
            llm_model="stub-model",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_pv",
            require_directional_thesis_v1=True,
        )
    assert not err and out is not None
    assert out.get("confidence_band") == "medium"
    assert out.get("student_action_v1") == "enter_long"
    assert out.get("hypothesis_kind_v1") == "trend_continuation"


@pytest.mark.parametrize(
    "fixture_fn,expected_action",
    [
        (legal_example_student_output_protocol_short_v1, "enter_short"),
        (legal_example_student_output_protocol_no_trade_v1, "no_trade"),
    ],
)
def test_ollama_accepts_protocol_short_and_no_trade(
    decision_packet: dict,
    fixture_fn: Callable[[], dict[str, Any]],
    expected_action: str,
) -> None:
    full = dict(fixture_fn())
    for k in ("schema", "contract_version", "graded_unit_type", "graded_unit_id", "decision_at_ms"):
        full.pop(k, None)

    def fake_once(**_kwargs: object) -> tuple[str, str | None]:
        return json.dumps(full), None

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        fake_once,
    ):
        out, err = emit_student_output_via_ollama_v1(
            decision_packet,
            graded_unit_id=f"tr_proto_{expected_action}",
            decision_at_ms=5_000_000,
            llm_model="stub-model",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_pv",
            require_directional_thesis_v1=True,
        )
    assert not err and out is not None
    assert out.get("student_action_v1") == expected_action


def test_ollama_thesis_optional_mode_allows_minimal(decision_packet: dict) -> None:
    minimal = {
        "act": True,
        "direction": "long",
        "confidence_01": 0.5,
        "pattern_recipe_ids": ["x"],
        "reasoning_text": "legacy optional thesis mode",
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
    }

    def fake_once(**_kwargs: object) -> tuple[str, str | None]:
        return json.dumps(minimal), None

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        fake_once,
    ):
        out, err = emit_student_output_via_ollama_v1(
            decision_packet,
            graded_unit_id="tr_ollama_thesis_3",
            decision_at_ms=5_000_000,
            llm_model="stub-model",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_pv",
            require_directional_thesis_v1=False,
        )
    assert not err and out is not None


def test_seam_llm_profile_no_stub_fallback_on_thesis_reject(tmp_path: Path) -> None:
    db = tmp_path / "bars.sqlite3"
    _mk_synthetic_db(db)
    store = tmp_path / "learn.jsonl"
    o = OutcomeRecord(
        trade_id="sto_trade_llm",
        symbol="TESTUSDT",
        direction="long",
        entry_time=6_000_000,
        exit_time=6_100_000,
        entry_price=100.0,
        exit_price=101.0,
        pnl=3.0,
        mae=0.0,
        mfe=1.0,
        exit_reason="tp",
    )
    results = [
        {
            "ok": True,
            "scenario_id": "row_a",
            "replay_outcomes_json": [outcome_record_to_jsonable(o)],
        }
    ]
    ex_req = {
        "student_brain_profile_v1": "memory_context_llm_student",
        "student_llm_v1": {"llm_model": "qwen3-coder:30b", "llm_provider": "ollama"},
        "prompt_version": "pv_seam_test",
    }

    def fake_emit(*_args: object, **_kwargs: object) -> tuple[None, list[str]]:
        return None, ["student_output_thesis_incomplete_for_llm_profile: missing confidence_band"]

    with mock.patch(
        "renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1.verify_ollama_model_tag_available_v1",
        lambda *_a, **_k: None,
    ):
        with mock.patch(
            "renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1.emit_student_output_via_ollama_v1",
            fake_emit,
        ):
            audit = student_loop_seam_after_parallel_batch_v1(
                results=results,
                run_id="run_llm_thesis_reject",
                db_path=db,
                store_path=store,
                strategy_id="pattern_learning",
                exam_run_contract_request_v1=ex_req,
            )
    assert int(audit.get("llm_student_output_rejections_v1") or 0) >= 1
    assert int(audit.get("student_learning_rows_appended") or 0) == 0
    errs = audit.get("errors") or []
    assert any("llm_student_output_rejected" in str(e) for e in errs)
