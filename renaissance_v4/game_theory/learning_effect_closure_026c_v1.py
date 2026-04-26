"""
GT_DIRECTIVE_026C addendum — learning-effect **closure** proof (no claimed behavior change without control).

Builds a structured ``learning_effect_closure_026c_v1`` block for ``debug_learning_loop_trace_v1`` that ties:

* Run A — closed-tape 026C record + scoring + promote/reject (learning_trace + optional JSONL)
* Run B (usually ``job_id`` from the request) — retrieval, packet injection, deterministic application,
  reasoning router, local model path, external OpenAI review (or explicit non-call reasons)
* Control run — same scenario/timeframe (operator supplies ``control_job_id`` for A/B on scorecard)

**Closure result** (exactly one): ``LEARNING_CHANGED_BEHAVIOR`` | ``LEARNING_RETRIEVED_BUT_NO_BEHAVIOR_CHANGE`` |
``LEARNING_BLOCKED_BY_GOVERNANCE`` | ``LEARNING_ROUTER_NOT_TRIGGERED`` | ``INSUFFICIENT_COMPARISON``
"""

from __future__ import annotations

import json
from typing import Any

from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    build_student_panel_run_learning_payload_v1,
)
from renaissance_v4.game_theory.student_proctor.lifecycle_deterministic_learning_026c_v1 import (
    default_lifecycle_deterministic_learning_store_path_v1,
)
from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1

SCHEMA_LEARNING_EFFECT_CLOSURE_026C = "learning_effect_closure_026c_v1"
SCHEMA_CUMULATIVE_026C_JOB_SURFACE = "cumulative_026c_learning_job_surface_v1"
CONTRACT_VERSION = 1

RESULT_LEARNING_CHANGED_BEHAVIOR = "LEARNING_CHANGED_BEHAVIOR"
RESULT_LEARNING_RETRIEVED_NO_CHANGE = "LEARNING_RETRIEVED_BUT_NO_BEHAVIOR_CHANGE"
RESULT_LEARNING_BLOCKED = "LEARNING_BLOCKED_BY_GOVERNANCE"
RESULT_ROUTER_NOT_TRIGGERED = "LEARNING_ROUTER_NOT_TRIGGERED"
RESULT_INSUFFICIENT = "INSUFFICIENT_COMPARISON"


def _evidence(ev: dict[str, Any] | None) -> dict[str, Any]:
    return ev if isinstance(ev, dict) else {}


def _events_for(jid: str) -> list[dict[str, Any]]:
    if not str(jid or "").strip():
        return []
    return read_learning_trace_events_for_job_v1(
        str(jid).strip(),
        path=default_learning_trace_events_jsonl(),
    )


def _first_event_by_stage(
    events: list[dict[str, Any]],
    stage: str,
) -> dict[str, Any] | None:
    for ev in events or []:
        if str(ev.get("stage") or "").strip() == stage:
            return ev
    return None


def _last_event_by_stage(
    events: list[dict[str, Any]],
    stage: str,
) -> dict[str, Any] | None:
    for ev in reversed(events or []):
        if str(ev.get("stage") or "").strip() == stage:
            return ev
    return None


