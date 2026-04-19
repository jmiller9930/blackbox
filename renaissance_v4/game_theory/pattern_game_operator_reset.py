"""
Operator-initiated **engine learning reset** (destructive, explicit confirm only).

Separate from ``batch_scorecard.jsonl`` truncation: scorecard is batch audit / UI history;
this module clears canonical files that replay and candidate search actually read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.context_signature_memory import default_memory_path
from renaissance_v4.game_theory.groundhog_memory import groundhog_bundle_path
from renaissance_v4.game_theory.memory_paths import default_experience_log_jsonl, default_run_memory_jsonl

# POST body must match exactly (UI prompts the operator to type this).
RESET_PATTERN_GAME_LEARNING_CONFIRM = "RESET_PATTERN_GAME_LEARNING"


def reset_pattern_game_engine_learning_state_v1(*, confirm: str) -> dict[str, Any]:
    """
    Truncate experience + run memory JSONL, truncate context-signature memory, delete Groundhog bundle.

    Does **not** touch ``batch_scorecard.jsonl`` or ``retrospective_log.jsonl``.
    """
    if confirm != RESET_PATTERN_GAME_LEARNING_CONFIRM:
        return {
            "ok": False,
            "error": f"confirm must be exactly {RESET_PATTERN_GAME_LEARNING_CONFIRM!r}",
        }

    cleared: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    def _truncate(p: Path, kind: str) -> None:
        try:
            pr = p.expanduser().resolve()
            pr.parent.mkdir(parents=True, exist_ok=True)
            pr.write_text("", encoding="utf-8")
            cleared.append({"kind": kind, "path": str(pr), "action": "truncated"})
        except OSError as e:
            errors.append({"kind": kind, "path": str(p), "error": f"{type(e).__name__}: {e}"})

    def _unlink_if_file(p: Path, kind: str) -> None:
        try:
            pr = p.expanduser().resolve()
            if pr.is_file():
                pr.unlink()
                cleared.append({"kind": kind, "path": str(pr), "action": "deleted"})
            else:
                cleared.append({"kind": kind, "path": str(pr), "action": "absent_skipped"})
        except OSError as e:
            errors.append({"kind": kind, "path": str(p), "error": f"{type(e).__name__}: {e}"})

    _truncate(default_experience_log_jsonl(), "experience_log")
    _truncate(default_run_memory_jsonl(), "run_memory")
    _truncate(default_memory_path(), "context_signature_memory")
    _unlink_if_file(groundhog_bundle_path(), "groundhog_bundle")

    return {"ok": len(errors) == 0, "cleared": cleared, "errors": errors}


__all__ = [
    "RESET_PATTERN_GAME_LEARNING_CONFIRM",
    "reset_pattern_game_engine_learning_state_v1",
]
