"""
Operator-facing **Reasoning Model** health surface (unified Student stack: local model, 026AI router, external gateway).

* ``GET`` snapshot for ``/api/reasoning-model/status`` (runtime probes + optional ``job_id`` trace slice).
* Persists the external API gateway toggle; :func:`load_reasoning_router_config_v1` merges it (blocks escalation when off).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import STUDENT_LLM_APPROVED_MODEL_V1
from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.ollama_role_routing_v1 import student_ollama_base_url_v1
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    verify_ollama_model_tag_available_v1,
)
from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 import (
    load_reasoning_router_config_v1,
    operator_reasoning_model_preferences_path_v1,
    read_operator_reasoning_model_preferences_v1,
)

SCHEMA_PREFS = "operator_reasoning_model_preferences_v1"
SCHEMA_SNAPSHOT = "reasoning_model_operator_snapshot_v1"

# Static billing portal (no API keys, no per-user tokens in URL). Operators add funds in browser.
ADD_FUNDS_BILLING_URL_V1 = "https://platform.openai.com/settings/organization/billing"


def write_operator_external_api_gateway_enabled_v1(allowed: bool) -> dict[str, Any]:
    """
    ``allowed`` True = operator allows external escalation (subject to config + env).
    ``allowed`` False = UI blocks external API regardless of config file.
    """
    p = operator_reasoning_model_preferences_path_v1()
    p.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {
        "schema": SCHEMA_PREFS,
        "contract_version": 1,
        "external_api_gateway_enabled": allowed,
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    p.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(p), "external_api_gateway_enabled": allowed}


def _openai_key_configured_v1(cfg: dict[str, Any]) -> bool:
    for k in ("OPENAI_API_KEY",):
        v = (os.environ.get(k) or "").strip()
        if len(v) > 8 and not v.lower().startswith("sk-placeholder"):
            return True
    ev = str(cfg.get("api_key_env_var") or "OPENAI_API_KEY").strip()
    v2 = (os.environ.get(ev) or "").strip()
    return len(v2) > 8 and not v2.lower().startswith("sk-placeholder")


def _last_router_and_governor_from_events(
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    last_d: dict[str, Any] | None = None
    last_g: dict[str, Any] | None = None
    for ev in events or []:
        st = str(ev.get("stage") or "").strip()
        ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
        if st == "reasoning_router_decision_v1":
            d = ep.get("reasoning_router_decision_v1")
            if isinstance(d, dict):
                last_d = d
        if st == "reasoning_cost_governor_v1":
            g = ep.get("reasoning_cost_governor_snapshot_v1") or ep.get("snapshot")
            if isinstance(g, dict):
                last_g = g
    return last_d, last_g


def _float_cost_from_ledger(ledger: Any) -> float:
    if not isinstance(ledger, dict):
        return 0.0
    for k in ("estimated_cost_usd_v1", "cost_usd_v1", "total_estimated_cost_usd_v1"):
        v = ledger.get(k)
        if v is not None:
            try:
                return max(0.0, float(v))
            except (TypeError, ValueError):
                pass
    return 0.0


def _aggregate_external_cost_from_trace_events(
    evs: list[dict[str, Any]] | None,
) -> tuple[int, int, float]:
    """Sums input/output tokens and USD from call_ledger_sanitized_v1; falls back to external_api_call_ledger_v1 if needed."""
    total_in, total_out, est_usd = 0, 0, 0.0
    for ev in evs or []:
        if str(ev.get("stage") or "") != "reasoning_router_decision_v1":
            continue
        ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
        cr = ep.get("call_ledger_sanitized_v1")
        d = ep.get("reasoning_router_decision_v1") if isinstance(ep.get("reasoning_router_decision_v1"), dict) else {}
        if isinstance(cr, dict):
            total_in += int(float(cr.get("input_tokens_v1") or 0) or 0)
            total_out += int(float(cr.get("output_tokens_v1") or 0) or 0)
            try:
                est_usd += float(cr.get("estimated_cost_usd_v1") or 0) or 0.0
            except (TypeError, ValueError):
                pass
        else:
            leg = d.get("external_api_call_ledger_v1")
            if isinstance(leg, dict):
                est_usd += _float_cost_from_ledger(leg)
    return total_in, total_out, est_usd


def get_reasoning_model_operator_snapshot_v1(job_id: str | None = None) -> dict[str, Any]:
    cfg = load_reasoning_router_config_v1(None)
    if not isinstance(cfg, dict):
        cfg = {}
    pref = read_operator_reasoning_model_preferences_v1()
    operator_blocks = pref.get("external_api_gateway_enabled") is False
    ext_effective = bool(cfg.get("external_api_enabled"))
    router_on = bool(cfg.get("router_enabled", True))
    base_url = student_ollama_base_url_v1()
    model = str(cfg.get("local_llm_model") or STUDENT_LLM_APPROVED_MODEL_V1)
    ollama_err = verify_ollama_model_tag_available_v1(base_url, model, timeout_s=8.0)
    key_ok = _openai_key_configured_v1(cfg)

    # External path status (distinct from operator checkbox: permission vs router config + key).
    if operator_blocks:
        ext_health = "operator_blocked"  # UI toggle off — escalation not allowed
    elif not ext_effective:
        ext_health = "router_config_off"  # merged config/env has external_api_enabled false
    elif not key_ok:
        ext_health = "missing_key"
    else:
        ext_health = "available"  # OpenAI can be called when the router escalates

    last_call = "not_called"
    last_dec: dict[str, Any] | None = None
    gov_last: dict[str, Any] | None = None
    total_in = 0
    total_out = 0
    est_usd = 0.0
    jid = (job_id or "").strip()
    evs: list[dict[str, Any]] = []
    if jid:
        evs = read_learning_trace_events_for_job_v1(jid) or []
        last_dec, gov_last = _last_router_and_governor_from_events(evs)
        total_in, total_out, est_usd = _aggregate_external_cost_from_trace_events(evs)
        if last_dec:
            esc = str(last_dec.get("escalation_decision_v1") or "")
            ok = last_dec.get("api_call_succeeded_v1")
            if esc != "escalation_requested":
                last_call = "not_called"
            elif ok is True:
                last_call = "success"
            elif ok is False:
                last_call = "failed"
            else:
                last_call = "unknown"

    br: list[str] = []
    if operator_blocks:
        br.append("operator_gateway_off")
    if router_on and not operator_blocks and not key_ok and ext_effective:
        br.append("missing_api_key")
    if last_dec and isinstance(last_dec.get("escalation_blockers_v1"), list):
        br.extend([str(x) for x in (last_dec.get("escalation_blockers_v1") or [])[:6]])

    bud = str((last_dec or {}).get("budget_status_v1") or (gov_last or {}).get("budget_status_v1") or "ok")
    if bud in ("exhausted",):
        budget_label = "exhausted"
        if ext_effective and not operator_blocks:
            br.append("budget_exhausted")
    elif bud in ("ok", "sufficient"):
        budget_label = "sufficient"
    else:
        budget_label = "low" if "low" in bud.lower() else bud

    # Single machine-readable reason for dashboards (order: faults → path → activity).
    primary_code = "ok"
    if ollama_err:
        primary_code = "local_model_error"
    elif not router_on:
        primary_code = "router_off"
    elif operator_blocks:
        primary_code = "operator_gateway_off"
    elif not ext_effective:
        primary_code = "router_external_disabled"
    elif not key_ok:
        primary_code = "missing_openai_key"
    elif jid and last_call == "failed" and ext_effective and key_ok:
        primary_code = "external_api_call_failed"
    elif budget_label == "exhausted" and ext_effective:
        primary_code = "budget_blocked"
    elif not jid and ext_effective and key_ok and not ollama_err:
        primary_code = "idle_no_job_scoped"
    elif jid and last_call == "not_called" and ext_effective and key_ok and not ollama_err:
        primary_code = "no_external_api_call_in_trace"

    _escalation_summary_map: dict[str, str] = {
        "ok": "Reasoning path healthy for local + router; see fields for external path.",
        "local_model_error": "Local Ollama/model probe failed; local reasoning may be unavailable.",
        "router_off": "026AI router is disabled in config.",
        "operator_gateway_off": "Operator has turned off the external API gateway (escalation not allowed).",
        "router_external_disabled": "External escalation is off in merged router config/env; enable in reasoning_router_config or OPENAI_ESCALATION_ENABLED. Operator 'gateway' can still show enabled.",
        "missing_openai_key": "External path would be used but OPENAI (or api_key_env_var) is missing or placeholder.",
        "budget_blocked": "External budget or caps block escalation for this run.",
        "idle_no_job_scoped": "No job_id in query — last-call trace not shown; add ?job_id= for a specific run.",
        "no_external_api_call_in_trace": "External is enabled, but this run’s trace shows no OpenAI call (no escalation, or local-only route).",
        "external_api_call_failed": "The last external API call in trace failed; see router decision / provider for details.",
    }
    escalation_summary_v1 = _escalation_summary_map.get(primary_code, f"State code: {primary_code}")

    cap = max(0.0, float(cfg.get("max_estimated_cost_usd_per_run") or 0.0))
    budget_cap_display_v1 = f"${cap:.2f}" if cap > 0 else "Not set"
    run_cost_usd_v1 = round(float(est_usd), 4)
    run_cost_display_v1 = f"${run_cost_usd_v1:.2f}"
    funding_account_balance_v1 = "Unknown"

    if not ext_effective or operator_blocks or not key_ok or cap <= 0:
        external_api_balance_status_v1 = "Unknown"
    elif budget_label == "exhausted" or "budget_exhausted" in br:
        external_api_balance_status_v1 = "Exhausted"
    elif budget_label == "low" or (cap > 0 and est_usd >= 0.7 * cap) or "low" in bud.lower():
        external_api_balance_status_v1 = "Low"
    else:
        external_api_balance_status_v1 = "Available"

    operator_block_code_v1: str | None
    if ollama_err:
        operator_block_code_v1 = None
    elif last_call == "failed" and ext_effective and key_ok:
        operator_block_code_v1 = "provider_unavailable"
    elif operator_blocks or not ext_effective:
        operator_block_code_v1 = "api_disabled"
    elif not key_ok and ext_effective:
        operator_block_code_v1 = "missing_key"
    elif budget_label == "exhausted" and ext_effective:
        operator_block_code_v1 = "budget_exceeded"
    elif primary_code == "no_external_api_call_in_trace":
        operator_block_code_v1 = "no_escalation_reason"
    else:
        operator_block_code_v1 = None

    last_external_call_result_v1 = (
        "Success" if last_call == "success" else ("Failed" if last_call == "failed" else "Not called")
    )

    local_model_label = "error" if ollama_err else "loaded"
    router_label = "disabled" if not router_on else "active"
    if ollama_err and router_on:
        router_label = "error"

    if ext_health == "operator_blocked":
        ext_line = "Ext op off"
    elif ext_health == "router_config_off":
        ext_line = "Ext off in config"
    elif ext_health == "missing_key":
        ext_line = "Ext need key"
    else:
        ext_line = "Ext path OK"

    trace_bits: list[str] = [local_model_label, f"Router {router_label}", ext_line]
    if jid:
        trace_bits.append(f"ext call: {last_call}")
    else:
        trace_bits.append("trace: add job_id")
    tile_detail_v1 = " · ".join(trace_bits)

    color = "amber"
    headline = "Idle"
    if not router_on:
        color = "blue"
        headline = "Router off"
    elif ollama_err:
        color = "red"
        headline = "Fault"
    elif operator_blocks:
        color = "amber"
        headline = "External off (operator)"
    elif not ext_effective:
        color = "amber"
        headline = "Local route"
    elif not key_ok:
        color = "red"
        headline = "Key missing"
    elif jid and last_call == "failed" and ext_effective and key_ok:
        color = "red"
        headline = "Fault"
    elif budget_label == "exhausted" and ext_effective:
        color = "red"
        headline = "Budget blocked"
    elif not jid and ext_effective and key_ok and not ollama_err and last_call != "failed":
        color = "blue"
        headline = "Idle"
    elif ext_effective and key_ok and not ollama_err and last_call != "failed" and budget_label != "exhausted":
        if external_api_balance_status_v1 == "Available":
            color = "green"
            headline = "Active"
        else:
            color = "amber"
            headline = "Active"
    else:
        color = "amber"
        headline = "Degraded"

    return {
        "ok": True,
        "schema": SCHEMA_SNAPSHOT,
        "refreshed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "job_id_scoped": jid or None,
        "tile_color_v1": color,
        "status_headline_v1": headline,
        "operator_external_api_gateway_allows_v1": not operator_blocks,
        "escalation_summary_v1": escalation_summary_v1,
        "primary_escalation_code_v1": primary_code,
        "add_funds_billing_url_v1": ADD_FUNDS_BILLING_URL_V1,
        "fields_v1": {
            "status": headline,
            "local_model_status": "error" if ollama_err else "loaded",
            "router_026ai_status": router_label,
            "external_api_gateway": "disabled" if operator_blocks else "enabled",
            "external_api_health": ext_health,
            "external_api_enabled_effective_v1": ext_effective,
            "funding_account_balance_v1": funding_account_balance_v1,
            "external_api_balance_status_v1": external_api_balance_status_v1,
            "run_cost_usd_v1": run_cost_usd_v1,
            "run_cost_display_v1": run_cost_display_v1,
            "budget_cap_usd_v1": cap if cap > 0 else None,
            "budget_cap_display_v1": budget_cap_display_v1,
            "api_budget_status": budget_label,
            "last_external_call": last_call,
            "last_external_call_result_v1": last_external_call_result_v1,
            "operator_block_code_v1": operator_block_code_v1,
            "funding_note_v1": (
                "OpenAI account balance is not queried by this server (use Add funds link). "
                "Run cost and cap are from trace + router config."
            ),
            "tile_detail_v1": tile_detail_v1,
            "tokens_current_run_v1": {"input": total_in, "output": total_out, "estimated_cost_usd_v1": round(est_usd, 6)},
            "block_reasons_v1": br,
        },
        "runtime_signals_v1": {
            "reasoning_router_config_effective": {
                "router_enabled": router_on,
                "external_api_enabled_effective": ext_effective,
            },
            "local_ollama_probe": {"error": ollama_err, "base_url": base_url, "model": model},
            "openai_key_configured": key_ok,
            "last_reasoning_router_decision_v1": last_dec,
        },
    }


__all__ = [
    "ADD_FUNDS_BILLING_URL_V1",
    "SCHEMA_PREFS",
    "SCHEMA_SNAPSHOT",
    "get_reasoning_model_operator_snapshot_v1",
    "write_operator_external_api_gateway_enabled_v1",
]
