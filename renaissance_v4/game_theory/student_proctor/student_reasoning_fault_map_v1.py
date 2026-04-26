"""
GT_DIRECTIVE_026R — ``student_reasoning_fault_map_v1`` (node-level visibility, no behavior change).

Structured fault map: fixed node order, allowed statuses, plain-English operator fields.
"""

from __future__ import annotations

from typing import Any

SCHEMA_STUDENT_REASONING_FAULT_MAP_V1 = "student_reasoning_fault_map_v1"
CONTRACT_VERSION_FAULT_MAP = 1

# Fixed order (026R + 026AI router + 026B lifecycle + 026C deterministic learning).
NODE_IDS_ORDER: tuple[str, ...] = (
    "market_data_loaded",
    "indicator_context_evaluated",
    "memory_context_evaluated",
    "prior_outcomes_evaluated",
    "risk_reward_evaluated",
    "decision_synthesized",
    "entry_reasoning_validated",
    "llm_output_checked",
    "student_output_sealed",
    "execution_intent_created",
    "reasoning_router_evaluated",
    "external_escalation_governed",
    "external_reasoning_review_recorded",
    # GT_DIRECTIVE_026B — full trade lifecycle (tape participation)
    "lifecycle_context_loaded",
    "lifecycle_reasoning_evaluated",
    "lifecycle_decision_made",
    "lifecycle_exit_evaluated",
    # GT_DIRECTIVE_026C — deterministic learning (no LLM memory writes)
    "learning_record_created",
    "learning_scoring_evaluated",
    "learning_promotion_decision",
    "learning_retrieval_applied",
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIPPED = "SKIPPED"
STATUS_NOT_PROVEN = "NOT_PROVEN"
ALLOWED_STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_SKIPPED, STATUS_NOT_PROVEN)


def make_fault_node_v1(
    node_id: str,
    status: str,
    *,
    input_summary_v1: str,
    output_summary_v1: str,
    blocking_rule_v1: str = "",
    error_codes_v1: list[str] | None = None,
    evidence_fields_v1: list[str] | None = None,
    evidence_values_v1: dict[str, Any] | None = None,
    operator_message_v1: str = "",
) -> dict[str, Any]:
    st = str(status or "").strip()
    if st not in ALLOWED_STATUSES:
        st = STATUS_NOT_PROVEN
    return {
        "node_id": str(node_id),
        "status": st,
        "input_summary_v1": str(input_summary_v1 or "")[:4000],
        "output_summary_v1": str(output_summary_v1 or "")[:4000],
        "blocking_rule_v1": str(blocking_rule_v1 or "")[:2000],
        "error_codes_v1": [str(x) for x in (error_codes_v1 or [])][:64],
        "evidence_fields_v1": [str(x) for x in (evidence_fields_v1 or [])][:64],
        "evidence_values_v1": dict(evidence_values_v1) if isinstance(evidence_values_v1, dict) else {},
        "operator_message_v1": str(operator_message_v1 or "")[:4000],
    }


def skipped_nodes_from_index_v1(from_index: int) -> list[dict[str, Any]]:
    """Nodes from_index .. end-1 as SKIPPED (0-based index into ``NODE_IDS_ORDER``)."""
    out: list[dict[str, Any]] = []
    for i in range(from_index, len(NODE_IDS_ORDER)):
        nid = NODE_IDS_ORDER[i]
        out.append(
            make_fault_node_v1(
                nid,
                STATUS_SKIPPED,
                input_summary_v1="Earlier step",
                output_summary_v1="Not run",
                operator_message_v1="Not reached: a required step before this one did not pass.",
            )
        )
    return out


def build_fault_map_v1(
    nodes_v1: list[dict[str, Any]],
    *,
    fill_missing_as: str = STATUS_SKIPPED,
) -> dict[str, Any]:
    by_id = {str(n.get("node_id") or ""): n for n in nodes_v1 if isinstance(n, dict)}
    ordered: list[dict[str, Any]] = []
    for nid in NODE_IDS_ORDER:
        if nid in by_id:
            ordered.append(by_id[nid])
        else:
            st = fill_missing_as if fill_missing_as in ALLOWED_STATUSES else STATUS_NOT_PROVEN
            ordered.append(
                make_fault_node_v1(
                    nid,
                    st,
                    input_summary_v1="—",
                    output_summary_v1="—",
                    operator_message_v1="This step was not filled for this response."
                    if st == STATUS_NOT_PROVEN
                    else "Not reached yet for this run.",
                )
            )
    return {
        "schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
        "contract_version": CONTRACT_VERSION_FAULT_MAP,
        "nodes_v1": ordered,
    }


