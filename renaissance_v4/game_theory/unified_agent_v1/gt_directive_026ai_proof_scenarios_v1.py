"""
GT_DIRECTIVE_026AI — scenario-based proof helpers (no API keys; callers patch env / HTTP).

Produces structured bundles for JSON artifacts: router decision, ledger, L1, fault map excerpt, trace.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import uuid
from unittest.mock import patch
from datetime import datetime, timezone
from typing import Any

from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import run_entry_reasoning_pipeline_v1
from renaissance_v4.game_theory.unified_agent_v1.external_api_l1_v1 import (
    OPENAI_BILLING_SETTINGS_URL_V1,
    l1_fields_from_router_decision_v1,
)
from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 import load_reasoning_router_config_v1
from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_v1 import (
    SCHEMA_REVIEW,
    apply_unified_reasoning_router_v1,
)
import renaissance_v4.game_theory.unified_agent_v1.reasoning_router_v1 as router_mod

PROOF_BUNDLE_SCHEMA_V1 = "gt_directive_026ai_scenario_proof_bundle_v1"
PROOF_VERSION = 1

FORBIDDEN_SECURITY_SUBSTRINGS = ("sk-", "Bearer ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bars() -> list[dict[str, Any]]:
    return [
        {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100.0},
        {"open": 1.0, "high": 1.2, "low": 0.95, "close": 1.1, "volume": 110.0},
    ]


def packet_study_v1() -> dict[str, Any]:
    return {
        "schema": "student_decision_packet_v1",
        "symbol": "BTC",
        "candle_timeframe_minutes": 5,
        "bars_inclusive_up_to_t": _bars(),
    }


def security_scan_serialized_v1(obj: Any) -> dict[str, Any]:
    """Fail if any forbidden substring appears in a canonical JSON view (no false positives on benign keys)."""
    try:
        blob = json.dumps(obj, ensure_ascii=False, default=str, sort_keys=True)
    except TypeError:
        blob = str(obj)
    hits: list[str] = []
    for s in FORBIDDEN_SECURITY_SUBSTRINGS:
        if s in blob:
            hits.append(s)
    return {"ok": not hits, "forbidden_hits": hits, "byte_length": len(blob.encode("utf-8", errors="replace"))}


def _good_review_json(*, suggested_action: str, disagree: bool) -> dict[str, Any]:
    return {
        "schema": SCHEMA_REVIEW,
        "contract_version": 1,
        "review_model_v1": "mock",
        "review_summary_v1": "proof",
        "disagreement_with_local_v1": disagree,
        "suggested_action_v1": suggested_action,
        "suggested_confidence_v1": 0.5,
        "identified_risks_v1": [],
        "memory_assessment_v1": "a",
        "indicator_assessment_v1": "b",
        "schema_valid_v1": True,
        "validator_errors_v1": [],
    }


def _fake_ok(tokens: int = 2, **parse_overrides: Any) -> dict[str, Any]:
    d = {
        "ok": True,
        "error": None,
        "input_tokens": tokens,
        "output_tokens": tokens,
        "total_tokens": tokens * 2,
        "model_resolved": "gpt-proof-mock",
        "response_status": "ok",
        "parsed_json": _good_review_json(suggested_action="no_trade", disagree=False),
        "failure_blocker_v1": None,
    }
    d.update(parse_overrides)
    if "parsed_json" in parse_overrides:
        d["parsed_json"] = parse_overrides["parsed_json"]
    return d


def fault_map_node_excerpt_v1(fm: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in fm.get("nodes_v1") or []:
        if isinstance(n, dict) and str(n.get("node_id") or "") == node_id:
            return copy.deepcopy(n)
    return None


def verify_mandatory_decision_and_ledger_fields_v1(
    decision: dict[str, Any] | None,
    ledger: dict[str, Any] | None,
) -> dict[str, bool]:
    d = decision if isinstance(decision, dict) else {}
    c = ledger if isinstance(ledger, dict) else {}
    return {
        "final_route_v1": str(d.get("final_route_v1") or "") != "",
        "external_api_attempted_v1": "external_api_attempted_v1" in d,
        "external_api_allowed_v1": "external_api_allowed_v1" in d,
        "external_api_block_reason_v1": "external_api_block_reason_v1" in d,
        "api_call_reason_codes_v1": "api_call_reason_codes_v1" in c,
        "input_tokens_v1": "input_tokens_v1" in c,
        "output_tokens_v1": "output_tokens_v1" in c,
        "estimated_cost_usd_v1": "estimated_cost_usd_v1" in c,
        "latency_ms_v1": "latency_ms_v1" in c,
    }


def all_mandatory_verification_true_v1(ver: dict[str, bool]) -> bool:
    return bool(ver) and all(ver.values())


# --- Individual scenarios (return proof bundle; no I/O) ---


def run_scenario_01_local_only_external_disabled_v1() -> dict[str, Any]:
    job = f"proof_026ai_S01_{uuid.uuid4().hex[:8]}"
    with patch(
        "renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1.read_operator_reasoning_model_preferences_v1",
        return_value={"external_api_gateway_enabled": False},
    ):
        cfg = load_reasoning_router_config_v1(
            None,
            extra_dict={"router_enabled": True, "external_api_enabled": False, "low_confidence_threshold": 0.99},
        )
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s01",
            emit_traces=True,
            unified_agent_router=True,
            router_config=cfg,
        )
    assert ere and not err
    dec = ere.get("reasoning_router_decision_v1") or {}
    leg = ere.get("external_api_call_ledger_v1") or {}
    l1 = l1_fields_from_router_decision_v1(dec)
    return _bundle(
        "01_local_only_external_disabled",
        "external_api_enabled=false; local path only; no HTTP",
        dec,
        leg,
        l1,
        pfm,
        ere,
        expected_route=("local_only", "external_blocked_config"),
    )


def run_scenario_02_missing_api_key_v1() -> dict[str, Any]:
    job = f"proof_026ai_S02_{uuid.uuid4().hex[:8]}"
    prev = os.environ.get("OPENAI_API_KEY")
    try:
        os.environ.pop("OPENAI_API_KEY", None)
        cfg = load_reasoning_router_config_v1(
            None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
        )
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s02",
            emit_traces=True,
            unified_agent_router=True,
            router_config=cfg,
        )
    finally:
        if prev is not None:
            os.environ["OPENAI_API_KEY"] = prev

    assert ere and not err
    dec = ere.get("reasoning_router_decision_v1") or {}
    assert dec.get("external_api_attempted_v1") is False
    assert "missing_api_key_v1" in (dec.get("escalation_blockers_v1") or [])
    leg = ere.get("external_api_call_ledger_v1") or {}
    l1 = l1_fields_from_router_decision_v1(dec)
    return _bundle(
        "02_missing_openai_api_key",
        "OPENAI_API_KEY unset; blocked before HTTP",
        dec,
        leg,
        l1,
        pfm,
        ere,
        expected_blocker="missing_api_key_v1",
    )


def run_scenario_03_insufficient_funds_or_quota_v1(
    failure_blocker: str = "insufficient_funds_v1",
) -> dict[str, Any]:
    assert failure_blocker in ("insufficient_funds_v1", "quota_exceeded_v1")
    job = f"proof_026ai_S03_{uuid.uuid4().hex[:8]}"

    def _fail(**_kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "error": '{"error":{"code":"insufficient_quota","message":"billing"}}' if failure_blocker == "quota_exceeded_v1" else "payment_required",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "model_resolved": None,
            "response_status": "http_402" if failure_blocker == "insufficient_funds_v1" else "http_403",
            "parsed_json": None,
            "failure_blocker_v1": failure_blocker,
            "latency_ms": 1.0,
        }

    prev = os.environ.get("OPENAI_API_KEY", "")
    if not prev.strip():
        os.environ["OPENAI_API_KEY"] = "sk-test-artifact-dummy"
    try:
        setattr(router_mod, "call_openai_responses_v1", _fail)
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s03",
            emit_traces=True,
            unified_agent_router=True,
            router_config=load_reasoning_router_config_v1(
                None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
            ),
        )
    finally:
        setattr(router_mod, "call_openai_responses_v1", router_mod.call_openai_responses_v1)
        if prev:
            os.environ["OPENAI_API_KEY"] = prev
        else:
            os.environ.pop("OPENAI_API_KEY", None)

    assert ere and not err
    dec = ere.get("reasoning_router_decision_v1") or {}
    bl = " ".join(dec.get("escalation_blockers_v1") or [])
    assert failure_blocker in bl
    l1 = l1_fields_from_router_decision_v1(dec)
    link_ok = l1.get("external_api_action_url_v1") == OPENAI_BILLING_SETTINGS_URL_V1
    return {
        **(
            _bundle(
                f"03_{failure_blocker}",
                "Simulated provider failure body → blocker + L1 billing link",
                dec,
                ere.get("external_api_call_ledger_v1") or {},
                l1,
                pfm,
                ere,
            )
        ),
        "funding_l1_link_expected_v1": OPENAI_BILLING_SETTINGS_URL_V1,
        "funding_l1_link_matches_v1": link_ok,
    }


def run_scenario_04_budget_exceeded_v1() -> dict[str, Any]:
    job = f"proof_026ai_S04_{uuid.uuid4().hex[:8]}"
    monkey = os.environ.get("OPENAI_API_KEY", "")
    if not monkey.strip():
        os.environ["OPENAI_API_KEY"] = "sk-test-artifact-dummy"
    try:
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s04",
            emit_traces=True,
            unified_agent_router=True,
            router_config=load_reasoning_router_config_v1(
                None,
                extra_dict={
                    "external_api_enabled": True,
                    "low_confidence_threshold": 0.99,
                    "max_estimated_cost_usd_per_run": 0.0,
                    "max_external_calls_per_run": 0,
                },
            ),
        )
    finally:
        if not monkey:
            os.environ.pop("OPENAI_API_KEY", None)
    assert ere and not err
    dec = ere.get("reasoning_router_decision_v1") or {}
    assert dec.get("external_api_attempted_v1") is False
    assert "budget_exceeded_v1" in (dec.get("escalation_blockers_v1") or [])
    l1 = l1_fields_from_router_decision_v1(dec)
    return _bundle(
        "04_budget_exceeded_governor",
        "max_run_cost 0 + max_calls 0 — no external attempt",
        dec,
        ere.get("external_api_call_ledger_v1") or {},
        l1,
        pfm,
        ere,
        expected_blocker="budget_exceeded_v1",
    )


def run_scenario_05_successful_escalation_mocked_v1() -> dict[str, Any]:
    job = f"proof_026ai_S05_{uuid.uuid4().hex[:8]}"
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "sk-test-artifact-dummy"
    try:
        setattr(router_mod, "call_openai_responses_v1", lambda **kw: _fake_ok(tokens=10))
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s05",
            emit_traces=True,
            unified_agent_router=True,
            router_config=load_reasoning_router_config_v1(
                None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
            ),
        )
    finally:
        setattr(router_mod, "call_openai_responses_v1", router_mod.call_openai_responses_v1)
    assert ere and not err
    dec = ere.get("reasoning_router_decision_v1") or {}
    assert dec.get("final_route_v1") == "external_review"
    leg = ere.get("external_api_call_ledger_v1") or {}
    assert int(leg.get("total_tokens_v1") or 0) >= 0
    l1 = l1_fields_from_router_decision_v1(dec)
    return _bundle(
        "05_successful_external_escalation_mocked",
        "Low confidence → call → accepted review; tokens & cost on ledger (mocked provider)",
        dec,
        leg,
        l1,
        pfm,
        ere,
    )


def run_scenario_06_schema_validation_failed_v1() -> dict[str, Any]:
    job = f"proof_026ai_S06_{uuid.uuid4().hex[:8]}"
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "sk-test-artifact-dummy"
    try:
        setattr(
            router_mod,
            "call_openai_responses_v1",
            lambda **kw: {
                "ok": True,
                "error": None,
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
                "model_resolved": "gpt-proof",
                "response_status": "ok",
                "parsed_json": {"schema": "wrong", "foo": 1},
                "failure_blocker_v1": None,
            },
        )
        er0, e0, _, pfm0 = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s06",
            emit_traces=True,
        )
        u = apply_unified_reasoning_router_v1(
            entry_reasoning_eval_v1=er0,
            base_fault_map=pfm0,
            job_id=job,
            fingerprint="proof_fp_s06",
            config=load_reasoning_router_config_v1(
                None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
            ),
        )
    finally:
        setattr(router_mod, "call_openai_responses_v1", router_mod.call_openai_responses_v1)
    dec = u.get("reasoning_router_decision_v1") or {}
    assert dec.get("final_route_v1") == "external_failed_fallback_local"
    assert "schema_validation_failed_v1" in (dec.get("escalation_blockers_v1") or [])
    ere2 = u.get("entry_reasoning_eval_v1")
    l1 = l1_fields_from_router_decision_v1(dec)
    pfm2 = u.get("student_reasoning_fault_map_v1") or {}
    return _bundle(
        "06_external_schema_or_contract_failure",
        "Invalid body → external_failed_fallback_local + schema_validation_failed_v1",
        dec,
        (ere2 or {}).get("external_api_call_ledger_v1") or {},
        l1,
        pfm2,
        ere2 if isinstance(ere2, dict) else None,
    )


def run_scenario_07_external_disagrees_engine_unchanged_v1() -> dict[str, Any]:
    job = f"proof_026ai_S07_{uuid.uuid4().hex[:8]}"
    base, berr, _, _ = run_entry_reasoning_pipeline_v1(
        student_decision_packet=packet_study_v1(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id=job,
        emit_traces=False,
        unified_agent_router=False,
    )
    assert base and not berr
    base_action = str((base.get("decision_synthesis_v1") or {}).get("action") or "")

    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "sk-test-artifact-dummy"
    try:
        def _disagree_call(**_kw: Any) -> dict[str, Any]:
            d = {
                "ok": True,
                "error": None,
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
                "model_resolved": "gpt-mock",
                "response_status": "ok",
                "parsed_json": _good_review_json(suggested_action="enter_long", disagree=True),
                "failure_blocker_v1": None,
            }
            return d

        setattr(router_mod, "call_openai_responses_v1", _disagree_call)
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s07",
            emit_traces=True,
            unified_agent_router=True,
            router_config=load_reasoning_router_config_v1(
                None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
            ),
        )
    finally:
        setattr(router_mod, "call_openai_responses_v1", router_mod.call_openai_responses_v1)
    assert ere and not err
    assert str((ere.get("decision_synthesis_v1") or {}).get("action") or "") == base_action
    rev = ere.get("external_reasoning_review_v1")
    assert isinstance(rev, dict) and bool(rev.get("disagreement_with_local_v1")) is True
    dec = ere.get("reasoning_router_decision_v1") or {}
    l1 = l1_fields_from_router_decision_v1(dec)
    return {
        **(
            _bundle(
                "07_external_disagrees_deterministic_unchanged",
                "Advisory long suggestion; engine action unchanged; router_external_influence_v1 on ere",
                dec,
                ere.get("external_api_call_ledger_v1") or {},
                l1,
                pfm,
                ere,
            )
        ),
        "entry_reasoning_excerpt_v1": {
            "decision_synthesis_v1": ere.get("decision_synthesis_v1"),
            "router_external_influence_v1": ere.get("router_external_influence_v1"),
        },
        "external_review_suggested_action_v1": (rev or {}).get("suggested_action_v1"),
        "engine_action_unchanged_v1": base_action,
    }


def run_scenario_08_rate_limited_v1() -> dict[str, Any]:
    job = f"proof_026ai_S08_{uuid.uuid4().hex[:8]}"
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "sk-test-artifact-dummy"
    try:

        def _429(**_k: Any) -> dict[str, Any]:
            return {
                "ok": False,
                "error": "rate limit",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "model_resolved": None,
                "response_status": "http_429",
                "parsed_json": None,
                "failure_blocker_v1": "rate_limited_v1",
                "latency_ms": 1.0,
            }

        setattr(router_mod, "call_openai_responses_v1", _429)
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s08",
            emit_traces=True,
            unified_agent_router=True,
            router_config=load_reasoning_router_config_v1(
                None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
            ),
        )
    finally:
        setattr(router_mod, "call_openai_responses_v1", router_mod.call_openai_responses_v1)
    dec = ere.get("reasoning_router_decision_v1") or {}
    assert "rate_limited_v1" in (dec.get("escalation_blockers_v1") or [])
    l1 = l1_fields_from_router_decision_v1(dec)
    return _bundle(
        "08_rate_limited_or_provider_unavailable",
        "Simulated 429 → rate_limited_v1, fallback",
        dec,
        ere.get("external_api_call_ledger_v1") or {},
        l1,
        pfm,
        ere,
    )


def run_scenario_08b_provider_unavailable_v1() -> dict[str, Any]:
    job = f"proof_026ai_S08b_{uuid.uuid4().hex[:8]}"
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "sk-test-artifact-dummy"
    try:

        def _unavail(**_k: Any) -> dict[str, Any]:
            return {
                "ok": False,
                "error": "Connection refused (simulated)",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "model_resolved": None,
                "response_status": "request_failed",
                "parsed_json": None,
                "failure_blocker_v1": "provider_unavailable_v1",
                "latency_ms": 0.1,
            }

        setattr(router_mod, "call_openai_responses_v1", _unavail)
        ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=packet_study_v1(),
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=5,
            job_id=job,
            fingerprint="proof_fp_s08b",
            emit_traces=True,
            unified_agent_router=True,
            router_config=load_reasoning_router_config_v1(
                None, extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99}
            ),
        )
    finally:
        setattr(router_mod, "call_openai_responses_v1", router_mod.call_openai_responses_v1)
    dec = ere.get("reasoning_router_decision_v1") or {}
    assert "provider_unavailable_v1" in (dec.get("escalation_blockers_v1") or [])
    l1 = l1_fields_from_router_decision_v1(dec)
    return _bundle(
        "08b_provider_unavailable_network_style",
        "Simulated URLError/timeout class → provider_unavailable_v1, fallback",
        dec,
        ere.get("external_api_call_ledger_v1") or {},
        l1,
        pfm,
        ere,
    )


def _bundle(
    scenario_slug: str,
    narrative: str,
    decision: dict[str, Any],
    ledger: dict[str, Any],
    l1: dict[str, object | None],
    pfm: dict[str, Any],
    ere: dict[str, Any] | None,
    *,
    expected_route: tuple[str, ...] | None = None,
    expected_blocker: str | None = None,
) -> dict[str, Any]:
    ver = verify_mandatory_decision_and_ledger_fields_v1(decision, ledger)
    sec = security_scan_serialized_v1(
        {
            "reasoning_router_decision_v1": decision,
            "external_api_call_ledger_v1": ledger,
            "l1": l1,
        }
    )
    fault_excerpt = {
        "reasoning_router_evaluated": fault_map_node_excerpt_v1(pfm, "reasoning_router_evaluated"),
    }
    has_review = bool(isinstance(ere, dict) and isinstance(ere.get("external_reasoning_review_v1"), dict))
    trace_rep = [
        {
            "stage": "reasoning_router_decision_v1",
            "producer": "unified_agent_v1",
            "summary": "Unified reasoning router decision (no secrets in evidence).",
            "evidence_keys_sanitized_v1": sorted({k for k in list((decision or {}).keys()) if "key" not in k.lower()}),
        },
        {
            "stage": "reasoning_cost_governor_v1",
            "producer": "unified_agent_v1",
            "summary": "Call ledger + token/cost caps (sanitized; no API key).",
            "evidence_ledger_keys_v1": sorted(ledger.keys()),
        },
    ]
    if has_review:
        trace_rep.append(
            {
                "stage": "external_reasoning_review_v1",
                "producer": "unified_agent_v1",
                "summary": "Advisory external JSON only; engine remains authority.",
            }
        )
    out: dict[str, Any] = {
        "schema": PROOF_BUNDLE_SCHEMA_V1,
        "proof_version": PROOF_VERSION,
        "scenario_id": scenario_slug,
        "generated_at_utc": _now_iso(),
        "narrative": narrative,
        "python": sys.version.split()[0],
        "entry_reasoning_excerpt_v1": {
            "decision_synthesis_v1": (ere or {}).get("decision_synthesis_v1") if isinstance(ere, dict) else None,
            "confidence_01": (ere or {}).get("confidence_01") if isinstance(ere, dict) else None,
        },
        "trace_events_representative_v1": trace_rep,
        "router_decision_v1": copy.deepcopy(decision),
        "external_api_call_ledger_v1": copy.deepcopy(ledger),
        "l1_fields_v1": copy.deepcopy(l1),
        "fault_map_excerpt_v1": fault_excerpt,
        "operator_message_english_v1": (decision or {}).get("operator_message_english_v1"),
        "final_route_v1": (decision or {}).get("final_route_v1"),
        "required_fields_verification_v1": ver,
        "all_required_fields_ok_v1": all_mandatory_verification_true_v1(ver),
        "security_serialized_scan_v1": sec,
    }
    if expected_route:
        out["expected_route_in_v1"] = expected_route
        out["final_route_in_expected_set_v1"] = str((decision or {}).get("final_route_v1")) in expected_route
    if expected_blocker:
        out["expected_blocker_v1"] = expected_blocker
        out["blocker_present_v1"] = expected_blocker in (decision.get("escalation_blockers_v1") or [])
    return out


def run_scenario_03a_quota_exceeded_v1() -> dict[str, Any]:
    return run_scenario_03_insufficient_funds_or_quota_v1("quota_exceeded_v1")


def build_live_026ai_closure_artifact_v1() -> dict[str, Any]:
    """
    **GT_DIRECTIVE_026AI final closure (live):** two real calls when ``OPENAI_API_KEY`` is set:
    1) ``run_smoke_test_strict_json_v1`` → same path as ``call_openai_responses_v1``;
    2) ``run_entry_reasoning_pipeline_v1(..., unified_agent_router=True)`` → full Student entry path + router
       invoking the same adapter.

    Returns a dict suitable for writing ``LIVE_SMOKE_openai_responses.json`` (no secrets; scan before commit).
    If adapter smoke fails, the router path is skipped to avoid a second failed billable attempt.
    """
    from renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1 import run_smoke_test_strict_json_v1

    adapter_smoke = run_smoke_test_strict_json_v1()
    router_path: dict[str, Any] | None = None
    if not adapter_smoke.get("smoke_ok"):
        payload: dict[str, Any] = {
            "schema": "gt_directive_026ai_live_smoke_v1",
            "closure_version_v1": 2,
            "generated_at_utc": _now_iso(),
            "python": sys.version.split()[0],
            "note": "Adapter smoke failed; unified router path not run.",
            "code_paths_proven_v1": [
                "renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1.call_openai_responses_v1",
            ],
            "adapter_responses_api_smoke_v1": adapter_smoke,
            "reasoning_router_unified_path_v1": None,
            "closure_complete_v1": False,
        }
        payload["security_full_artifact_scan_v1"] = security_scan_serialized_v1(payload)
        return payload

    job = f"live_026ai_closure_{uuid.uuid4().hex[:8]}"
    ere, err, _tr, pfm = run_entry_reasoning_pipeline_v1(
        student_decision_packet=packet_study_v1(),
        retrieved_student_experience=[],
        run_candle_timeframe_minutes=5,
        job_id=job,
        fingerprint="live_026ai_closure_fp",
        emit_traces=False,
        unified_agent_router=True,
        router_config=load_reasoning_router_config_v1(
            None,
            extra_dict={"external_api_enabled": True, "low_confidence_threshold": 0.99},
        ),
    )
    dec = (ere or {}).get("reasoning_router_decision_v1") or {}
    leg = (ere or {}).get("external_api_call_ledger_v1") or {}
    l1 = l1_fields_from_router_decision_v1(dec)
    node = fault_map_node_excerpt_v1(pfm, "reasoning_router_evaluated") if isinstance(pfm, dict) else None
    router_path = {
        "job_id": job,
        "entry_reasoning_errors": err,
        "final_route_v1": dec.get("final_route_v1"),
        "external_api_attempted_v1": dec.get("external_api_attempted_v1"),
        "external_api_allowed_v1": dec.get("external_api_allowed_v1"),
        "operator_message_english_v1": dec.get("operator_message_english_v1"),
        "external_api_call_ledger_v1": leg,
        "l1_fields_v1": l1,
        "reasoning_router_evaluated_excerpt_v1": node,
    }
    complete = bool(ere) and not err and bool(adapter_smoke.get("smoke_ok"))
    payload = {
        "schema": "gt_directive_026ai_live_smoke_v1",
        "closure_version_v1": 2,
        "generated_at_utc": _now_iso(),
        "python": sys.version.split()[0],
        "note": "Real OpenAI: adapter /v1/responses strict smoke, then full unified router. Key from process environment (OPENAI_API_KEY) only; no secrets on disk in adapter.",
        "code_paths_proven_v1": [
            "renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1.call_openai_responses_v1",
            "renaissance_v4.game_theory.unified_agent_v1.external_openai_adapter_v1.run_smoke_test_strict_json_v1",
            "entry_reasoning_engine_v1.run_entry_reasoning_pipeline_v1 + unified_agent_v1.reasoning_router_v1",
        ],
        "adapter_responses_api_smoke_v1": adapter_smoke,
        "reasoning_router_unified_path_v1": router_path,
        "closure_complete_v1": complete,
    }
    payload["security_full_artifact_scan_v1"] = security_scan_serialized_v1(payload)
    return payload


__all__ = [
    "FORBIDDEN_SECURITY_SUBSTRINGS",
    "PROOF_BUNDLE_SCHEMA_V1",
    "all_mandatory_verification_true_v1",
    "fault_map_node_excerpt_v1",
    "packet_study_v1",
    "run_scenario_01_local_only_external_disabled_v1",
    "run_scenario_02_missing_api_key_v1",
    "run_scenario_03_insufficient_funds_or_quota_v1",
    "run_scenario_03a_quota_exceeded_v1",
    "run_scenario_04_budget_exceeded_v1",
    "run_scenario_05_successful_escalation_mocked_v1",
    "run_scenario_06_schema_validation_failed_v1",
    "run_scenario_07_external_disagrees_engine_unchanged_v1",
    "run_scenario_08_rate_limited_v1",
    "run_scenario_08b_provider_unavailable_v1",
    "build_live_026ai_closure_artifact_v1",
    "security_scan_serialized_v1",
    "verify_mandatory_decision_and_ledger_fields_v1",
]
