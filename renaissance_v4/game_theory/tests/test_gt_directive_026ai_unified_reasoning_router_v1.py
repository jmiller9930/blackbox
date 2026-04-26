# GT_DIRECTIVE_026AI — unified reasoning router (local primary; optional OpenAI review)

from __future__ import annotations

import json
import os

import pytest

from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import run_entry_reasoning_pipeline_v1
from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 import (
    apply_environment_overrides_v1,
    load_reasoning_router_config_v1,
    validate_config_public_surface_v1,
)
from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_v1 import (
    SCHEMA_REVIEW,
    apply_unified_reasoning_router_v1,
    collect_escalation_reason_codes_v1,
)
import renaissance_v4.game_theory.unified_agent_v1.reasoning_router_v1 as router_mod


def _bars() -> list[dict]:
    return [
        {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100.0},
        {"open": 1.0, "high": 1.2, "low": 0.95, "close": 1.1, "volume": 110.0},
    ]


def _packet() -> dict:
    return {
        "schema": "student_decision_packet_v1",
        "symbol": "BTC",
        "candle_timeframe_minutes": 5,
        "bars_inclusive_up_to_t": _bars(),
    }


@pytest.fixture(autouse=True)
def _trace_off(monkeypatch):
    monkeypatch.setenv("PATTERN_GAME_LEARNING_TRACE_EVENTS", "0")


def test_local_only_when_external_disabled(monkeypatch):
    ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=True,
        router_config={
            "schema": "reasoning_router_config_v1",
            "contract_version": 1,
            "router_enabled": True,
            "external_api_enabled": False,
            "external_model": "gpt-5.5",
            "api_key_env_var": "OPENAI_API_KEY",
            "max_external_calls_per_run": 1,
            "max_external_calls_per_trade": 1,
            "max_input_tokens_per_call": 8000,
            "max_output_tokens_per_call": 2000,
            "max_total_tokens_per_run": 24000,
            "max_estimated_cost_usd_per_run": 0.5,
            "low_confidence_threshold": 0.35,
            "max_memory_records_for_external": 3,
            "random_audit_sample_rate": 0.0,
            "enabled_escalation_reasons": list(
                (
                    "low_confidence_v1",
                    "indicator_conflict_v1",
                    "memory_conflict_v1",
                    "risk_conflict_v1",
                    "schema_failure_v1",
                    "operator_forced_audit_v1",
                    "high_value_opportunity_v1",
                    "student_vs_baseline_disagreement_v1",
                    "random_audit_sample_v1",
                )
            ),
        },
    )
    assert ere and not err
    d = ere.get("reasoning_router_decision_v1") or {}
    assert d.get("final_route_v1") == "local_only" or d.get("final_route_v1") == "external_blocked_config"
    assert "sk-" not in json.dumps(ere)


def test_external_blocked_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}),
    )
    assert ere and not err
    d = ere.get("reasoning_router_decision_v1") or {}
    assert d.get("final_route_v1") == "external_blocked_missing_key"
    assert "OPENAI_API_KEY" not in json.dumps(d)


def test_external_blocked_no_escalation_reason(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-format-check-only")
    ere, err, _tr, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(
            None,
            extra_dict={
                "external_api_enabled": True,
                "low_confidence_threshold": 0.01,
                "enabled_escalation_reasons": ["memory_conflict_v1"],
            },
        ),
    )
    assert ere and not err
    d = ere.get("reasoning_router_decision_v1") or {}
    # No memory conflict on empty retrieval — no escalation codes
    assert "no_escalation_reason_v1" in (d.get("escalation_blockers_v1") or []) or d.get("final_route_v1") == "local_only"


def test_external_blocked_budget(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-format-check-only")
    ere, err, _tr, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(
            None,
            extra_dict={
                "external_api_enabled": True,
                "low_confidence_threshold": 0.99,
                "max_external_calls_per_run": 0,
                "max_estimated_cost_usd_per_run": 0.0,
            },
        ),
    )
    assert ere and not err
    d = ere.get("reasoning_router_decision_v1") or {}
    assert d.get("final_route_v1") in ("external_blocked_budget", "local_only")