def cumulative_026c_job_surface_v1(
    entry: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Operator-facing: whether prior 026C learning was N/A, retrieved, applied, etc. (from trace + scorecard).
    """
    from renaissance_v4.game_theory.exam_run_contract_v1 import (
        STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
        normalize_student_reasoning_mode_v1,
    )

    ent = entry if isinstance(entry, dict) else {}
    oba = ent.get("operator_batch_audit")
    _prof = normalize_student_reasoning_mode_v1(
        str(ent.get("student_brain_profile_v1") or ent.get("student_reasoning_mode") or "")
    )
    if _prof == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1 or (
        isinstance(oba, dict) and str(oba.get("operator_run_mode_surface_v1") or "") == "baseline"
    ):
        return {
            "schema": SCHEMA_CUMULATIVE_026C_JOB_SURFACE,
            "outcome_v1": "NOT_APPLICABLE",
            "plain_english_v1": "Baseline control run — cumulative Student 026C learning is not applied.",
        }
    for ev in reversed(events or []):
        if str(ev.get("stage") or "") != "lifecycle_tape_summary_v1":
            continue
        ep = ev.get("evidence_payload")
        if not isinstance(ep, dict):
            break
        ltr = ep.get("lifecycle_tape_result_v1")
        if not isinstance(ltr, dict):
            break
        surf = ltr.get("cumulative_026c_learning_operator_surface_v1")
        if isinstance(surf, dict):
            return {
                "schema": SCHEMA_CUMULATIVE_026C_JOB_SURFACE,
                "from_lifecycle_tape_summary_v1": True,
                "operator_surface_v1": surf,
                "outcome_v1": surf.get("outcome_v1"),
                "plain_english_v1": surf.get("plain_english_v1"),
            }
        break
    return {
        "schema": SCHEMA_CUMULATIVE_026C_JOB_SURFACE,
        "outcome_v1": "UNKNOWN",
        "plain_english_v1": "No lifecycle tape summary with cumulative 026C surface in learning_trace for this job.",
    }


def _load_026c_records_from_store() -> list[dict[str, Any]]:
    p = default_lifecycle_deterministic_learning_store_path_v1()
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(o, dict):
            rows.append(o)
    return rows


def _lookup_026c_record_id(record_id: str) -> dict[str, Any] | None:
    rid = str(record_id or "").strip()
    if not rid:
        return None
    for r in _load_026c_records_from_store():
        if str(r.get("record_id_026c") or "") == rid:
            return r
    return None


def _parse_run_a_from_events(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Run A: learning_record_created + scoring + decision (same job_id in trace as the producing job)."""
    e_created = _first_event_by_stage(events, "learning_record_created_v1")
    e_scoring = _first_event_by_stage(events, "learning_scoring_completed_v1")
    e_decision = _first_event_by_stage(events, "learning_decision_made_v1")
    if not e_created and not e_scoring and not e_decision:
        return None
    p0 = _evidence(e_created).get("evidence_payload")
    p1 = _evidence(e_scoring).get("evidence_payload")
    p2 = _evidence(e_decision).get("evidence_payload")
    return {
        "learning_record_created_v1": p0,
        "learning_scoring_completed_v1": p1,
        "learning_decision_made_v1": p2,
        "record_id_026c": (p0 or {}).get("record_id_026c") if isinstance(p0, dict) else None,
    }


def _router_proof_from_b(events: list[dict[str, Any]]) -> dict[str, Any]:
    evr = _last_event_by_stage(events, "reasoning_router_decision_v1")
    if not evr:
        return {"router_evaluated_v1": False, "reason": "no_reasoning_router_decision_v1 event for this job_id"}
    pl = _evidence(evr).get("evidence_payload")
    if not isinstance(pl, dict):
        return {"router_evaluated_v1": False, "reason": "reasoning_router_decision event missing evidence_payload"}
    d = pl.get("reasoning_router_decision_v1")
    cr = pl.get("call_ledger_sanitized_v1")
    d = d if isinstance(d, dict) else {}
    cr = cr if isinstance(cr, dict) else {}
    final_route = str(d.get("final_route_v1") or "")
    return {
        "router_evaluated_v1": True,
        "reasoning_router_decision_v1": d,
        "call_ledger_sanitized_v1": cr,
        "escalation_reason_codes_v1": list(d.get("escalation_reason_codes_v1") or []),
        "escalation_blockers_v1": list(d.get("escalation_blockers_v1") or []),
        "final_route_v1": final_route,
    }


def _external_openai_call_proof_b(events: list[dict[str, Any]], router: dict[str, Any]) -> dict[str, Any]:
    """When external review ran: provider, model, tokens, cost, validator, route; else explicit non-call reason."""
    evx = _last_event_by_stage(events, "external_reasoning_review_v1")
    d = (router or {}).get("reasoning_router_decision_v1")
    d = d if isinstance(d, dict) else {}
    cr0 = (router or {}).get("call_ledger_sanitized_v1")
    cr = cr0 if isinstance(cr0, dict) else {}
    if isinstance(evx, dict) and _evidence(evx).get("evidence_payload"):
        pl = _evidence(evx).get("evidence_payload")
        review = (pl or {}).get("external_reasoning_review_v1") if isinstance(pl, dict) else None
        review = review if isinstance(review, dict) else {}
        return {
            "external_openai_call_made_v1": True,
            "provider_v1": str(cr.get("provider_v1") or d.get("external_provider_v1") or "openai"),
            "model_requested_v1": str(cr.get("model_requested_v1") or d.get("external_model_requested_v1") or ""),
            "model_resolved_v1": cr.get("model_resolved_v1") or d.get("external_model_resolved_v1"),
            "escalation_reason_codes_v1": list(d.get("escalation_reason_codes_v1") or []),
            "input_tokens_v1": int(cr.get("input_tokens_v1") or 0),
            "output_tokens_v1": int(cr.get("output_tokens_v1") or 0),
            "total_tokens_v1": int(cr.get("total_tokens_v1") or 0),
            "latency_ms_v1": float(cr.get("latency_ms_v1") or 0.0),
            "estimated_cost_usd_v1": float(cr.get("estimated_cost_usd_v1") or 0.0),
            "validator_status_v1": str(cr.get("validator_status_v1") or ""),
            "final_route_v1": str(d.get("final_route_v1") or ""),
            "external_reasoning_review_v1": review,
        }
    # No external review event — document why
    fr = str(d.get("final_route_v1") or "local_only")
    reasons = list(d.get("escalation_reason_codes_v1") or [])
    bl = [str(x) for x in (d.get("escalation_blockers_v1") or [])]
    why: list[str] = []
    if "no_escalation_reason_v1" in bl or (not reasons and "external" not in fr):
        why.append("no_escalation_reason")
    if "budget_exceeded_v1" in bl or "token_limit_exceeded_v1" in bl or fr == "external_blocked_budget":
        why.append("budget_blocked")
    if not d.get("external_api_enabled_v1", True) or "external_disabled" in fr:
        why.append("external_disabled")
    if "missing_api_key" in " ".join(bl).lower() or fr == "external_blocked_missing_key":
        why.append("missing_key")
    if fr == "local_only" and not why:
        why.append("local_only_route")
    return {
        "external_openai_call_made_v1": False,
        "final_route_v1": fr,
        "escalation_blockers_v1": bl,
        "escalation_reason_codes_v1": reasons,
        "no_call_reasons_plain_v1": why
        or [
            f"see final_route_v1={fr!r} and blockers; review event absent — external path not taken or not logged."
        ],
    }


def _local_model_path_proof_b(events: list[dict[str, Any]], entry: dict[str, Any] | None) -> dict[str, Any]:
    from renaissance_v4.game_theory.debug_learning_loop_trace_v1 import _model_provenance_chain_v1

    mchain = _model_provenance_chain_v1(entry or {}, events)
    called = [x for x in (events or []) if str(x.get("stage") or "") == "llm_called_v1"]
    last_llm = called[-1] if called else None
    pl = _evidence(last_llm).get("evidence_payload") if last_llm else None
    return {
        "model_provenance_chain_v1": mchain,
        "llm_called_last_evidence_v1": pl if isinstance(pl, dict) else None,
    }


def _lifecycle_summary_from_events(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for ev in reversed(events or []):
        if str(ev.get("stage") or "") != "lifecycle_tape_summary_v1":
            continue
        pl = _evidence(ev).get("evidence_payload")
        if not isinstance(pl, dict):
            continue
        tr = pl.get("lifecycle_tape_result_v1")
        if not isinstance(tr, dict):
            continue
        if tr.get("per_bar_slim_v1") is not None or tr.get("closed_v1") is not None:
            return tr
        if tr.get("retrieved_lifecycle_deterministic_learning_026c_v1") or tr.get(
            "deterministic_learning_context_026c_v1"
        ):
            return tr
    return None


def _run_b_026c_injection_proof(events: list[dict[str, Any]]) -> dict[str, Any]:
    tr = _lifecycle_summary_from_events(events) or {}
    inj = tr.get("retrieved_lifecycle_deterministic_learning_026c_v1")
    ctx0 = tr.get("deterministic_learning_context_026c_v1")
    rids: list[str] = []
    if isinstance(inj, list):
        for s in inj:
            if isinstance(s, dict) and s.get("record_id_026c"):
                rids.append(str(s.get("record_id_026c")))
    return {
        "packet_injection_evidence_in_trace_v1": bool(inj or ctx0),
        "retrieved_lifecycle_deterministic_learning_026c_v1": inj,
        "deterministic_learning_context_026c_v1": ctx0,
        "retrieved_record_ids_026c_v1": rids,
    }


def _resolve_run_a_job_id(
    run_a_arg: str | None,
    retrieved_rids: list[str],
) -> str | None:
    if str(run_a_arg or "").strip():
        return str(run_a_arg).strip()
    for rid in retrieved_rids:
        rec = _lookup_026c_record_id(rid)
        if rec and str(rec.get("job_id_v1") or "").strip():
            return str(rec.get("job_id_v1")).strip()
    return None


def _scorecard_snapshot(job_id: str) -> dict[str, Any] | None:
    e = find_scorecard_entry_by_job_id(str(job_id).strip())
    if not isinstance(e, dict):
        return None
    return {
        "job_id": str(job_id).strip(),
        "student_action_v1": e.get("student_action_v1") or e.get("student_output_action"),
        "student_confidence_01": e.get("student_confidence_01") or e.get("confidence_01"),
        "student_brain_profile_v1": e.get("student_brain_profile_v1") or e.get("student_reasoning_mode"),
        "exam_e_score_v1": e.get("exam_e_score_v1"),
        "exam_p_score_v1": e.get("exam_p_score_v1"),
        "expectancy_per_trade": e.get("expectancy_per_trade"),
        "referee_outcomes_digest_v1": e.get("referee_outcomes_digest_v1"),
    }


def _lifecycle_metrics_from_tr(tr: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(tr, dict):
        return {"hold_bars_inferred_v1": None, "exit_reason_v1": None, "closed_v1": None}
    slim = tr.get("per_bar_slim_v1")
    n_hold = 0
    if isinstance(slim, list):
        n_hold = sum(1 for r in slim if str((r or {}).get("decision_v1") or "") in ("hold", ""))
    return {
        "hold_bars_inferred_v1": n_hold,
        "exit_reason_code_v1": tr.get("exit_reason_code_v1"),
        "closed_v1": tr.get("closed_v1"),
        "exit_at_bar_index_v1": tr.get("exit_at_bar_index_v1"),
    }


def _governance_blocked(job_id: str) -> bool:
    learn = build_student_panel_run_learning_payload_v1(str(job_id).strip())
    g = learn.get("learning_governance_v1") if isinstance(learn, dict) else None
    if not isinstance(g, dict):
        return False
    return str(g.get("decision") or "").strip().lower() == "reject"


def build_learning_effect_closure_026c_v1(
    job_id_run_b: str,
    *,
    run_a_job_id: str | None = None,
    control_job_id: str | None = None,
    scorecard_entry_run_b: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build closure proof for Run B. Pass scorecard line for B when available (for local model / provenance).
    """
    j_b = str(job_id_run_b or "").strip()
    out: dict[str, Any] = {
        "schema": SCHEMA_LEARNING_EFFECT_CLOSURE_026C,
        "contract_version": CONTRACT_VERSION,
        "run_b_job_id_v1": j_b,
    }
    if not j_b:
        out["closure_result_v1"] = RESULT_INSUFFICIENT
        out["closure_detail_v1"] = "empty job_id"
        return out

    ev_b = _events_for(j_b)
    entry_b = scorecard_entry_run_b if isinstance(scorecard_entry_run_b, dict) else find_scorecard_entry_by_job_id(j_b)

    inj = _run_b_026c_injection_proof(ev_b)
    rids = list(inj.get("retrieved_record_ids_026c_v1") or [])
    j_a = _resolve_run_a_job_id(run_a_job_id, rids)
    out["run_a_job_id_inferred_v1"] = j_a
    if run_a_job_id:
        out["run_a_job_id_supplied_v1"] = str(run_a_job_id).strip()

    ev_a = _events_for(j_a) if j_a else []
    run_a = _parse_run_a_from_events(ev_a) if j_a else None
    if not run_a and j_a:
        # Store fallback for A
        for rid in rids:
            rec = _lookup_026c_record_id(rid)
            if rec and str(rec.get("job_id_v1") or "") == j_a:
                run_a = {
                    "from_store_v1": True,
                    "record_id_026c": rec.get("record_id_026c"),
                    "decision_quality_score_v1": rec.get("decision_quality_score_v1"),
                    "learning_decision_v1": rec.get("learning_decision_v1"),
                }
                break
    out["run_a_evidence_v1"] = run_a

    router = _router_proof_from_b(ev_b)
    out["run_b_reasoning_router_v1"] = router
    out["run_b_external_openai_v1"] = _external_openai_call_proof_b(ev_b, router)
    out["run_b_local_model_path_v1"] = _local_model_path_proof_b(ev_b, entry_b)
    out["run_b_026c_injection_and_apply_v1"] = {
        **inj,
        "deterministic_apply_markers_v1": bool(inj.get("deterministic_learning_context_026c_v1")),
    }

    tr_b = _lifecycle_summary_from_events(ev_b)
    out["run_b_lifecycle_summary_from_trace_v1"] = {
        "tape_headline_v1": tr_b,
        "metrics_v1": _lifecycle_metrics_from_tr(tr_b),
    }

    # Link retrieved record to Run A store row
    link: list[dict[str, Any]] = []
    for rid in rids:
        rec = _lookup_026c_record_id(rid)
        if rec:
            link.append(
                {
                    "record_id_026c": rid,
                    "store_job_id_v1": rec.get("job_id_v1"),
                    "store_trade_id_v1": rec.get("trade_id_v1"),
                    "matches_inferred_run_a_v1": bool(j_a) and str(rec.get("job_id_v1") or "") == j_a,
                }
            )
    out["run_b_to_run_a_link_v1"] = link

    ctrl = (str(control_job_id or "").strip() or None)
    snap_b = _scorecard_snapshot(j_b) or {}
    snap_c = _scorecard_snapshot(ctrl) if ctrl else None
    tr_c = _lifecycle_summary_from_events(_events_for(ctrl)) if ctrl else None
    out["control_job_id_v1"] = ctrl
    out["comparison_v1"] = {
        "treatment_snapshot_v1": snap_b,
        "control_snapshot_v1": snap_c,
        "lifecycle_treatment_v1": _lifecycle_metrics_from_tr(tr_b),
        "lifecycle_control_v1": _lifecycle_metrics_from_tr(tr_c),
        "deltas_v1": None,
    }

    dvs: dict[str, Any] = {}
    if snap_c and snap_b:
        for k in ("student_action_v1", "student_confidence_01", "exam_e_score_v1", "exam_p_score_v1", "expectancy_per_trade"):
            vb, vc = snap_b.get(k), snap_c.get(k)
            if vb != vc:
                dvs[k] = {"treatment": vb, "control": vc}
        mt, mc = _lifecycle_metrics_from_tr(tr_b), _lifecycle_metrics_from_tr(tr_c)
        for k in ("exit_reason_code_v1", "hold_bars_inferred_v1", "closed_v1"):
            if mt.get(k) != mc.get(k):
                dvs[f"lifecycle_{k}"] = {"treatment": mt.get(k), "control": mc.get(k)}
    out["comparison_v1"]["deltas_v1"] = dvs or None

    # --- closure result (strict; order is normative) ---
    gov_block = _governance_blocked(j_b)
    if gov_block:
        out["closure_result_v1"] = RESULT_LEARNING_BLOCKED
        out["closure_detail_v1"] = "learning_governance_v1 decision is reject for Run B (GT018 store)."
    elif not (router or {}).get("router_evaluated_v1"):
        out["closure_result_v1"] = RESULT_ROUTER_NOT_TRIGGERED
        out["closure_detail_v1"] = "No reasoning_router_decision_v1 event for Run B; router not proven in learning_trace."
    elif not inj.get("packet_injection_evidence_in_trace_v1") and not rids:
        out["closure_result_v1"] = RESULT_INSUFFICIENT
        out["closure_detail_v1"] = (
            "No 026C packet injection in lifecycle_tape_summary evidence and no resolvable record_id_026c to load from store — "
            "full stack (retrieve + apply) is not provable from trace alone."
        )
    elif not ctrl:
        out["closure_result_v1"] = RESULT_INSUFFICIENT
        out["closure_detail_v1"] = "control_job_id not supplied — cannot assert behavior change vs no-learning baseline."
    elif dvs:
        out["closure_result_v1"] = RESULT_LEARNING_CHANGED_BEHAVIOR
        out["closure_detail_v1"] = "Treatment vs control differ on at least one compared field (entry, confidence, lifecycle, scores)."
    else:
        out["closure_result_v1"] = RESULT_LEARNING_RETRIEVED_NO_CHANGE
        out["closure_detail_v1"] = (
            "026C + router are evidenced; treatment vs control snapshots match on compared fields (no behavior difference detected)."
        )

    out["cumulative_026c_learning_job_surface_v1"] = cumulative_026c_job_surface_v1(entry_b, ev_b)

    return out


__all__ = [
    "SCHEMA_LEARNING_EFFECT_CLOSURE_026C",
    "cumulative_026c_job_surface_v1",
    "build_learning_effect_closure_026c_v1",
    "RESULT_LEARNING_CHANGED_BEHAVIOR",
    "RESULT_LEARNING_RETRIEVED_NO_CHANGE",
    "RESULT_LEARNING_BLOCKED",
    "RESULT_ROUTER_NOT_TRIGGERED",
    "RESULT_INSUFFICIENT",
]
