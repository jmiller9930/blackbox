"""
Directive 08 — Operator controls for the Student Learning **store** (truth separation).

``batch_scorecard.jsonl`` and engine memory files are **separate** from
``student_learning_records_v1.jsonl``. Clearing one must never silently clear another.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    default_student_learning_store_path_v1,
)

# Typed confirm for destructive truncation (UI must prompt exactly).
RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM = "RESET_STUDENT_PROCTOR_LEARNING_STORE"


def student_learning_store_status_v1() -> dict[str, Any]:
    """Read-only metadata for the default JSONL path (no mutation)."""
    p = default_student_learning_store_path_v1()
    exists = p.is_file()
    nbytes = int(p.stat().st_size) if exists else 0
    line_count = 0
    if exists:
        with p.open(encoding="utf-8") as fh:
            line_count = sum(1 for line in fh if line.strip())
    return {
        "schema": "student_learning_store_status_v1",
        "ok": True,
        "path": str(p.resolve()),
        "exists": exists,
        "bytes": nbytes,
        "line_count": line_count,
    }


def clear_student_learning_store_v1(*, confirm: str) -> dict[str, Any]:
    """
    Truncate the Student Learning Store JSONL **only** when ``confirm`` matches exactly.

    Does **not** touch ``batch_scorecard.jsonl``, engine memory JSONL, bundles, or session folders.
    """
    if confirm != RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM:
        return {
            "ok": False,
            "error": (
                "confirm must be exactly "
                f"{RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM!r}"
            ),
        }
    p = default_student_learning_store_path_v1()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "path": str(p)}
    return {
        "ok": True,
        "path": str(p.resolve()),
        "action": "truncated",
        "note": (
            "Student Proctor learning store truncated. Scorecard and engine learning files "
            "were not modified by this action."
        ),
    }


__all__ = [
    "RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM",
    "clear_student_learning_store_v1",
    "student_learning_store_status_v1",
]