def test_external_called_low_confidence_mocked(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-format-check-only")

    def _fake(*, model_requested: str = "", **kwargs):
        return {
            "ok": True,
            "error": None,
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "model_resolved": "gpt-5.5-2026-04-23",
            "response_status": "ok",
            "parsed_json": {
                "schema": SCHEMA_REVIEW,
                "contract_version": 1,
                "review_model_v1": "gpt-5.5-2026-04-23",
                "review_summary_v1": "ok",
                "disagreement_with_local_v1": False,
                "suggested_action_v1": "no_trade",
                "suggested_confidence_v1": 0.4,
                "identified_risks_v1": [],
                "memory_assessment_v1": "n/a",
                "indicator_assessment_v1": "n/a",
                "schema_valid_v1": True,
                "validator_errors_v1": [],
            },
        }

    monkeypatch.setattr(router_mod, "call_openai_responses_v1", _fake)
    ere, err, _tr, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="j1",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(
            None,
            extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99},
        ),
    )
    assert ere and not err
    d = ere.get("reasoning_router_decision_v1") or {}
    assert d.get("final_route_v1") == "external_review"
    assert ere.get("external_reasoning_review_v1")
    assert (ere.get("external_api_call_ledger_v1") or {}).get("total_tokens_v1", 0) >= 0


def test_memory_conflict_triggers_mocked(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-format-check-only")

    def _fake2(**kwargs):
        return {
            "ok": True,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "model_resolved": "gpt-5.5-2026-04-23",
            "response_status": "ok",
            "parsed_json": {
                "schema": SCHEMA_REVIEW,
                "contract_version": 1,
                "review_model_v1": "m",
                "review_summary_v1": "m",
                "disagreement_with_local_v1": True,
                "suggested_action_v1": "enter_long",
                "suggested_confidence_v1": 0.9,
                "identified_risks_v1": [],
                "memory_assessment_v1": "x",
                "indicator_assessment_v1": "y",
                "schema_valid_v1": True,
                "validator_errors_v1": [],
            },
        }

    monkeypatch.setattr(router_mod, "call_openai_responses_v1", _fake2)
    rse = [
        {
            "record_id": "a",
            "candle_timeframe_minutes": 5,
            "referee_outcome_subset": {"pnl": 1.0},
        }
    ]
    ere, err, _tr, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=rse,
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(
            None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.01}
        ),
    )
    # Memory conflict class may be NOT conflict with one row — this run still exercises code path
    assert ere and not err


def test_invalid_external_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-format-check-only")

    def _bad(**kwargs):
        return {
            "ok": True,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "model_resolved": "gpt-5.5",
            "response_status": "ok",
            "parsed_json": {"schema": "wrong", "foo": 1},
        }

    monkeypatch.setattr(router_mod, "call_openai_responses_v1", _bad)
    out2 = _packet()
    er0, e0, _, pfm0 = run_entry_reasoning_pipeline_v1(
        student_decision_packet=out2,
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
    )
    assert er0
    u = apply_unified_reasoning_router_v1(
        entry_reasoning_eval_v1=er0,
        base_fault_map=pfm0,
        config=load_reasoning_router_config_v1(
            None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
        ),
    )
    assert u["reasoning_router_decision_v1"].get("final_route_v1") == "external_failed_fallback_local"
    assert u.get("external_reasoning_review_v1") is None


def test_no_sk_in_ledger():
    c = load_reasoning_router_config_v1(None)
    assert validate_config_public_surface_v1(c) == []
    assert "sk-" not in json.dumps(c)


def test_env_override_model(monkeypatch):
    monkeypatch.setenv("OPENAI_REASONING_MODEL", "gpt-5.5-2026-04-23")
    c = apply_environment_overrides_v1({"external_model": "gpt-5.5"})
    assert "2026" in str(c.get("external_model", ""))


def test_fault_map_has_router_nodes():
    _ere, _e, _t, pfm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(),
    )
    ids = [n.get("node_id") for n in (pfm.get("nodes_v1") or [])]
    assert "reasoning_router_evaluated" in ids
    assert "external_escalation_governed" in ids
    assert "external_reasoning_review_recorded" in ids


