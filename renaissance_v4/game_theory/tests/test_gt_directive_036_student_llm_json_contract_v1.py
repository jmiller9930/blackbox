"""GT_DIRECTIVE_036 — Student LLM JSON contract, deterministic options, single repair retry."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONFLICTING_INDICATORS_NO_CONFLICT_PACKET_LABEL_V1,
)
import json

from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    emit_student_output_via_ollama_v1,
)


def _valid_thesis_json_v1() -> str:
    return json.dumps(
        {
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
        },
        ensure_ascii=False,
    )


@pytest.fixture()
def minimal_packet_v1() -> dict:
    return {
        "symbol": "SOLUSDT",
        "bars_inclusive_up_to_t": [
            {"open_time": 1700000000000, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100.0},
        ],
    }


def test_non_student_test_no_retry_on_prose(monkeypatch: pytest.MonkeyPatch, minimal_packet_v1: dict) -> None:
    monkeypatch.delenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", raising=False)
    calls: list[int] = []

    def _once(**_: object) -> tuple[str | None, str | None]:
        calls.append(1)
        return "这是中文分析，不是 JSON", None

    with patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        side_effect=_once,
    ):
        out, errs = emit_student_output_via_ollama_v1(
            minimal_packet_v1,
            graded_unit_id="t1",
            decision_at_ms=1700000000000,
            llm_model="qwen2.5:7b",
            ollama_base_url="http://127.0.0.1:11434",
            prompt_version="test_v1",
            require_directional_thesis_v1=True,
            llm_io_capture_v1=None,
        )
    assert out is None
    assert calls == [1]
    assert errs and "ollama_response_not_json_object" in errs[0]


def test_student_test_retry_succeeds_second_call(
    monkeypatch: pytest.MonkeyPatch,
    minimal_packet_v1: dict,
) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")
    attempt = {"n": 0}

    def _once(**_: object) -> tuple[str | None, str | None]:
        attempt["n"] += 1
        if attempt["n"] == 1:
            return "### Analysis\nNot JSON at all.", None
        return _valid_thesis_json_v1(), None

    cap: dict = {}
    with patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        side_effect=_once,
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
    assert out.get("student_action_v1") == "no_trade"
    assert attempt["n"] == 2
    assert cap.get("json_contract_retry_used_v1") is True
    assert cap.get("raw_assistant_text_attempt_2_v1")


def test_student_test_first_call_valid_no_retry(monkeypatch: pytest.MonkeyPatch, minimal_packet_v1: dict) -> None:
    monkeypatch.setenv("PATTERN_GAME_STUDENT_TEST_ISOLATION_V1", "1")
    calls = 0

    def _once(**_: object) -> tuple[str | None, str | None]:
        nonlocal calls
        calls += 1
        return _valid_thesis_json_v1(), None

    cap: dict = {}
    with patch(
        "renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1._ollama_chat_once_v1",
        side_effect=_once,
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
    assert calls == 1
    assert cap.get("json_contract_retry_used_v1") is False
