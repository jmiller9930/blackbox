"""
GT_DIRECTIVE_026L — Causal learning-loop proof graph (read-only, artifact-backed).

Node-by-node validation: Run A → memory → Run B → reasoning → decision → execution → score.
No execution or reasoning engine changes; consumes stored scorecard, learning store, traces, batch results.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.learning_flow_validator_v1 import (
    _collect_record_ids_for_run,
    _first_intent_row,
    _first_scr_block,
    _load_run_ctx,
    _stages_of,
    _trace_proves_b_retrieved_from_a,
    _walk_mentions,
)
from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl
from renaissance_v4.game_theory.pml_runtime_layout import pml_runtime_root
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_panel_d13 import _ordered_parallel_rows
from renaissance_v4.game_theory.student_panel_l1_road_v1 import (
    line_e_value_for_l1_v1,
    line_p_value_for_l1_v1,
    scorecard_line_fingerprint_sha256_40_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    memory_retrieval_eligible_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    list_student_learning_records_by_run_id,
    default_student_learning_store_path_v1,
)

SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1 = "learning_loop_proof_graph_v1"
CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1 = 1

MATERIALIZE_LEARNING_LOOP_PROOF_V1 = "MATERIALIZE_LEARNING_LOOP_PROOF_V1"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIPPED = "SKIPPED"
STATUS_NOT_PROVEN = "NOT_PROVEN"

VERDICT_LEARNING_CONFIRMED = "LEARNING_CONFIRMED"
VERDICT_LEARNING_NOT_CONFIRMED = "LEARNING_NOT_CONFIRMED"
VERDICT_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

PRODUCER = "learning_loop_proof_graph_v1"

# --- Breakpoint codes (v1) — must match directive ---

BP_RUN_A_MISSING = "run_a_missing_v1"
BP_RUN_A_NOT_DONE = "run_a_not_done_v1"
BP_RUN_A_REASONING_MISSING = "run_a_reasoning_missing_v1"
BP_RUN_A_STUDENT_EXECUTION_MISSING = "run_a_student_execution_missing_v1"
BP_RUN_A_SCORE_MISSING = "run_a_score_missing_v1"
BP_LEARNING_RECORD_MISSING = "learning_record_missing_v1"
BP_GOVERNANCE_MISSING = "governance_missing_v1"
BP_MEMORY_NOT_PROMOTED = "memory_not_promoted_v1"
BP_MEMORY_MISSING_REUSE_FIELDS = "memory_missing_reuse_fields_v1"
BP_RUN_B_MISSING = "run_b_missing_v1"
BP_RUN_B_NOT_DONE = "run_b_not_done_v1"
BP_RUN_B_DID_NOT_RETRIEVE = "run_b_did_not_retrieve_run_a_memory_v1"
BP_MEMORY_NOT_IN_PACKET = "memory_not_in_student_packet_v1"
BP_MEMORY_NOT_IN_REASONING = "memory_not_considered_by_reasoning_v1"
BP_MEMORY_HAD_NO_EFFECT = "memory_had_no_effect_v1"
BP_DECISION_NOT_CHANGED = "decision_not_changed_v1"
BP_EXECUTION_NOT_CHANGED = "execution_not_changed_v1"
BP_SCORE_NOT_CHANGED = "score_not_changed_v1"
BP_INSUFFICIENT_BASELINE = "insufficient_comparison_baseline_v1"
BP_TIMEFRAME_MISMATCH = "timeframe_mismatch_v1"
BP_FINGERPRINT_MISMATCH = "fingerprint_mismatch_v1"


def _verdict_loop_broken(node_id: str) -> str:
    return f"LOOP_BROKEN_AT_NODE_{node_id}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ere_digest(so: dict[str, Any] | None) -> str | None:
    if not isinstance(so, dict):
        return None
    ere = so.get("entry_reasoning_eval_v1")
    if not isinstance(ere, dict):
        return None
    d = ere.get("entry_reasoning_eval_digest_v1")
    return str(d).strip() if isinstance(d, str) and d.strip() else None


def _intent_digest_from_payload(payload: dict[str, Any] | None) -> str | None:
    row = _first_intent_row(payload)
    if not row:
        return None
    scr = row.get("student_controlled_replay_v1")
    if not isinstance(scr, dict):
        return None
    d = scr.get("student_execution_intent_digest_v1")
    return str(d).strip() if isinstance(d, str) and d.strip() else None


def _outcomes_hash_from_payload(payload: dict[str, Any] | None) -> str | None:
    scr = _first_scr_block(payload)
    if not isinstance(scr, dict):
        return None
    h = scr.get("outcomes_hash_v1") or scr.get("student_outcomes_hash_v1")
    return str(h).strip() if isinstance(h, str) and h.strip() else None


def _derive_memory_effect_label_v1(ere: dict[str, Any] | None) -> str:
    """Map stored reasoning memory fields to directive effect vocabulary (read-only)."""
    if not isinstance(ere, dict):
        return "no_effect"
    mctx = ere.get("memory_context_eval_v1")
    if not isinstance(mctx, dict):
        return "no_effect"
    scored = mctx.get("scored_records_v1")
    if not isinstance(scored, list) or not scored:
        return "no_effect"
    agg = str(mctx.get("aggregate_memory_effect_v1") or "none")
    ds = ere.get("decision_synthesis_v1")
    action = str((ds or {}).get("action") or "") if isinstance(ds, dict) else ""
    if agg == "conflict" and action == "no_trade":
        return "blocked_trade"
    if agg in ("aligned", "partial") and action in ("enter_long", "enter_short"):
        return "changed_action"
    if agg == "aligned":
        return "increased_confidence"
    if agg == "conflict":
        return "decreased_confidence"
    return "no_effect"


def _scored_memory_id_lists_v1(
    ere: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    """Return (seen_ids, used_ids, rejected_ids) from ``scored_records_v1`` rows."""
    if not isinstance(ere, dict):
        return [], [], []
    mctx = ere.get("memory_context_eval_v1")
    if not isinstance(mctx, dict):
        return [], [], []
    raw = mctx.get("scored_records_v1")
    if not isinstance(raw, list):
        return [], [], []
    seen: list[str] = []
    used: list[str] = []
    rejected: list[str] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("record_id") or "").strip()
        if not rid:
            continue
        seen.append(rid)
        cl = str(row.get("memory_effect_class_v1") or "").strip().lower()
        if cl == "ignore":
            rejected.append(rid)
        else:
            used.append(rid)
    return seen, used, rejected


def _first_learning_row_with_reasoning(
    run_id: str, store_path: Path
) -> dict[str, Any] | None:
    for d in list_student_learning_records_by_run_id(store_path, run_id):
        so = d.get("student_output")
        if not isinstance(so, dict):
            continue
        if isinstance(so.get("entry_reasoning_eval_v1"), dict):
            return d
    return None


def _node(
    node_id: str,
    node_type: str,
    status: str,
    *,
    evidence_fields: list[str],
    evidence_values: dict[str, Any],
    provenance: list[str],
    explanation: str,
    required: bool,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "status": status,
        "producer": PRODUCER,
        "evidence_fields_v1": evidence_fields,
        "evidence_values_v1": evidence_values,
        "evidence_provenance_v1": provenance,
        "explanation_v1": explanation,
        "required_for_learning_v1": required,
    }


def _linear_edges(node_ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(len(node_ids) - 1):
        out.append(
            {
                "edge_id": f"edge_{i+1:02d}_v1",
                "from_node_id": node_ids[i],
                "to_node_id": node_ids[i + 1],
            }
        )
    return out


def _plain_summary(g: dict[str, Any]) -> str:
    v = g.get("final_verdict_v1")
    bps = g.get("breakpoints_v1") or []
    n_map = {n["node_id"]: n for n in (g.get("nodes_v1") or []) if isinstance(n, dict)}
    n17 = n_map.get("node_17_learning_feedback_loop_closed_v1")
    br = (n17 or {}).get("evidence_values_v1", {}).get("first_break_node_id") if isinstance(n17, dict) else None
    sn = g.get("source_run_id_v1")
    tn = g.get("target_run_id_v1")
    lines = [
        f"Final result: {v}.",
        f"Runs compared: first run {sn!r}, second run {tn!r}.",
        "Did the system learn from the first run? See whether the learning record node passed.",
        "Did the second run retrieve that lesson? See the memory retrieval node.",
        "Did the Student use it in reasoning? See the memory-in-reasoning node.",
        "Did the decision change? See the decision comparison node.",
        "Did execution change? See the execution comparison node.",
        "Did profitability or decision quality change? See the score comparison node.",
    ]
    if bps:
        lines.append("Where the loop broke (codes): " + ", ".join(str(x) for x in bps) + ".")
    if br:
        lines.append(f"First node that failed: {br}.")
    return " ".join(lines)


def build_learning_loop_proof_graph_v1(
    run_a: str,
    run_b: str,
    *,
    scorecard_path: Path | None = None,
    store_path: Path | None = None,
    baseline_job_id: str | None = None,
) -> dict[str, Any]:
    """
    Build ``learning_loop_proof_graph_v1`` for operator/API (read-only).
    """
    sc_p = scorecard_path or default_batch_scorecard_jsonl()
    st_p = store_path or default_student_learning_store_path_v1()
    sa = str(run_a or "").strip()
    sb = str(run_b or "").strip()
    breakpoints: list[str] = []
    nodes: list[dict[str, Any]] = []
    node_ids: list[str] = []

    def add(n: dict[str, Any]) -> None:
        nodes.append(n)
        node_ids.append(n["node_id"])

    # --- Run contexts ---
    ctx_a = _load_run_ctx(sa, scorecard_path=sc_p)
    ctx_b = _load_run_ctx(sb, scorecard_path=sc_p)
    entry_a = ctx_a.entry
    entry_b = ctx_b.entry

    fp_a = scorecard_line_fingerprint_sha256_40_v1(entry_a) if entry_a else None
    fp_b = scorecard_line_fingerprint_sha256_40_v1(entry_b) if entry_b else None

    # Node 1
    if not entry_a:
        breakpoints.append(BP_RUN_A_MISSING)
        add(
            _node(
                "node_01_run_a_completed_v1",
                "run_a_completed_v1",
                STATUS_FAIL,
                evidence_fields=["scorecard_line.job_id", "status"],
                evidence_values={"run_a": sa, "found": False},
                provenance=["batch_scorecard.jsonl via find_scorecard_entry_by_job_id"],
                explanation="No scorecard line for Run A.",
                required=True,
            )
        )
        final = VERDICT_INSUFFICIENT_DATA
        if node_ids:
            final = _verdict_loop_broken("node_01_run_a_completed_v1")
        g_early = {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_b or fp_a,
            "candle_timeframe_minutes": None,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": final,
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": final,
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }
        return g_early

    st_a = str(entry_a.get("status") or "").strip().lower()
    ctf_a = None
    try:
        ctf_a = int(entry_a.get("candle_timeframe_minutes")) if entry_a.get("candle_timeframe_minutes") is not None else None
    except (TypeError, ValueError):
        ctf_a = None
    n1_ok = st_a == "done" and fp_a
    n1_st = STATUS_PASS if n1_ok else STATUS_FAIL
    if not n1_ok:
        breakpoints.append(BP_RUN_A_NOT_DONE if st_a != "done" else BP_RUN_A_MISSING)
    add(
        _node(
            "node_01_run_a_completed_v1",
            "run_a_completed_v1",
            n1_st,
            evidence_fields=["status", "memory_context_impact_audit_v1.run_config_fingerprint_sha256_40", "candle_timeframe_minutes"],
            evidence_values={
                "job_id": sa,
                "status": st_a,
                "fingerprint_sha256_40": fp_a,
                "candle_timeframe_minutes": ctf_a,
            },
            provenance=["batch_scorecard.jsonl"],
            explanation="Run A must be done with fingerprint and optional candle timeframe on line.",
            required=True,
        )
    )
    if n1_st != STATUS_PASS:
        vid = "node_01_run_a_completed_v1"
        g_fail = {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken(vid),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken(vid),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }
        return g_fail

    lr_a = _first_learning_row_with_reasoning(sa, st_p)
    so_a = lr_a.get("student_output") if isinstance(lr_a, dict) else None
    ere_a = (so_a or {}).get("entry_reasoning_eval_v1") if isinstance(so_a, dict) else None
    has_reasoning = isinstance(ere_a, dict) and str(ere_a.get("schema") or "") == "entry_reasoning_eval_v1"
    dig_a = _ere_digest(so_a if isinstance(so_a, dict) else None)
    n2_st = STATUS_PASS if has_reasoning and dig_a else STATUS_FAIL
    if n2_st != STATUS_PASS:
        breakpoints.append(BP_RUN_A_REASONING_MISSING)
    add(
        _node(
            "node_02_run_a_student_reasoning_exists_v1",
            "run_a_student_reasoning_exists_v1",
            n2_st,
            evidence_fields=[
                "student_output.entry_reasoning_eval_v1",
                "student_output.entry_reasoning_eval_digest_v1",
                "entry_reasoning_eval_v1.decision_synthesis_v1",
            ],
            evidence_values={
                "record_id": lr_a.get("record_id") if isinstance(lr_a, dict) else None,
                "entry_reasoning_eval_digest_v1": dig_a,
                "decision_synthesis_v1": (ere_a or {}).get("decision_synthesis_v1") if has_reasoning else None,
            },
            provenance=["student_learning_store_v1", "student_output embedded in record"],
            explanation="Run A learning record must carry sealed reasoning + digest.",
            required=True,
        )
    )
    if n2_st != STATUS_PASS:
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken("node_02_run_a_student_reasoning_exists_v1"),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken("node_02_run_a_student_reasoning_exists_v1"),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    ex_auth = str(entry_a.get("execution_authority_v1") or "").strip() or None
    prof_a = str(entry_a.get("student_brain_profile_v1") or "").strip()
    payload_a = ctx_a.batch_payload
    id_dig_a = _intent_digest_from_payload(payload_a)
    h_a = _outcomes_hash_from_payload(payload_a)
    row_scr = _first_scr_block(payload_a)
    lane = None
    if isinstance(row_scr, dict):
        lane = str(row_scr.get("execution_lane_v1") or row_scr.get("lane_v1") or "") or None
    baseline_only = prof_a == "baseline_no_memory_no_llm" or (not ex_auth or ex_auth == "baseline_control")
    n3_st = STATUS_FAIL if baseline_only or not id_dig_a else STATUS_PASS
    if baseline_only or not id_dig_a:
        breakpoints.append(BP_RUN_A_STUDENT_EXECUTION_MISSING)
    add(
        _node(
            "node_03_run_a_student_execution_exists_v1",
            "run_a_student_execution_exists_v1",
            n3_st,
            evidence_fields=[
                "execution_authority_v1",
                "batch_parallel_results_v1.student_controlled_replay_v1",
                "student_execution_intent_digest_v1",
                "outcomes_hash_v1",
            ],
            evidence_values={
                "student_brain_profile_v1": prof_a,
                "execution_authority_v1": ex_auth,
                "execution_lane_v1": lane,
                "student_execution_intent_digest_v1": id_dig_a,
                "student_outcomes_hash_v1": h_a,
            },
            provenance=["batch_scorecard.jsonl", "batch_parallel_results_v1 session folder"],
            explanation="Student lane must show intent digest and outcomes hash, not cold baseline only.",
            required=True,
        )
    )
    if n3_st != STATUS_PASS:
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken("node_03_run_a_student_execution_exists_v1"),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken("node_03_run_a_student_execution_exists_v1"),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    e_a = line_e_value_for_l1_v1(entry_a)
    p_a = line_p_value_for_l1_v1(entry_a)
    n4_st = (
        STATUS_PASS
        if e_a is not None or p_a is not None or entry_a.get("expectancy_per_trade") is not None
        else STATUS_FAIL
    )
    if n4_st != STATUS_PASS:
        breakpoints.append(BP_RUN_A_SCORE_MISSING)
    add(
        _node(
            "node_04_run_a_score_exists_v1",
            "run_a_score_exists_v1",
            n4_st,
            evidence_fields=["expectancy_per_trade", "exam_e_score_v1", "exam_p_score_v1", "referee_win_pct"],
            evidence_values={
                "expectancy_per_trade": entry_a.get("expectancy_per_trade"),
                "l1_e_scalar": e_a,
                "l1_p_scalar": p_a,
            },
            provenance=["batch_scorecard.jsonl"],
            explanation="Scored line with profitability / decision quality scalars when present.",
            required=True,
        )
    )
    if n4_st == STATUS_FAIL:
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken("node_04_run_a_score_exists_v1"),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken("node_04_run_a_score_exists_v1"),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    if not isinstance(lr_a, dict):
        breakpoints.append(BP_LEARNING_RECORD_MISSING)
        add(
            _node(
                "node_05_learning_record_created_v1",
                "learning_record_created_v1",
                STATUS_FAIL,
                evidence_values={"run_id": sa},
                evidence_fields=["student_learning_store_v1"],
                provenance=["student_learning_store_v1"],
                explanation="No learning record with entry reasoning for Run A.",
                required=True,
            )
        )
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken("node_05_learning_record_created_v1"),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken("node_05_learning_record_created_v1"),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    rec_id_a = str(lr_a.get("record_id") or "").strip()
    gov = lr_a.get("learning_governance_v1")
    n5_st = STATUS_PASS
    add(
        _node(
            "node_05_learning_record_created_v1",
            "learning_record_created_v1",
            n5_st,
            evidence_fields=[
                "record_id",
                "run_id",
                "candle_timeframe_minutes",
                "student_output.entry_reasoning_eval_digest_v1",
                "batch_parallel_results_v1.student_execution_intent_digest_v1",
            ],
            evidence_values={
                "record_id": rec_id_a,
                "source_run_id": sa,
                "candle_timeframe_minutes": lr_a.get("candle_timeframe_minutes"),
                "entry_reasoning_eval_digest_v1": dig_a,
                "student_execution_intent_digest_v1": id_dig_a,
            },
            provenance=["student_learning_store_v1", "batch_parallel_results_v1 (digest cross-check)"],
            explanation="Learning record created with digest for retrieval.",
            required=True,
        )
    )

    n6_st = STATUS_FAIL
    gdec = None
    if isinstance(gov, dict) and str(gov.get("schema") or "") == "learning_governance_v1":
        gdec = str(gov.get("decision") or "").strip().lower()
        if gdec in ("promote", "hold", "reject"):
            n6_st = STATUS_PASS
    if n6_st != STATUS_PASS:
        breakpoints.append(BP_GOVERNANCE_MISSING)
    add(
        _node(
            "node_06_learning_record_governed_v1",
            "learning_record_governed_v1",
            n6_st,
            evidence_fields=["learning_governance_v1.decision", "learning_governance_v1.reason_codes"],
            evidence_values={"decision": gdec, "reason_codes": (gov or {}).get("reason_codes") if isinstance(gov, dict) else None},
            provenance=["student_learning_store_v1"],
            explanation="Governance promote|hold|reject required.",
            required=True,
        )
    )
    if n6_st != STATUS_PASS:
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken("node_06_learning_record_governed_v1"),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken("node_06_learning_record_governed_v1"),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    n7_st = STATUS_PASS if gdec == "promote" else STATUS_FAIL
    if n7_st != STATUS_PASS:
        breakpoints.append(BP_MEMORY_NOT_PROMOTED)
    elig = memory_retrieval_eligible_v1(lr_a) if isinstance(lr_a, dict) else False
    add(
        _node(
            "node_07_memory_promoted_v1",
            "memory_promoted_v1",
            n7_st,
            evidence_fields=["learning_governance_v1.decision", "memory_retrieval_eligible_v1"],
            evidence_values={"decision": gdec, "retrieval_eligible": bool(elig)},
            provenance=["learning_memory_promotion_v1"],
            explanation="Only promote allows downstream Run B retrieval proof.",
            required=True,
        )
    )
    if n7_st != STATUS_PASS:
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": VERDICT_LEARNING_NOT_CONFIRMED,
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": VERDICT_LEARNING_NOT_CONFIRMED,
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    sk = (lr_a.get("context_signature_v1") or {}).get("signature_key") if isinstance(lr_a.get("context_signature_v1"), dict) else None
    sym = None
    ro = lr_a.get("referee_outcome_subset")
    n8_ok = all([rec_id_a, fp_a, sk, ctf_a is not None, isinstance(ro, dict)])
    n8_st = STATUS_PASS if n8_ok else STATUS_FAIL
    if not n8_ok:
        breakpoints.append(BP_MEMORY_MISSING_REUSE_FIELDS)
    add(
        _node(
            "node_08_memory_stored_with_context_v1",
            "memory_stored_with_context_v1",
            n8_st,
            evidence_fields=["record_id", "fingerprint", "signature_key", "candle_timeframe_minutes", "referee_outcome_subset"],
            evidence_values={
                "record_id": rec_id_a,
                "fingerprint_sha256_40": fp_a,
                "signature_key": sk,
                "candle_timeframe_minutes": ctf_a,
                "referee_outcome_subset": ro,
            },
            provenance=["student_learning_store_v1", "batch_scorecard fingerprint"],
            explanation="Memory row must have reuse fields for cross-run retrieval.",
            required=True,
        )
    )
    if n8_st != STATUS_PASS:
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken("node_08_memory_stored_with_context_v1"),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken("node_08_memory_stored_with_context_v1"),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    # --- Run B ---
    if not entry_b:
        breakpoints.append(BP_RUN_B_MISSING)
        add(
            _node(
                "node_09_run_b_completed_v1",
                "run_b_completed_v1",
                STATUS_FAIL,
                evidence_values={"run_b": sb},
                evidence_fields=[],
                provenance=["batch_scorecard.jsonl"],
                explanation="Run B scorecard line missing.",
                required=True,
            )
        )
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_a,
            "candle_timeframe_minutes": ctf_a,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": VERDICT_INSUFFICIENT_DATA,
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": VERDICT_INSUFFICIENT_DATA,
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    st_b = str(entry_b.get("status") or "").strip().lower()
    try:
        ctf_b = int(entry_b.get("candle_timeframe_minutes")) if entry_b.get("candle_timeframe_minutes") is not None else None
    except (TypeError, ValueError):
        ctf_b = None
    tf_match = ctf_b is None or ctf_a is None or ctf_b == ctf_a
    fp_match = not fp_b or not fp_a or fp_b == fp_a
    n9_ok = st_b == "done" and bool(fp_b) and tf_match and fp_match
    n9_st = STATUS_PASS if n9_ok else STATUS_FAIL
    if st_b != "done":
        breakpoints.append(BP_RUN_B_NOT_DONE)
    if ctf_b is not None and ctf_a is not None and ctf_b != ctf_a:
        breakpoints.append(BP_TIMEFRAME_MISMATCH)
    if fp_b and fp_a and fp_b != fp_a:
        breakpoints.append(BP_FINGERPRINT_MISMATCH)
    add(
        _node(
            "node_09_run_b_completed_v1",
            "run_b_completed_v1",
            n9_st,
            evidence_values={
                "job_id": sb,
                "status": st_b,
                "fingerprint_sha256_40": fp_b,
                "candle_timeframe_minutes": ctf_b,
                "timeframe_matches_run_a": tf_match,
                "fingerprint_matches_run_a": fp_match,
            },
            evidence_fields=["status", "candle_timeframe_minutes", "memory_context_impact_audit_v1"],
            provenance=["batch_scorecard.jsonl"],
            explanation="Run B completed and fingerprinted.",
            required=True,
        )
    )
    if n9_st != STATUS_PASS:
        return {
            "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
            "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
            "generated_utc": _utc_now(),
            "source_run_id_v1": sa,
            "target_run_id_v1": sb,
            "fingerprint_v1": fp_b or fp_a,
            "candle_timeframe_minutes": ctf_b,
            "nodes_v1": nodes,
            "edges_v1": _linear_edges(node_ids),
            "breakpoints_v1": breakpoints,
            "final_verdict_v1": _verdict_loop_broken("node_09_run_b_completed_v1"),
            "operator_summary_v1": _plain_summary(
                {
                    "final_verdict_v1": _verdict_loop_broken("node_09_run_b_completed_v1"),
                    "breakpoints_v1": breakpoints,
                    "nodes_v1": nodes,
                    "source_run_id_v1": sa,
                    "target_run_id_v1": sb,
                }
            ),
        }

    record_ids_a = _collect_record_ids_for_run(st_p, sa)
    trace_b = read_learning_trace_events_for_job_v1(sb, path=None)
    retr_b = int(entry_b.get("student_retrieval_matches") or 0)
    strict_in_trace = (rec_id_a in record_ids_a) and _trace_proves_b_retrieved_from_a(
        trace_b, sa, {rec_id_a}
    )
    # Strict: record id in Run A store set AND (trace mention OR retrieval count with matching learning row)
    lr_b = _first_learning_row_with_reasoning(sb, st_p)
    so_b = lr_b.get("student_output") if isinstance(lr_b, dict) else None
    ere_b = (so_b or {}).get("entry_reasoning_eval_v1") if isinstance(so_b, dict) else None
    s_seen, s_used, s_rej = _scored_memory_id_lists_v1(ere_b if isinstance(ere_b, dict) else None)
    seen_ids = set(s_seen)
    exact_record_in_b = rec_id_a in seen_ids
    n10_st = (
        STATUS_PASS
        if (exact_record_in_b or (retr_b > 0 and strict_in_trace))
        else (STATUS_NOT_PROVEN if retr_b > 0 else STATUS_FAIL)
    )
    if n10_st == STATUS_FAIL:
        breakpoints.append(BP_RUN_B_DID_NOT_RETRIEVE)
    add(
        _node(
            "node_10_run_b_retrieved_run_a_memory_v1",
            "run_b_retrieved_run_a_memory_v1",
            n10_st,
            evidence_fields=[
                "scorecard_line.student_retrieval_matches",
                "learning_trace_events_v1",
                "entry_reasoning_eval_v1.memory_context_eval_v1.scored_records_v1.record_id",
            ],
            evidence_values={
                "run_a_record_id": rec_id_a,
                "student_retrieval_matches": retr_b,
                "scored_record_ids_in_run_b_reasoning": sorted(seen_ids),
                "trace_suggests_link": strict_in_trace,
            },
            provenance=["batch_scorecard.jsonl", "learning_trace_events_v1", "student_learning_store_v1"],
            explanation="Exact Run A record id must appear in Run B reasoning scored records, or strict trace + retrieval.",
            required=True,
        )
    )

    pkt_b = (so_b or {}).get("student_decision_packet_v1") if isinstance(so_b, dict) else None
    rse_b: list[dict[str, Any]] = []
    if isinstance(pkt_b, dict):
        rawx = pkt_b.get("retrieved_student_experience_v1")
        if isinstance(rawx, list):
            rse_b = [x for x in rawx if isinstance(x, dict)]
    in_packet = any(str((x or {}).get("record_id") or "").strip() == rec_id_a for x in rse_b)
    has_packet_artifact = isinstance(pkt_b, dict) and "retrieved_student_experience_v1" in pkt_b
    n11_st = STATUS_NOT_PROVEN
    if has_packet_artifact and retr_b > 0 and in_packet:
        n11_st = STATUS_PASS
    elif has_packet_artifact and retr_b > 0 and not in_packet:
        n11_st = STATUS_FAIL
        breakpoints.append(BP_MEMORY_NOT_IN_PACKET)
    elif not has_packet_artifact and retr_b > 0 and exact_record_in_b:
        n11_st = STATUS_NOT_PROVEN
    elif retr_b == 0:
        n11_st = STATUS_FAIL
        breakpoints.append(BP_MEMORY_NOT_IN_PACKET)
    add(
        _node(
            "node_11_memory_reached_student_packet_v1",
            "memory_reached_student_packet_v1",
            n11_st,
            evidence_fields=[
                "student_decision_packet_v1",
                "retrieved_student_experience_v1",
                "student_retrieval_matches",
            ],
            evidence_values={
                "retrieval_matches": retr_b,
                "record_id_in_scored_rows": rec_id_a in seen_ids,
                "record_id_in_decision_packet_rse": in_packet,
                "retrieved_student_experience_count": len(rse_b),
                "student_decision_packet_present": has_packet_artifact,
            },
            provenance=["student_learning_store_v1", "batch_scorecard.jsonl"],
            explanation="When packet is stored, RSE must list Run A record_id; else NOT_PROVEN without packet artifact.",
            required=True,
        )
    )

    mctx_b = (ere_b or {}).get("memory_context_eval_v1") if isinstance(ere_b, dict) else None
    n12_st = STATUS_PASS if isinstance(mctx_b, dict) and (seen_ids or isinstance(mctx_b.get("scored_records_v1"), list)) else STATUS_FAIL
    if n12_st == STATUS_FAIL and retr_b > 0:
        breakpoints.append(BP_MEMORY_NOT_IN_REASONING)
    add(
        _node(
            "node_12_entry_reasoning_considered_memory_v1",
            "entry_reasoning_considered_memory_v1",
            n12_st,
            evidence_fields=[
                "memory_context_eval_v1",
                "retrieved_record_ids_seen_v1",
                "retrieved_record_ids_used_v1",
                "retrieved_record_ids_rejected_v1",
            ],
            evidence_values={
                "memory_context_eval_v1": mctx_b,
                "retrieved_record_ids_seen_v1": list(s_seen),
                "retrieved_record_ids_used_v1": list(s_used),
                "retrieved_record_ids_rejected_v1": list(s_rej),
                "memory_effect_v1": (mctx_b or {}).get("aggregate_memory_effect_v1") if isinstance(mctx_b, dict) else None,
            },
            provenance=["entry_reasoning_eval_v1 in student learning record"],
            explanation="Engine scored_records_v1 lists seen/used vs ignore (rejected) per row.",
            required=True,
        )
    )

    effect_label = _derive_memory_effect_label_v1(ere_b if isinstance(ere_b, dict) else None)
    n13_st = STATUS_PASS if effect_label != "no_effect" else STATUS_FAIL
    if n13_st == STATUS_FAIL:
        breakpoints.append(BP_MEMORY_HAD_NO_EFFECT)
    add(
        _node(
            "node_13_memory_effect_recorded_v1",
            "memory_effect_recorded_v1",
            n13_st,
            evidence_fields=["derived_memory_effect_v1", "decision_synthesis_v1"],
            evidence_values={"memory_effect_v1": effect_label, "decision_synthesis_v1": (ere_b or {}).get("decision_synthesis_v1")},
            provenance=["derived from memory_context_eval_v1 + decision_synthesis_v1 (read-only)"],
            explanation="Effect label derived from stored reasoning (no engine change).",
            required=True,
        )
    )

    # Baseline: optional baseline job or run_a profile as control
    base_line = find_scorecard_entry_by_job_id(str(baseline_job_id or "").strip(), path=sc_p) if (baseline_job_id or "").strip() else None
    lr_base = _first_learning_row_with_reasoning(str(baseline_job_id or "").strip(), st_p) if base_line else None
    so_base = (lr_base or {}).get("student_output") if isinstance(lr_base, dict) else None
    ere_base = (so_base or {}).get("entry_reasoning_eval_v1") if isinstance(so_base, dict) else None
    dsa = (ere_a or {}).get("decision_synthesis_v1") if isinstance(ere_a, dict) else None
    dsb = (ere_b or {}).get("decision_synthesis_v1") if isinstance(ere_b, dict) else None
    act_a = str((dsa or {}).get("action") or "")
    act_b = str((dsb or {}).get("action") or "")
    dsb_l = float((ere_b or {}).get("confidence_01") or 0.0) if isinstance(ere_b, dict) else 0.0
    cmp_out = "not_comparable"
    n14_st = STATUS_NOT_PROVEN
    act_control = act_a
    if base_line and isinstance(ere_base, dict):
        ds_base = ere_base.get("decision_synthesis_v1")
        act_bl = str((ds_base if isinstance(ds_base, dict) else {}).get("action") or "")
        act_control = act_bl
        c_base = float(ere_base.get("confidence_01") or 0.0)
        if act_b != act_bl:
            cmp_out = "decision_changed"
            n14_st = STATUS_PASS
        elif abs(dsb_l - c_base) > 1e-9:
            cmp_out = "confidence_changed_only"
            n14_st = STATUS_NOT_PROVEN
        else:
            cmp_out = "decision_unchanged"
            n14_st = STATUS_FAIL
    else:
        if act_b != act_a and act_a:
            cmp_out = "decision_changed"
            n14_st = STATUS_PASS
        else:
            cmp_out = "not_comparable"
            n14_st = STATUS_NOT_PROVEN
            breakpoints.append(BP_INSUFFICIENT_BASELINE)
    if cmp_out == "decision_unchanged":
        breakpoints.append(BP_DECISION_NOT_CHANGED)
    add(
        _node(
            "node_14_decision_comparison_v1",
            "decision_comparison_v1",
            n14_st,
            evidence_fields=["decision_synthesis_v1.action", "comparison_baseline"],
            evidence_values={"comparison_outcome_v1": cmp_out, "run_b_action": act_b, "control_action": act_control},
            provenance=["entry_reasoning_eval_v1 decision_synthesis on Run A and Run B learning rows"],
            explanation="Compare Run B to baseline job when set, else Run A action as weak control.",
            required=True,
        )
    )

    h_b = _outcomes_hash_from_payload(ctx_b.batch_payload)
    n15_st = STATUS_NOT_PROVEN
    if h_a and h_b and h_a != h_b:
        n15_st = STATUS_PASS
    elif h_a and h_b and h_a == h_b:
        n15_st = STATUS_FAIL
        breakpoints.append(BP_EXECUTION_NOT_CHANGED)
    elif not h_a or not h_b:
        n15_st = STATUS_NOT_PROVEN
    add(
        _node(
            "node_15_execution_comparison_v1",
            "execution_comparison_v1",
            n15_st,
            evidence_fields=["outcomes_hash_v1"],
            evidence_values={"run_a_outcomes_hash": h_a, "run_b_outcomes_hash": h_b},
            provenance=["batch_parallel_results_v1 student_controlled_replay_v1"],
            explanation="Execution change if Student outcomes hash differs between runs (when both present).",
            required=True,
        )
    )

    eb = line_e_value_for_l1_v1(entry_b)
    pb = line_p_value_for_l1_v1(entry_b)
    d_e = (eb - e_a) if (eb is not None and e_a is not None) else None
    d_p = (pb - p_a) if (pb is not None and p_a is not None) else None
    n16_st = STATUS_NOT_PROVEN
    if d_e is None and d_p is None:
        n16_st = STATUS_NOT_PROVEN
    elif (d_e or 0.0) != 0.0 or (d_p or 0.0) != 0.0:
        n16_st = STATUS_PASS
    else:
        n16_st = STATUS_FAIL
        breakpoints.append(BP_SCORE_NOT_CHANGED)
    add(
        _node(
            "node_16_score_comparison_v1",
            "score_comparison_v1",
            n16_st,
            evidence_fields=["l1_e_scalar", "l1_p_scalar"],
            evidence_values={
                "run_a_l1_e": e_a,
                "run_b_l1_e": eb,
                "delta_e": d_e,
                "run_a_l1_p": p_a,
                "run_b_l1_p": pb,
                "delta_p": d_p,
            },
            provenance=["batch_scorecard.jsonl L1 scalars"],
            explanation="Score changed if E or P delta non-zero (profitability / decision quality proxies).",
            required=True,
        )
    )

    # Node 17 — causal loop closed (learning moved behavior / outcome where comparable).
    mem_chain_ok = (n7_st == STATUS_PASS) and (n8_st == STATUS_PASS) and (n10_st == STATUS_PASS) and (n12_st == STATUS_PASS) and (n11_st in (STATUS_PASS, STATUS_NOT_PROVEN))  # not blocked at packet
    decision_or_conf = (n14_st == STATUS_PASS) or (cmp_out == "confidence_changed_only")
    execution_or_score_moved = (n15_st == STATUS_PASS) or (n16_st == STATUS_PASS)
    feedback_ok = (
        mem_chain_ok
        and (n13_st == STATUS_PASS)
        and decision_or_conf
        and execution_or_score_moved
    )
    n17_st = STATUS_PASS if feedback_ok else STATUS_FAIL
    n17 = _node(
        "node_17_learning_feedback_loop_closed_v1",
        "learning_feedback_loop_closed_v1",
        n17_st,
        evidence_fields=["pre_nodes_aggregate_v1"],
        evidence_values={
            "mem_chain_ok": mem_chain_ok,
            "memory_effect_pass": n13_st == STATUS_PASS,
            "decision_or_confidence_moved": decision_or_conf,
            "execution_or_score_moved": execution_or_score_moved,
            "first_fail_node_id": None,
        },
        provenance=[PRODUCER],
        explanation="Promoted memory, Run B strict retrieval+reasoning, non-no_effect, decision/confidence move, execution or score move.",
        required=True,
    )
    n17["evidence_values_v1"]["feedback_ok"] = feedback_ok
    add(n17)

    first_fail_id = next((n["node_id"] for n in nodes if n.get("status") == STATUS_FAIL), None)
    n17["evidence_values_v1"]["first_fail_node_id"] = first_fail_id

    # Final verdict (allowed set only; see GT_DIRECTIVE_026L)
    final: str = VERDICT_LEARNING_NOT_CONFIRMED
    if n17_st == STATUS_PASS:
        final = VERDICT_LEARNING_CONFIRMED
    elif BP_MEMORY_HAD_NO_EFFECT in breakpoints:
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif n10_st == STATUS_NOT_PROVEN:
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif n10_st == STATUS_FAIL:
        final = _verdict_loop_broken("node_10_run_b_retrieved_run_a_memory_v1")
    elif n11_st == STATUS_FAIL and BP_MEMORY_NOT_IN_PACKET in breakpoints:
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif n12_st == STATUS_FAIL and BP_MEMORY_NOT_IN_REASONING in breakpoints:
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif n14_st == STATUS_PASS and n15_st == STATUS_FAIL:
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif n15_st == STATUS_PASS and n16_st == STATUS_FAIL:
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif n11_st == STATUS_NOT_PROVEN:
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif n14_st == STATUS_NOT_PROVEN and cmp_out == "not_comparable":
        final = VERDICT_LEARNING_NOT_CONFIRMED
    elif first_fail_id:
        final = _verdict_loop_broken(str(first_fail_id))
    else:
        final = VERDICT_LEARNING_NOT_CONFIRMED

    g = {
        "schema": SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1,
        "contract_version": CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1,
        "generated_utc": _utc_now(),
        "source_run_id_v1": sa,
        "target_run_id_v1": sb,
        "fingerprint_v1": fp_b or fp_a,
        "candle_timeframe_minutes": ctf_b if ctf_b is not None else ctf_a,
        "nodes_v1": nodes,
        "edges_v1": _linear_edges(node_ids),
        "breakpoints_v1": list(dict.fromkeys(breakpoints)),
        "final_verdict_v1": final,
        "operator_summary_v1": "",
    }
    g["operator_summary_v1"] = _plain_summary(g)
    return g


def default_learning_loop_proof_output_path_v1(
    run_a: str, run_b: str
) -> Path:
    safe_a = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(run_a))[:64]
    safe_b = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(run_b))[:64]
    root = pml_runtime_root() / "student_learning" / "proofs"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"learning_loop_proof_{safe_a}__{safe_b}.json"


def materialize_learning_loop_proof_graph_v1(
    *,
    run_a: str,
    run_b: str,
    scorecard_path: Path | None,
    store_path: Path | None,
    output_path: Path | None,
    confirm: str,
    baseline_job_id: str | None = None,
) -> dict[str, Any]:
    if str(confirm or "").strip() != MATERIALIZE_LEARNING_LOOP_PROOF_V1:
        return {
            "ok": False,
            "error": f"confirm must be {MATERIALIZE_LEARNING_LOOP_PROOF_V1!r}",
        }
    g = build_learning_loop_proof_graph_v1(
        run_a,
        run_b,
        scorecard_path=scorecard_path,
        store_path=store_path,
        baseline_job_id=baseline_job_id,
    )
    outp = output_path or default_learning_loop_proof_output_path_v1(run_a, run_b)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(
        json.dumps(
            {
                "ok": True,
                "output_path": str(outp.resolve()),
                "learning_loop_proof_graph_v1": g,
                "final_verdict_v1": g.get("final_verdict_v1"),
                "breakpoints_v1": g.get("breakpoints_v1"),
                "operator_summary_v1": g.get("operator_summary_v1"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"ok": True, "path": str(outp.resolve())}


__all__ = [
    "SCHEMA_LEARNING_LOOP_PROOF_GRAPH_V1",
    "CONTRACT_VERSION_LEARNING_LOOP_PROOF_V1",
    "MATERIALIZE_LEARNING_LOOP_PROOF_V1",
    "build_learning_loop_proof_graph_v1",
    "default_learning_loop_proof_output_path_v1",
    "materialize_learning_loop_proof_graph_v1",
]
