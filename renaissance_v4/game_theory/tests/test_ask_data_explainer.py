"""Ask DATA bounded explainer — bundle, sanitize, refusal, fallback."""

from __future__ import annotations

from renaissance_v4.game_theory.ask_data_explainer import (
    ask_data_answer,
    build_ask_data_bundle_v1,
    looks_off_topic,
    refusal_text_general,
    sanitize_ui_context,
    scorecard_snapshot_for_ask,
)


def test_sanitize_ui_context_strips_unknown_and_long() -> None:
    raw = {
        "operator_recipe_id": "pattern_learning",
        "evil": "payload",
        "recipe_label": "x" * 200,
        "evaluation_window_custom_months": "12",
    }
    out = sanitize_ui_context(raw)
    assert "evil" not in out
    assert out["operator_recipe_id"] == "pattern_learning"
    assert len(out["recipe_label"]) <= 160


def test_scorecard_snapshot_whitelist() -> None:
    entry = {
        "job_id": "abc",
        "learning_status": "execution_only",
        "selected_candidate_id": None,
        "huge_blob": {"nested": True},
    }
    snap = scorecard_snapshot_for_ask(entry)
    assert snap is not None
    assert snap.get("job_id") == "abc"
    assert "huge_blob" not in snap


def test_looks_off_topic() -> None:
    assert looks_off_topic("What is the weather in Paris?") is True
    assert looks_off_topic("What does memory mode do in this UI?") is False


def test_refusal_path_no_llm(monkeypatch) -> None:
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={"operator_recipe_id": "custom"},
        operator_strategy_state={"strategy_loaded": False},
        job_resolution="no_job",
    )
    out = ask_data_answer("What is the weather tomorrow?", bundle)
    assert out["ok"] is True
    assert "only explains" in out["text"].lower() or "pattern machine" in out["text"].lower()
    assert out["answer_source"] == "refused"

    out2 = ask_data_answer("What does PML do?", bundle)
    assert out2["ok"] is True
    assert "pattern" in out2["text"].lower()
    monkeypatch.delenv("ASK_DATA_USE_LLM", raising=False)


def test_run_facts_fallback(monkeypatch) -> None:
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    facts = {
        "schema": "barney_facts_v1",
        "run_status": "error",
        "error_message": "disk full",
        "no_winner": True,
    }
    bundle = build_ask_data_bundle_v1(
        barney_facts=facts,
        scorecard_snapshot=None,
        ui_context={},
        operator_strategy_state=None,
        job_resolution="live_job_terminal",
    )
    out = ask_data_answer("Why did this run fail?", bundle)
    assert out["ok"] is True
    assert "disk full" in out["text"].lower() or "failed" in out["text"].lower()
    assert out["answer_source"] == "run_facts"
    monkeypatch.delenv("ASK_DATA_USE_LLM", raising=False)
