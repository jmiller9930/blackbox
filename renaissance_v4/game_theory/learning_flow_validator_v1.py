"""
GT_DIRECTIVE_025 — Learning flow step validator (read-only, system-level learning proof).

Proves a **run-to-run** learning chain using ``batch_scorecard.jsonl``,
``learning_trace_events_v1``, ``student_learning_store_v1``, and
``batch_parallel_results_v1`` (no model-weight claims).

**Truth label:** this validates **control-plane / data-plane** handoffs, not a trained
reasoning model.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.learning_trace_events_v1 import (
    read_learning_trace_events_for_job_v1,
)
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl
from renaissance_v4.game_theory.scorecard_drill import (
    find_scorecard_entry_by_job_id,
    load_batch_parallel_results_v1,
)
from renaissance_v4.game_theory.student_panel_d13 import _ordered_parallel_rows
from renaissance_v4.game_theory.student_panel_l1_road_v1 import (
    line_e_value_for_l1_v1,
    scorecard_line_fingerprint_sha256_40_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_PROMOTE,
    build_student_panel_run_learning_payload_v1,
    memory_retrieval_eligible_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    list_student_learning_records_by_run_id,
)

SCHEMA_LEARNING_FLOW_VALIDATION_V1 = "learning_flow_validation_v1"
CONTRACT_VERSION_LEARNING_FLOW_VALIDATION_V1 = 1

MATERIALIZE_LEARNING_FLOW_VALIDATION_V1 = "MATERIALIZE_LEARNING_FLOW_VALIDATION_V1"

_STEP_PASS = "PASS"
_STEP_FAIL = "FAIL"
_STEP_SKIPPED = "SKIPPED"
_STEP_NOT_PROVEN = "NOT_PROVEN"

VERDICT_LEARNING_CONFIRMED = "LEARNING_CONFIRMED"
VERDICT_LEARNING_NOT_CONFIRMED = "LEARNING_NOT_CONFIRMED"
VERDICT_INSUFFICIENT = "INSUFFICIENT_DATA"


def verdict_loop_broken_v1(step_index: int) -> str:
    return f"LOOP_BROKEN_AT_STEP_{int(step_index)}"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_learning_flow_validation_report_path_v1() -> Path:
    """Default JSON audit path under the PML runtime tree."""
    override = (os.environ.get("PATTERN_GAME_LEARNING_FLOW_VALIDATION_V1") or "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    from renaissance_v4.game_theory.pml_runtime_layout import pml_runtime_root

    root = pml_runtime_root() / "student_learning"
    root.mkdir(parents=True, exist_ok=True)
    return root / "learning_flow_validation_v1.json"


@dataclass
class _RunCtx:
    job_id: str
    entry: dict[str, Any] | None
    trace: list[dict[str, Any]] = field(default_factory=list)
    batch_dir: Path | None = None
    batch_payload: dict[str, Any] | None = None
    err: str | None = None


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _stages_of(trace: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    return [e for e in trace if str(e.get("stage") or "").strip() == stage]


def _any_trace_pass(tr: list[dict[str, Any]], stage: str) -> bool:
    for e in _stages_of(tr, stage):
        st = str(e.get("status") or "").strip().lower()
        if st in ("pass", "ok", "true", "partial", "running", "hold", "promote", "reject", "1"):
            return True
    return False


def _trace_memory_matches(tr: list[dict[str, Any]]) -> int:
    m = 0
    for e in _stages_of(tr, "memory_retrieval_completed"):
        if str(e.get("status") or "").lower() == "skipped":
            continue
        ep = e.get("evidence_payload")
        if isinstance(ep, dict):
            m = max(m, _int(ep.get("student_retrieval_matches"), 0))
    return m


def _collect_record_ids_for_run(
    store_path: Path, run_id: str
) -> set[str]:
    out: set[str] = set()
    for d in list_student_learning_records_by_run_id(store_path, run_id):
        rid = d.get("record_id")
        if isinstance(rid, str) and rid.strip():
            out.add(rid.strip())
    return out


def _walk_mentions(
    x: Any,
    *,
    need_run: str,
    need_record_ids: set[str],
) -> bool:
    if isinstance(x, str):
        t = str(x or "").strip()
        if t == need_run or t in need_record_ids:
            return True
        if need_run and need_run in t:
            return True
    if isinstance(x, dict):
        for k, v in x.items():
            if str(k) in (
                "source_run_id",
                "prior_run_id",
                "prior_job_id",
                "source_job_id",
                "contributing_source_run_id_v1",
                "provenance_source_run_id_v1",
                "source_run_id_v1",
                "memory_source_run_id_v1",
            ) and str(v or "").strip() == need_run:
                return True
            if k == "source_record_id" and str(v or "").strip() in need_record_ids:
                return True
            if _walk_mentions(v, need_run=need_run, need_record_ids=need_record_ids):
                return True
    if isinstance(x, list):
        for it in x:
            if _walk_mentions(it, need_run=need_run, need_record_ids=need_record_ids):
                return True
    return False


def _trace_proves_b_retrieved_from_a(
    trace_b: list[dict[str, Any]],
    run_a: str,
    record_ids_a: set[str],
) -> bool:
    for ev in trace_b:
        ep = ev.get("evidence_payload")
        if not isinstance(ep, dict):
            continue
        stg = str(ev.get("stage") or "")
        if stg in (
            "memory_retrieval_completed",
            "future_retrieval_observed",
            "packet_built",
        ) or stg:
            if _walk_mentions(ep, need_run=run_a, need_record_ids=record_ids_a):
                return True
    return False


def _load_run_ctx(
    job_id: str,
    *,
    scorecard_path: Path | None = None,
) -> _RunCtx:
    jid = str(job_id or "").strip()
    if not jid:
        return _RunCtx(
            job_id="",
            entry=None,
            err="empty job_id",
        )
    ent = find_scorecard_entry_by_job_id(jid, path=scorecard_path)
    tr = read_learning_trace_events_for_job_v1(
        jid, path=None
    )  # uses default; tests patch module function
    bd: Path | None = None
    payload: dict[str, Any] | None = None
    if isinstance(ent, dict):
        sdir = ent.get("session_log_batch_dir")
        if isinstance(sdir, str) and sdir.strip():
            d = Path(sdir).expanduser().resolve()
            if d.is_dir():
                bd = d
                payload = load_batch_parallel_results_v1(bd) or None
    return _RunCtx(
        job_id=jid,
        entry=ent if isinstance(ent, dict) else None,
        trace=tr,
        batch_dir=bd,
        batch_payload=payload,
        err=None if ent is not None else "scorecard line not found for job_id",
    )


def _cmem_mode(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    oba = entry.get("operator_batch_audit")
    if not isinstance(oba, dict):
        return ""
    return str(oba.get("context_signature_memory_mode") or "").strip().lower()


def _first_intent_row(batch_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(batch_payload, dict):
        return None
    for r in _ordered_parallel_rows(batch_payload):
        if not r.get("ok"):
            continue
        scr = r.get("student_controlled_replay_v1")
        if not isinstance(scr, dict):
            continue
        if scr.get("student_execution_intent_digest_v1") or scr.get("student_execution_intent_v1"):
            return r
    return None


def _first_scr_block(batch_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(batch_payload, dict):
        return None
    for r in _ordered_parallel_rows(batch_payload):
        if not r.get("ok"):
            continue
        scr = r.get("student_controlled_replay_v1")
        if isinstance(scr, dict) and (
            scr.get("outcomes_hash_v1") or scr.get("student_outcomes_hash_v1")
        ):
            return scr
    return None


def _step_dict(
    sid: str,
    status: str,
    fields: list[str],
    values: dict[str, Any],
    expl: str,
) -> dict[str, Any]:
    return {
        "step_id_v1": sid,
        "status_v1": status,
        "evidence_fields_v1": list(fields),
        "evidence_values_v1": values,
        "explanation_v1": expl,
    }


def _validate_run_a_chain(
    ctx: _RunCtx,
    *,
    store_path: Path,
) -> list[dict[str, Any]]:
    e = ctx.entry
    if not e:
        return [
            _step_dict(
                "1_memory_retrieved_v1",
                _STEP_NOT_PROVEN,
                ["scorecard_line.missing_v1"],
                {"job_id": ctx.job_id},
                "No scorecard line — cannot observe memory path.",
            )
        ]
    tr = ctx.trace
    cmem = _cmem_mode(e)
    retr = _int(e.get("student_retrieval_matches"), 0)
    tmatches = _trace_memory_matches(tr)
    mci = e.get("memory_context_impact_audit_v1")
    recall = _int(mci.get("recall_match_windows_total_sum"), 0) if isinstance(mci, dict) else 0
    mem_yes = bool(
        isinstance(mci, dict) and str(mci.get("memory_impact_yes_no") or "").upper() == "YES"
    )
    if cmem not in ("read", "read_write"):
        s1 = _step_dict(
            "1_memory_retrieved_v1",
            _STEP_SKIPPED,
            ["operator_batch_audit.context_signature_memory_mode", "analysis.memory_lane"],
            {
                "context_signature_memory_mode": cmem or None,
            },
            "Context signature memory mode is not read — retrieval lane not expected on this run.",
        )
    elif retr > 0 or tmatches > 0 or mem_yes or recall > 0:
        s1 = _step_dict(
            "1_memory_retrieved_v1",
            _STEP_PASS,
            [
                "scorecard_line.student_retrieval_matches",
                "learning_trace_events_v1.memory_retrieval_completed",
                "memory_context_impact_audit_v1",
            ],
            {
                "student_retrieval_matches": retr,
                "trace_max_retrieval_matches": tmatches,
                "memory_impact_yes_no": mci.get("memory_impact_yes_no") if isinstance(mci, dict) else None,
            },
            "Retrieval or recall signals present (scorecard and/or learning trace).",
        )
    else:
        s1 = _step_dict(
            "1_memory_retrieved_v1",
            _STEP_FAIL,
            [
                "scorecard_line.student_retrieval_matches",
                "learning_trace_events_v1.memory_retrieval_completed",
            ],
            {"student_retrieval_matches": retr, "trace_max_retrieval_matches": tmatches},
            "Memory read mode on but no retrieval matches, trace matches, MCI, or recall sum observed.",
        )

    s1s = s1.get("status_v1")
    if s1s == _STEP_SKIPPED:
        s2 = _step_dict(
            "2_memory_used_v1",
            _STEP_SKIPPED,
            ["chain.link_after_step_1"],
            {"after_step_1": s1s},
            "No memory read configuration — use step not applicable (skipped with step 1).",
        )
    elif s1s == _STEP_FAIL:
        s2 = _step_dict(
            "2_memory_used_v1",
            _STEP_FAIL,
            ["chain.link_after_step_1"],
            {"after_step_1": s1s},
            "No usable memory after failed retrieval (step 1).",
        )
    else:
        rej = [x for x in tr if str(x.get("stage") or "") == "llm_output_rejected"]
        if retr > 0 or tmatches > 0 or mem_yes or recall > 0:
            s2 = _step_dict(
                "2_memory_used_v1",
                _STEP_PASS,
                [
                    "memory_retrieval",
                    "memory_context_impact_audit_v1",
                ],
                {
                    "student_retrieval_matches": retr,
                    "explicit_llm_rejections_trace_count": len(rej),
                },
                "Retrieval/impact path engaged or rejected explicitly downstream — memory slice path proven.",
            )
        elif rej:
            s2 = _step_dict(
                "2_memory_used_v1",
                _STEP_PASS,
                ["learning_trace_events_v1.llm_output_rejected"],
                {"rejection_event_count": len(rej)},
                "Explicit student thesis rejections in trace (memory/LLM path closed with reject events).",
            )
        else:
            s2 = _step_dict(
                "2_memory_used_v1",
                _STEP_NOT_PROVEN,
                [
                    "scorecard_line",
                    "learning_trace_events_v1",
                ],
                {
                    "student_retrieval_matches": retr,
                },
                "Cannot prove memory was applied or explicitly rejected (no conclusive events).",
            )

    dcf = e.get("student_output_fingerprint")
    sealed = _stages_of(tr, "student_output_sealed")
    sealed_ok = any(str(x.get("status") or "").lower() in ("pass", "ok") for x in sealed)
    if sealed_ok or (isinstance(dcf, str) and dcf.strip()):
        s3 = _step_dict(
            "3_student_decision_created_v1",
            _STEP_PASS,
            [
                "scorecard_line.student_output_fingerprint",
                "learning_trace_events_v1.student_output_sealed",
            ],
            {
                "student_output_fingerprint_present": bool(isinstance(dcf, str) and dcf.strip()),
                "sealed_events_count": len(sealed),
            },
            "Student output sealed in trace and/or scorecard carries output fingerprint.",
        )
    else:
        s3 = _step_dict(
            "3_student_decision_created_v1",
            _STEP_NOT_PROVEN,
            [
                "scorecard_line.student_output_fingerprint",
                "learning_trace_events_v1.student_output_sealed",
            ],
            {},
            "No output fingerprint and no pass-class sealed events — decision not directly proven.",
        )

    has_intent_trace = bool(_stages_of(tr, "student_execution_intent_consumed"))
    row0 = _first_intent_row(ctx.batch_payload)
    digest = None
    if isinstance(row0, dict):
        scrb = row0.get("student_controlled_replay_v1")
        if isinstance(scrb, dict):
            digest = scrb.get("student_execution_intent_digest_v1")
    if has_intent_trace or (isinstance(digest, str) and digest.strip()):
        s4 = _step_dict(
            "4_student_execution_intent_created_v1",
            _STEP_PASS,
            [
                "learning_trace_events_v1.student_execution_intent_consumed",
                "batch_parallel_results_v1.results[].student_controlled_replay_v1.student_execution_intent_digest_v1",
            ],
            {
                "intent_digest": digest or "(trace_only)",
            },
            "Execution intent digest present in trace and/or student_controlled_replay on batch result row.",
        )
    else:
        s4 = _step_dict(
            "4_student_execution_intent_created_v1",
            _STEP_NOT_PROVEN,
            [
                "learning_trace_events_v1",
                "batch_parallel_results_v1",
            ],
            {},
            "No execution intent in trace and no student_controlled digest on result rows — not proven.",
        )

    st_cmp = any(
        str(x.get("status") or "").lower() in ("pass",)
        for x in _stages_of(tr, "student_controlled_replay_completed")
    )
    ran_rc = _int(e.get("student_controlled_replay_ran_v1"), 0)
    has_sc_row = _first_scr_block(ctx.batch_payload) is not None
    if st_cmp or ran_rc > 0 or has_sc_row:
        s5 = _step_dict(
            "5_student_execution_applied_v1",
            _STEP_PASS,
            [
                "learning_trace_events_v1.student_controlled_replay_started",
                "learning_trace_events_v1.student_controlled_replay_completed",
                "scorecard_line.student_controlled_replay_ran_v1",
            ],
            {
                "student_controlled_replay_ran_v1": ran_rc,
                "trace_completed_count": len(_stages_of(tr, "student_controlled_replay_completed")),
                "result_row_had_controlled_block": has_sc_row,
            },
            "Student-controlled 024C/024D lane completed (trace and/or scorecard count).",
        )
    else:
        s5 = _step_dict(
            "5_student_execution_applied_v1",
            _STEP_NOT_PROVEN,
            [
                "learning_trace_events_v1",
                "scorecard_line.student_controlled_replay_ran_v1",
                "batch_parallel_results_v1.results[].student_controlled_replay_v1",
            ],
            {
                "student_controlled_replay_ran_v1": ran_rc,
                "result_row_had_controlled_block": has_sc_row,
            },
            "No proof that the Student execution lane was applied (no trace, zero ran, no controlled block on rows).",
        )

    scrb0 = _first_scr_block(ctx.batch_payload)
    hsh = None
    if isinstance(scrb0, dict):
        hsh = scrb0.get("outcomes_hash_v1") or scrb0.get("student_outcomes_hash_v1")
    if hsh or _any_trace_pass(tr, "student_controlled_replay_completed"):
        s6 = _step_dict(
            "6_execution_outcomes_generated_v1",
            _STEP_PASS,
            [
                "batch_parallel_results_v1.results[].student_controlled_replay_v1.outcomes_hash_v1",
            ],
            {"outcomes_hash_v1": hsh or "(from_trace_outcomes_payload)"},
            "Scored student outcomes (hash on batch and/or complete trace).",
        )
    else:
        s6 = _step_dict(
            "6_execution_outcomes_generated_v1",
            _STEP_NOT_PROVEN,
            ["batch_parallel_results_v1", "learning_trace_events_v1"],
            {},
            "No outcomes hash on student controlled block and no trace completion evidence.",
        )

    e_val = line_e_value_for_l1_v1(e)
    p_val = e.get("exam_p_score_v1")
    grad = _stages_of(tr, "grading_completed")
    if e_val is not None or p_val is not None or grad:
        s7 = _step_dict(
            "7_score_computed_v1",
            _STEP_PASS,
            [
                "scorecard_line.exam_e_score_v1",
                "scorecard_line.exam_p_score_v1",
                "learning_trace_events_v1.grading_completed",
            ],
            {
                "exam_e": e_val,
                "exam_p": p_val,
            },
            "Exam/expectancy and/or grade trace line present (E/P/expectancy path).",
        )
    else:
        s7 = _step_dict(
            "7_score_computed_v1",
            _STEP_NOT_PROVEN,
            [
                "scorecard_line",
                "learning_trace_events_v1.grading_completed",
            ],
            {},
            "No E/P and no grading trace — score not proven.",
        )

    gtr = [x for x in tr if str(x.get("stage") or "") == "governance_decided"]
    learn = build_student_panel_run_learning_payload_v1(ctx.job_id)
    gov = learn.get("learning_governance_v1")
    ddec = str(gov.get("decision") or "").strip().lower() if isinstance(gov, dict) else ""
    if gtr or ddec in ("promote", "hold", "reject"):
        s8 = _step_dict(
            "8_governance_decision_v1",
            _STEP_PASS,
            [
                "learning_trace_events_v1.governance_decided",
                "build_student_panel_run_learning_payload.learning_governance_v1",
            ],
            {
                "aggregated_governance": ddec,
                "trace_governance_count": len(gtr),
            },
            "GT-018 style governance available from trace and/or L3/synthetic aggregate.",
        )
    else:
        s8 = _step_dict(
            "8_governance_decision_v1",
            _STEP_NOT_PROVEN,
            ["learning_trace_events_v1", "student_panel_run_learning"],
            {},
            "Governance decision not proven.",
        )

    st_rows = _int(e.get("student_learning_rows_appended"), 0)
    lr = [x for x in tr if str(x.get("stage") or "") == "learning_record_appended"]
    stored = list_student_learning_records_by_run_id(store_path, ctx.job_id)
    n_stored = len(stored)
    if ddec and ddec != GOVERNANCE_PROMOTE:
        s9 = _step_dict(
            "9_learning_record_appended_v1",
            _STEP_SKIPPED,
            [
                "build_student_panel_run_learning_payload.learning_governance_v1",
            ],
            {"decision": ddec},
            "Governance not promote — no append required for a promotion-only learning store row.",
        )
    else:
        if st_rows > 0 or lr or n_stored > 0:
            s9 = _step_dict(
                "9_learning_record_appended_v1",
                _STEP_PASS,
                [
                    "learning_trace_events_v1.learning_record_appended",
                    "scorecard_line.student_learning_rows_appended",
                    "student_learning_records_v1@run_id",
                ],
                {
                    "student_learning_rows_appended": st_rows,
                    "trace_append_count": len(lr),
                    "store_count_for_run": len(stored),
                },
                "Append path observed (trace, scorecard denorm, and/or store by run_id).",
            )
        else:
            s9 = _step_dict(
                "9_learning_record_appended_v1",
                _STEP_FAIL,
                [
                    "learning_store",
                ],
                {"governance": ddec, "rows_app": st_rows},
                "Promote path expected learning row — no append signal on scorecard, trace, or store.",
            )

    return [s1, s2, s3, s4, s5, s6, s7, s8, s9]


def _fingerprint(e: dict[str, Any] | None) -> str | None:
    if not isinstance(e, dict):
        return None
    return scorecard_line_fingerprint_sha256_40_v1(e) or None


def _comp_changed(
    a: Any,
    b: Any,
    *,
    label: str,
) -> dict[str, Any]:
    if a is None or b is None:
        return {
            "status": _STEP_NOT_PROVEN,
            "fields": [label],
            "values": {"a": a, "b": b},
            "expl": "Missing comparator on one side — cannot prove a delta.",
        }
    if str(a) == str(b):
        return {
            "status": _STEP_FAIL,
            "fields": [label],
            "values": {"a": a, "b": b, "compared": "str_equal"},
            "expl": "Values identical — no proven change (system-level, not model variance).",
        }
    return {
        "status": _STEP_PASS,
        "fields": [label],
        "values": {"a": a, "b": b, "compared": "str_diff"},
        "expl": "Field differs between run A and run B (deterministic string compare on normalized scalars).",
    }


def _validate_run_b_chain(
    ctx_b: _RunCtx,
    ctx_a: _RunCtx,
    store_path: Path,
) -> list[dict[str, Any]]:
    """
    Run B: steps 10-13. Uses trace explicit linkage to run A, then outcome deltas.
    """
    run_a = ctx_a.job_id
    e_a = ctx_a.entry
    e_b = ctx_b.entry
    trace_b = ctx_b.trace
    rid_a = _collect_record_ids_for_run(store_path, run_a)
    s10: dict[str, Any]
    if not e_b:
        s10 = _step_dict(
            "10_memory_retrieved_from_run_A_v1",
            _STEP_NOT_PROVEN,
            ["scorecard_line.missing_v1"],
            {"run_b": ctx_b.job_id},
            "No scorecard for run B — cannot ground retrieval to run A.",
        )
    elif _trace_proves_b_retrieved_from_a(trace_b, run_a, rid_a):
        s10 = _step_dict(
            "10_memory_retrieved_from_run_A_v1",
            _STEP_PASS,
            [
                "learning_trace_events_v1.*.evidence_payload.source_run_id*",
            ],
            {
                "run_a": run_a,
                "record_ids_from_run_a_count": len(rid_a),
            },
            "Trace evidence references run A and/or a learning record_id sourced from A.",
        )
    else:
        retr_b = _int(e_b.get("student_retrieval_matches"), 0)
        fp_b = _fingerprint(e_b)
        fp_a = _fingerprint(e_a) if e_a is not None else None
        rec_a_elig = [r for r in list_student_learning_records_by_run_id(store_path, run_a) if memory_retrieval_eligible_v1(r)]
        has_eligible = bool(rec_a_elig)
        if (
            retr_b > 0
            and has_eligible
            and fp_b
            and fp_a
            and fp_b == fp_a
        ):
            s10 = _step_dict(
                "10_memory_retrieved_from_run_A_v1",
                _STEP_NOT_PROVEN,
                [
                    "learning_trace_events_v1 (missing explicit source_run_id)",
                    "store.list_student_learning_records_by_run_id",
                    "scorecard_line.student_retrieval_matches",
                ],
                {
                    "student_retrieval_matches": retr_b,
                    "fingerprint_equal": True,
                    "eligible_store_rows_for_run_a": len(rec_a_elig),
                },
                "Retrieval is positive and fingerprints match, but there is no explicit evidence that "
                "the slices included run A (do not infer) — add trace payload with source_run_id/record_id.",
            )
        elif retr_b <= 0:
            s10 = _step_dict(
                "10_memory_retrieved_from_run_A_v1",
                _STEP_FAIL,
                [
                    "scorecard_line.student_retrieval_matches",
                ],
                {
                    "student_retrieval_matches": retr_b,
                },
                "Run B has zero recorded retrieval — cannot have retrieved A row material.",
            )
        else:
            s10 = _step_dict(
                "10_memory_retrieved_from_run_A_v1",
                _STEP_NOT_PROVEN,
                ["fingerprint", "store"],
                {
                    "fp_a": fp_a,
                    "fp_b": fp_b,
                    "eligible_for_run_a": has_eligible,
                },
                "Retrieval>0 on B but no explicit link to A and weak fingerprint / store preconditions not met — NOT_PROVEN.",
            )

    s11 = {**_comp_changed(
        (e_a or {}).get("student_output_fingerprint") if e_a else None,
        (e_b or {}).get("student_output_fingerprint") if e_b else None,
        label="scorecard_line.student_output_fingerprint",
    )}
    s11d = _step_dict(
        "11_student_decision_changed_v1",
        s11["status"],
        s11.get("fields", []),
        s11.get("values", {}),
        str(s11.get("expl") or ""),
    )

    dig_a: Any = None
    r_a = _first_intent_row(ctx_a.batch_payload)
    if isinstance(r_a, dict):
        sba = r_a.get("student_controlled_replay_v1")
        if isinstance(sba, dict):
            dig_a = sba.get("student_execution_intent_digest_v1")
    dig_b: Any = None
    r_b = _first_intent_row(ctx_b.batch_payload)
    if isinstance(r_b, dict):
        sbb = r_b.get("student_controlled_replay_v1")
        if isinstance(sbb, dict):
            dig_b = sbb.get("student_execution_intent_digest_v1")
    cex = _comp_changed(dig_a, dig_b, label="batch.student_execution_intent_digest_v1")
    s12 = _step_dict(
        "12_execution_changed_v1",
        cex["status"],
        cex.get("fields", []),
        cex.get("values", {}),
        str(cex.get("expl") or ""),
    )

    # Prefer exam E, then L1 E proxy, for deterministic scalar compare
    e_a2 = line_e_value_for_l1_v1(e_a) if e_a else None
    e_b2 = line_e_value_for_l1_v1(e_b) if e_b else None
    csc = _comp_changed(e_a2, e_b2, label="line_e_value_for_l1_v1 (exam or expectancy proxy)")
    s13 = _step_dict(
        "13_score_changed_v1",
        csc["status"],
        csc.get("fields", []),
        csc.get("values", {}),
        str(csc.get("expl") or ""),
    )

    return [s10, s11d, s12, s13]


def _verdict(
    run_a: _RunCtx,
    run_b: _RunCtx,
    steps: list[dict[str, Any]],
) -> str:
    if run_a.err or not run_a.entry or run_b.err or not run_b.entry:
        return VERDICT_INSUFFICIENT
    s1 = next(
        (x for x in steps if str(x.get("step_id_v1") or "") == "1_memory_retrieved_v1"), None
    )
    if s1 and s1.get("status_v1") == _STEP_SKIPPED:
        return VERDICT_INSUFFICIENT
    for i, st in enumerate(steps, start=1):
        s = st.get("status_v1")
        if s == _STEP_NOT_PROVEN and i <= 9:
            return VERDICT_INSUFFICIENT
        if s == _STEP_FAIL and i <= 9:
            return verdict_loop_broken_v1(i)
    s10 = next(
        (x for x in steps if str(x.get("step_id_v1") or "") == "10_memory_retrieved_from_run_A_v1"),
        None,
    )
    if s10 and s10.get("status_v1") == _STEP_NOT_PROVEN:
        return VERDICT_LEARNING_NOT_CONFIRMED
    if s10 and s10.get("status_v1") == _STEP_FAIL:
        return VERDICT_LEARNING_NOT_CONFIRMED
    if any(
        st.get("status_v1") == _STEP_NOT_PROVEN
        for st in steps
        if str(st.get("step_id_v1", "")).startswith("11_")
    ):
        return VERDICT_INSUFFICIENT
    if any(
        st.get("status_v1") == _STEP_NOT_PROVEN
        for st in steps
        if str(st.get("step_id_v1", "")).startswith("12_")
    ):
        return VERDICT_INSUFFICIENT
    if any(
        st.get("status_v1") == _STEP_NOT_PROVEN
        for st in steps
        if str(st.get("step_id_v1", "")).startswith("13_")
    ):
        return VERDICT_INSUFFICIENT
    if s10 and s10.get("status_v1") != _STEP_PASS:
        return VERDICT_LEARNING_NOT_CONFIRMED
    for st in steps:
        if str(st.get("step_id_v1", "")).startswith(("11_", "12_", "13_")):
            if st.get("status_v1") == _STEP_FAIL:
                return VERDICT_LEARNING_NOT_CONFIRMED
    return VERDICT_LEARNING_CONFIRMED


def build_learning_flow_validation_v1(
    run_a: str,
    run_b: str,
    *,
    scorecard_path: Path | None = None,
    store_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Build the full 13-step validation payload for (run A → run B).

    ``store_path`` defaults to the Student learning store JSONL path.
    """
    from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
        default_student_learning_store_path_v1,
    )

    sp = Path(str(store_path or default_student_learning_store_path_v1()))
    a = _load_run_ctx(str(run_a or "").strip(), scorecard_path=scorecard_path)
    b = _load_run_ctx(str(run_b or "").strip(), scorecard_path=scorecard_path)
    steps_a = _validate_run_a_chain(a, store_path=sp)
    steps_b = _validate_run_b_chain(b, a, sp)
    all_steps = [*steps_a, *steps_b]
    v = _verdict(a, b, all_steps)
    if not str(run_a or "").strip() or not str(run_b or "").strip():
        v = VERDICT_INSUFFICIENT
    sc_ref = "default"
    if scorecard_path is not None:
        sc_ref = str(Path(scorecard_path).expanduser().resolve())
    else:
        sc_ref = str(default_batch_scorecard_jsonl().expanduser().resolve())
    out: dict[str, Any] = {
        "schema": SCHEMA_LEARNING_FLOW_VALIDATION_V1,
        "contract_version": CONTRACT_VERSION_LEARNING_FLOW_VALIDATION_V1,
        "generated_at_utc": _utc_iso(),
        "verdict_v1": v,
        "run_a": a.job_id,
        "run_b": b.job_id,
        "sources_v1": {
            "store_path": str(sp.resolve()),
            "scorecard_path": sc_ref,
        },
        "steps_v1": all_steps,
        "disclaimer_v1": (
            "This validates system-level control/data handoffs in the learning pipeline, "
            "not model-weight training. LLM non-determinism is not evidence of learning."
        ),
    }
    if a.err:
        out["error_run_a"] = a.err
    if b.err:
        out["error_run_b"] = b.err
    return out


