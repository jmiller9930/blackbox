"""
learning_trace_events_v1 — append-only **runtime** learning-loop trace (capture layer).

The operator **reconstructed** graph (``learning_loop_trace_v1``) is built from scorecard + batch +
learning API. This module persists **handoffs that cannot be reliably inferred later** when workers
call ``append_learning_trace_event_v1``.

Schema line: ``learning_trace_event_v1`` (one JSON object per append).
"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl

# When set, ``append_learning_trace_event_v1`` appends deep-copied events here only — **no JSONL write**.
_learning_trace_memory_sink: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "learning_trace_memory_sink_v1", default=None
)

SCHEMA_EVENT = "learning_trace_event_v1"
SCHEMA_VERSION = 1

# Architect / product contract — emit from workers as stages complete.
EVENT_STAGES_V1 = (
    "packet_built",
    "memory_retrieval_completed",
    "llm_called",
    "llm_output_received",
    "llm_output_rejected",
    "student_output_sealed",
    "student_execution_intent_consumed",
    "student_controlled_replay_started",
    "student_controlled_replay_completed",
    "referee_execution_started",
    "referee_execution_completed",
    "referee_used_student_output",
    "grading_completed",
    "governance_decided",
    "learning_record_appended",
    "future_retrieval_observed",
    "candle_timeframe_nexus_v1",
    "timeframe_mismatch_detected_v1",
    "market_data_loaded",
    "indicator_context_eval_v1",
    "perps_state_model_evaluated_v1",
    "pattern_memory_evaluated_v1",
    "expected_value_risk_cost_evaluated_v1",
    "memory_context_evaluated",
    "prior_outcomes_evaluated",
    "risk_reward_evaluated",
    "decision_synthesis_v1",
    "entry_reasoning_validated",
    "entry_reasoning_sealed_v1",
    "student_reasoning_fault_map_v1",
    "reasoning_router_decision_v1",
    "external_reasoning_review_v1",
    "reasoning_cost_governor_v1",
    # GT_DIRECTIVE_026B — per-bar lifecycle + tape summary (trace_store)
    "lifecycle_reasoning_stage_v1",
    "lifecycle_tape_summary_v1",
    "student_decision_authority_v1",
    # Runtime contract — seam/job terminal when authority rows exceed sealed (after mandate processing).
    "fatal_authority_seal_mismatch_v1",
    # student_test_mode_v1 proof harness (prompt + raw LLM + sealed snapshot).
    "student_test_llm_turn_v1",
    "student_test_sealed_output_snapshot_v1",
    "student_test_pre_reveal_structured_context_v1",
    # LLM/stub failed before student_decision_authority_v1 — no authority/seal orphan.
    "student_decision_failed_before_authority_v1",
)

# Map persisted ``stage`` → graph node ``id`` (reconstructed trace) for merge / provenance.
STAGE_TO_NODE_IDS_V1: dict[str, tuple[str, ...]] = {
    "packet_built": ("packet_build",),
    "memory_retrieval_completed": ("memory_retrieval",),
    "llm_called": ("llm_reasoning",),
    "llm_output_received": ("llm_reasoning",),
    "llm_output_rejected": ("llm_reasoning",),
    "student_output_sealed": ("student_decision",),
    "student_execution_intent_consumed": ("student_decision", "referee_execution"),
    "student_controlled_replay_started": ("referee_execution",),
    "student_controlled_replay_completed": ("referee_execution",),
    "referee_execution_started": ("referee_execution",),
    "referee_execution_completed": ("referee_execution",),
    "referee_used_student_output": ("referee_student_output_coupling", "referee_execution"),
    "grading_completed": ("ep_grading",),
    "governance_decided": ("governance_018",),
    "learning_record_appended": ("learning_store",),
    "future_retrieval_observed": ("future_retrieval",),
    "candle_timeframe_nexus_v1": ("memory_retrieval", "referee_execution"),
    "timeframe_mismatch_detected_v1": ("memory_retrieval", "referee_execution"),
    # GT_DIRECTIVE_026A_IMPL — entry reasoning engine stages.
    "market_data_loaded": ("student_reasoning", "llm_reasoning"),
    "indicator_context_eval_v1": ("student_reasoning", "llm_reasoning"),
    "perps_state_model_evaluated_v1": ("student_reasoning", "llm_reasoning"),
    "pattern_memory_evaluated_v1": ("student_reasoning", "llm_reasoning"),
    "expected_value_risk_cost_evaluated_v1": ("student_reasoning", "llm_reasoning"),
    "memory_context_evaluated": ("student_reasoning", "llm_reasoning"),
    "prior_outcomes_evaluated": ("student_reasoning", "llm_reasoning"),
    "risk_reward_evaluated": ("student_reasoning", "llm_reasoning"),
    "decision_synthesis_v1": ("student_reasoning", "llm_reasoning"),
    "entry_reasoning_validated": ("student_reasoning", "llm_reasoning"),
    "entry_reasoning_sealed_v1": ("student_reasoning", "llm_reasoning"),
    "student_reasoning_fault_map_v1": ("student_reasoning", "llm_reasoning"),
    "reasoning_router_decision_v1": ("student_reasoning", "llm_reasoning"),
    "external_reasoning_review_v1": ("student_reasoning", "llm_reasoning"),
    "reasoning_cost_governor_v1": ("student_reasoning", "llm_reasoning"),
    "lifecycle_reasoning_stage_v1": ("student_reasoning", "llm_reasoning"),
    "lifecycle_tape_summary_v1": ("student_reasoning", "llm_reasoning"),
    "student_decision_authority_v1": ("student_decision", "student_reasoning"),
    "fatal_authority_seal_mismatch_v1": ("student_decision",),
    "student_decision_failed_before_authority_v1": ("student_decision", "llm_reasoning"),
    "student_test_pre_reveal_structured_context_v1": ("student_decision", "student_reasoning"),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def learning_trace_memory_sink_active_v1() -> bool:
    return _learning_trace_memory_sink.get() is not None


@contextmanager
def learning_trace_memory_sink_session_v1() -> Iterator[list[dict[str, Any]]]:
    """Collect trace events in-memory only (RM preflight wiring validation)."""
    buf: list[dict[str, Any]] = []
    token = _learning_trace_memory_sink.set(buf)
    try:
        yield buf
    finally:
        _learning_trace_memory_sink.reset(token)


def build_learning_trace_event_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    stage: str,
    status: str,
    summary: str,
    evidence_payload: dict[str, Any] | None = None,
    producer: str,
    trade_id: str | None = None,
    scenario_id: str | None = None,
    trace_extensions_v1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "schema": SCHEMA_EVENT,
        "schema_version": SCHEMA_VERSION,
        "job_id": str(job_id or "").strip(),
        "fingerprint": (str(fingerprint).strip() if fingerprint else None),
        "trade_id": (str(trade_id).strip() if trade_id else None),
        "scenario_id": (str(scenario_id).strip() if scenario_id else None),
        "stage": str(stage or "").strip(),
        "timestamp_utc": _utc_now_iso(),
        "status": str(status or "").strip(),
        "summary": str(summary or "").strip(),
        "evidence_payload": evidence_payload if isinstance(evidence_payload, dict) else {},
        "producer": str(producer or "").strip() or "unknown",
    }
    if isinstance(trace_extensions_v1, dict) and trace_extensions_v1:
        ev.update(trace_extensions_v1)
    return ev


def append_learning_trace_event_v1(
    event: dict[str, Any],
    *,
    path: Path | None = None,
) -> Path:
    """Append one validated line to ``learning_trace_events_v1.jsonl`` (creates parent dirs)."""
    p = (path or default_learning_trace_events_jsonl()).expanduser().resolve()
    if str(event.get("schema") or "") != SCHEMA_EVENT:
        raise ValueError("event schema must be learning_trace_event_v1")
    sink = _learning_trace_memory_sink.get()
    if sink is not None:
        sink.append(copy.deepcopy(event))
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return p


def read_learning_trace_events_for_job_v1(
    job_id: str,
    *,
    path: Path | None = None,
    max_lines: int = 500_000,
) -> list[dict[str, Any]]:
    """Return all persisted events for ``job_id`` (file order), bounded scan."""
    jid = str(job_id or "").strip()
    if not jid:
        return []
    p = (path or default_learning_trace_events_jsonl()).expanduser().resolve()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    n = 0
    with p.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if n >= max_lines:
                break
            n += 1
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(obj.get("job_id") or "").strip() != jid:
                continue
            if str(obj.get("schema") or "") == SCHEMA_EVENT:
                out.append(obj)
    return out


def count_learning_trace_terminal_integrity_v1(
    job_id: str,
    *,
    path: Path | None = None,
    max_lines: int = 2_000_000,
) -> dict[str, Any]:
    """
    Single-pass scan of ``learning_trace_events_v1.jsonl`` for **this job only** — counts rows whose
    ``stage`` is exactly ``student_decision_authority_v1`` or ``student_output_sealed``. No inference;
    used for live Terminal integrity (authority vs sealed trade events).
    """
    jid = str(job_id or "").strip()
    out: dict[str, Any] = {
        "schema": "learning_trace_terminal_integrity_v1",
        "job_id": jid or None,
        "student_decision_authority_v1_count": 0,
        "student_output_sealed_count": 0,
        "integrity_ok": True,
        "trace_file_exists": False,
        "lines_scanned_total": 0,
        "lines_matched_job": 0,
    }
    if not jid:
        out["integrity_ok"] = True
        return out
    p = (path or default_learning_trace_events_jsonl()).expanduser().resolve()
    if not p.is_file():
        return out
    out["trace_file_exists"] = True
    auth_n = 0
    sealed_n = 0
    scanned = 0
    matched = 0
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if scanned >= max_lines:
                    break
                scanned += 1
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(obj.get("schema") or "") != SCHEMA_EVENT:
                    continue
                if str(obj.get("job_id") or "").strip() != jid:
                    continue
                matched += 1
                st = str(obj.get("stage") or "").strip()
                if st == "student_decision_authority_v1":
                    auth_n += 1
                elif st == "student_output_sealed":
                    sealed_n += 1
    except OSError:
        out["read_error_v1"] = True
        return out
    out["student_decision_authority_v1_count"] = auth_n
    out["student_output_sealed_count"] = sealed_n
    out["integrity_ok"] = auth_n == sealed_n
    out["lines_scanned_total"] = scanned
    out["lines_matched_job"] = matched
    return out


def count_learning_trace_rm_breadcrumbs_for_job_v1(
    job_id: str,
    *,
    path: Path | None = None,
    max_lines: int = 2_000_000,
) -> dict[str, Any]:
    """
    Count RM-related stages for **this job_id** in ``learning_trace_events_v1.jsonl`` (parallel + seam).

    Used for operator Results panel live counts (file-backed, not UI guesses).
    """
    jid = str(job_id or "").strip()
    out: dict[str, Any] = {
        "schema": "learning_trace_rm_breadcrumb_counts_v1",
        "job_id": jid or None,
        "entry_reasoning_sealed_v1": 0,
        "reasoning_router_decision_v1": 0,
        "reasoning_cost_governor_v1": 0,
        "student_decision_authority_v1": 0,
        "student_output_sealed": 0,
        "decision_source_reasoning_model_v1": 0,
        "authority_with_safety_pass_v1": 0,
        "authority_safety_missing_or_fail_v1": 0,
        "authority_sealed_mismatch_v1": 0,
        "last_scenario_id_v1": None,
        "last_trade_id_v1": None,
        "trace_file_exists": False,
        "lines_scanned_total": 0,
        "lines_matched_job": 0,
    }
    if not jid:
        return out
    p = (path or default_learning_trace_events_jsonl()).expanduser().resolve()
    if not p.is_file():
        return out
    out["trace_file_exists"] = True
    ds_rm = "reasoning_model"
    scanned = 0
    matched = 0
    auth_n = 0
    sealed_n = 0
    last_sid: str | None = None
    last_tid: str | None = None
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if scanned >= max_lines:
                    break
                scanned += 1
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(obj.get("schema") or "") != SCHEMA_EVENT:
                    continue
                if str(obj.get("job_id") or "").strip() != jid:
                    continue
                matched += 1
                st = str(obj.get("stage") or "").strip()
                if obj.get("scenario_id") is not None:
                    last_sid = str(obj.get("scenario_id") or "").strip() or last_sid
                if obj.get("trade_id") is not None:
                    last_tid = str(obj.get("trade_id") or "").strip() or last_tid
                if st == "entry_reasoning_sealed_v1":
                    out["entry_reasoning_sealed_v1"] += 1
                elif st == "reasoning_router_decision_v1":
                    out["reasoning_router_decision_v1"] += 1
                elif st == "reasoning_cost_governor_v1":
                    out["reasoning_cost_governor_v1"] += 1
                elif st == "student_decision_authority_v1":
                    auth_n += 1
                    ep = obj.get("evidence_payload") if isinstance(obj.get("evidence_payload"), dict) else {}
                    inner = ep.get("student_decision_authority_v1") if isinstance(ep.get("student_decision_authority_v1"), dict) else {}
                    ref = inner.get("referee_safety_check_v1")
                    refd = ref if isinstance(ref, dict) else {}
                    if refd.get("passed_v1") is True:
                        out["authority_with_safety_pass_v1"] += 1
                    else:
                        out["authority_safety_missing_or_fail_v1"] += 1
                    if inner.get("decision_source_v1") == ds_rm:
                        out["decision_source_reasoning_model_v1"] += 1
                elif st == "student_output_sealed":
                    sealed_n += 1
                    ep = obj.get("evidence_payload") if isinstance(obj.get("evidence_payload"), dict) else {}
                    if ep.get("decision_source_v1") == ds_rm:
                        out["decision_source_reasoning_model_v1"] += 1
    except OSError:
        out["read_error_v1"] = True
        return out
    out["student_decision_authority_v1"] = auth_n
    out["student_output_sealed"] = sealed_n
    out["authority_sealed_mismatch_v1"] = abs(auth_n - sealed_n) if (auth_n or sealed_n) else 0
    if auth_n and sealed_n and auth_n != sealed_n:
        out["authority_sealed_mismatch_v1"] = max(int(out["authority_sealed_mismatch_v1"]), 1)
    out["last_scenario_id_v1"] = last_sid
    out["last_trade_id_v1"] = last_tid
    out["lines_scanned_total"] = scanned
    out["lines_matched_job"] = matched
    return out


def _node_by_id(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for n in nodes:
        if str(n.get("id") or "") == node_id:
            return n
    return None


def merge_learning_trace_events_into_nodes_v1(
    nodes: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    """
    Mutates ``nodes`` in place: adds ``trace_store`` to ``evidence_provenance_v1`` when a runtime
    event maps to that node; clears ``not_captured_at_runtime_v1`` when the stage supplies proof.

    ``referee_used_student_output`` may carry ``status`` of ``true`` / ``false`` / ``unknown`` (or
    legacy ``pass`` / ``fail`` synonyms). Coupling moves off **NOT PROVEN** when a runtime line exists
    with a resolved verdict.
    """
    for ev in events:
        stage = str(ev.get("stage") or "").strip()
        nids = STAGE_TO_NODE_IDS_V1.get(stage, ())
        for nid in nids:
            n = _node_by_id(nodes, nid)
            if not n:
                continue
            prov = n.setdefault("evidence_provenance_v1", [])
            if "trace_store" not in prov:
                prov.append("trace_store")
            rb = n.setdefault("runtime_breakpoints_v1", [])
            if nid != "referee_student_output_coupling" and "not_captured_at_runtime_v1" in rb:
                rb.remove("not_captured_at_runtime_v1")

        if stage == "referee_used_student_output":
            cn = _node_by_id(nodes, "referee_student_output_coupling")
            if cn:
                ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
                st = str(ev.get("status") or "").strip().lower()
                inf = str(ep.get("student_influence_on_worker_replay_v1") or "").strip().lower()
                if inf in ("true", "false", "unknown"):
                    st = inf
                if st in ("pass", "ok", "true", "yes", "used"):
                    cn["node_status_v1"] = "pass"
                    cn["summary_v1"] = str(ev.get("summary") or "Runtime event: Referee used Student output (trace_store).")
                    evd = cn.setdefault("evidence_v1", {})
                    if isinstance(evd, dict):
                        evd["verdict_v1"] = "PROVEN_BY_RUNTIME_EVENT_V1"
                        evd["source_event_v1"] = {k: ev.get(k) for k in ("stage", "timestamp_utc", "producer") if k in ev}
                    rb2 = cn.setdefault("runtime_breakpoints_v1", [])
                    if "not_captured_at_runtime_v1" in rb2:
                        rb2.remove("not_captured_at_runtime_v1")
                elif st in ("fail", "no", "false", "ignored", "not_used"):
                    cn["node_status_v1"] = "partial"
                    cn["summary_v1"] = str(
                        ev.get("summary") or "Runtime event: Student output not used by Referee (trace_store)."
                    )
                    evd = cn.setdefault("evidence_v1", {})
                    if isinstance(evd, dict):
                        evd["verdict_v1"] = "REFUSED_OR_IGNORED_V1"
                    rb2 = cn.setdefault("runtime_breakpoints_v1", [])
                    if "not_captured_at_runtime_v1" in rb2:
                        rb2.remove("not_captured_at_runtime_v1")
                elif st in ("unknown", "unclear", "maybe", "skipped"):
                    cn["node_status_v1"] = "unknown"
                    cn["summary_v1"] = str(
                        ev.get("summary") or "Runtime event: Referee–Student coupling not determined (trace_store)."
                    )
                    evd = cn.setdefault("evidence_v1", {})
                    if isinstance(evd, dict):
                        evd["verdict_v1"] = "COUPLING_UNKNOWN_V1"
                        evd["source_event_v1"] = {k: ev.get(k) for k in ("stage", "timestamp_utc", "producer") if k in ev}
                    rb2 = cn.setdefault("runtime_breakpoints_v1", [])
                    if "not_captured_at_runtime_v1" in rb2:
                        rb2.remove("not_captured_at_runtime_v1")


def append_learning_trace_event_from_kwargs_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    stage: str,
    status: str,
    summary: str,
    producer: str,
    evidence_payload: dict[str, Any] | None = None,
    trade_id: str | None = None,
    scenario_id: str | None = None,
    path: Path | None = None,
    trace_extensions_v1: dict[str, Any] | None = None,
) -> Path:
    """Convenience: build + append."""
    ev = build_learning_trace_event_v1(
        job_id=job_id,
        fingerprint=fingerprint,
        stage=stage,
        status=status,
        summary=summary,
        evidence_payload=evidence_payload,
        producer=producer,
        trade_id=trade_id,
        scenario_id=scenario_id,
        trace_extensions_v1=trace_extensions_v1,
    )
    return append_learning_trace_event_v1(ev, path=path)


__all__ = [
    "SCHEMA_EVENT",
    "SCHEMA_VERSION",
    "EVENT_STAGES_V1",
    "STAGE_TO_NODE_IDS_V1",
    "append_learning_trace_event_v1",
    "append_learning_trace_event_from_kwargs_v1",
    "build_learning_trace_event_v1",
    "count_learning_trace_rm_breadcrumbs_for_job_v1",
    "count_learning_trace_terminal_integrity_v1",
    "learning_trace_memory_sink_active_v1",
    "learning_trace_memory_sink_session_v1",
    "merge_learning_trace_events_into_nodes_v1",
    "read_learning_trace_events_for_job_v1",
]
