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

    ext_health = "unavailable"
    if operator_blocks:
        ext_health = "blocked"
    elif not ext_effective:
        ext_health = "disabled"
    elif not key_ok:
        ext_health = "error"
    else:
        ext_health = "available"

    last_call = "not_called"
    last_dec: dict[str, Any] | None = None
    gov_last: dict[str, Any] | None = None
    total_in = 0
    total_out = 0
    est_usd = 0.0
    jid = (job_id or "").strip()
    if jid:
        evs = read_learning_trace_events_for_job_v1(jid)
        last_dec, gov_last = _last_router_and_governor_from_events(evs)
        for ev in evs or []:
            if str(ev.get("stage") or "") != "reasoning_router_decision_v1":
                continue
            ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
            cr = ep.get("call_ledger_sanitized_v1")
            if isinstance(cr, dict):
                total_in += int(float(cr.get("input_tokens_v1") or 0) or 0)
                total_out += int(float(cr.get("output_tokens_v1") or 0) or 0)
                est_usd += float(cr.get("estimated_cost_usd_v1") or 0) or 0.0
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
    if router_on and not operator_blocks and not key_ok:
        br.append("missing_api_key")
    if last_dec and isinstance(last_dec.get("escalation_blockers_v1"), list):
        br.extend([str(x) for x in (last_dec.get("escalation_blockers_v1") or [])[:6]])

    bud = str((last_dec or {}).get("budget_status_v1") or (gov_last or {}).get("budget_status_v1") or "ok")
    if bud in ("exhausted",):
        budget_label = "exhausted"
    elif bud in ("ok", "sufficient"):
        budget_label = "sufficient"
    else:
        budget_label = "low" if "low" in bud.lower() else bud

    color = "amber"
    headline = "Idle"
    if not router_on:
        color = "blue"
        headline = "Idle"
    elif ollama_err:
        color = "red"
        headline = "Fault"
    elif operator_blocks or (not ext_effective and ext_health in ("disabled", "blocked")):
        color = "amber"
        headline = "Local only" if not ext_effective else "Degraded"
    elif ext_health == "error":
        color = "red"
        headline = "Fault"
    elif ext_effective and key_ok and not ollama_err:
        color = "green"
        headline = "Active"
    else:
        color = "amber"
        headline = "Degraded"

    router_label = "disabled" if not router_on else "active"
    if ollama_err and router_on:
        router_label = "error"

    return {
        "ok": True,
        "schema": SCHEMA_SNAPSHOT,
        "refreshed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "job_id_scoped": jid or None,
        "tile_color_v1": color,
        "status_headline_v1": headline,
        "operator_external_api_gateway_allows_v1": not operator_blocks,
        "fields_v1": {
            "status": headline,
            "local_model_status": "error" if ollama_err else "loaded",
            "router_026ai_status": router_label,
            "external_api_gateway": "disabled" if operator_blocks else "enabled",
            "external_api_health": ext_health,
            "api_budget_status": budget_label,
            "last_external_call": last_call,
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
    "SCHEMA_PREFS",
    "SCHEMA_SNAPSHOT",
    "get_reasoning_model_operator_snapshot_v1",
    "write_operator_external_api_gateway_enabled_v1",
]