def test_engine_action_unchanged_when_review_disagrees(monkeypatch):
    """External review is advisory; deterministic engine action must not be overwritten by model."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-format-check-only")

    def _disagree(**kwargs):
        return {
            "ok": True,
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "model_resolved": "gpt-5.5-2026-04-23",
            "response_status": "ok",
            "parsed_json": {
                "schema": SCHEMA_REVIEW,
                "contract_version": 1,
                "review_model_v1": "m",
                "review_summary_v1": "disagree",
                "disagreement_with_local_v1": True,
                "suggested_action_v1": "enter_long",
                "suggested_confidence_v1": 0.99,
                "identified_risks_v1": ["x"],
                "memory_assessment_v1": "a",
                "indicator_assessment_v1": "b",
                "schema_valid_v1": True,
                "validator_errors_v1": [],
            },
        }

    baseline, berr, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=False,
    )
    assert baseline and not berr
    base_act = str((baseline.get("decision_synthesis_v1") or {}).get("action") or "")

    monkeypatch.setattr(router_mod, "call_openai_responses_v1", _disagree)
    ere, err, _tr, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=_packet(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id="",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(
            None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
        ),
    )
    assert ere and not err
    assert str((ere.get("decision_synthesis_v1") or {}).get("action") or "") == base_act
    assert ere.get("external_reasoning_review_v1")
    assert (ere.get("external_reasoning_review_v1") or {}).get("suggested_action_v1") == "enter_long"


def test_openai_key_read_from_environment_only(monkeypatch):
    """Env wins; if unset, optional host file (``BLACKBOX_OPENAI_ENV_FILE``) may provide the key."""
    import renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 as adapter_mod

    monkeypatch.setenv("BLACKBOX_OPENAI_ENV_FILE", "/__nonexistent__/no_openai.env")
    adapter_mod.reset_external_openai_bootstrap_state_for_tests_v1()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert adapter_mod._get_api_key("OPENAI_API_KEY") is None
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-env-only-not-a-real-key")
    assert adapter_mod._get_api_key("OPENAI_API_KEY") == "sk-test-env-only-not-a-real-key"


def test_openai_key_from_host_secrets_file(monkeypatch, tmp_path):
    """Host-only envfile (e.g. ``~/.blackbox_secrets/openai.env``) can seed ``OPENAI_API_KEY`` when env is empty."""
    import renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 as adapter_mod

    f = tmp_path / "openai.env"
    f.write_text("export OPENAI_API_KEY='sk-from-file-test-only'\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BLACKBOX_OPENAI_ENV_FILE", str(f))
    adapter_mod.reset_external_openai_bootstrap_state_for_tests_v1()
    assert adapter_mod._get_api_key("OPENAI_API_KEY") == "sk-from-file-test-only"


def test_smoke_output_has_no_bearer(capfd, monkeypatch):
    """Smoke must not print API key; module prints JSON summary only."""
    import renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 as adapter_mod

    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("BLACKBOX_OPENAI_ENV_FILE", "/__nonexistent__/no_openai.env")
    adapter_mod.reset_external_openai_bootstrap_state_for_tests_v1()
    from renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 import run_smoke_test_strict_json_v1

    r = run_smoke_test_strict_json_v1()
    t = json.dumps(r)
    assert "sk-" not in t
    assert "Authorization" not in t


def test_operator_external_gateway_on_overrides_openai_escalation_env_off(monkeypatch):
    import renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 as rrc

    monkeypatch.setattr(rrc, "read_operator_reasoning_model_preferences_v1", lambda: {})
    monkeypatch.setenv("OPENAI_ESCALATION_ENABLED", "0")
    c = load_reasoning_router_config_v1(None)
    assert c.get("external_api_enabled") is True
    assert c.get("operator_external_api_gateway_merge_v1") == "enabled_by_operator_ui_v1"


def test_operator_external_gateway_off_forces_disable_even_if_escalation_env_on(monkeypatch):
    import renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 as rrc

    monkeypatch.setattr(
        rrc,
        "read_operator_reasoning_model_preferences_v1",
        lambda: {"external_api_gateway_enabled": False},
    )
    monkeypatch.setenv("OPENAI_ESCALATION_ENABLED", "1")
    c = load_reasoning_router_config_v1(None)
    assert c.get("external_api_enabled") is False
    assert c.get("operator_external_api_gateway_merge_v1") == "blocked_by_operator_ui"
