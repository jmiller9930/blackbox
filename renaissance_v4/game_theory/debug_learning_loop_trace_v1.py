"""
Debug Learning Loop Trace — LangGraph-style graph + fingerprint profile compare (GT operator).

**Truth:** base nodes are **reconstructed**; this module **merges** ``learning_trace_events_v1`` lines
(when present) so provenance can include ``trace_store`` and the Referee–Student coupling is updated
from ``referee_used_student_output`` (``true`` / ``false`` / ``unknown``). Events are written from
parent-thread instrumentation (batch / seam / scorecard), not from process-pool workers.

``GET /api/debug/learning-loop/trace/<job_id>`` (optional: ``?run_a_job_id=…&control_job_id=…`` for 026C closure) — extends ``learning_loop_trace_v1`` with:
- extra node **Decision delta vs baseline**
- ``breakpoints_v1`` — machine-detectable fault codes (including triple-profile identical visible fields)
- ``fingerprint_profile_compare_v1`` — newest-done row per canonical brain profile for same fingerprint
- ``model_provenance_chain_v1`` — contract vs scorecard vs seam vs runtime ``llm_called`` model strings
- ``student_decision_cross_profile_verdict_v1`` — plain-language **NOT PROVEN** answers (no decoration)
- ``same_visible_outcome_candidates_v1`` — ranked hypotheses with **evidence_tier_v1**
- ``referee_student_output_operator_line_v1`` — blunt **Referee used Student output** headline after merge
- ``fault_focus_v1.decisive_operator_questions_v1`` — coupling + cross-profile summary for triage
- ``GET /api/debug/learning-loop/trace-stream/<job_id>`` — NDJSON ``stage`` lines then ``complete`` (UI progress)
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    resolved_llm_for_exam_contract_v1,
)
from renaissance_v4.game_theory.learning_loop_trace_v1 import (
    build_learning_loop_trace_v1,
    ensure_node_evidence_provenance_defaults_v1,
    rebuild_linear_edges_v1,
)
from renaissance_v4.game_theory.learning_trace_events_v1 import (
    merge_learning_trace_events_into_nodes_v1,
    read_learning_trace_events_for_job_v1,
)
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_panel_d11 import _batch_trade_win_pct_from_line
from renaissance_v4.game_theory.student_panel_l1_road_v1 import (
    line_e_value_for_l1_v1,
    line_p_value_for_l1_v1,
    newest_done_rows_by_brain_profile_for_fingerprint_v1,
    resolved_brain_profile_v1,
    resolved_llm_model_tag_v1,
    scorecard_line_fingerprint_sha256_40_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_REJECT,
    build_student_panel_run_learning_payload_v1,
)
from renaissance_v4.game_theory.training_exam_audit_v1 import build_training_exam_audit_v1

SCHEMA_DEBUG = "debug_learning_loop_trace_v1"

_PROFILE_ORDER = (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
)


def _row_snapshot_v1(line: dict[str, Any]) -> dict[str, Any]:
    prof = resolved_brain_profile_v1(line)
    llm_model = resolved_llm_model_tag_v1(line, prof)
    tw = _batch_trade_win_pct_from_line(line)
    return {
        "job_id": line.get("job_id"),
        "student_brain_profile_v1": prof,
        "llm_model": llm_model,
        "student_action_v1": line.get("student_action_v1"),
        "direction": line.get("student_direction") or line.get("student_output_direction"),
        "confidence_01": line.get("student_confidence_01") or line.get("confidence_01"),
        "confidence_band": line.get("student_confidence_band"),
        "retrieved_context_ids": line.get("retrieved_context_ids"),
        "referee_win_pct": line.get("referee_win_pct"),
        "avg_trade_win_pct": line.get("avg_trade_win_pct"),
        "referee_trade_win_pct_proxy_v1": tw,
        "expectancy_per_trade": line.get("expectancy_per_trade"),
        "exam_e_score_v1": line.get("exam_e_score_v1"),
        "exam_p_score_v1": line.get("exam_p_score_v1"),
        "l1_e_scalar_v1": line_e_value_for_l1_v1(line),
        "l1_p_scalar_v1": line_p_value_for_l1_v1(line),
        "l1_e_value_source_v1": line.get("l1_e_value_source_v1"),
        "l1_p_value_source_v1": line.get("l1_p_value_source_v1"),
        "student_learning_rows_appended": line.get("student_learning_rows_appended"),
        "student_retrieval_matches": line.get("student_retrieval_matches"),
        "student_supporting_indicators": line.get("student_supporting_indicators"),
        "student_conflicting_indicators": line.get("student_conflicting_indicators"),
        "note_v1": (
            "Scorecard-line snapshot. Per-trade student_action_v1 / thesis often live in L3 or "
            "Student store only — null here does not prove absence."
        ),
    }


def _best_lifecycle_tape_summary_v1(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    When many ``lifecycle_tape_summary_v1`` lines exist (multi-trade or repeated emits), pick the
    most informative summary for review: prefer **closed** tape with a concrete **exit** code,
    then any **closed**, then any with **exit** code, else the last line (same as v1).
    """
    if not candidates:
        return None
    for pred in (
        lambda c: bool(c.get("closed_v1")) and bool(c.get("exit_reason_code_v1")),
        lambda c: bool(c.get("closed_v1")),
        lambda c: bool(c.get("exit_reason_code_v1")),
    ):
        for c in reversed(candidates):
            if pred(c):
                return c
    return candidates[-1]