def materialize_learning_flow_validation_v1(
    *,
    run_a: str,
    run_b: str,
    scorecard_path: Path | None,
    store_path: Path | str,
    output_path: Path | str | None,
    confirm: str | None,
) -> dict[str, Any]:
    if str(confirm or "").strip() != MATERIALIZE_LEARNING_FLOW_VALIDATION_V1:
        return {
            "ok": False,
            "error": "confirm must match MATERIALIZE_LEARNING_FLOW_VALIDATION_V1",
        }
    out_p = Path(str(output_path)) if output_path else default_learning_flow_validation_report_path_v1()
    doc = build_learning_flow_validation_v1(run_a, run_b, scorecard_path=scorecard_path, store_path=store_path)
    body = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    out_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_p.with_suffix(out_p.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(out_p)
    return {
        "ok": True,
        "path": str(out_p.resolve()),
        "bytes_written": len(body.encode("utf-8")),
    }


__all__ = [
    "CONTRACT_VERSION_LEARNING_FLOW_VALIDATION_V1",
    "MATERIALIZE_LEARNING_FLOW_VALIDATION_V1",
    "SCHEMA_LEARNING_FLOW_VALIDATION_V1",
    "VERDICT_INSUFFICIENT",
    "VERDICT_LEARNING_CONFIRMED",
    "VERDICT_LEARNING_NOT_CONFIRMED",
    "build_learning_flow_validation_v1",
    "verdict_loop_broken_v1",
    "default_learning_flow_validation_report_path_v1",
    "materialize_learning_flow_validation_v1",
]
