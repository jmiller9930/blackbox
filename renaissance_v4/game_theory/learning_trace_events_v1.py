"""
learning_trace_events_v1 — append-only **runtime** learning-loop trace (capture layer).

The operator **reconstructed** graph (``learning_loop_trace_v1``) is built from scorecard + batch +
learning API. This module persists **handoffs that cannot be reliably inferred later** when workers
call ``append_learning_trace_event_v1``.

Schema line: ``learning_trace_event_v1`` (one JSON object per append).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl

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
    "referee_execution_started",
    "referee_execution_completed",
    "referee_used_student_output",
    "grading_completed",
    "governance_decided",
    "learning_record_appended",
    "future_retrieval_observed",
)

# Map persisted ``stage`` → graph node ``id`` (reconstructed trace) for merge / provenance.
STAGE_TO_NODE_IDS_V1: dict[str, tuple[str, ...]] = {
    "packet_built": ("packet_build",),
    "memory_retrieval_completed": ("memory_retrieval",),
    "llm_called": ("llm_reasoning",),
    "llm_output_received": ("llm_reasoning",),
    "llm_output_rejected": ("llm_reasoning",),
    "student_output_sealed": ("student_decision",),
    "referee_execution_started": ("referee_execution",),
    "referee_execution_completed": ("referee_execution",),
    "referee_used_student_output": ("referee_student_output_coupling", "referee_execution"),
    "grading_completed": ("ep_grading",),
    "governance_decided": ("governance_018",),
    "learning_record_appended": ("learning_store",),
    "future_retrieval_observed": ("future_retrieval",),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
) -> dict[str, Any]:
    return {
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


def append_learning_trace_event_v1(
    event: dict[str, Any],
    *,
    path: Path | None = None,
) -> Path:
    """Append one validated line to ``learning_trace_events_v1.jsonl`` (creates parent dirs)."""
    p = (path or default_learning_trace_events_jsonl()).expanduser().resolve()
    if str(event.get("schema") or "") != SCHEMA_EVENT:
        raise ValueError("event schema must be learning_trace_event_v1")
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
    "merge_learning_trace_events_into_nodes_v1",
    "read_learning_trace_events_for_job_v1",
]
