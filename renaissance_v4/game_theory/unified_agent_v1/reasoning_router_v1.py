"""
GT_DIRECTIVE_026AI — Hybrid local / external reasoning router (advisory only; engine remains authority).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from typing import Any

from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import merge_unified_agent_router_fault_nodes_v1
from renaissance_v4.game_theory.unified_agent_v1.external_api_l1_v1 import finalize_router_decision_addendum_v1
from renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 import call_openai_responses_v1
from renaissance_v4.game_theory.unified_agent_v1.reasoning_cost_governor_v1 import ReasoningCostGovernorV1
from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 import load_reasoning_router_config_v1

SCHEMA_DECISION = "reasoning_router_decision_v1"
SCHEMA_REVIEW = "external_reasoning_review_v1"
CONTRACT_VERSION = 1

FINAL_ROUTES = (
    "local_only",
    "external_review",
    "external_blocked_budget",
    "external_blocked_config",
    "external_blocked_missing_key",
    "external_failed_fallback_local",
)

ESCALATION_CODES = (
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

BLOCKER_CODES = (
    "external_disabled_v1",
    "missing_api_key_v1",
    "insufficient_funds_v1",
    "quota_exceeded_v1",
    "rate_limited_v1",
    "provider_unavailable_v1",
    "budget_exceeded_v1",
    "token_limit_exceeded_v1",
    "provider_error_v1",
    "schema_validation_failed_v1",
    "no_escalation_reason_v1",
)


def _digest_v1(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _external_reasoning_json_schema_v1() -> dict[str, Any]:
    # Strict JSON schema for OpenAI Responses API (all properties required for strict mode).
    return {
        "type": "object",
        "properties": {
            "schema": {"type": "string"},
            "contract_version": {"type": "integer"},
            "review_model_v1": {"type": "string"},
            "review_summary_v1": {"type": "string"},
            "disagreement_with_local_v1": {"type": "boolean"},
            "suggested_action_v1": {"type": "string"},
            "suggested_confidence_v1": {"type": "number"},
            "identified_risks_v1": {"type": "array", "items": {"type": "string"}},
            "memory_assessment_v1": {"type": "string"},
            "indicator_assessment_v1": {"type": "string"},
            "schema_valid_v1": {"type": "boolean"},
            "validator_errors_v1": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "schema",
            "contract_version",
            "review_model_v1",
            "review_summary_v1",
            "disagreement_with_local_v1",
            "suggested_action_v1",
            "suggested_confidence_v1",
            "identified_risks_v1",
            "memory_assessment_v1",
            "indicator_assessment_v1",
            "schema_valid_v1",
            "validator_errors_v1",
        ],
        "additionalProperties": False,
    }


def validate_external_reasoning_review_v1(doc: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["external_reasoning_review must be a dict"]
    if str(doc.get("schema") or "") != SCHEMA_REVIEW:
        errs.append("schema must be external_reasoning_review_v1")
    if int(doc.get("contract_version") or 0) != CONTRACT_VERSION:
        errs.append("contract_version mismatch")
    if not str(doc.get("review_summary_v1") or "").strip():
        errs.append("review_summary_v1 required")
    return errs


def build_compact_external_payload_v1(
    *,
    entry_reasoning: dict[str, Any],
    retrieved: list[dict[str, Any]] | None,
    max_memory_records: int = 3,
) -> dict[str, Any]:
    """Bounded payload only — no full logs, scorecard, or raw trace."""
    ictx = entry_reasoning.get("indicator_context_eval_v1")
    mctx = entry_reasoning.get("memory_context_eval_v1")
    poe = entry_reasoning.get("prior_outcome_eval_v1")
    risk = entry_reasoning.get("risk_inputs_v1")
    ds = entry_reasoning.get("decision_synthesis_v1")
    rlist = list(retrieved or [])
    rlist.sort(
        key=lambda r: float((r or {}).get("relevance_v1", 0) or 0) if isinstance(r, dict) else 0.0,
        reverse=True,
    )
    topm = rlist[: max(0, int(max_memory_records))]

    return {
        "schema": "external_reasoning_compact_payload_v1",
        "indicator_digest": _digest_v1(ictx) if isinstance(ictx, dict) else None,
        "indicator_context_summary": {
            "rsi_state": (ictx or {}).get("rsi_state") if isinstance(ictx, dict) else None,
            "ema_trend": (ictx or {}).get("ema_trend") if isinstance(ictx, dict) else None,
        }
        if isinstance(ictx, dict)
        else {},
        "memory_context_summary": {
            "aggregate_memory_effect_v1": (mctx or {}).get("aggregate_memory_effect_v1")
            if isinstance(mctx, dict)
            else None,
        }
        if isinstance(mctx, dict)
        else {},
        "top_memory_record_digests_v1": [
            {
                "record_id": str((x or {}).get("record_id", ""))[:200],
                "digest": _digest_v1({k: v for k, v in (x or {}).items() if k in ("record_id", "candle_timeframe_minutes", "referee_outcome_subset")})
                if isinstance(x, dict)
                else "na",
            }
            for x in topm
        ],
        "prior_outcome_summary": {
            "prior_outcome_confidence_delta_v1": (poe or {}).get("prior_outcome_confidence_delta_v1")
            if isinstance(poe, dict)
            else None,
        }
        if isinstance(poe, dict)
        else {},
        "risk_inputs": risk if isinstance(risk, dict) else {},
        "decision_synthesis": ds if isinstance(ds, dict) else {},
        "local_reasoning_summary": {
            "confidence_01": entry_reasoning.get("confidence_01"),
            "confidence_band": entry_reasoning.get("confidence_band"),
        },
    }


def collect_escalation_reason_codes_v1(
    *,
    entry_reasoning: dict[str, Any],
    config: dict[str, Any],
    operator_forced_audit: bool = False,
    baseline_action: str | None = None,
    trade_notional_usd: float | None = None,
    high_value_threshold_usd: float = 10_000.0,
    rng: random.Random | None = None,
) -> list[str]:
    out: list[str] = []
    en = set(str(x) for x in (config.get("enabled_escalation_reasons") or ESCALATION_CODES))

    conf = float(entry_reasoning.get("confidence_01") or 0.0)
    thr = float(config.get("low_confidence_threshold") or 0.35)
    if "low_confidence_v1" in en and conf < thr:
        out.append("low_confidence_v1")

    ictx = entry_reasoning.get("indicator_context_eval_v1")
    mctx = entry_reasoning.get("memory_context_eval_v1")
    mclass = str((mctx or {}).get("aggregate_memory_effect_v1") or "") if isinstance(mctx, dict) else ""
    if "memory_conflict_v1" in en and mclass == "conflict":
        out.append("memory_conflict_v1")

    if "indicator_conflict_v1" in en and isinstance(ictx, dict):
        # Heuristic: conflicting momentum vs label from support_flags
        fl = ictx.get("support_flags_v1") or {}
        if bool(fl.get("long")) and bool(fl.get("short")):
            out.append("indicator_conflict_v1")
        rs = str(ictx.get("rsi_state") or "")
        em = str(ictx.get("ema_trend") or "")
        if "exhaustion" in rs and "bull" in em:
            if "indicator_conflict_v1" not in out:
                out.append("indicator_conflict_v1")

    ds = entry_reasoning.get("decision_synthesis_v1") or {}
    act = str((ds or {}).get("action") or "")
    rdef = bool(entry_reasoning.get("risk_defined_v1"))
    if "risk_conflict_v1" in en and act in ("enter_long", "enter_short") and not rdef:
        out.append("risk_conflict_v1")

    if "operator_forced_audit_v1" in en and operator_forced_audit:
        out.append("operator_forced_audit_v1")

    if (
        "high_value_opportunity_v1" in en
        and trade_notional_usd is not None
        and float(trade_notional_usd) >= high_value_threshold_usd
    ):
        out.append("high_value_opportunity_v1")

    if (
        "student_vs_baseline_disagreement_v1" in en
        and baseline_action
        and str(baseline_action).strip()
        and str(baseline_action).strip() != str(act)
    ):
        out.append("student_vs_baseline_disagreement_v1")

    rate = float(config.get("random_audit_sample_rate") or 0.0)
    r = rng or random.Random()
    if "random_audit_sample_v1" in en and rate > 0.0 and r.random() < rate:
        out.append("random_audit_sample_v1")

    return sorted({str(x) for x in out})


def _empty_decision(
    *,
    final_route: str,
    blockers: list[str],
    reasons: list[str],
    local_url: str,
    local_m: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_DECISION,
        "contract_version": CONTRACT_VERSION,
        "router_enabled_v1": True,
        "external_api_enabled_v1": False,
        "local_model_requested_v1": local_m,
        "local_model_resolved_v1": local_m,
        "local_base_url_used_v1": local_url,
        "external_provider_v1": "openai",
        "external_model_requested_v1": "gpt-5.5",
        "external_model_resolved_v1": None,
        "escalation_decision_v1": "no_escalation" if not reasons else "escalation_requested",
        "escalation_reason_codes_v1": reasons,
        "escalation_blockers_v1": blockers,
        "budget_status_v1": "ok",
        "api_call_allowed_v1": False,
        "final_route_v1": final_route,
    }


def apply_unified_reasoning_router_v1(
    *,
    entry_reasoning_eval_v1: dict[str, Any],
    base_fault_map: dict[str, Any],
    config: dict[str, Any] | None = None,
    config_path: str | None = None,
    job_id: str = "",
    fingerprint: str | None = None,
    student_decision_packet: dict[str, Any] | None = None,
    retrieved_student_experience: list[dict[str, Any]] | None = None,
    run_candle_timeframe_minutes: int = 5,
    operator_forced_audit: bool = False,
    baseline_action: str | None = None,
    trade_notional_usd: float | None = None,
    seed: int | None = None,
    scenario_id: str | None = None,
    trade_id: str | None = None,
) -> dict[str, Any]:
    """
    After deterministic entry reasoning is built, evaluate router + optional external review.
    Does **not** change ``decision_synthesis_v1``; attaches advisory + visibility fields only.
    """
    t0 = time.perf_counter()
    cfg = config if isinstance(config, dict) else load_reasoning_router_config_v1(config_path)
    rng = random.Random(int(seed) if seed is not None else hash((job_id, fingerprint) or 0) & 0xFFFF)

    from renaissance_v4.game_theory.exam_run_contract_v1 import STUDENT_LLM_APPROVED_MODEL_V1
    from renaissance_v4.game_theory.learning_trace_events_v1 import learning_trace_memory_sink_active_v1
    from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
        emit_external_reasoning_review_v1,
        emit_reasoning_cost_governor_v1,
        emit_reasoning_router_decision_v1,
    )
    from renaissance_v4.game_theory.ollama_role_routing_v1 import student_ollama_base_url_v1

    _emit_router_trace = bool(str(job_id or "").strip()) or learning_trace_memory_sink_active_v1()

    local_m = str(cfg.get("local_llm_model") or STUDENT_LLM_APPROVED_MODEL_V1)
    local_url = str(cfg.get("local_ollama_base_url") or student_ollama_base_url_v1())

    if not bool(cfg.get("router_enabled", True)):
        dec = _empty_decision(
            final_route="local_only",
            blockers=["external_disabled_v1"],
            reasons=[],
            local_url=local_url,
            local_m=local_m,
        )
        dec["router_enabled_v1"] = False
        finalize_router_decision_addendum_v1(
            dec,
            policy_permitted_http_call=False,
            http_attempted=False,
            review_accepted=False,
            blockers=["external_disabled_v1"],
            router_final_route="local_only",
            api_failure_detail_sanitized=None,
        )
        fm = merge_unified_agent_router_fault_nodes_v1(
            base_fault_map,
            decision_node=dec,
            governor_snapshot={"schema": "reasoning_cost_governor_snapshot_v1", "blocked": True, "note": "router disabled"},
            review_obj=None,
        )
        gov_snap = {"schema": "reasoning_cost_governor_snapshot_v1", "blocked": True, "note": "router disabled in config"}
        call_record_off = {
            "api_call_attempted_v1": False,
            "api_call_allowed_v1": False,
            "api_call_reason_codes_v1": [],
            "input_tokens_v1": 0,
            "output_tokens_v1": 0,
            "total_tokens_v1": 0,
            "estimated_cost_usd_v1": 0.0,
            "latency_ms_v1": 0.0,
            "provider_v1": "openai",
            "model_requested_v1": str(cfg.get("external_model") or "gpt-5.5"),
            "model_resolved_v1": None,
            "response_status_v1": "not_called",
        }
        if _emit_router_trace:
            emit_reasoning_router_decision_v1(
                job_id=job_id,
                fingerprint=fingerprint,
                decision=dec,
                call_record=call_record_off,
                scenario_id=scenario_id,
                trade_id=trade_id,
            )
            emit_reasoning_cost_governor_v1(
                job_id=job_id,
                fingerprint=fingerprint,
                snapshot=gov_snap,
                call_record=call_record_off,
                scenario_id=scenario_id,
                trade_id=trade_id,
            )
        return {
            "entry_reasoning_eval_v1": _attach_to_ere(entry_reasoning_eval_v1, dec, None, None),
            "student_reasoning_fault_map_v1": fm,
            "reasoning_router_decision_v1": dec,
            "external_reasoning_review_v1": None,
            "reasoning_cost_governor_snapshot_v1": None,
            "ms_elapsed": round((time.perf_counter() - t0) * 1000.0, 3),
        }

    reasons = collect_escalation_reason_codes_v1(
        entry_reasoning=entry_reasoning_eval_v1,
        config=cfg,
        operator_forced_audit=operator_forced_audit,
        baseline_action=baseline_action,
        trade_notional_usd=trade_notional_usd,
        rng=rng,
    )
    ext_enabled = bool(cfg.get("external_api_enabled"))
    api_var = str(cfg.get("api_key_env_var") or "OPENAI_API_KEY")
    import os

    has_key = bool((os.environ.get(api_var) or "").strip())
    ext_model = str(cfg.get("external_model") or "gpt-5.5")
    blockers: list[str] = []
    if not ext_enabled:
        blockers.append("external_disabled_v1")
    if ext_enabled and not has_key:
        blockers.append("missing_api_key_v1")
    if not reasons:
        if ext_enabled and not blockers:
            blockers.append("no_escalation_reason_v1")

    def _ic(k: str, default: int) -> int:
        v = cfg.get(k)
        if v is None:
            return default
        return int(v)

    def _fc(k: str, default: float) -> float:
        v = cfg.get(k)
        if v is None:
            return default
        return float(v)

    gov = ReasoningCostGovernorV1(
        max_external_calls_per_run=max(0, _ic("max_external_calls_per_run", 1)),
        max_external_calls_per_trade=max(0, _ic("max_external_calls_per_trade", 1)),
        max_input_tokens_per_call=max(1, _ic("max_input_tokens_per_call", 8000)),
        max_output_tokens_per_call=max(1, _ic("max_output_tokens_per_call", 2000)),
        max_total_tokens_per_run=max(1, _ic("max_total_tokens_per_run", 24_000)),
        max_estimated_cost_usd_per_run=max(0.0, _fc("max_estimated_cost_usd_per_run", 0.5)),
    )

    compact = build_compact_external_payload_v1(
        entry_reasoning=entry_reasoning_eval_v1,
        retrieved=retrieved_student_experience,
        max_memory_records=int(cfg.get("max_memory_records_for_external") or 3),
    )
    est_in = min(int(len(json.dumps(compact)) / 4) + 64, int(cfg.get("max_input_tokens_per_call") or 8000))
    est_out = int(cfg.get("max_output_tokens_per_call") or 2000)
    can_budget, bblock, _ = gov.can_attempt_external(estimated_input_tokens=est_in, estimated_output_cap=est_out)
    if ext_enabled and reasons and not can_budget and bblock and bblock not in blockers:
        blockers.append(bblock)

    final_route: str = "local_only"
    if ext_enabled and has_key and reasons and not any(
        x in blockers
        for x in ("external_disabled_v1", "missing_api_key_v1", "no_escalation_reason_v1", "budget_exceeded_v1", "token_limit_exceeded_v1")
    ) and can_budget:
        final_route = "external_review"
    elif ext_enabled and not has_key:
        final_route = "external_blocked_missing_key"
    elif not ext_enabled:
        final_route = "local_only" if not reasons else "external_blocked_config"
    elif not reasons:
        final_route = "local_only"
    elif "budget_exceeded_v1" in blockers or "token_limit_exceeded_v1" in blockers:
        final_route = "external_blocked_budget"
    elif "no_escalation_reason_v1" in blockers:
        final_route = "local_only"

    review_obj: dict[str, Any] | None = None
    call_record: dict[str, Any] | None = None
    api_call_allowed_flag = final_route == "external_review"
    http_executed = False
    api_failure_detail: str | None = None
    router_wants_external = bool(api_call_allowed_flag)

    if api_call_allowed_flag:
        http_executed = True
        system_inst = (
            "You are an external reviewer. Output one JSON object matching the schema. "
            "You must not assert execution authority; the host engine is authoritative."
        )
        user_txt = json.dumps(compact, ensure_ascii=False)[: 120_000]
        t_call = time.perf_counter()
        res = call_openai_responses_v1(
            model_requested=ext_model,
            system_instruction=system_inst,
            user_text=user_txt,
            api_key_env_var=api_var,
            response_json_schema=_external_reasoning_json_schema_v1(),
        )
        lat = (time.perf_counter() - t_call) * 1000.0
        if not res.get("ok"):
            api_failure_detail = str(res.get("error") or "provider_error")[:2000]
            fb = res.get("failure_blocker_v1")
            if isinstance(fb, str) and fb.strip():
                if str(fb).strip() not in blockers:
                    blockers.append(str(fb).strip())
            else:
                blockers.append("provider_error_v1")
        call_record = {
            "api_call_attempted_v1": True,
            "api_call_allowed_v1": True,
            "api_call_reason_codes_v1": list(reasons),
            "input_tokens_v1": int(res.get("input_tokens") or 0),
            "output_tokens_v1": int(res.get("output_tokens") or 0),
            "total_tokens_v1": int(res.get("total_tokens") or 0),
            "estimated_cost_usd_v1": round(float(res.get("input_tokens") or 0) * 2e-6 + float(res.get("output_tokens") or 0) * 1e-5, 8),
            "latency_ms_v1": float(res.get("latency_ms") or lat),
            "provider_v1": "openai",
            "model_requested_v1": ext_model,
            "model_resolved_v1": res.get("model_resolved"),
            "response_status_v1": str(res.get("response_status") or "unknown"),
        }
        if not res.get("ok"):
            call_record["validator_status_v1"] = "rejected"
            call_record["error"] = res.get("error")
        gov.record_external_result_v1(
            input_tokens=int(res.get("input_tokens") or 0),
            output_tokens=int(res.get("output_tokens") or 0),
            total_tokens=int(res.get("total_tokens") or 0),
            estimated_cost_usd=float(call_record["estimated_cost_usd_v1"]),
            record=call_record,
        )
        parsed = res.get("parsed_json")
        if not res.get("ok") or not isinstance(parsed, dict):
            final_route = "external_failed_fallback_local"
            call_record["validator_status_v1"] = "rejected"
            if res.get("ok") and not isinstance(parsed, dict):
                blockers = list({*blockers, "schema_validation_failed_v1"})
                api_failure_detail = api_failure_detail or "response_not_valid_json_object"
        else:
            pj = {
                "schema": SCHEMA_REVIEW,
                "contract_version": CONTRACT_VERSION,
                "review_model_v1": str(res.get("model_resolved") or ext_model),
                "review_summary_v1": str(parsed.get("review_summary_v1") or parsed.get("review_summary", "")),
                "disagreement_with_local_v1": bool(parsed.get("disagreement_with_local_v1", False)),
                "suggested_action_v1": str(parsed.get("suggested_action_v1") or "no_trade"),
                "suggested_confidence_v1": float(parsed.get("suggested_confidence_v1") or 0.0),
                "identified_risks_v1": list(parsed.get("identified_risks_v1") or []),
                "memory_assessment_v1": str(parsed.get("memory_assessment_v1") or ""),
                "indicator_assessment_v1": str(parsed.get("indicator_assessment_v1") or ""),
                "schema_valid_v1": bool(parsed.get("schema_valid_v1", True)),
                "validator_errors_v1": [str(x) for x in (parsed.get("validator_errors_v1") or [])][:32],
            }
            val_errs = validate_external_reasoning_review_v1(pj)
            if val_errs:
                pj["schema_valid_v1"] = False
                pj["validator_errors_v1"] = val_errs
                call_record["validator_status_v1"] = "rejected"
                final_route = "external_failed_fallback_local"
                blockers = list({*blockers, "schema_validation_failed_v1"})
                api_failure_detail = "; ".join(val_errs)[:2000]
            else:
                call_record["validator_status_v1"] = "accepted"
                review_obj = pj
    else:
        call_record = {
            "api_call_attempted_v1": False,
            "api_call_allowed_v1": False,
            "api_call_reason_codes_v1": [],
            "input_tokens_v1": 0,
            "output_tokens_v1": 0,
            "total_tokens_v1": 0,
            "estimated_cost_usd_v1": 0.0,
            "latency_ms_v1": 0.0,
            "provider_v1": "openai",
            "model_requested_v1": ext_model,
            "model_resolved_v1": None,
            "response_status_v1": "not_called",
        }

    decision: dict[str, Any] = {
        "schema": SCHEMA_DECISION,
        "contract_version": CONTRACT_VERSION,
        "router_enabled_v1": True,
        "external_api_enabled_v1": ext_enabled,
        "local_model_requested_v1": local_m,
        "local_model_resolved_v1": local_m,
        "local_base_url_used_v1": local_url,
        "external_provider_v1": "openai",
        "external_model_requested_v1": ext_model,
        "external_model_resolved_v1": (call_record or {}).get("model_resolved_v1")
        if isinstance(call_record, dict)
        else None,
        "escalation_decision_v1": "escalation_requested" if reasons else "no_escalation",
        "escalation_reason_codes_v1": reasons,
        "escalation_blockers_v1": sorted(set(blockers)),
        "budget_status_v1": "exhausted" if "budget_exceeded_v1" in blockers or "token_limit_exceeded_v1" in blockers else "ok",
        "api_call_succeeded_v1": bool(
            review_obj is not None and str((call_record or {}).get("validator_status_v1") or "") == "accepted"
        ),
        "final_route_v1": final_route,
    }
    finalize_router_decision_addendum_v1(
        decision,
        policy_permitted_http_call=router_wants_external,
        http_attempted=http_executed,
        review_accepted=review_obj is not None
        and str((call_record or {}).get("validator_status_v1") or "") == "accepted",
        blockers=list(blockers),
        router_final_route=final_route,
        api_failure_detail_sanitized=api_failure_detail,
    )
    decision["escalation_blockers_v1"] = sorted(set(blockers))

    if _emit_router_trace:
        emit_reasoning_router_decision_v1(
            job_id=job_id,
            fingerprint=fingerprint,
            decision=decision,
            call_record=call_record,
            scenario_id=scenario_id,
            trade_id=trade_id,
        )
        emit_reasoning_cost_governor_v1(
            job_id=job_id,
            fingerprint=fingerprint,
            snapshot=gov.to_snapshot_v1(),
            call_record=call_record,
            scenario_id=scenario_id,
            trade_id=trade_id,
        )
        if review_obj:
            emit_external_reasoning_review_v1(job_id=job_id, fingerprint=fingerprint, review=review_obj)

    fm = merge_unified_agent_router_fault_nodes_v1(
        base_fault_map,
        decision_node=decision,
        governor_snapshot=gov.to_snapshot_v1() if call_record else {"schema": "reasoning_cost_governor_snapshot_v1", "no_call": True},
        review_obj=review_obj,
    )
    ere2 = _attach_to_ere(entry_reasoning_eval_v1, decision, review_obj, call_record)

    if review_obj and review_obj.get("disagreement_with_local_v1"):
        # Deterministic path wins — advisory only; record influence flag without changing action.
        ere2["router_external_influence_v1"] = "advisory_no_execution_authority"

    return {
        "entry_reasoning_eval_v1": ere2,
        "student_reasoning_fault_map_v1": fm,
        "reasoning_router_decision_v1": decision,
        "external_reasoning_review_v1": review_obj,
        "reasoning_cost_governor_snapshot_v1": gov.to_snapshot_v1(),
        "ms_elapsed": round((time.perf_counter() - t0) * 1000.0, 3),
    }


def _attach_to_ere(
    ere: dict[str, Any],
    decision: dict[str, Any] | None,
    review: dict[str, Any] | None,
    call_rec: dict[str, Any] | None,
) -> dict[str, Any]:
    out = json.loads(json.dumps(ere)) if isinstance(ere, dict) else {}
    if decision:
        out["reasoning_router_decision_v1"] = decision
    if review:
        out["external_reasoning_review_v1"] = review
    if call_rec:
        out["external_api_call_ledger_v1"] = {k: v for k, v in call_rec.items() if "key" not in k.lower() and "api_key" not in k.lower()}
    return out
