"""Reasoning Model operator tile: key resolution must match the OpenAI adapter (env + host env file)."""

from __future__ import annotations

import pytest

import renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 as adapter_mod
from renaissance_v4.game_theory.reasoning_model_operator_surface_v1 import _openai_key_configured_v1


def test_openai_key_configured_uses_host_secrets_file_like_adapter(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter_mod.reset_external_openai_bootstrap_state_for_tests_v1()
    f = tmp_path / "openai.env"
    f.write_text("export OPENAI_API_KEY='sk-surface-align-test-not-real-xyz'\n", encoding="utf-8")
    monkeypatch.setenv("BLACKBOX_OPENAI_ENV_FILE", str(f))
    assert _openai_key_configured_v1({"api_key_env_var": "OPENAI_API_KEY"}) is True


def test_headline_not_fault_when_ollama_probe_fails_but_external_key_ok(monkeypatch):
    from renaissance_v4.game_theory import reasoning_model_operator_surface_v1 as surf

    monkeypatch.setattr(
        surf,
        "load_reasoning_router_config_v1",
        lambda _p: {
            "router_enabled": True,
            "external_api_enabled": True,
            "api_key_env_var": "OPENAI_API_KEY",
            "local_llm_model": "llama3",
        },
    )
    monkeypatch.setattr(
        surf,
        "read_operator_reasoning_model_preferences_v1",
        lambda: {"external_api_gateway_enabled": True},
    )
    monkeypatch.setattr(
        surf,
        "verify_ollama_model_tag_available_v1",
        lambda *_a, **_k: "ollama unavailable",
    )
    monkeypatch.setattr(surf, "_openai_key_configured_v1", lambda _c: True)
    monkeypatch.setattr(
        surf,
        "read_learning_trace_events_for_job_v1",
        lambda _j: [],
    )
    out = surf.get_reasoning_model_operator_snapshot_v1(None)
    assert out["headline_badge_v1"] != "Fault"
    assert out["headline_badge_v1"] == "External active"
    assert out["tile_color_v1"] in ("amber", "blue", "green")


def test_active_student_headline_when_parallel_job_running(monkeypatch):
    from renaissance_v4.game_theory import reasoning_model_operator_surface_v1 as surf

    jid32 = "a" * 32
    fake_rt = {
        "status": "running",
        "reasoning_tile_run_kind_v1": "student",
        "operator_run_mode_surface_v1": "student",
    }
    monkeypatch.setattr(
        surf,
        "_parallel_job_runtime_from_web_app_v1",
        lambda _req: (jid32, fake_rt, True),
    )
    monkeypatch.setattr(
        surf,
        "load_reasoning_router_config_v1",
        lambda _p: {
            "router_enabled": True,
            "external_api_enabled": True,
            "api_key_env_var": "OPENAI_API_KEY",
            "local_llm_model": "llama3",
            "max_estimated_cost_usd_per_run": 1.0,
        },
    )
    monkeypatch.setattr(
        surf,
        "read_operator_reasoning_model_preferences_v1",
        lambda: {"external_api_gateway_enabled": True},
    )
    monkeypatch.setattr(surf, "verify_ollama_model_tag_available_v1", lambda *_a, **_k: None)
    monkeypatch.setattr(surf, "_openai_key_configured_v1", lambda _c: True)
    monkeypatch.setattr(surf, "read_learning_trace_events_for_job_v1", lambda _j: [])
    out = surf.get_reasoning_model_operator_snapshot_v1(None)
    assert out["headline_badge_v1"] == "Active — Student reasoning in progress"
    assert out["student_reasoning_execution_v1"] == "active"
    assert out["job_id_scoped"] == jid32
    assert out.get("parallel_job_auto_scoped_v1") is True
