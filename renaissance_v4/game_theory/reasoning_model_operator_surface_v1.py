"""
Operator-facing **Reasoning Model** health surface (unified Student stack: local model, 026AI router, external gateway).

* ``GET`` snapshot for ``/api/reasoning-model/status`` (runtime probes + optional ``job_id`` trace slice).
* Persists the **Allow External API** toggle; :func:`load_reasoning_router_config_v1` merges it as
  authoritative: off blocks external entirely; on forces **external_api_enabled** at runtime and overrides
  ``OPENAI_ESCALATION_ENABLED`` when the operator has not turned the gateway off.
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
from renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 import (
    host_secrets_file_has_plausible_openai_key_line_v1,
    host_secrets_path_openai_v1,
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
    ``allowed`` **True** = effective router config is merged with **external API enabled** (overrides
    ``OPENAI_ESCALATION_ENABLED=0`` and the static config default when false).

    ``allowed`` **False** = external API is **fully disabled**; the router will not use the external gateway
    under any condition (no other hidden file/env switch for “optional” use).
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
    """
    Must match :func:`_get_api_key` / OpenAI call path: process env first, then one-time read from
    ``BLACKBOX_OPENAI_ENV_FILE`` or default ``~/.blackbox_secrets/openai.env`` (see
    ``external_openai_adapter_v1``). The status tile must not show “missing key” when runtime calls
    would resolve a key.
    """
    from renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 import _get_api_key

    ev = str(cfg.get("api_key_env_var") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY"
    v = (_get_api_key(ev) or "").strip()
    return len(v) > 8 and not v.lower().startswith("sk-placeholder")


def _classify_openai_key_situation_v1(cfg: dict[str, Any], key_ok: bool) -> str:
    """
    Machine-readable key situation for the web process (no key material in API).

    * ``unavailable_to_web_process`` — host file has a plausible ``OPENAI_API_KEY=`` line but
      this process has no resolvable key in ``api_key_env_var`` (wrong var, permissions, or inject error).
    * ``missing_in_web_process`` — no key in the process and no such line in the host file (e.g. key only
      in an interactive shell, not in systemd/Flask).
    * ``invalid_or_placeholder`` — non-empty env value for ``api_key_env_var`` that fails the plausibility check.
    * ``ok`` — key usable for the adapter.
    """
    if key_ok:
        return "ok"
    ev = str(cfg.get("api_key_env_var") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY"
    env_raw = (os.environ.get(ev) or "").strip()
    if env_raw and not key_ok:
        return "invalid_or_placeholder"
    if host_secrets_file_has_plausible_openai_key_line_v1() and not key_ok and not env_raw:
        return "unavailable_to_web_process"
    return "missing_in_web_process"


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


def _operator_block_message_v1(
    operator_blocks: bool,
    ext_effective: bool,
    key_ok: bool,
    last_call: str,
    primary_code: str,
    ollama_err: Any,
    openai_key_situation: str = "ok",
) -> str | None:
    """One human sentence for tooltip only (not internal codes)."""
    if ollama_err:
        return "Local Ollama/model check failed. See local model line below."
    if last_call == "failed":
        return "The last OpenAI call failed. Check key, quota, and provider; see trace for the run."
    if operator_blocks:
        return "Allow External AI is off — escalation to OpenAI is blocked in operator settings."
    if not ext_effective and not operator_blocks:
        return "External API is not enabled in effective configuration (atypical: expected only if config bypassed load merge)."
    if not key_ok and ext_effective:
        if openai_key_situation == "unavailable_to_web_process":
            return (
                "A host OpenAI env file appears to have a key line, but this web process could not use it. "
                "Check api_key_env_var, BLACKBOX_OPENAI_ENV_FILE, and that the process user can read the file; "
                "a shell export does not apply to the Flask service without a service env file."
            )
        if openai_key_situation == "missing_in_web_process":
            return (
                "No OpenAI API key in this process (and no usable line in the default host file). "
                "Set OPENAI for the service user or add ~/.blackbox_secrets/openai.env; interactive shell is not enough."
            )
        if openai_key_situation == "invalid_or_placeholder":
            return "The API key in this process is missing, too short, or a placeholder. Replace it or use Allow External AI off."
        return "OpenAI key is not available to this process; turn off Allow External AI or fix the service environment."
    if primary_code == "budget_blocked":
        return "External API Blocked (Budget) — per-run cap or token limits."
    if primary_code == "no_external_api_call_in_trace":
        return "This run’s trace has no OpenAI call; the router may have stayed on the local model."
    return None


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
    openai_key_situation_v1 = _classify_openai_key_situation_v1(cfg, key_ok)

    # External path: operator “off” blocks; when not blocked, load merge forces external_api_enabled true.
    if operator_blocks:
        ext_health = "operator_blocked"
    elif not ext_effective:
        ext_health = "router_config_off"
    elif not key_ok:
        if openai_key_situation_v1 == "unavailable_to_web_process":
            ext_health = "openai_unavailable_to_web"
        elif openai_key_situation_v1 == "invalid_or_placeholder":
            ext_health = "openai_key_invalid"
        else:
            ext_health = "missing_key"
    else:
        ext_health = "available"

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
        if openai_key_situation_v1 == "unavailable_to_web_process":
            primary_code = "openai_unavailable_in_web_process"
        elif openai_key_situation_v1 == "invalid_or_placeholder":
            primary_code = "openai_key_invalid_in_web_process"
        elif openai_key_situation_v1 == "missing_in_web_process":
            primary_code = "openai_key_missing_in_web_process"
        else:
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
        "router_external_disabled": "External API is off in effective config (unusual if load merge runs; check for dict-only router config path).",
        "missing_openai_key": "Legacy code path for OpenAI key; see openai_key_missing_in_web_process and related codes.",
        "openai_unavailable_in_web_process": "Host file suggests OPENAI_API_KEY, but the web process has no resolvable key (service env, permissions, or wrong api_key_env_var).",
        "openai_key_invalid_in_web_process": "A value exists for the API key in this process, but it is not usable (placeholder or too short).",
        "openai_key_missing_in_web_process": "No OpenAI key in the web process and no plausible key line in the host file (shell-only key shows here).",
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
        if openai_key_situation_v1 == "unavailable_to_web_process":
            operator_block_code_v1 = "key_unavailable_to_web"
        elif openai_key_situation_v1 == "invalid_or_placeholder":
            operator_block_code_v1 = "key_invalid_in_env"
        else:
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

    # Proof of external path (no debug: no job_id, no "config" jargon in the primary string).
    # With load merge, external_api_enabled is true whenever the operator has not turned the gateway off.
    external_api_proof_state_v1: str
    external_api_proof_line_v1: str
    if ollama_err:
        external_api_proof_state_v1 = "not_connected"
        external_api_proof_line_v1 = "External API: Unavailable (local model error)"
    elif last_call == "success":
        external_api_proof_state_v1 = "connected"
        external_api_proof_line_v1 = "External API: Connected"
    elif operator_blocks:
        external_api_proof_state_v1 = "blocked"
        external_api_proof_line_v1 = "External API: Blocked (operator off)"
    elif not ext_effective:
        external_api_proof_state_v1 = "not_connected"
        external_api_proof_line_v1 = "External API: Not Configured"
    elif not key_ok and openai_key_situation_v1 == "unavailable_to_web_process":
        external_api_proof_state_v1 = "blocked"
        external_api_proof_line_v1 = "External API: Not available to web process"
    elif not key_ok and openai_key_situation_v1 == "missing_in_web_process":
        external_api_proof_state_v1 = "blocked"
        external_api_proof_line_v1 = "External API: Missing key in web process"
    elif not key_ok and openai_key_situation_v1 == "invalid_or_placeholder":
        external_api_proof_state_v1 = "blocked"
        external_api_proof_line_v1 = "External API: Blocked (invalid or placeholder key)"
    elif not key_ok:
        external_api_proof_state_v1 = "blocked"
        external_api_proof_line_v1 = "External API: Not available to web process"
    elif budget_label == "exhausted" and not operator_blocks:
        external_api_proof_state_v1 = "blocked"
        external_api_proof_line_v1 = "External API: Blocked (Budget)"
    elif last_call == "failed" and key_ok:
        external_api_proof_state_v1 = "not_connected"
        external_api_proof_line_v1 = "External API: Not Connected (call failed)"
    elif not router_on:
        external_api_proof_state_v1 = "idle"
        external_api_proof_line_v1 = "External API: Idle"
    elif not jid:
        external_api_proof_state_v1 = "enabled"
        external_api_proof_line_v1 = "External API: Enabled"
    else:
        external_api_proof_state_v1 = "ready_no_call"
        external_api_proof_line_v1 = "External API: Ready"

    local_display = "Error" if ollama_err else "Loaded"
    router_display = "Disabled" if router_label == "disabled" else ("Error" if router_label == "error" else "Active")

    if ollama_err:
        external_line_core = "Unavailable"
    elif external_api_proof_state_v1 == "connected":
        external_line_core = "Connected"
    elif external_api_proof_state_v1 == "enabled":
        external_line_core = "Enabled"
    elif external_api_proof_state_v1 == "ready_no_call":
        external_line_core = "Ready"
    elif external_api_proof_state_v1 == "blocked":
        if "Not available to web" in external_api_proof_line_v1:
            external_line_core = "Not available to web"
        elif "Missing key" in external_api_proof_line_v1:
            external_line_core = "No key in web process"
        elif "invalid or placeholder" in external_api_proof_line_v1:
            external_line_core = "Invalid key"
        else:
            external_line_core = "Blocked"
    elif external_api_proof_state_v1 == "not_connected":
        external_line_core = "Not connected" if last_call == "failed" else "Not Configured"
    else:
        external_line_core = "Idle"

    ui_core_lines_v1 = [
        f"Local model: {local_display}",
        f"Router: {router_display}",
        f"External API: {external_line_core}",
    ]
    tile_detail_v1 = " | ".join(ui_core_lines_v1)

    operator_block_message_v1 = _operator_block_message_v1(
        operator_blocks,
        ext_effective,
        key_ok,
        last_call,
        primary_code,
        ollama_err,
        openai_key_situation_v1,
    )

    if not router_on:
        headline_badge_v1 = "Router off"
    elif ollama_err:
        headline_badge_v1 = "Fault"
    elif ext_effective and not key_ok and openai_key_situation_v1 == "unavailable_to_web_process":
        headline_badge_v1 = "Degraded"
    elif ext_effective and not key_ok:
        headline_badge_v1 = "Fault"
    elif jid and last_call == "failed" and ext_effective and key_ok:
        headline_badge_v1 = "Fault"
    elif budget_label == "exhausted" and ext_effective:
        headline_badge_v1 = "Blocked"
    elif operator_blocks:
        headline_badge_v1 = "Blocked"
    elif not ext_effective:
        headline_badge_v1 = "Local route"
    elif not jid and ext_effective and key_ok and not ollama_err and last_call != "failed":
        headline_badge_v1 = "Idle"
    elif ext_effective and key_ok and not ollama_err:
        headline_badge_v1 = "External active"
    else:
        headline_badge_v1 = "Degraded"

    headline = headline_badge_v1
    if not router_on:
        color = "blue"
    elif ext_effective and not key_ok and openai_key_situation_v1 == "unavailable_to_web_process":
        color = "amber"
    elif ollama_err or (ext_effective and not key_ok) or (jid and last_call == "failed" and ext_effective and key_ok) or (budget_label == "exhausted" and ext_effective):
        color = "red"
    elif operator_blocks or not ext_effective:
        color = "amber"
    elif not jid and ext_effective and key_ok and not ollama_err and last_call != "failed":
        color = "blue"
    elif last_call == "success" and ext_effective and key_ok and not ollama_err and budget_label != "exhausted":
        color = "green"
    elif ext_effective and key_ok and not ollama_err and last_call != "failed" and budget_label != "exhausted":
        if external_api_balance_status_v1 == "Available":
            color = "green"
        else:
            color = "amber"
    else:
        color = "amber"

    return {
        "ok": True,
        "schema": SCHEMA_SNAPSHOT,
        "refreshed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "job_id_scoped": jid or None,
        "tile_color_v1": color,
        "status_headline_v1": headline,
        "headline_badge_v1": headline_badge_v1,
        "external_api_proof_line_v1": external_api_proof_line_v1,
        "operator_external_api_gateway_allows_v1": not operator_blocks,
        "escalation_summary_v1": escalation_summary_v1,
        "primary_escalation_code_v1": primary_code,
        "add_funds_billing_url_v1": ADD_FUNDS_BILLING_URL_V1,
        "fields_v1": {
            "status": headline,
            "headline_badge_v1": headline_badge_v1,
            "ui_core_lines_v1": ui_core_lines_v1,
            "external_api_proof_state_v1": external_api_proof_state_v1,
            "external_api_proof_line_v1": external_api_proof_line_v1,
            "local_model_status": "error" if ollama_err else "loaded",
            "local_model_label_display_v1": local_display,
            "router_026ai_status": router_label,
            "router_label_display_v1": router_display,
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
            "operator_block_message_v1": operator_block_message_v1,
            "funding_note_v1": (
                "OpenAI account balance is not queried on the server. Run cost and cap come from trace + config."
            ),
            "tile_detail_v1": tile_detail_v1,
            "tokens_current_run_v1": {"input": total_in, "output": total_out, "estimated_cost_usd_v1": round(est_usd, 6)},
            "openai_key_situation_v1": openai_key_situation_v1,
            "openai_secrets_path_v1": host_secrets_path_openai_v1(),
            "openai_secrets_plausible_key_line_in_file": host_secrets_file_has_plausible_openai_key_line_v1(),
            "block_reasons_v1": br,
        },
        "runtime_signals_v1": {
            "reasoning_router_config_effective": {
                "router_enabled": router_on,
                "external_api_enabled_effective": ext_effective,
            },
            "local_ollama_probe": {"error": ollama_err, "base_url": base_url, "model": model},
            "openai_key_configured": key_ok,
            "openai_key_diagnostics_v1": {
                "key_resolved": key_ok,
                "situation": openai_key_situation_v1,
                "api_key_env_var": str(cfg.get("api_key_env_var") or "OPENAI_API_KEY"),
                "key_nonempty_in_process_environ": bool(
                    (os.environ.get(str(cfg.get("api_key_env_var") or "OPENAI_API_KEY").strip() or "OPENAI_API_KEY") or "").strip()
                ),
                "host_secrets_path": host_secrets_path_openai_v1(),
                "host_secrets_plausible_key_line": host_secrets_file_has_plausible_openai_key_line_v1(),
            },
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