def _lifecycle_trace_overlay_v1(events: list[dict[str, Any]]) -> dict[str, Any]:
    """GT_DIRECTIVE_026B — surface lifecycle events from learning_trace for debug/L3 (no proof-file hunt)."""
    stages: list[dict[str, Any]] = []
    summary_cands: list[dict[str, Any]] = []
    for ev in events or []:
        st = str(ev.get("stage") or "").strip()
        ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
        if st == "lifecycle_reasoning_stage_v1":
            s = ep.get("lifecycle_reasoning_stage_v1")
            if isinstance(s, dict):
                stages.append(s)
        elif st == "lifecycle_tape_summary_v1":
            s2 = ep.get("lifecycle_tape_result_v1")
            cand = s2 if isinstance(s2, dict) else (ep if isinstance(ep, dict) else None)
            if isinstance(cand, dict):
                summary_cands.append(cand)
    summary = _best_lifecycle_tape_summary_v1(summary_cands)
    return {
        "schema": "lifecycle_debug_overlay_v1",
        "contract_version": 1,
        "lifecycle_stage_events_count_v1": len(stages),
        "lifecycle_stages_v1": stages[-500:],
        "lifecycle_tape_summary_v1": summary,
    }


def _fingerprint_profile_compare_v1(entry: dict[str, Any]) -> dict[str, Any]:
    fp = scorecard_line_fingerprint_sha256_40_v1(entry)
    if not fp:
        return {
            "schema": "fingerprint_profile_compare_v1",
            "fingerprint_sha256_40": None,
            "row_snapshots_v1": {p: None for p in _PROFILE_ORDER},
            "same_referee_trade_win_proxy_v1": None,
            "detail_v1": "No fingerprint on this scorecard line — cannot align A/B/C profiles.",
        }
    newest_by_profile = newest_done_rows_by_brain_profile_for_fingerprint_v1(
        fp,
        accepted_profiles=frozenset(_PROFILE_ORDER),
    )
    snaps = {p: _row_snapshot_v1(newest_by_profile[p]) if p in newest_by_profile else None for p in _PROFILE_ORDER}
    tws = [
        _batch_trade_win_pct_from_line(newest_by_profile[p])
        for p in _PROFILE_ORDER
        if p in newest_by_profile
    ]
    tws_f = [x for x in tws if isinstance(x, (int, float))]
    same_tw = None
    if len(tws_f) >= 2:
        same_tw = len({round(float(x), 4) for x in tws_f}) == 1

    return {
        "schema": "fingerprint_profile_compare_v1",
        "fingerprint_sha256_40": fp,
        "row_snapshots_v1": snaps,
        "same_referee_trade_win_proxy_v1": same_tw,
        "detail_v1": (
            "Newest completed scorecard line per canonical brain profile in this fingerprint. "
            "``referee_trade_win_pct_proxy_v1`` uses the same batch trade-win rollup as L1 Run TW %."
        ),
    }


def _breakpoints_v1(
    *,
    entry: dict[str, Any],
    tea: dict[str, Any],
    compare: dict[str, Any],
    llm_prof: bool,
    cmem: str,
    retr: int,
    ollama_att: int,
    ollama_ok: int,
    llm_rej: int,
    rows_app: int,
    gov_dec: str,
    exam_e: Any,
    exam_p: Any,
) -> list[str]:
    out: list[str] = []
    prof = str(entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or "").strip()
    if retr <= 0 and cmem in ("read", "read_write") and prof != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
        out.append("no_memory_retrieved_scorecard_zero")
    if llm_prof and ollama_att <= 0:
        out.append("llm_not_called_no_ollama_attempts")
    if llm_prof and llm_rej > 0 and ollama_ok <= 0 and ollama_att > 0:
        out.append("llm_rejected_or_failed_before_seal")
    if tea.get("training_learning_verdict_v1") == "ENGAGEMENT_WITHOUT_STORE_WRITES":
        out.append("learning_record_not_appended_despite_engagement")
    if gov_dec == GOVERNANCE_REJECT:
        out.append("governance_018_reject_aggregate")
    if exam_e is None and exam_p is None and str(entry.get("status") or "").lower() == "done":
        out.append("exam_ep_missing_on_done_line")
    if compare.get("same_referee_trade_win_proxy_v1") is True and len(compare.get("row_snapshots_v1") or {}) >= 2:
        out.append("referee_trade_win_proxy_identical_across_profiles_same_fp")
    tv = str(tea.get("training_learning_verdict_v1") or "")
    if tv == "NO_SCORECARD_EVIDENCE_OF_STUDENT_PATH":
        out.append("no_scorecard_evidence_student_path")
    if tv == "STUDENT_LANE_NOT_CONFIGURED_OR_OFF":
        out.append("student_lane_not_configured")
    snaps = compare.get("row_snapshots_v1") or {}
    trip = [snaps[p] for p in _PROFILE_ORDER if isinstance(snaps.get(p), dict)]
    if len(trip) >= 3:
        keys_trip = (
            "referee_trade_win_pct_proxy_v1",
            "exam_e_score_v1",
            "exam_p_score_v1",
            "l1_e_scalar_v1",
            "l1_p_scalar_v1",
            "student_action_v1",
            "direction",
        )

        def _eq3(a: Any, b: Any, c: Any) -> bool:
            if a is None or b is None or c is None:
                return False
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and isinstance(c, (int, float)):
                return abs(float(a) - float(b)) < 1e-9 and abs(float(b) - float(c)) < 1e-9
            return str(a).strip() == str(b).strip() == str(c).strip()

        same_all: list[str] = []
        for k in keys_trip:
            if _eq3(trip[0].get(k), trip[1].get(k), trip[2].get(k)):
                same_all.append(k)
        if len(same_all) >= 4:
            out.append("triple_profile_same_fp_identical_on_core_visible_fields_v1")
    return sorted(set(out))


