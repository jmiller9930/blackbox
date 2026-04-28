"""
Persist **terminal** parallel batch state to disk so long Student runs remain provable after Flask
restarts (``_JOBS`` is in-memory only).

Writes ``runtime/batches/<job_id>/student_runtime_result_<job_id>.json`` (under
:class:`pml_runtime_layout.pml_runtime_batches_dir`). Prune logic only removes directories named
``batch_*``, so ``job_id`` hex folders are retained unless manually deleted.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.pml_runtime_layout import (
    ensure_pml_runtime_dirs,
    pml_runtime_batches_dir,
)


SCHEMA_PARALLEL_JOB_TERMINAL_RECORD_V1 = "parallel_job_terminal_record_v1"
SCHEMA_STUDENT_RM_MANDATORY_RUNTIME_PROOF_INPUT_V1 = "student_rm_mandatory_runtime_proof_input_v1"


def terminal_student_runtime_result_path_v1(job_id: str) -> Path:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("job_id required")
    return pml_runtime_batches_dir() / jid / f"student_runtime_result_{jid}.json"


def _seam_audit_from_api_payload_v1(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    for k in ("student_loop_directive_09_v1", "student_loop_seam_audit", "student_loop_seam_audit_v1"):
        v = payload.get(k)
        if isinstance(v, dict):
            return v
    return None


def _atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def write_parallel_job_terminal_record_v1(
    *,
    job_id: str,
    terminal_status: str,
    api_result_payload: dict[str, Any] | None,
    session_log_batch_dir: str | None = None,
    telemetry_dir: str | None = None,
    learning_trace_path: Path | None = None,
) -> Path | None:
    """
    Persist full API-shaped result plus proof-oriented mirrors. Safe to call from any terminal path.

    Returns written path, or ``None`` if ``job_id`` empty (should not happen).
    """
    jid = str(job_id or "").strip()
    if not jid:
        return None
    ensure_pml_runtime_dirs()
    lt = learning_trace_path or default_learning_trace_events_jsonl()
    lt_resolved = lt.expanduser().resolve()
    seam = _seam_audit_from_api_payload_v1(api_result_payload)
    stop_reason = None
    if isinstance(seam, dict):
        stop_reason = seam.get("student_seam_stop_reason_v1")
        if stop_reason is not None:
            stop_reason = str(stop_reason)

    proof_input: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_RM_MANDATORY_RUNTIME_PROOF_INPUT_V1,
        "job_id": jid,
        "results": api_result_payload.get("results") if isinstance(api_result_payload, dict) else None,
        "student_loop_seam_audit": seam,
        "student_loop_directive_09_v1": (
            api_result_payload.get("student_loop_directive_09_v1")
            if isinstance(api_result_payload, dict)
            else None
        ),
    }

    out_path = terminal_student_runtime_result_path_v1(jid)
    record: dict[str, Any] = {
        "schema": SCHEMA_PARALLEL_JOB_TERMINAL_RECORD_V1,
        "version": 1,
        "job_id": jid,
        "batch_id_v1": jid,
        "terminal_status": str(terminal_status or "").strip(),
        "persisted_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runtime_batch_folder_v1": str(out_path.parent.resolve()),
        "session_log_batch_dir": session_log_batch_dir,
        "telemetry_dir": telemetry_dir,
        "learning_trace_events_path_v1": str(lt_resolved),
        "student_seam_stop_reason_v1": stop_reason,
        "student_loop_seam_audit_v1": seam,
        "student_rm_mandatory_runtime_proof_input_v1": proof_input,
        "full_parallel_result_v1": api_result_payload,
        "terminal_record_path_v1": str(out_path.resolve()),
    }
    _atomic_write_json(out_path, record)
    return out_path


def load_parallel_job_terminal_record_v1(job_id: str) -> dict[str, Any] | None:
    """Return persisted terminal record JSON, or ``None`` if missing."""
    jid = str(job_id or "").strip()
    if not jid:
        return None
    p = terminal_student_runtime_result_path_v1(jid)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


__all__ = [
    "SCHEMA_PARALLEL_JOB_TERMINAL_RECORD_V1",
    "SCHEMA_STUDENT_RM_MANDATORY_RUNTIME_PROOF_INPUT_V1",
    "load_parallel_job_terminal_record_v1",
    "terminal_student_runtime_result_path_v1",
    "write_parallel_job_terminal_record_v1",
]
