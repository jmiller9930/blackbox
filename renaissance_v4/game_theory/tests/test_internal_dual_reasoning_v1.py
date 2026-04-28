"""Internal dual-reasoning classification and comparison (no live Ollama)."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.internal_dual_reasoning_v1 import (
    classify_internal_reasoning_mode_v1,
    compare_dual_review_outputs_v1,
    data_validation_sensitive_topic_v1,
)


def test_classify_auto_qwen_only_simple_question() -> None:
    mode, meta = classify_internal_reasoning_mode_v1(
        "What does PML do?",
        ask_data_route="pml_lightweight",
        job_resolution="",
    )
    assert mode == "qwen_only"
    assert meta.get("dual_topic_hint_v1") is False


def test_classify_dual_on_trading_policy_topic() -> None:
    mode, meta = classify_internal_reasoning_mode_v1(
        "Walk through trading policy assignment for this replay window",
        ask_data_route="pml_lightweight",
        job_resolution="",
    )
    assert mode == "dual_review"
    assert meta.get("dual_topic_hint_v1") is True


def test_classify_deepseek_route_without_dual_topics() -> None:
    mode, _ = classify_internal_reasoning_mode_v1(
        "Prove this strategy is optimal under game theory",
        ask_data_route="deepseek_escalation",
        job_resolution="",
    )
    assert mode == "deepseek_only"


def test_env_force_dual_review(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_REASONING_MODE", "dual_review")
    mode, meta = classify_internal_reasoning_mode_v1(
        "hello",
        ask_data_route="pml_lightweight",
        job_resolution="",
    )
    assert mode == "dual_review"
    assert meta.get("internal_reasoning_env_override") == "dual_review"


def test_data_validation_sensitive_topic() -> None:
    assert data_validation_sensitive_topic_v1("Explain PnL math for risk gate", "") is True
    assert data_validation_sensitive_topic_v1("What color is the UI?", "") is False


def test_compare_outputs_marks_data_validation_for_sensitive_domain() -> None:
    c = compare_dual_review_outputs_v1(
        "alpha beta gamma replay summary",
        "delta beta gamma scorecard note",
        data_validation_domain=True,
    )
    assert c["agreement_level_v1"] in ("agree", "partial", "disagree")
    assert c["data_validation_required_v1"] is True


def test_compare_outputs_requires_data_when_disagree() -> None:
    c = compare_dual_review_outputs_v1(
        "aaa bbb ccc ddd eee fff ggg",
        "zzz yyy xxx www vvv uuu ttt",
        data_validation_domain=False,
    )
    if c["agreement_level_v1"] == "disagree":
        assert c["data_validation_required_v1"] is True
