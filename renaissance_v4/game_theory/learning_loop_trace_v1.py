"""
Learning Loop Trace — LangGraph-style **structured** execution graph for the Student path.

**Truth label:** this is a **reconstructed learning trace** (scorecard + batch + learning API), not a
captured execution timeline. Runtime handoffs belong in ``learning_trace_events_v1`` (merged by
the debug API when present).

Operator payload: ``build_learning_loop_trace_v1(job_id)`` → nodes + edges + blunt health banner.
Operator HTML: ``GET /debug/learning-loop`` (legacy ``GET /learning-loop-trace`` redirects there).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
)
from renaissance_v4.game_theory.scorecard_drill import (
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    load_batch_parallel_results_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_HOLD,
    GOVERNANCE_PROMOTE,
    GOVERNANCE_REJECT,
    build_student_panel_run_learning_payload_v1,
)
from renaissance_v4.game_theory.training_exam_audit_v1 import build_training_exam_audit_v1

SCHEMA = "learning_loop_trace_v1"

NodeStatus = Literal["pass", "fail", "skipped", "unknown", "partial"]
EdgeFlow = Literal["ok", "blocked", "skipped", "unknown"]

_HEALTH_BROKEN = "LEARNING LOOP BROKEN"
_HEALTH_HEALTHY = "LEARNING LOOP HEALTHY"
_HEALTH_INCONCLUSIVE = "LEARNING LOOP INCONCLUSIVE"
_HEALTH_NOT_CONFIGURED = "LEARNING NOT CONFIGURED"


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _node(
    node_id: str,
    label: str,
    status: NodeStatus,
    summary: str,
    sources: list[str],
    evidence: dict[str, Any],
    *,
    evidence_provenance_v1: list[str] | None = None,
    runtime_breakpoints_v1: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": node_id,
        "label": label,
        "node_status_v1": status,
        "summary_v1": summary,
        "source_fields_v1": sources,
        "evidence_v1": evidence,
    }
    if evidence_provenance_v1:
        out["evidence_provenance_v1"] = list(evidence_provenance_v1)
    if runtime_breakpoints_v1:
        out["runtime_breakpoints_v1"] = list(runtime_breakpoints_v1)
    return out


def ensure_node_evidence_provenance_defaults_v1(nodes: list[dict[str, Any]]) -> None:
    """Fill ``evidence_provenance_v1`` when missing (does not overwrite explicit capture merge)."""
    defaults: dict[str, list[str]] = {
        "run_started": ["scorecard"],
        "run_config": ["scorecard"],
        "packet_build": ["batch_artifact", "scorecard"],
        "memory_retrieval": ["scorecard"],
        "llm_reasoning": ["scorecard"],
        "student_decision": ["scorecard"],
        "referee_student_output_coupling": ["unknown"],
        "referee_execution": ["scorecard"],
        "ep_grading": ["scorecard"],
        "governance_018": ["learning_store"],
        "learning_store": ["scorecard", "learning_store"],
        "future_retrieval": ["learning_store"],
        "decision_delta_vs_baseline": ["unknown", "l3"],
    }
    for n in nodes:
        nid = str(n.get("id") or "")
        if n.get("evidence_provenance_v1"):
            continue
        n["evidence_provenance_v1"] = list(defaults.get(nid, ["unknown"]))


def _edge(frm: str, to: str, flow: EdgeFlow, detail: str) -> dict[str, Any]:
    return {"from_node": frm, "to_node": to, "edge_flow_v1": flow, "detail_v1": detail}


def _fault_focus_v1(
    *,
    job_id: str,
    entry: dict[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    tea: dict[str, Any],
) -> dict[str, Any]:
    """
    Single object for **human + AI** triage: first hard failure, blocked hop, training verdict echo,
    and optional **intelligence vs floor** trade-win parity (non-baseline profile but TW% == Sys BL).
    """
    first_fail_id = None
    first_fail_label = None
    for n in nodes:
        if str(n.get("node_status_v1") or "") == "fail":
            first_fail_id = n.get("id")
            first_fail_label = n.get("label")
            break
    blocked: dict[str, Any] | None = None
    for e in edges:
        if str(e.get("edge_flow_v1") or "") == "blocked":
            blocked = {
                "from_node": e.get("from_node"),
                "to_node": e.get("to_node"),
                "detail_v1": e.get("detail_v1"),
            }
            break

    tea_verdict = str(tea.get("training_learning_verdict_v1") or "")
    if first_fail_label and first_fail_id:
        headline = f"First failing stage: {first_fail_label} ({first_fail_id})."
    elif blocked:
        headline = (
            f"Flow blocked before {blocked.get('to_node')!r} "
            f"(from {blocked.get('from_node')!r}) — {blocked.get('detail_v1') or 'see edges_v1'}."
        )
    elif tea_verdict in ("ENGAGEMENT_WITHOUT_STORE_WRITES", "NO_SCORECARD_EVIDENCE_OF_STUDENT_PATH"):
        headline = str(tea.get("training_learning_verdict_reason_v1") or tea_verdict)[:400]
    else:
        headline = (
            "No explicit node_status_v1=fail — use learning_loop_health_banner_v1 "
            "and partial/unknown nodes for the story."
        )

    prof = str(
        entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or ""
    ).strip()
    intelligence_floor: dict[str, Any] | None = None
    if prof and prof != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
        try:
            from renaissance_v4.game_theory.student_panel_d11 import fetch_d11_run_rows_v1

            d11_row = next(
                (x for x in fetch_d11_run_rows_v1(limit=200) if str(x.get("run_id") or "") == job_id),
                None,
            )
        except (OSError, TypeError, ValueError):
            d11_row = None
        if isinstance(d11_row, dict):
            beats = d11_row.get("beats_system_baseline_trade_win")
            tw = d11_row.get("run_trade_win_percent")
            bl = d11_row.get("harness_baseline_trade_win_percent")
            if beats == "—":
                intelligence_floor = {
                    "code": "ANCHOR_OR_NO_BASELINE_COMPARE",
                    "detail": "This row is the fingerprint anchor or Sys BL % is unavailable — exact tie vs floor does not apply.",
                }
            elif (
                beats == "="
                and isinstance(tw, (int, float))
                and isinstance(bl, (int, float))
                and abs(float(tw) - float(bl)) < 1e-9
            ):
                intelligence_floor = {
                    "code": "INTELLIGENCE_NON_BASELINE_EXACT_TIE_TO_SYS_BL",
                    "detail": (
                        "Non-baseline brain profile, but batch trade win % exactly equals the same-fingerprint "
                        "system baseline (Sys BL). The intelligence lane did not change Referee-visible trade "
                        "outcomes vs the no-intelligence floor on this run (or the counterfactual never diverged)."
                    ),
                    "student_brain_profile_v1": prof,
                    "run_trade_win_percent": float(tw),
                    "harness_baseline_trade_win_percent": float(bl),
                }
                headline = (
                    "FAULT FOCUS — Trade win % tied the intelligence floor (Sys BL) on a non-baseline profile. "
                    + headline
                )

    return {
        "schema": "fault_focus_v1",
        "job_id": job_id,
        "first_failed_node_id": first_fail_id,
        "first_failed_node_label": first_fail_label,
        "first_blocked_edge_v1": blocked,
        "headline_one_liner_v1": headline[:500],
        "intelligence_floor_trade_win_v1": intelligence_floor,
        "training_learning_verdict_echo_v1": tea_verdict,
        "for_collaboration_v1": (
            f"Share job_id={job_id!r} plus JSON key fault_focus_v1 (or full GET …/learning-loop-trace) "
            "so operators and AI agree on the same fault object."
        ),
    }


def _flow_from_status(up: NodeStatus, down: NodeStatus) -> tuple[EdgeFlow, str]:
    if up == "fail":
        return "blocked", "Upstream stage failed — downstream may be stale or bypassed."
    if up == "skipped":
        return "skipped", "Upstream skipped — branch not applicable for this run."
    if up == "unknown" or down == "unknown":
        return "unknown", "Insufficient evidence on scorecard or batch artifacts for this hop."
    if up == "partial" or down == "partial":
        return "ok", "Data flowed with partial / weak signals (see node summaries)."
    return "ok", "Scorecard and batch fields consistent with data reaching the next stage."


def rebuild_linear_edges_v1(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rebuild ``edges_v1`` after inserting or reordering nodes (same rules as initial trace)."""
    edges: list[dict[str, Any]] = []
    order = [str(n.get("id") or "") for n in nodes if n.get("id")]
    for i in range(len(order) - 1):
        a = nodes[i]["node_status_v1"]
        b = nodes[i + 1]["node_status_v1"]
        fl, det = _flow_from_status(a, b)  # type: ignore[arg-type]
        edges.append(_edge(order[i], order[i + 1], fl, det))
    return edges