def merge_unified_agent_router_fault_nodes_v1(
    base: dict[str, Any],
    *,
    decision_node: dict[str, Any] | None,
    governor_snapshot: dict[str, Any] | None,
    review_obj: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    GT_DIRECTIVE_026AI — last three nodes: router, budget/key visibility, external review outcome.
    """
    import copy

    b = base if isinstance(base, dict) else {"schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1, "nodes_v1": []}
    nodes = [copy.deepcopy(x) for x in (b.get("nodes_v1") or []) if isinstance(x, dict)]
    by_id: dict[str, dict[str, Any]] = {str(n.get("node_id") or ""): n for n in nodes}
    d = decision_node if isinstance(decision_node, dict) else {}
    route = str(d.get("final_route_v1") or "local_only")
    reasons = list(d.get("escalation_reason_codes_v1") or [])
    bl = list(d.get("escalation_blockers_v1") or [])
    omsg = str(d.get("operator_message_english_v1") or "").strip()

    if omsg:
        rmsg = omsg
    elif route == "external_blocked_missing_key" or "missing_api_key" in " ".join(bl).lower():
        rmsg = "External review was blocked because the OpenAI API key was not configured."
    elif route == "external_blocked_budget" or any("budget" in str(x) for x in bl):
        rmsg = "External review was blocked because the run budget was exceeded."
    elif not reasons:
        rmsg = "External review was not called because no escalation reason was present."
    elif route == "external_review" and review_obj and reasons:
        rmsg = (
            "External review was called because escalation reasons were present: " + ", ".join(reasons[:6]) + "."
        )
    else:
        rmsg = f"Reasoning router evaluated; final route: {route}."

    def _funding_cause() -> bool:
        return any(
            str(x) in ("insufficient_funds_v1", "quota_exceeded_v1", "budget_exceeded_v1", "token_limit_exceeded_v1")
            for x in bl
        )

    by_id["reasoning_router_evaluated"] = make_fault_node_v1(
        "reasoning_router_evaluated",
        STATUS_PASS if d else STATUS_NOT_PROVEN,
        input_summary_v1="Unified routing policy for this decision.",
        output_summary_v1=route,
        evidence_fields_v1=[
            "final_route_v1",
            "escalation_reason_codes_v1",
            "escalation_blockers_v1",
            "external_api_attempted_v1",
            "external_api_block_reason_v1",
            "external_api_action_url_v1",
            "funding_blocker_suspected_v1",
        ],
        evidence_values_v1={
            "final_route_v1": route,
            "escalation_reason_codes_v1": reasons,
            "escalation_blockers_v1": bl,
            "external_api_attempted_v1": bool(d.get("external_api_attempted_v1")),
            "external_api_block_reason_v1": d.get("external_api_block_reason_v1"),
            "external_api_action_url_v1": d.get("external_api_action_url_v1")
            if d.get("external_api_action_url_v1")
            else None,
            "funding_blocker_suspected_v1": _funding_cause(),
        },
        operator_message_v1=rmsg[:4000],
    )

    g = governor_snapshot if isinstance(governor_snapshot, dict) else {}
    budget_ok = "exhausted" not in str(d.get("budget_status_v1") or "")
    gmsg = (
        "Cost governor allowed an external check under current caps."
        if budget_ok and route == "external_review"
        else "Cost governor held external usage within configured run and token caps (or no external call was made)."
    )
    by_id["external_escalation_governed"] = make_fault_node_v1(
        "external_escalation_governed",
        STATUS_PASS,
        input_summary_v1="Budget, token caps, and key presence (no secret values in evidence).",
        output_summary_v1="Governor state recorded in trace (no API keys).",
        evidence_fields_v1=["budget_status_v1", "governor_snapshot"],
        evidence_values_v1=(
            {
                "budget_status_v1": str(d.get("budget_status_v1") or ""),
                "governor": {k: v for k, v in g.items() if "key" not in k.lower()},
            }
            if g
            else {"budget_status_v1": str(d.get("budget_status_v1") or ""), "governor": {}}
        ),
        operator_message_v1=gmsg,
    )

    if review_obj and isinstance(review_obj, dict):
        disagree = bool(review_obj.get("disagreement_with_local_v1"))
        st_rev = "External review returned structured JSON and was recorded as advisory; engine authority unchanged."
        if disagree:
            st_rev = (
                "External review disagreed with local reasoning, but the final action stayed with the "
                "deterministic engine and validator; models do not take execution here."
            )
        by_id["external_reasoning_review_recorded"] = make_fault_node_v1(
            "external_reasoning_review_recorded",
            STATUS_PASS,
            input_summary_v1="External model review (advisory).",
            output_summary_v1="Recorded",
            evidence_fields_v1=["disagreement_with_local_v1", "schema_valid_v1"],
            evidence_values_v1={
                "disagreement_with_local_v1": disagree,
                "schema_valid_v1": bool(review_obj.get("schema_valid_v1")),
            },
            operator_message_v1=st_rev[:4000],
        )
    else:
        st_skip = "No external review was recorded for this run."
        nstat = STATUS_SKIPPED if route != "external_review" else STATUS_FAIL
        nmsg = st_skip
        if route == "external_review" and not review_obj:
            nmsg = "An external call was attempted but no accepted review was stored (schema or API outcome)."
        by_id["external_reasoning_review_recorded"] = make_fault_node_v1(
            "external_reasoning_review_recorded",
            nstat,
            input_summary_v1="External model review (advisory).",
            output_summary_v1="Not recorded" if route != "external_review" else "Not accepted",
            operator_message_v1=nmsg,
        )

    ordered = [
        by_id.get(nid)
        or make_fault_node_v1(
            nid,
            STATUS_NOT_PROVEN,
            input_summary_v1="—",
            output_summary_v1="—",
            operator_message_v1="Missing node.",
        )
        for nid in NODE_IDS_ORDER
    ]
    return {
        "schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
        "contract_version": CONTRACT_VERSION_FAULT_MAP,
        "nodes_v1": ordered,
    }


def validate_student_reasoning_fault_map_v1(doc: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["student_reasoning_fault_map_v1 must be a dict"]
    if str(doc.get("schema") or "") != SCHEMA_STUDENT_REASONING_FAULT_MAP_V1:
        errs.append("schema must be student_reasoning_fault_map_v1")
    nodes = doc.get("nodes_v1")
    if not isinstance(nodes, list) or len(nodes) != len(NODE_IDS_ORDER):
        errs.append("nodes_v1 must list all nodes in order")
        return errs
    for i, nid in enumerate(NODE_IDS_ORDER):
        n = nodes[i] if i < len(nodes) else None
        if not isinstance(n, dict) or str(n.get("node_id") or "") != nid:
            errs.append(f"nodes_v1[{i}] must be node_id {nid!r}")
            continue
        st = str(n.get("status") or "")
        if st not in ALLOWED_STATUSES:
            errs.append(f"node {nid}: status not allowed: {st!r}")
    return errs


def merge_runtime_fault_nodes_v1(
    base: dict[str, Any],
    *,
    llm_checked_pass: bool,
    llm_error_codes: list[str] | None,
    llm_operator_message: str,
    student_sealed_pass: bool,
    student_seal_error_codes: list[str] | None,
    student_seal_message: str,
    execution_intent_pass: bool,
    execution_intent_error_codes: list[str] | None,
    execution_intent_message: str,
    use_llm_path: bool,
) -> dict[str, Any]:
    """
    Overwrite nodes 8–10 on a fault map that already has seven prefix nodes (or a full map).
    """
    b = base if isinstance(base, dict) else {"schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1, "nodes_v1": []}
    nodes = [dict(x) for x in (b.get("nodes_v1") or []) if isinstance(x, dict)]
    by_id: dict[str, dict[str, Any]] = {str(n.get("node_id") or ""): n for n in nodes}

    if use_llm_path:
        by_id["llm_output_checked"] = make_fault_node_v1(
            "llm_output_checked",
            STATUS_PASS if llm_checked_pass else STATUS_FAIL,
            input_summary_v1="Model output for this decision.",
            output_summary_v1="Accepted by the contract." if llm_checked_pass else "Rejected.",
            error_codes_v1=list(llm_error_codes or []),
            operator_message_v1=llm_operator_message
            or (
                "The model’s answer was accepted and could be merged."
                if llm_checked_pass
                else "The model’s answer did not pass the required checks."
            ),
        )
    else:
        by_id["llm_output_checked"] = make_fault_node_v1(
            "llm_output_checked",
            STATUS_SKIPPED,
            input_summary_v1="Model path.",
            output_summary_v1="Not used for this run.",
            operator_message_v1="This run used the rule-based student path, not a live model call.",
        )

    by_id["student_output_sealed"] = make_fault_node_v1(
        "student_output_sealed",
        STATUS_PASS if student_sealed_pass else STATUS_FAIL,
        input_summary_v1="Student answer and engine merge.",
        output_summary_v1="Sealed student output is ready to store." if student_sealed_pass else "Seal or merge failed.",
        error_codes_v1=list(student_seal_error_codes or []),
        operator_message_v1=student_seal_message
        or ("The student output was sealed and matches the engine." if student_sealed_pass else "The student output could not be sealed."),
    )

    by_id["execution_intent_created"] = make_fault_node_v1(
        "execution_intent_created",
        STATUS_PASS if execution_intent_pass else STATUS_FAIL,
        input_summary_v1="Sealed output plus run identity.",
        output_summary_v1="Execution handoff was built." if execution_intent_pass else "Handoff not built.",
        error_codes_v1=list(execution_intent_error_codes or []),
        operator_message_v1=execution_intent_message
        or (
            "A formal execution handoff was created from the sealed output."
            if execution_intent_pass
            else "A formal execution handoff could not be created from the sealed output."
        ),
    )

    ordered = [
        by_id.get(nid)
        or make_fault_node_v1(
            nid, STATUS_NOT_PROVEN, input_summary_v1="—", output_summary_v1="—", operator_message_v1="Missing node."
        )
        for nid in NODE_IDS_ORDER
    ]
    return {
        "schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
        "contract_version": CONTRACT_VERSION_FAULT_MAP,
        "nodes_v1": ordered,
    }


def merge_lifecycle_reasoning_fault_nodes_v1(
    base: dict[str, Any],
    *,
    context_loaded_ok: bool,
    reasoning_eval_ok: bool,
    decision_ok: bool,
    exit_eval_ok: bool,
    operator_messages: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    GT_DIRECTIVE_026B — set last four fault nodes (after 026AI router nodes) for a lifecycle bar or tape run.
    """
    import copy

    msg = operator_messages if isinstance(operator_messages, dict) else {}
    b = base if isinstance(base, dict) else {"schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1, "nodes_v1": []}
    nodes = [copy.deepcopy(x) for x in (b.get("nodes_v1") or []) if isinstance(x, dict)]
    by_id: dict[str, dict[str, Any]] = {str(n.get("node_id") or ""): n for n in nodes}

    by_id["lifecycle_context_loaded"] = make_fault_node_v1(
        "lifecycle_context_loaded",
        STATUS_PASS if context_loaded_ok else STATUS_FAIL,
        input_summary_v1="Per-bar market + position context for in-trade reasoning.",
        output_summary_v1="Loaded" if context_loaded_ok else "Failed to load",
        operator_message_v1=msg.get(
            "lifecycle_context_loaded", "Entry thesis, PnL state, and bar window are available for lifecycle evaluation."
        )[:4000],
    )
    by_id["lifecycle_reasoning_evaluated"] = make_fault_node_v1(
        "lifecycle_reasoning_evaluated",
        STATUS_PASS if reasoning_eval_ok and context_loaded_ok else (STATUS_FAIL if not reasoning_eval_ok else STATUS_SKIPPED),
        input_summary_v1="Thesis, indicators, memory over the open trade.",
        output_summary_v1="Eval record produced" if reasoning_eval_ok else "Missing or failed",
        operator_message_v1=msg.get(
            "lifecycle_reasoning_evaluated", "Thesis and risk are compared to current tape each bar (deterministic)."
        )[:4000],
    )
    by_id["lifecycle_decision_made"] = make_fault_node_v1(
        "lifecycle_decision_made",
        STATUS_PASS if decision_ok and reasoning_eval_ok else (STATUS_FAIL if not decision_ok else STATUS_SKIPPED),
        input_summary_v1="Explicit hold/exit/force_exit decision.",
        output_summary_v1="Decision recorded" if decision_ok else "Not recorded",
        operator_message_v1=msg.get(
            "lifecycle_decision_made", "Engine chose hold, exit, or force_exit; no silent continuation between bars."
        )[:4000],
    )
    by_id["lifecycle_exit_evaluated"] = make_fault_node_v1(
        "lifecycle_exit_evaluated",
        STATUS_PASS if exit_eval_ok and decision_ok else (STATUS_FAIL if not exit_eval_ok else STATUS_SKIPPED),
        input_summary_v1="When closing, reason codes and last-bar evaluation.",
        output_summary_v1="Exit state evaluated" if exit_eval_ok else "Not evaluated",
        operator_message_v1=msg.get(
            "lifecycle_exit_evaluated", "Stops, targets, time cap, and thesis lines are applied in fixed order (deterministic)."
        )[:4000],
    )
    if not context_loaded_ok:
        by_id["lifecycle_reasoning_evaluated"] = make_fault_node_v1(
            "lifecycle_reasoning_evaluated", STATUS_SKIPPED, input_summary_v1="—", output_summary_v1="—",
            operator_message_v1="Earlier lifecycle step did not pass.",
        )
        by_id["lifecycle_decision_made"] = make_fault_node_v1(
            "lifecycle_decision_made", STATUS_SKIPPED, input_summary_v1="—", output_summary_v1="—",
            operator_message_v1="Not reached: lifecycle context did not load.",
        )
        by_id["lifecycle_exit_evaluated"] = make_fault_node_v1(
            "lifecycle_exit_evaluated", STATUS_SKIPPED, input_summary_v1="—", output_summary_v1="—",
            operator_message_v1="Not reached: lifecycle context did not load.",
        )

    ordered = [
        by_id.get(nid)
        or make_fault_node_v1(
            nid, STATUS_NOT_PROVEN, input_summary_v1="—", output_summary_v1="—", operator_message_v1="Missing node."
        )
        for nid in NODE_IDS_ORDER
    ]
    return {
        "schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
        "contract_version": CONTRACT_VERSION_FAULT_MAP,
        "nodes_v1": ordered,
    }


def attach_fault_map_v1(
    target: dict[str, Any] | None,
    fault_map: dict[str, Any] | None,
) -> None:
    if not isinstance(target, dict) or not isinstance(fault_map, dict):
        return
    target["student_reasoning_fault_map_v1"] = fault_map
    if isinstance(target.get("entry_reasoning_eval_v1"), dict):
        target["entry_reasoning_eval_v1"]["student_reasoning_fault_map_v1"] = copy_fault_map(fault_map)


def copy_fault_map(fm: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(fm)


__all__ = [
    "SCHEMA_STUDENT_REASONING_FAULT_MAP_V1",
    "CONTRACT_VERSION_FAULT_MAP",
    "NODE_IDS_ORDER",
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_SKIPPED",
    "STATUS_NOT_PROVEN",
    "ALLOWED_STATUSES",
    "make_fault_node_v1",
    "skipped_nodes_from_index_v1",
    "build_fault_map_v1",
    "merge_unified_agent_router_fault_nodes_v1",
    "merge_lifecycle_reasoning_fault_nodes_v1",
    "validate_student_reasoning_fault_map_v1",
    "merge_runtime_fault_nodes_v1",
    "attach_fault_map_v1",
    "copy_fault_map",
]
