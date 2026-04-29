"""GT_DIRECTIVE_037 — validation-only repair when JSON parses but thesis/schema fails."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    emit_student_output_via_ollama_v1,
)


def _good_thesis_obj_v1() -> dict:
    return {
        "act": False,
        "direction": "flat",
        "confidence_01": 0.5,
        "pattern_recipe_ids": ["probe_recipe_v1"],
        "reasoning_text": "Probe rationale grounded in packet.",
        "context_interpretation_v1": "Sixteen-plus chars describing bars-only context here.",
        "hypothesis_kind_v1": "no_clear_edge",
        "hypothesis_text_v1": "No actionable edge from this slice.",
        "supporting_indicators": ["close_structure"],
        "conflicting_indicators": [CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1],
        "confidence_band": "low",
        "context_fit": "range",
        "invalidation_text": "Would need clearer alignment before sizing risk.",
        "student_action_v1": "no_trade",
    }


@pytest.fixture()
def minimal_packet_v1() -> dict:
    return {
        "symbol": "SOLUSDT",
        "bars_inclusive_up_to_t": [
            {"open_time": 1700000000000, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100.0},
        ],
    }


def test_validation_repair_only_two_calls(monkeypatch: pytest.MonkeyPatch, minimal_packet_v1: dict) -> None:
    """Parse succeeds on first reply but thesis too short → validation repair, no JSON repair."""
    monkeypatch.setenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")
    bad = _good_thesis_obj_v1()
    bad["context_interpretation_v1"] = "too_short"
    calls: list[int] = []

    def fake(**_: object) -> tuple[str | None, str | None]:
        calls.append(1)
        if len(calls) == 1:
            return json.dumps(bad, ensure_ascii=False), None
        return json.dumps(_good_thesis_obj_v1(), ensure_ascii=False), None

    cap: dict = {}
    with patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        side_effect=fake,
    ):
        out, errs = emit_student_output_via_ollama_v1(
            minimal_packet_v1,
            graded_unit_id="t1",
            decision_at_ms=1700000000000,
            llm_model="qwen2.5:7b",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_v1",
            require_directional_thesis_v1=True,
            llm_io_capture_v1=cap,
        )
    assert out is not None and not errs
    assert len(calls) == 2
    assert cap.get("json_repair_attempted_v1") is False
    assert cap.get("validation_repair_attempted_v1") is True
    assert cap.get("json_contract_retry_used_v1") is True


def test_json_then_validation_repair_three_calls(monkeypatch: pytest.MonkeyPatch, minimal_packet_v1: dict) -> None:
    """Prose → JSON repair → valid JSON but short thesis → validation repair."""
    monkeypatch.setenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")
    bad = _good_thesis_obj_v1()
    bad["context_interpretation_v1"] = "x" * 8
    calls: list[int] = []

    def fake(**_: object) -> tuple[str | None, str | None]:
        calls.append(1)
        n = len(calls)
        if n == 1:
            return "### not json", None
        if n == 2:
            return json.dumps(bad, ensure_ascii=False), None
        return json.dumps(_good_thesis_obj_v1(), ensure_ascii=False), None

    cap: dict = {}
    with patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        side_effect=fake,
    ):
        out, errs = emit_student_output_via_ollama_v1(
            minimal_packet_v1,
            graded_unit_id="t1",
            decision_at_ms=1700000000000,
            llm_model="qwen2.5:7b",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_v1",
            require_directional_thesis_v1=True,
            llm_io_capture_v1=cap,
        )
    assert out is not None and not errs
    assert len(calls) == 3
    assert cap.get("json_repair_attempted_v1") is True
    assert cap.get("validation_repair_attempted_v1") is True