def build_learning_loop_trace_v1(job_id: str) -> dict[str, Any]:
    """
    Build a deterministic trace graph for one ``job_id`` (scorecard + GT018 + batch dir when present).
    """
    jid = str(job_id or "").strip()
    if not jid:
        return {
            "schema": SCHEMA,
            "ok": False,
            "error": "job_id required",
            "job_id": "",
            "page_title_v1": "Learning Loop Trace",
            "page_subtitle_v1": "LangGraph-style visual proof of whether the Student learned or where the loop broke.",
            "learning_loop_health_banner_v1": _HEALTH_INCONCLUSIVE,
            "learning_loop_health_detail_v1": "Missing job_id.",
            "fault_focus_v1": {
                "schema": "fault_focus_v1",
                "headline_one_liner_v1": "Missing job_id — cannot locate a scorecard line.",
            },
            "nodes_v1": [],
            "edges_v1": [],
        }

    entry = find_scorecard_entry_by_job_id(jid)
    if not isinstance(entry, dict):
        return {
            "schema": SCHEMA,
            "ok": False,
            "error": "Unknown job_id",
            "job_id": jid,
            "page_title_v1": "Learning Loop Trace",
            "page_subtitle_v1": "LangGraph-style visual proof of whether the Student learned or where the loop broke.",
            "learning_loop_health_banner_v1": _HEALTH_INCONCLUSIVE,
            "learning_loop_health_detail_v1": "No scorecard line for this job_id.",
            "fault_focus_v1": {
                "schema": "fault_focus_v1",
                "job_id": jid,
                "headline_one_liner_v1": "Unknown job_id — nothing to trace in batch_scorecard.jsonl.",
            },
            "nodes_v1": [],
            "edges_v1": [],
        }

    status = str(entry.get("status") or "").strip().lower()
    oba = entry.get("operator_batch_audit")
    cmem = str(oba.get("context_signature_memory_mode") or "").strip().lower() if isinstance(oba, dict) else ""
    prof = str(
        entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or ""
    ).strip()
    llm_prof = prof == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1

    batch_dir, _scenarios, batch_err = build_scenario_list_for_batch(
        jid, entry.get("session_log_batch_dir") if isinstance(entry.get("session_log_batch_dir"), str) else None
    )
    payload = load_batch_parallel_results_v1(batch_dir) if batch_dir and batch_dir.is_dir() else None
    scenarios_n = 0
    if isinstance(payload, dict):
        scenarios_n = len(payload.get("scenarios") or payload.get("results") or [])  # type: ignore[arg-type]

    mci = entry.get("memory_context_impact_audit_v1")
    mem_yes = isinstance(mci, dict) and str(mci.get("memory_impact_yes_no") or "").upper() == "YES"
    recall_sum = _int(mci.get("recall_match_windows_total_sum"), 0) if isinstance(mci, dict) else 0

    retr = _int(entry.get("student_retrieval_matches"), 0)
    rows_app = _int(entry.get("student_learning_rows_appended"), 0)
    llm_ex = entry.get("student_llm_execution_v1")
    ollama_ok = _int(llm_ex.get("ollama_trades_succeeded"), 0) if isinstance(llm_ex, dict) else 0
    ollama_att = _int(llm_ex.get("ollama_trades_attempted"), 0) if isinstance(llm_ex, dict) else 0
    llm_rej = _int(entry.get("llm_student_output_rejections_v1"), 0)

    learn = build_student_panel_run_learning_payload_v1(jid)
    run_gov = learn.get("learning_governance_v1") if isinstance(learn, dict) else None
    gov_dec = (
        str(run_gov.get("decision") or "").strip().lower()
        if isinstance(run_gov, dict)
        else ""
    )
    run_was_stored = bool(learn.get("run_was_stored")) if isinstance(learn, dict) else False
    eligible_retrieval = bool(learn.get("eligible_for_retrieval")) if isinstance(learn, dict) else False
    stored_n = _int(learn.get("stored_record_count_v1"), 0) if isinstance(learn, dict) else 0

    tea = build_training_exam_audit_v1(entry)
    tea_verdict = str(tea.get("training_learning_verdict_v1") or "")

    total_proc = _int(entry.get("total_processed"), 0)

    exam_e = entry.get("exam_e_score_v1")
    exam_p = entry.get("exam_p_score_v1")
    exam_pass = entry.get("exam_pass_v1")

    # --- nodes ---
    nodes: list[dict[str, Any]] = []

    if status == "done":
        ns: NodeStatus = "pass"
        sm = "Batch finished with status done — Referee + replay workers completed for submitted scenarios."
    elif status == "error":
        ns = "fail"
        sm = f"Batch error — {str(entry.get('error') or 'unknown')[:200]}"
    elif status == "cancelled":
        ns = "partial"
        sm = "Batch cancelled mid-flight — aggregates may be partial."
    elif status == "preflight":
        ns = "unknown"
        sm = "RM preflight gate — parallel workers have not started yet."
    elif status == "running":
        ns = "unknown"
        sm = "Run still in flight — scorecard line may be incomplete."
    else:
        ns = "unknown"
        sm = f"Unexpected status {status!r}."

    nodes.append(
        _node(
            "run_started",
            "Run started",
            ns,
            sm,
            ["scorecard_line.status", "scorecard_line.job_id"],
            {"status": status, "job_id": jid, "total_processed": total_proc},
        )
    )

    if isinstance(oba, dict) and oba:
        cfg_status: NodeStatus = "pass" if cmem in ("read", "read_write") else "partial"
        cfg_sm = (
            f"Operator batch audit present — context_signature_memory_mode={cmem or 'off'}."
            if cmem
            else "Operator batch audit present but memory mode off or empty — Student lane may be inactive."
        )
        nodes.append(
            _node(
                "run_config",
                "Run config",
                cfg_status,
                cfg_sm,
                ["scorecard_line.operator_batch_audit.context_signature_memory_mode"],
                {"context_signature_memory_mode": cmem or None, "student_brain_profile_v1": prof or None},
            )
        )
    else:
        nodes.append(
            _node(
                "run_config",
                "Run config",
                "partial",
                "No operator_batch_audit on scorecard — recipe/window echo may live only in session logs.",
                ["scorecard_line.operator_batch_audit"],
                {},
            )
        )

    if payload and scenarios_n > 0:
        pkt: NodeStatus = "pass"
        pkt_sm = f"batch_parallel_results_v1 present with {scenarios_n} scenario slot(s)."
    elif batch_dir and batch_dir.is_dir():
        pkt = "partial"
        pkt_sm = "Session folder exists but parallel results JSON missing or empty — packet incomplete."
    else:
        pkt = "unknown" if status == "done" else "skipped"
        pkt_sm = (
            batch_err or "No batch folder or batch_parallel_results_v1 — cannot verify worker packet."
        )
    nodes.append(
        _node(
            "packet_build",
            "Packet build",
            pkt,
            pkt_sm,
            ["session_log_batch_dir", "batch_parallel_results_v1"],
            {"batch_dir": str(batch_dir) if batch_dir else None, "scenario_rows": scenarios_n},
        )
    )

    if cmem not in ("read", "read_write"):
        mr: NodeStatus = "skipped"
        mr_sm = "Memory lane off — retrieval not expected on Student path for this configuration."
    elif retr > 0:
        mr = "pass"
        mr_sm = f"Retrieval engaged — student_retrieval_matches={retr}."
    elif mem_yes or recall_sum > 0:
        mr = "partial"
        mr_sm = "Harness recall counters moved but zero explicit retrieval matches on scorecard."
    else:
        mr = "fail" if llm_prof else "partial"
        mr_sm = (
            "No retrieval matches on this scorecard line — prior Student rows may not have matched context."
            if not llm_prof
            else "LLM profile but zero retrieval matches — check context slices and store."
        )
    nodes.append(
        _node(
            "memory_retrieval",
            "Memory retrieval",
            mr,
            mr_sm,
            ["scorecard_line.student_retrieval_matches", "memory_context_impact_audit_v1"],
            {"student_retrieval_matches": retr},
        )
    )

    if not llm_prof:
        llm_st: NodeStatus = "skipped"
        llm_sm = f"Brain profile {prof or '—'} — Ollama / LLM thesis lane not selected."
    elif ollama_ok > 0:
        llm_st = "pass"
        llm_sm = f"LLM sealed trades succeeded: {ollama_ok} (attempted {ollama_att})."
    elif ollama_att > 0:
        llm_st = "fail"
        llm_sm = f"LLM attempted {ollama_att} trade(s) with zero successes; rejections={llm_rej}."
    else:
        llm_st = "partial"
        llm_sm = "LLM profile active but no ollama trade attempts on scorecard — model may not have run on closed trades."
    nodes.append(
        _node(
            "llm_reasoning",
            "LLM reasoning",
            llm_st,
            llm_sm,
            ["scorecard_line.student_llm_execution_v1", "llm_student_output_rejections_v1"],
            {"ollama_trades_succeeded": ollama_ok, "ollama_trades_attempted": ollama_att},
        )
    )

    dcf = entry.get("student_output_fingerprint")
    if isinstance(dcf, str) and dcf.strip():
        sd_st: NodeStatus = "partial"
        sd_sm = "Student output fingerprint recorded on scorecard — compare to baseline in L3 per trade."
    elif rows_app > 0 or retr > 0:
        sd_st = "partial"
        sd_sm = "Handoff signals without fingerprint — use L3 decision_changed_flag per trade."
    else:
        sd_st = "unknown"
        sd_sm = "No fingerprint and no store/retrieval proof at run grain — open L3 for decision deltas."
    nodes.append(
        _node(
            "student_decision",
            "Student decision",
            sd_st,
            sd_sm,
            ["scorecard_line.student_output_fingerprint"],
            {"fingerprint_present": bool(isinstance(dcf, str) and dcf.strip())},
        )
    )

    nodes.append(
        _node(
            "referee_student_output_coupling",
            "Referee use of Student output",
            "unknown",
            "NOT PROVEN — no runtime ``learning_trace_events_v1`` (or equivalent persisted coupling) "
            "proves Referee consumed vs ignored Student thesis; scorecard aggregates are insufficient.",
            [
                "learning_trace_events_v1 (stage referee_used_student_output)",
                "per-trade worker coupling audit (future)",
            ],
            {
                "verdict_v1": "NOT_PROVEN",
                "detail_v1": "Reconstructed trace cannot certify influence; workers must emit capture events.",
            },
            evidence_provenance_v1=["unknown"],
            runtime_breakpoints_v1=["not_captured_at_runtime_v1"],
        )
    )

    if total_proc <= 0 and status == "done":
        rf: NodeStatus = "fail"
        rf_sm = "total_processed is zero despite done — Referee row aggregate missing."
    elif total_proc > 0:
        rf = "pass"
        rf_sm = f"Referee path completed scenarios: total_processed={total_proc}."
    else:
        rf = "unknown"
        rf_sm = "Cannot assert Referee completion from scorecard totals."
    nodes.append(
        _node(
            "referee_execution",
            "Referee execution",
            rf,
            rf_sm,
            ["scorecard_line.total_processed", "scorecard_line.avg_trade_win_pct"],
            {
                "total_processed": total_proc,
                "avg_trade_win_pct": entry.get("avg_trade_win_pct"),
            },
        )
    )

    if exam_e is not None or exam_p is not None or exam_pass is not None:
        eg: NodeStatus = "pass"
        eg_sm = "Exam-pack E/P (or pass) present on scorecard for this run."
    elif status != "done":
        eg = "skipped"
        eg_sm = "Batch not done — exam grading may not apply."
    else:
        eg = "partial"
        eg_sm = "No exam_e_score_v1 / exam_p_score_v1 on line — grading absent or not denormalized."
    nodes.append(
        _node(
            "ep_grading",
            "E / P grading",
            eg,
            eg_sm,
            ["scorecard_line.exam_e_score_v1", "exam_p_score_v1", "exam_pass_v1"],
            {"exam_e_score_v1": exam_e, "exam_p_score_v1": exam_p, "exam_pass_v1": exam_pass},
        )
    )

    if gov_dec == GOVERNANCE_PROMOTE:
        gv: NodeStatus = "pass"
        gv_sm = "GT018 aggregate governance: promote — rows eligible for default retrieval weighting."
    elif gov_dec == GOVERNANCE_HOLD:
        gv = "partial"
        gv_sm = "GT018 aggregate: hold — promotion deferred (sample or policy thresholds)."
    elif gov_dec == GOVERNANCE_REJECT:
        gv = "fail"
        gv_sm = "GT018 aggregate: reject — governance blocked promotion for at least one trade slice."
    else:
        gv = "unknown"
        gv_sm = "Governance decision missing or empty — learning API may be incomplete."
    nodes.append(
        _node(
            "governance_018",
            "018 governance",
            gv,
            gv_sm,
            ["GET /api/student-panel/run/<job_id>/learning → learning_governance_v1"],
            run_gov if isinstance(run_gov, dict) else {},
        )
    )

    if rows_app > 0:
        ls: NodeStatus = "pass"
        ls_sm = f"Learning rows appended for this job: {rows_app}."
    elif run_was_stored:
        ls = "pass"
        ls_sm = f"Store lists {stored_n} record(s) for this run_id (append path may predate counter field)."
    elif retr > 0 or ollama_ok > 0:
        ls = "fail"
        ls_sm = "Engagement without append — loop broke before durable store write (see training_exam_audit_v1)."
    else:
        ls = "partial"
        ls_sm = "No append counter and no stored rows for this run — Student store not proven."
    nodes.append(
        _node(
            "learning_store",
            "Learning store append",
            ls,
            ls_sm,
            ["scorecard_line.student_learning_rows_appended", "stored_record_count_v1"],
            {"student_learning_rows_appended": rows_app, "stored_record_count_v1": stored_n},
        )
    )

    if not run_was_stored and rows_app <= 0:
        fr: NodeStatus = "skipped"
        fr_sm = "No stored learning rows for this run — future retrieval cannot use this run yet."
    elif eligible_retrieval:
        fr = "pass"
        fr_sm = "At least one stored row is eligible for cross-run retrieval (promote / legacy)."
    else:
        fr = "partial"
        fr_sm = "Rows exist but none marked retrieval-eligible (hold/reject governance on stored lines)."
    nodes.append(
        _node(
            "future_retrieval",
            "Future retrieval impact",
            fr,
            fr_sm,
            ["eligible_for_retrieval", "run_was_stored"],
            {"eligible_for_retrieval": eligible_retrieval, "run_was_stored": run_was_stored},
        )
    )

    ensure_node_evidence_provenance_defaults_v1(nodes)
    edges = rebuild_linear_edges_v1(nodes)

    # --- top banner from training audit (single source of truth for "did store learn?") ---
    if tea_verdict == "STUDENT_LANE_NOT_CONFIGURED_OR_OFF":
        banner = _HEALTH_NOT_CONFIGURED
        detail = tea.get("training_learning_verdict_reason_v1") or "Memory / Student lane off."
    elif status == "error":
        banner = _HEALTH_BROKEN
        detail = "Batch failed before a trustworthy learning trace."
    elif status in ("cancelled",) or tea_verdict == "INSUFFICIENT_BATCH_STATUS":
        banner = _HEALTH_INCONCLUSIVE
        detail = tea.get("training_learning_verdict_reason_v1") or "Incomplete batch status."
    elif tea_verdict == "PERSISTED_LEARNING_ROWS":
        banner = _HEALTH_HEALTHY
        detail = "Store append counter proves at least one learning row for this job_id."
    elif tea_verdict in ("ENGAGEMENT_WITHOUT_STORE_WRITES", "NO_SCORECARD_EVIDENCE_OF_STUDENT_PATH"):
        banner = _HEALTH_BROKEN
        detail = tea.get("training_learning_verdict_reason_v1") or "Student path did not complete to persistence."
    elif tea_verdict == "HARNESS_MEMORY_COUNTERS_ONLY":
        banner = _HEALTH_INCONCLUSIVE
        detail = "Harness memory moved; Student store / retrieval flags weak on scorecard."
    else:
        banner = _HEALTH_INCONCLUSIVE
        detail = tea.get("training_learning_verdict_reason_v1") or "See per-node statuses."

    fault_focus = _fault_focus_v1(job_id=jid, entry=entry, nodes=nodes, edges=edges, tea=tea)

    return {
        "schema": SCHEMA,
        "ok": True,
        "job_id": jid,
        "page_title_v1": "Learning Loop Trace",
        "page_subtitle_v1": "LangGraph-style visual proof of whether the Student learned or where the loop broke.",
        "learning_loop_health_banner_v1": banner,
        "learning_loop_health_detail_v1": detail,
        "fault_focus_v1": fault_focus,
        "training_exam_audit_v1": tea,
        "nodes_v1": nodes,
        "edges_v1": edges,
        "trace_classification_v1": {
            "display_mode_v1": "reconstructed_learning_trace",
            "capture_schema_v1": "learning_trace_event_v1",
            "note_v1": (
                "Graph is derived post-run from scorecard, batch artifacts, and learning API — "
                "not a captured execution trace. Merge ``learning_trace_events_v1`` in the debug API "
                "when runtime events exist."
            ),
        },
        # Echo for callers (e.g. debug trace) so they do not re-scan scorecard for the same row.
        "scorecard_line_v1": dict(entry),
    }


def read_learning_loop_trace_page_html_v1() -> str:
    """Standalone operator page (Learning Loop Trace) shipped next to this module."""
    p = Path(__file__).resolve().parent / "learning_loop_trace_page_v1.html"
    return p.read_text(encoding="utf-8")


__all__ = [
    "SCHEMA",
    "build_learning_loop_trace_v1",
    "ensure_node_evidence_provenance_defaults_v1",
    "read_learning_loop_trace_page_html_v1",
    "rebuild_linear_edges_v1",
]
