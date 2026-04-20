"""Barney summary facts + deterministic fallback."""

from __future__ import annotations

import os

from renaissance_v4.game_theory.barney_summary import (
    barney_summarize_job_facts,
    build_barney_facts_from_job_state,
    render_barney_fallback_text,
)


def test_build_facts_error_job() -> None:
    facts = build_barney_facts_from_job_state(
        status="error",
        error_message="RuntimeError: replay_noop_batch",
        parallel_result=None,
        batch_timing={"operator_batch_audit": {"operator_recipe_id": "pattern_learning"}},
        telemetry_echo=None,
    )
    assert facts["run_status"] == "error"
    assert "replay_noop" in (facts.get("error_message") or "")
    txt = render_barney_fallback_text(facts)
    assert "failed" in txt.lower()
    assert "replay_noop" in txt


def test_build_facts_done_minimal() -> None:
    pr = {
        "ran": 1,
        "ok_count": 1,
        "failed_count": 0,
        "operator_batch_audit": {
            "operator_recipe_id": "pattern_learning",
            "operator_label": "PML",
            "manifest_path_primary": "renaissance_v4/configs/manifests/baseline_v1_recipe.json",
            "evaluation_window_effective_calendar_months": 12,
        },
        "pnl_summary": {
            "starting_equity_usd": 1000.0,
            "batch_total_pnl_usd": 12.5,
            "ending_equity_usd": 1012.5,
        },
        "results": [
            {
                "ok": True,
                "policy_contract": {"strategy_id": "renaissance_baseline_v1_stack"},
            }
        ],
    }
    bt = {
        "learning_status": "execution_only",
        "candidate_count": 0,
        "selected_candidate_id": None,
        "groundhog_status": "inactive",
    }
    facts = build_barney_facts_from_job_state(
        status="done",
        error_message=None,
        parallel_result=pr,
        batch_timing=bt,
        telemetry_echo={"context_signature_memory_mode": "read_write"},
    )
    assert facts["strategy_id"] == "renaissance_baseline_v1_stack"
    assert facts["memory_mode"] == "read_write"
    assert facts["no_winner"] is False


def test_summarize_fallback_when_llm_off(monkeypatch) -> None:
    monkeypatch.setenv("BARNEY_USE_LLM", "0")
    facts = build_barney_facts_from_job_state(
        status="done",
        error_message=None,
        parallel_result={
            "ran": 1,
            "ok_count": 1,
            "failed_count": 0,
            "operator_batch_audit": {"operator_recipe_id": "pattern_learning"},
            "pnl_summary": {"starting_equity_usd": 1000.0, "batch_total_pnl_usd": 0.0, "ending_equity_usd": 1000.0},
            "results": [{"ok": True, "policy_contract": {"strategy_id": "x"}}],
        },
        batch_timing={"candidate_count": 2, "selected_candidate_id": None},
        telemetry_echo=None,
    )
    out = barney_summarize_job_facts(facts)
    assert out["ok"] is True
    assert out["source"] == "fallback"
    assert "no candidate" in out["text"].lower() or "winner" in out["text"].lower()
    monkeypatch.delenv("BARNEY_USE_LLM", raising=False)