def _norm_val(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return str(round(float(v), 8))
    if isinstance(v, list):
        return json.dumps(v, sort_keys=True, default=str)
    s = str(v).strip()
    return s or None


def _model_provenance_chain_v1(entry: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Where model strings can diverge — no guessing; only fields present on this row + runtime events."""
    prof = resolved_brain_profile_v1(entry)
    oba = entry.get("operator_batch_audit") if isinstance(entry.get("operator_batch_audit"), dict) else {}
    ex_req = oba.get("exam_run_contract_request_v1")
    ex_req = ex_req if isinstance(ex_req, dict) else None
    contract_model: str | None = None
    contract_url: str | None = None
    if ex_req:
        m, u, _slm, _llm_errs = resolved_llm_for_exam_contract_v1(ex_req)
        contract_model = m
        contract_url = u or None
    raw_llm_block = entry.get("student_llm_v1") if isinstance(entry.get("student_llm_v1"), dict) else {}
    scorecard_top_llm = entry.get("llm_model")
    scorecard_top_llm_s = str(scorecard_top_llm).strip() if scorecard_top_llm else None
    resolved_tag = resolved_llm_model_tag_v1(entry, prof)
    llm_ex = entry.get("student_llm_execution_v1") if isinstance(entry.get("student_llm_execution_v1"), dict) else {}
    seam_model = str(llm_ex.get("model_resolved") or "").strip() or None
    seam_url = str(llm_ex.get("base_url_resolved") or "").strip() or None
    runtime_models: list[str] = []
    for ev in events:
        if str(ev.get("stage") or "").strip() != "llm_called":
            continue
        ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
        mm = ep.get("llm_model")
        if isinstance(mm, str) and mm.strip():
            runtime_models.append(mm.strip())
    uniq_runtime = list(dict.fromkeys(runtime_models))
    switches: list[dict[str, Any]] = []
    if contract_model and scorecard_top_llm_s and contract_model.strip() != scorecard_top_llm_s.strip():
        switches.append(
            {
                "where_v1": "exam_run_contract_request_vs_scorecard_llm_model_column",
                "left_v1": contract_model,
                "right_v1": scorecard_top_llm_s,
            }
        )
    if contract_model and resolved_tag and contract_model.strip() != resolved_tag.strip():
        switches.append(
            {
                "where_v1": "exam_contract_vs_resolved_llm_model_tag_v1",
                "left_v1": contract_model,
                "right_v1": resolved_tag,
            }
        )
    if seam_model and resolved_tag and seam_model.strip() != resolved_tag.strip():
        switches.append(
            {
                "where_v1": "seam_student_llm_execution_vs_resolved_llm_model_tag_v1",
                "left_v1": seam_model,
                "right_v1": resolved_tag,
            }
        )
    if uniq_runtime and contract_model:
        if uniq_runtime[0].strip() != contract_model.strip():
            switches.append(
                {
                    "where_v1": "runtime_llm_called_vs_exam_contract_model",
                    "contract_v1": contract_model,
                    "runtime_first_v1": uniq_runtime[0],
                }
            )
    if len(uniq_runtime) > 1:
        switches.append({"where_v1": "runtime_multiple_distinct_llm_called_models_same_job", "models_v1": uniq_runtime})
    return {
        "schema": "model_provenance_chain_v1",
        "exam_run_contract_request_v1_present_v1": bool(ex_req),
        "contract_resolved_llm_model_v1": contract_model,
        "contract_default_ollama_base_url_v1": contract_url,
        "scorecard_llm_model_column_v1": scorecard_top_llm_s,
        "scorecard_student_llm_v1_block": raw_llm_block or None,
        "scorecard_resolved_llm_model_tag_v1": resolved_tag,
        "seam_student_llm_execution_model_resolved_v1": seam_model,
        "seam_student_llm_execution_base_url_resolved_v1": seam_url,
        "runtime_llm_called_models_ordered_v1": uniq_runtime,
        "l1_display_v1": {
            "l1_e_scalar_v1": line_e_value_for_l1_v1(entry),
            "l1_p_scalar_v1": line_p_value_for_l1_v1(entry),
            "l1_e_value_source_v1": entry.get("l1_e_value_source_v1"),
            "l1_p_value_source_v1": entry.get("l1_p_value_source_v1"),
            "l1_execution_authority_v1": entry.get("l1_execution_authority_v1"),
            "l1_student_full_control_v1": entry.get("l1_student_full_control_v1"),
            "execution_authority_v1": entry.get("execution_authority_v1"),
            "student_lane_authority_truth_v1": entry.get("student_lane_authority_truth_v1"),
        },
        "model_switch_events_v1": switches,
        "note_v1": (
            "UI-selected model is only proven here if the client sent ``exam_run_contract_request_v1`` "
            "inside ``operator_batch_audit`` on this scorecard row. ``llm_called`` runtime lines prove "
            "what model tag was passed into the seam Ollama call for that trade."
        ),
    }


def _cross_profile_student_verdict_v1(
    compare: dict[str, Any],
    entry: dict[str, Any],
    model_chain: dict[str, Any],
) -> dict[str, Any]:
    snaps = compare.get("row_snapshots_v1") or {}
    cov = {p: isinstance(snaps.get(p), dict) for p in _PROFILE_ORDER}
    fields_compared = (
        "student_action_v1",
        "direction",
        "confidence_01",
        "confidence_band",
        "student_supporting_indicators",
        "student_conflicting_indicators",
        "retrieved_context_ids",
        "llm_model",
        "referee_win_pct",
        "referee_trade_win_pct_proxy_v1",
        "expectancy_per_trade",
        "exam_e_score_v1",
        "exam_p_score_v1",
        "l1_e_scalar_v1",
        "l1_p_scalar_v1",
    )
    if not all(cov.values()):
        return {
            "schema": "student_decision_cross_profile_verdict_v1",
            "row_coverage_v1": cov,
            "fields_compared_v1": list(fields_compared),
            "plain_language_answer_v1": (
                "NOT PROVEN — newest **done** scorecard rows for all three canonical brain profiles "
                "are not all present for this fingerprint; cannot decide whether three different brains ran."
            ),
            "answer_code_v1": "NOT_PROVEN_INCOMPLETE_ROWS",
        }
    rows = [snaps[p] for p in _PROFILE_ORDER]
    diffs: list[str] = []
    for k in fields_compared:
        a, b, c = (_norm_val(rows[0].get(k)), _norm_val(rows[1].get(k)), _norm_val(rows[2].get(k)))
        if a is None and b is None and c is None:
            continue
        if a != b or b != c or a != c:
            diffs.append(k)
    same_tw = compare.get("same_referee_trade_win_proxy_v1") is True
    action_same = _norm_val(rows[0].get("student_action_v1")) == _norm_val(rows[2].get("student_action_v1")) == _norm_val(rows[1].get("student_action_v1"))
    direction_same = _norm_val(rows[0].get("direction")) == _norm_val(rows[1].get("direction")) == _norm_val(rows[2].get("direction"))
    exam_same = _norm_val(rows[0].get("exam_e_score_v1")) == _norm_val(rows[1].get("exam_e_score_v1")) == _norm_val(rows[2].get("exam_e_score_v1"))
    l1e_same = _norm_val(rows[0].get("l1_e_scalar_v1")) == _norm_val(rows[1].get("l1_e_scalar_v1")) == _norm_val(rows[2].get("l1_e_scalar_v1"))
    has_decision_on_snapshots = any(
        rows[i].get("student_action_v1") not in (None, "")
        or rows[i].get("direction") not in (None, "")
        for i in range(3)
    )

    if not diffs:
        if not has_decision_on_snapshots:
            msg = (
                "NOT PROVEN — all three profile rows exist for this fingerprint, but scorecard snapshots "
                "omit ``student_action_v1`` / ``direction``; prove per-trade decisions in L3 or the Student store."
            )
            code = "NOT_PROVEN_MISSING_DECISION_FIELDS_ON_SCORECARD"
        elif action_same and direction_same:
            msg = (
                "Student decision did not change on the compared scorecard snapshots (same action/direction "
                "and no differences on compared fields that carry values). Same visible E / L1 road across "
                "profiles is **consistent with one Referee replay** — **NOT PROVEN** that three "
                "independent Student brains produced different decisions."
            )
            code = "STUDENT_DECISION_UNCHANGED_ON_SNAPSHOTS"
        else:
            msg = (
                "Compared fields with any values are identical across profiles. **NOT PROVEN** that three "
                "distinct decision paths produced this fingerprint."
            )
            code = "SNAPSHOTS_IDENTICAL_WHERE_VALUES_EXIST"
    elif diffs and ("student_action_v1" in diffs or "direction" in diffs) and same_tw:
        msg = (
            "Student decision fields differ between profiles on these snapshots, but the Referee trade-win "
            "proxy matches. Architecture note: Referee replay is scheduled before the Student seam — "
            "**NOT PROVEN** that Referee execution consumed Student output for worker rows; see "
            "``referee_used_student_output`` runtime line and coupling node."
        )
        code = "STUDENT_DECISION_CHANGED_REFEREE_PROXY_UNCHANGED"
    elif diffs and (not exam_same or not l1e_same) and same_tw:
        msg = (
            "Exam or L1 E scalars differ across profiles while Referee proxy matches — check "
            "``l1_e_value_source_v1`` / ``l1_p_value_source_v1`` on each row. **NOT PROVEN** (without "
            "per-field wiring audit) that the UI is showing the wrong score column."
        )
        code = "NOT_PROVEN_EP_L1_DIVERGE_REFEREE_SAME"
    else:
        msg = (
            "Profiles diverge on one or more compared fields — inspect ``fingerprint_profile_compare_v1`` "
            "row_snapshots_v1. This is not a failure of the trace; it narrows where to look next (memory, "
            "LLM, store, or display)."
        )
        code = "PROFILES_DIVERGE_ON_COMPARED_FIELDS"

    out: dict[str, Any] = {
        "schema": "student_decision_cross_profile_verdict_v1",
        "row_coverage_v1": cov,
        "fields_compared_v1": list(fields_compared),
        "fields_differing_across_profiles_v1": diffs,
        "plain_language_answer_v1": msg,
        "answer_code_v1": code,
        "same_referee_trade_win_proxy_across_profiles_v1": same_tw,
        "this_run_brain_profile_v1": resolved_brain_profile_v1(entry),
        "model_switch_events_echo_v1": model_chain.get("model_switch_events_v1") or [],
    }
    return out


def _same_visible_outcome_candidates_v1(
    entry: dict[str, Any],
    compare: dict[str, Any],
    events: list[dict[str, Any]],
    bps: list[str],
    model_chain: dict[str, Any],
) -> dict[str, Any]:
    """Ranked hypotheses when A/B/C look the same — each line states evidence tier; no decoration."""
    cands: list[dict[str, Any]] = []
    if "no_memory_retrieved_scorecard_zero" in bps:
        cands.append(
            {
                "code_v1": "memory_not_retrieved",
                "detail_v1": "Breakpoint: no_memory_retrieved_scorecard_zero.",
                "evidence_tier_v1": "proven_from_breakpoint",
            }
        )
    if "llm_not_called_no_ollama_attempts" in bps:
        cands.append(
            {
                "code_v1": "llm_did_not_run",
                "detail_v1": "Breakpoint: llm_not_called_no_ollama_attempts on this run row.",
                "evidence_tier_v1": "proven_from_breakpoint",
            }
        )
    if "runtime_learning_trace_events_empty_v1" in bps or "learning_trace_integrity_failed_v1" in bps:
        cands.append(
            {
                "code_v1": "runtime_trace_missing_or_invalid",
                "detail_v1": "Cannot prove stage boundaries without learning_trace_event_v1 lines for this job_id.",
                "evidence_tier_v1": "proven_from_breakpoint",
            }
        )
    sw = model_chain.get("model_switch_events_v1") if isinstance(model_chain.get("model_switch_events_v1"), list) else []
    if sw:
        cands.append(
            {
                "code_v1": "model_string_mismatch_in_chain",
                "detail_v1": f"model_provenance_chain_v1 reports {len(sw)} switch(es) — inspect model_switch_events_v1.",
                "evidence_tier_v1": "proven_from_scorecard_and_or_runtime",
            }
        )
    if compare.get("same_referee_trade_win_proxy_v1") is True:
        cands.append(
            {
                "code_v1": "shared_referee_replay_same_trade_win_proxy",
                "detail_v1": (
                    "Same-fingerprint newest rows share Referee trade-win proxy — expected if worker replay "
                    "does not vary by Student brain profile for that fingerprint."
                ),
                "evidence_tier_v1": "proven_from_scorecard_compare",
            }
        )
    ru_status: str | None = None
    for ev in reversed(events):
        if str(ev.get("stage") or "").strip() == "referee_used_student_output":
            ru_status = str(ev.get("status") or "").strip().lower()
            ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
            inf = str(ep.get("student_influence_on_worker_replay_v1") or "").strip().lower()
            if inf in ("true", "false", "unknown"):
                ru_status = inf
            break
    if ru_status == "false":
        cands.append(
            {
                "code_v1": "referee_worker_replay_did_not_use_student_output",
                "detail_v1": "Runtime line referee_used_student_output status=false (documented ordering).",
                "evidence_tier_v1": "proven_from_runtime_event",
            }
        )
    elif ru_status == "unknown":
        cands.append(
            {
                "code_v1": "referee_student_coupling_unknown",
                "detail_v1": "Runtime line marked unknown — cannot prove influence on worker replay.",
                "evidence_tier_v1": "proven_from_runtime_event",
            }
        )
    if not cands:
        cands.append(
            {
                "code_v1": "no_single_root_cause_identified",
                "detail_v1": "No matching breakpoint chain — use plain_language_answer_v1 and per-node evidence.",
                "evidence_tier_v1": "not_proven",
            }
        )
    return {"schema": "same_visible_outcome_candidates_v1", "candidates_v1": cands}


def _referee_coupling_operator_line_v1(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    for n in nodes:
        if str(n.get("id") or "") != "referee_student_output_coupling":
            continue
        evd = n.get("evidence_v1") if isinstance(n.get("evidence_v1"), dict) else {}
        verdict = str(evd.get("verdict_v1") or "NOT_PROVEN").strip()
        rb = list(n.get("runtime_breakpoints_v1") or [])
        if verdict == "PROVEN_BY_RUNTIME_EVENT_V1":
            headline = "Referee used Student output: PROVEN (runtime event)"
        elif verdict == "REFUSED_OR_IGNORED_V1":
            headline = "Referee used Student output: NOT USED / IGNORED (runtime event)"
        elif verdict == "COUPLING_UNKNOWN_V1":
            headline = "Referee used Student output: UNKNOWN (runtime event)"
        elif verdict in ("NOT_PROVEN", "") or "not_captured_at_runtime_v1" in rb:
            headline = "Referee used Student output: NOT PROVEN"
        else:
            headline = f"Referee used Student output: {verdict}"
        return {
            "schema": "referee_student_output_operator_line_v1",
            "headline_v1": headline,
            "node_status_v1": n.get("node_status_v1"),
            "summary_v1": n.get("summary_v1"),
            "verdict_v1": verdict,
            "runtime_breakpoints_v1": rb,
        }
    return {
        "schema": "referee_student_output_operator_line_v1",
        "headline_v1": "Referee used Student output: NOT PROVEN (coupling node missing)",
        "verdict_v1": "NOT_PROVEN",
    }


def _finalize_debug_trace_from_base_v1(
    base: dict[str, Any],
    entry: dict[str, Any],
    *,
    run_a_job_id: str | None = None,
    control_job_id: str | None = None,
) -> dict[str, Any]:
    """Attach debug-only fields; does not mutate the ``base`` dict passed in."""
    work = dict(base)
    jid = str(work.get("job_id") or "").strip()

    nodes = copy.deepcopy(work.get("nodes_v1") or [])
    for n in nodes:
        if n.get("id") == "ep_grading":
            n["label"] = "Scoring / E-P"

    ins_at = next((i for i, n in enumerate(nodes) if n.get("id") == "student_decision"), None)
    if ins_at is not None:
        delta_node = {
            "id": "decision_delta_vs_baseline",
            "label": "Decision delta vs baseline",
            "node_status_v1": "unknown",
            "summary_v1": (
                "Run-level scorecard does not carry baseline_action / decision_changed_flag "
                "(see student_data_capability_audit_v1). Use L3 per-trade "
                "``decision_changed_flag`` + baseline slice vs Student store."
            ),
            "source_fields_v1": [
                "student_decision_record_v1.baseline_comparison (L3)",
                "student_data_capability_audit_v1",
            ],
            "evidence_v1": {
                "student_output_fingerprint": entry.get("student_output_fingerprint"),
                "training_learning_verdict_v1": (work.get("training_exam_audit_v1") or {}).get(
                    "training_learning_verdict_v1"
                ),
            },
            "evidence_provenance_v1": ["unknown", "l3"],
            "runtime_breakpoints_v1": ["not_captured_at_runtime_v1"],
        }
        nodes.insert(ins_at + 1, delta_node)
    work["nodes_v1"] = nodes
    work["edges_v1"] = rebuild_linear_edges_v1(nodes)

    tea = work.get("training_exam_audit_v1") or build_training_exam_audit_v1(entry)
    oba = entry.get("operator_batch_audit")
    cmem = str(oba.get("context_signature_memory_mode") or "").strip().lower() if isinstance(oba, dict) else ""
    retr = int(entry.get("student_retrieval_matches") or 0)
    llm_ex = entry.get("student_llm_execution_v1")
    ollama_att = int(llm_ex.get("ollama_trades_attempted") or 0) if isinstance(llm_ex, dict) else 0
    ollama_ok = int(llm_ex.get("ollama_trades_succeeded") or 0) if isinstance(llm_ex, dict) else 0
    llm_rej = int(entry.get("llm_student_output_rejections_v1") or 0)
    prof = str(entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or "").strip()
    llm_prof = prof == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    rows_app = int(entry.get("student_learning_rows_appended") or 0)

    learn = build_student_panel_run_learning_payload_v1(jid)
    run_gov = learn.get("learning_governance_v1") if isinstance(learn, dict) else None
    gov_dec = str(run_gov.get("decision") or "").strip().lower() if isinstance(run_gov, dict) else ""
    exam_e = entry.get("exam_e_score_v1")
    exam_p = entry.get("exam_p_score_v1")
    t_fp0 = time.perf_counter()
    compare = _fingerprint_profile_compare_v1(entry)
    fp_ms = round((time.perf_counter() - t_fp0) * 1000.0, 2)
    events = read_learning_trace_events_for_job_v1(jid)
    status_lc = str(entry.get("status") or "").strip().lower()
    model_chain = _model_provenance_chain_v1(entry, events)
    cross_profile = _cross_profile_student_verdict_v1(compare, entry, model_chain)
    bps = _breakpoints_v1(
        entry=entry,
        tea=tea if isinstance(tea, dict) else {},
        compare=compare,
        llm_prof=llm_prof,
        cmem=cmem,
        retr=retr,
        ollama_att=ollama_att,
        ollama_ok=ollama_ok,
        llm_rej=llm_rej,
        rows_app=rows_app,
        gov_dec=gov_dec,
        exam_e=exam_e,
        exam_p=exam_p,
    )
    integrity_failed = bool(not events and status_lc == "done")
    if integrity_failed:
        bps = sorted({*bps, "runtime_learning_trace_events_empty_v1", "learning_trace_integrity_failed_v1"})

    out = dict(work)
    out["schema"] = SCHEMA_DEBUG
    out["fingerprint_profile_compare_v1"] = compare
    out["breakpoints_v1"] = bps
    out["trace_build_timings_ms_v1"] = {"fingerprint_profile_compare_v1": fp_ms}
    out["learning_trace_events_v1"] = events
    out["learning_trace_events_count_v1"] = len(events)
    out["lifecycle_trace_overlay_v1"] = _lifecycle_trace_overlay_v1(events)
    out["learning_trace_events_path_v1"] = str(
        default_learning_trace_events_jsonl().expanduser().resolve()
    )
    if integrity_failed:
        out["learning_trace_integrity_failed_v1"] = True
        out["learning_loop_health_banner_v1"] = "LEARNING LOOP BROKEN"
        out["learning_loop_health_detail_v1"] = (
            "Completed scorecard row has **zero** ``learning_trace_event_v1`` lines for this job_id — "
            "runtime trace capture is mandatory for a valid learning-loop proof."
        )
    merge_learning_trace_events_into_nodes_v1(out["nodes_v1"], events)
    ensure_node_evidence_provenance_defaults_v1(out["nodes_v1"])
    out["edges_v1"] = rebuild_linear_edges_v1(out["nodes_v1"])
    out["model_provenance_chain_v1"] = model_chain
    out["student_decision_cross_profile_verdict_v1"] = cross_profile
    out["referee_student_output_operator_line_v1"] = _referee_coupling_operator_line_v1(out["nodes_v1"])
    out["same_visible_outcome_candidates_v1"] = _same_visible_outcome_candidates_v1(
        entry, compare, events, bps, model_chain
    )
    ff = dict(out.get("fault_focus_v1") or {})
    coup_h = (out.get("referee_student_output_operator_line_v1") or {}).get("headline_v1")
    cp_a = (out.get("student_decision_cross_profile_verdict_v1") or {}).get("plain_language_answer_v1")
    ff["decisive_operator_questions_v1"] = [x for x in (coup_h, cp_a) if x]
    out["fault_focus_v1"] = ff
    tc = dict(out.get("trace_classification_v1") or {})
    tc["runtime_events_loaded_count_v1"] = len(events)
    tc["merge_mode_v1"] = "reconstructed_plus_trace_store_v1"
    if integrity_failed:
        tc["learning_trace_integrity_failed_v1"] = True
    out["trace_classification_v1"] = tc
    _fault_map = None
    for _ev in reversed(events):
        if str(_ev.get("stage") or "").strip() == "student_reasoning_fault_map_v1":
            _ep = _ev.get("evidence_payload") if isinstance(_ev.get("evidence_payload"), dict) else {}
            _fm = _ep.get("student_reasoning_fault_map_v1")
            if isinstance(_fm, dict):
                _fault_map = _fm
            break
    out["student_reasoning_fault_map_v1"] = _fault_map
    has_life = any(str(x.get("stage") or "").strip() == "lifecycle_tape_summary_v1" for x in events)
    out["gt_directive_026b_lifecycle_v1"] = {
        "lifecycle_in_learning_trace_v1": has_life,
        "unified_agent_router_lifecycle_v1": (
            "On-demand when the operator runtime packet includes ``unified_agent_router_lifecycle_v1`` and "
            "``bars_trade_lifecycle_inclusive_v1``; otherwise hybrid router in lifecycle remains optional."
        ),
    }
    out["operator_notes_v1"] = {
        "referee_vs_student_metric_v1": (
            "L1 Run TW % and Sys BL % are Referee batch trade-win rollups — they can match across "
            "profiles when replay outcomes do not diverge. Student thesis deltas are L3 / store."
        ),
        "trace_truth_v1": (
            "Primary graph is **reconstructed** from persisted artifacts. "
            "``learning_trace_events_v1`` is appended from the **batch / seam / scorecard** threads "
            "(single-writer); those lines merge as runtime proof — not from pool worker processes."
        ),
        "lifecycle_026B_v1": (
            "``lifecycle_trace_overlay_v1`` aggregates **lifecycle_reasoning_stage_v1** and "
            "**lifecycle_tape_summary_v1** from the same job’s trace lines (see evidence_payload)."
        ),
    }
    try:
        from renaissance_v4.game_theory.learning_effect_closure_026c_v1 import build_learning_effect_closure_026c_v1

        out["learning_effect_closure_026c_v1"] = build_learning_effect_closure_026c_v1(
            str(jid or "").strip(),
            run_a_job_id=run_a_job_id,
            control_job_id=control_job_id,
            scorecard_entry_run_b=entry,
        )
    except Exception as e:
        out["learning_effect_closure_026c_v1"] = {
            "schema": "learning_effect_closure_026c_v1",
            "ok": False,
            "error": str(e)[:2000],
        }
    return out


def build_debug_learning_loop_trace_v1(
    job_id: str,
    *,
    run_a_job_id: str | None = None,
    control_job_id: str | None = None,
) -> dict[str, Any]:
    base = build_learning_loop_trace_v1(job_id)
    if not base.get("ok"):
        return {
            "schema": SCHEMA_DEBUG,
            "ok": False,
            "error": base.get("error"),
            "job_id": base.get("job_id") or str(job_id or "").strip(),
            "trace_v1": base,
        }

    jid = str(base.get("job_id") or "").strip()
    entry = base.get("scorecard_line_v1")
    if not isinstance(entry, dict):
        entry = find_scorecard_entry_by_job_id(jid)
    if not isinstance(entry, dict):
        return {**base, "schema": SCHEMA_DEBUG, "ok": False, "error": "entry_missing_after_trace"}

    return _finalize_debug_trace_from_base_v1(
        base, entry, run_a_job_id=run_a_job_id, control_job_id=control_job_id
    )


def iter_debug_learning_loop_trace_ndjson_v1(
    job_id: str,
    *,
    run_a_job_id: str | None = None,
    control_job_id: str | None = None,
) -> Iterator[str]:
    """
    NDJSON stream: ``stage`` lines (server-side steps + ``ms``) then one ``complete`` line with the
    same payload as ``build_debug_learning_loop_trace_v1`` (for live operator progress in the UI).
    """

    def _line(obj: dict[str, Any]) -> str:
        return json.dumps(obj, ensure_ascii=False) + "\n"

    jid = str(job_id or "").strip()
    t0 = time.perf_counter()
    yield _line(
        {
            "type": "stage",
            "id": "learning_loop_trace_v1",
            "label": "Learning loop trace (scorecard + nodes)",
            "status": "running",
        }
    )
    base = build_learning_loop_trace_v1(jid)
    yield _line(
        {
            "type": "stage",
            "id": "learning_loop_trace_v1",
            "label": "Learning loop trace (scorecard + nodes)",
            "status": "ok" if base.get("ok") else "error",
            "ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    )
    if not base.get("ok"):
        yield _line(
            {
                "type": "complete",
                "payload": {
                    "schema": SCHEMA_DEBUG,
                    "ok": False,
                    "error": base.get("error"),
                    "job_id": base.get("job_id") or jid,
                    "trace_v1": base,
                },
            }
        )
        return

    entry = base.get("scorecard_line_v1")
    if not isinstance(entry, dict):
        entry = find_scorecard_entry_by_job_id(str(base.get("job_id") or jid).strip())
    if not isinstance(entry, dict):
        yield _line(
            {
                "type": "complete",
                "payload": {**base, "schema": SCHEMA_DEBUG, "ok": False, "error": "entry_missing_after_trace"},
            }
        )
        return

    t1 = time.perf_counter()
    yield _line(
        {
            "type": "stage",
            "id": "debug_extensions_v1",
            "label": "Fingerprint scan + breakpoints + graph patch",
            "status": "running",
        }
    )
    out = _finalize_debug_trace_from_base_v1(
        base, entry, run_a_job_id=run_a_job_id, control_job_id=control_job_id
    )
    yield _line(
        {
            "type": "stage",
            "id": "debug_extensions_v1",
            "label": "Fingerprint scan + breakpoints + graph patch",
            "status": "ok",
            "ms": round((time.perf_counter() - t1) * 1000.0, 2),
        }
    )
    yield _line({"type": "complete", "payload": out})


def read_debug_learning_loop_page_html_v1() -> str:
    p = Path(__file__).resolve().parent / "debug_learning_loop_page_v1.html"
    return p.read_text(encoding="utf-8")


__all__ = [
    "SCHEMA_DEBUG",
    "build_debug_learning_loop_trace_v1",
    "iter_debug_learning_loop_trace_ndjson_v1",
    "read_debug_learning_loop_page_html_v1",
]
