"""
Directive 05 — Student learning store (append-only JSONL).

Persists ``student_learning_record_v1`` rows for later retrieval without an LLM. Storage is
**versioned JSON** under the PML runtime tree — **not** engine memory / fusion bundles.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from renaissance_v4.game_theory.pml_runtime_layout import pml_runtime_root
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    SCHEMA_STUDENT_LEARNING_RECORD_V1,
    validate_reveal_v1,
    validate_student_learning_record_v1,
    validate_student_output_v1,
)


def default_student_learning_store_path_v1() -> Path:
    """
    Default JSONL path: ``<pml_runtime_root>/student_learning/student_learning_records_v1.jsonl``.

    ``pml_runtime_root`` follows ``BLACKBOX_PML_RUNTIME_ROOT`` or ``<repo>/runtime``.

    **Override (lab / CI):** set ``PATTERN_GAME_STUDENT_LEARNING_STORE`` to an absolute or repo-relative
    path for ``*.jsonl`` — used by the operator seam, ``clear_student_learning_store_v1``, and status APIs.
    """
    override = (os.environ.get("PATTERN_GAME_STUDENT_LEARNING_STORE") or "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    p = pml_runtime_root() / "student_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p / "student_learning_records_v1.jsonl"


def _iter_records_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(doc, dict):
                yield doc


def _existing_record_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for doc in _iter_records_jsonl(path):
        rid = doc.get("record_id")
        if isinstance(rid, str) and rid.strip():
            ids.add(rid.strip())
    return ids


def append_student_learning_record_v1(
    store_path: Path | str,
    record: dict[str, Any],
    *,
    forbid_duplicate_record_id: bool = True,
) -> None:
    """
    Append one validated ``student_learning_record_v1`` line (atomic open-append-close).

    When ``forbid_duplicate_record_id`` is True, scans the file for an existing ``record_id``
    and raises ``ValueError`` if found (append-only integrity).
    """
    p = Path(store_path)
    errs = validate_student_learning_record_v1(record)
    if errs:
        raise ValueError("invalid student_learning_record_v1: " + "; ".join(errs))
    rid = record.get("record_id")
    if not isinstance(rid, str) or not rid.strip():
        raise ValueError("record_id required")
    if forbid_duplicate_record_id and p.is_file():
        if rid.strip() in _existing_record_ids(p):
            raise ValueError(f"record_id already present (append-only): {rid!r}")

    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line)


def load_student_learning_records_v1(store_path: Path | str) -> list[dict[str, Any]]:
    """Load all JSONL records (order preserved). Skips malformed lines."""
    p = Path(store_path)
    out: list[dict[str, Any]] = []
    for doc in _iter_records_jsonl(p):
        errs = validate_student_learning_record_v1(doc)
        if not errs:
            out.append(doc)
    return out


def get_student_learning_record_by_id(
    store_path: Path | str,
    record_id: str,
) -> dict[str, Any] | None:
    """Return the **first** schema-valid record with ``record_id`` (canonical for append-only file)."""
    want = record_id.strip()
    for doc in _iter_records_jsonl(Path(store_path)):
        rid = doc.get("record_id")
        if isinstance(rid, str) and rid.strip() == want:
            if validate_student_learning_record_v1(doc) == []:
                return doc
    return None


def list_student_learning_records_by_graded_unit_id(
    store_path: Path | str,
    graded_unit_id: str,
) -> list[dict[str, Any]]:
    gid = graded_unit_id.strip()
    return [
        d
        for d in load_student_learning_records_v1(store_path)
        if str(d.get("graded_unit_id", "")).strip() == gid
    ]


def list_student_learning_records_by_run_id(
    store_path: Path | str,
    run_id: str,
) -> list[dict[str, Any]]:
    r = run_id.strip()
    return [d for d in load_student_learning_records_v1(store_path) if str(d.get("run_id", "")).strip() == r]


def list_student_learning_records_by_signature_key(
    store_path: Path | str,
    signature_key: str,
) -> list[dict[str, Any]]:
    """Match ``context_signature_v1["signature_key"]`` when present."""
    sk = signature_key.strip()
    out: list[dict[str, Any]] = []
    for d in load_student_learning_records_v1(store_path):
        ctx = d.get("context_signature_v1")
        if not isinstance(ctx, dict):
            continue
        if str(ctx.get("signature_key", "")).strip() == sk:
            out.append(d)
    return out


def build_student_learning_record_v1_from_reveal(
    reveal: dict[str, Any],
    *,
    run_id: str,
    context_signature_v1: dict[str, Any],
    record_id: str | None = None,
    created_utc: str | None = None,
    manifest_sha256: str | None = None,
    strategy_id: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Build a storeable ``student_learning_record_v1`` from a validated ``reveal_v1``-shaped dict.

    Does **not** invoke replay or mutate Referee state — projection only.
    """
    errs_rv = validate_reveal_v1(reveal)
    if errs_rv:
        return None, ["reveal invalid: " + "; ".join(errs_rv)]

    so = reveal.get("student_output")
    rt = reveal.get("referee_truth_v1")
    comp = reveal.get("comparison_v1")
    if not isinstance(so, dict) or not isinstance(rt, dict):
        return None, ["reveal missing student_output or referee_truth_v1"]

    so_errs = validate_student_output_v1(so)
    if so_errs:
        return None, ["embedded student_output invalid: " + "; ".join(so_errs)]

    gid = str(reveal.get("graded_unit_id", "") or so.get("graded_unit_id", "")).strip()
    if not gid:
        return None, ["graded_unit_id missing"]

    rid = record_id.strip() if isinstance(record_id, str) and record_id.strip() else str(uuid.uuid4())
    if created_utc is None:
        created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Referee subset: only fields needed for retrieval / alignment (Referee-sourced).
    referee_subset: dict[str, Any] = {
        "trade_id": rt.get("trade_id"),
        "symbol": rt.get("symbol"),
        "pnl": rt.get("pnl"),
        "exit_reason": rt.get("exit_reason"),
    }

    direction_match = comp.get("direction_match") if isinstance(comp, dict) else None
    pnl_pos = comp.get("referee_pnl_positive") if isinstance(comp, dict) else None
    alignment_flags_v1: dict[str, Any] = {
        "direction_aligned": direction_match,
        "referee_pnl_positive": bool(pnl_pos) if pnl_pos is not None else None,
    }

    doc: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_LEARNING_RECORD_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "record_id": rid,
        "created_utc": created_utc,
        "run_id": run_id.strip(),
        "graded_unit_id": gid,
        "context_signature_v1": dict(context_signature_v1),
        "student_output": so,
        "referee_outcome_subset": referee_subset,
        "alignment_flags_v1": alignment_flags_v1,
    }
    if manifest_sha256 is not None:
        doc["manifest_sha256"] = manifest_sha256
    if strategy_id is not None:
        doc["strategy_id"] = strategy_id

    errs = validate_student_learning_record_v1(doc)
    if errs:
        return None, errs
    return doc, []


__all__ = [
    "append_student_learning_record_v1",
    "build_student_learning_record_v1_from_reveal",
    "default_student_learning_store_path_v1",
    "get_student_learning_record_by_id",
    "list_student_learning_records_by_graded_unit_id",
    "list_student_learning_records_by_run_id",
    "list_student_learning_records_by_signature_key",
    "load_student_learning_records_v1",
]
