"""Ask DATA bounded explainer — bundle, sanitize, refusal, fallback."""

from __future__ import annotations

import pytest

from renaissance_v4.game_theory.ask_data_explainer import (
    ask_data_answer,
    build_ask_data_bundle_v1,
    looks_off_topic,
    refusal_text_general,
    sanitize_ui_context,
    scorecard_snapshot_for_ask,
)
from renaissance_v4.game_theory.ask_data_operator_surface_v1 import (
    ASK_DATA_UI_CONTEXT_ALLOWED,
    build_operator_surface_catalog_for_ask_v1,
)


@pytest.fixture(autouse=True)
def _ask_data_feedback_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid writing ``ask_data_operator_feedback.jsonl`` during unrelated explainer tests."""
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK", "0")


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


def test_operator_surface_catalog_and_ui_context_contract_match() -> None:
    cat = build_operator_surface_catalog_for_ask_v1()
    assert cat.get("schema") == "operator_surface_catalog_v1"
    assert frozenset(cat.get("ask_data_ui_context_keys") or []) == ASK_DATA_UI_CONTEXT_ALLOWED
    assert cat.get("parallel_limits", {}).get("hard_cap_workers") is not None
    assert cat.get("evaluation_window", {}).get("dom_id") == "evaluationWindowPick"


def test_fallback_download_artifacts_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={},
        operator_strategy_state=None,
        job_resolution="no_job",
    )
    out = ask_data_answer("How do I download a CSV report of the scorecard?", bundle)
    assert out["ok"] is True
    assert out["answer_source"] == "operator_surface"
    assert "/api/batch-scorecard.csv" in out["text"]


def test_build_bundle_includes_operator_surface_catalog() -> None:
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={},
        operator_strategy_state=None,
        job_resolution="no_job",
    )
    osc = bundle.get("operator_surface_catalog")
    assert isinstance(osc, dict)
    assert osc.get("schema") == "operator_surface_catalog_v1"
    arts = osc.get("downloadable_artifacts") or []
    assert any(a.get("path") == "/api/batch-scorecard.csv" for a in arts if isinstance(a, dict))


def test_build_bundle_includes_data_health_evaluation_wiring() -> None:
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={"evaluation_window_mode": "18"},
        operator_strategy_state=None,
        job_resolution="no_job",
    )
    dh = bundle.get("data_health_snapshot")
    assert isinstance(dh, dict)
    assert dh.get("schema") == "ask_data_data_health_snapshot_v1"
    assert "database_path" in dh
    assert "all_bars_count" in dh
    ew = bundle.get("evaluation_window_resolved")
    assert isinstance(ew, dict)
    assert ew.get("effective_calendar_months") == 18
    wb = bundle.get("wiring_module_board")
    assert isinstance(wb, dict)
    assert wb.get("schema") == "ask_data_wiring_module_board_v1"
    assert isinstance(wb.get("modules"), list)
    assert any(m.get("id") == "web_ui" for m in wb["modules"] if isinstance(m, dict))


def test_fallback_multisense_5m_trade_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambiguous “window” + 5m / trade → calendar slice + bar cadence (+ DW if scorecard has sum)."""
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot={
            "schema": "pml_scorecard_snapshot_v1",
            "job_id": "j1",
            "replay_decision_windows_sum": 4200,
        },
        ui_context={"evaluation_window_mode": "12"},
        operator_strategy_state=None,
        job_resolution="scorecard_only",
    )
    out = ask_data_answer(
        "What 5m trade window are we operating under right now?",
        bundle,
    )
    assert out["ok"] is True
    assert out["answer_source"] == "static+data_health+evaluation_window"
    low = out["text"].lower()
    assert "calendar" in low or "12" in out["text"]
    assert "5-minute" in low or "5m" in low or "market_bars" in low
    assert "decision window" in low or "4200" in out["text"]
    assert "follow-up" in low


def test_fallback_data_health_and_evaluation_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={"evaluation_window_mode": "12"},
        operator_strategy_state=None,
        job_resolution="no_job",
    )
    out_db = ask_data_answer("How much data is in the SQLite database?", bundle)
    assert out_db["ok"] is True
    assert out_db["answer_source"] == "data_health"
    out_win = ask_data_answer("What time window are we operating under?", bundle)
    assert out_win["ok"] is True
    assert out_win["answer_source"] == "evaluation_window"
    assert "calendar month" in out_win["text"].lower()
    out_wire = ask_data_answer("How is the code wired together for replay?", bundle)
    assert out_wire["ok"] is True
    assert out_wire["answer_source"] == "wiring"
    assert "web_app.py" in out_wire["text"].lower() or "parallel_runner" in out_wire["text"].lower()


def test_scorecard_snapshot_includes_memory_context_audit() -> None:
    entry = {
        "job_id": "j1",
        "memory_context_impact_audit_v1": {
            "schema": "memory_context_impact_audit_v1",
            "memory_impact_yes_no": "YES",
            "barney_operator_truth_line_v1": (
                "Memory matched prior context on 1 windows, applied fusion bias 1 times, "
                "changed the trade set (Δ trades), and altered outcome (Δ PnL)."
            ),
        },
    }
    snap = scorecard_snapshot_for_ask(entry)
    assert snap is not None
    assert snap.get("memory_context_impact_audit_v1", {}).get("memory_impact_yes_no") == "YES"


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


def test_fallback_memory_impact_from_scorecard(monkeypatch) -> None:
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot={
            "schema": "pml_scorecard_snapshot_v1",
            "job_id": "x",
            "memory_context_impact_audit_v1": {
                "barney_operator_truth_line_v1": (
                    "Memory was enabled but had zero impact; this run is deterministic."
                ),
            },
        },
        ui_context={},
        operator_strategy_state=None,
        job_resolution="scorecard_only",
    )
    out = ask_data_answer("Did memory impact this run?", bundle)
    assert out["ok"] is True
    assert "deterministic" in out["text"].lower()
    assert out["answer_source"] == "run_facts"
    monkeypatch.delenv("ASK_DATA_USE_LLM", raising=False)


def test_build_bundle_includes_system_dictionary() -> None:
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={},
        operator_strategy_state=None,
        job_resolution="no_job",
    )
    sd = bundle.get("system_dictionary")
    assert isinstance(sd, dict)
    assert sd.get("schema") == "ask_data_system_dictionary_v1"
    assert isinstance(sd.get("topics"), dict)


def test_fallback_system_dictionary_levels(monkeypatch) -> None:
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={},
        operator_strategy_state=None,
        job_resolution="no_job",
    )
    out = ask_data_answer("What is level 2 in the student path?", bundle)
    assert out["ok"] is True
    assert out["answer_source"] == "system_dictionary"
    assert "level" in out["text"].lower() or "fold" in out["text"].lower()
    assert out.get("ask_data_route") == "pml_lightweight"
    monkeypatch.delenv("ASK_DATA_USE_LLM", raising=False)
