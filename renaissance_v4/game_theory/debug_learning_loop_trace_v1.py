"""
Debug Learning Loop Trace — LangGraph-style graph + fingerprint profile compare (GT operator).

**Truth:** base nodes are **reconstructed**; this module **merges** ``learning_trace_events_v1`` lines
(when present) so provenance can include ``trace_store`` and the Referee–Student coupling is updated
from ``referee_used_student_output`` (``true`` / ``false`` / ``unknown``). Events are written from
parent-thread instrumentation (batch / seam / scorecard), not from process-pool workers.

``GET /api/debug/learning-loop/trace/<job_id>`` — extends ``learning_loop_trace_v1`` with:
- extra node **Decision delta vs baseline**
- ``breakpoints_v1`` — machine-detectable fault codes
- ``fingerprint_profile_compare_v1`` — newest-done row per canonical brain profile for same fingerprint
  (single streaming scorecard pass; no full-file ``read_text``)
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
        "note_v1": (
            "Scorecard-line snapshot. Per-trade student_action_v1 / thesis often live in L3 or "
            "Student store only — null here does not prove absence."
        ),
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
    return sorted(set(out))


def _finalize_debug_trace_from_base_v1(base: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
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
    tc = dict(out.get("trace_classification_v1") or {})
    tc["runtime_events_loaded_count_v1"] = len(events)
    tc["merge_mode_v1"] = "reconstructed_plus_trace_store_v1"
    if integrity_failed:
        tc["learning_trace_integrity_failed_v1"] = True
    out["trace_classification_v1"] = tc
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
    }
    return out


def build_debug_learning_loop_trace_v1(job_id: str) -> dict[str, Any]:
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

    return _finalize_debug_trace_from_base_v1(base, entry)


def iter_debug_learning_loop_trace_ndjson_v1(job_id: str) -> Iterator[str]:
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
    out = _finalize_debug_trace_from_base_v1(base, entry)
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
