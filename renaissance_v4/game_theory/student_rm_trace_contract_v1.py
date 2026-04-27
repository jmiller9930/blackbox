"""
Student (non-baseline) RM wiring contract — **closed path** through the Reasoning Model.

* ``PATTERN_GAME_LEARNING_TRACE_EVENTS=0`` must **not** suppress mandated trace emits during
  the Student seam; ``student_rm_trace_mandate_emit_active_v1()`` is set for the seam body.
* ``student_rm_wiring_mandate_active_v1`` identifies non-baseline exam contracts for preflight
  / post-run enforcement helpers.
"""

from __future__ import annotations

import contextvars
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    normalize_student_reasoning_mode_v1,
)

_STUDENT_RM_MANDATE_EMIT_V1: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "student_rm_mandate_emit_v1", default=False
)


def student_rm_trace_mandate_emit_active_v1() -> bool:
    return bool(_STUDENT_RM_MANDATE_EMIT_V1.get())


def student_rm_trace_mandate_begin_v1() -> contextvars.Token[bool]:
    """Call when entering the Student seam body for a non-baseline profile; pair with reset."""
    return _STUDENT_RM_MANDATE_EMIT_V1.set(True)


def student_rm_trace_mandate_reset_v1(token: contextvars.Token[bool]) -> None:
    _STUDENT_RM_MANDATE_EMIT_V1.reset(token)


def student_rm_wiring_mandate_active_v1(exam_run_contract_request_v1: dict[str, Any] | None) -> bool:
    ex_req = exam_run_contract_request_v1 if isinstance(exam_run_contract_request_v1, dict) else None
    profile = normalize_student_reasoning_mode_v1(
        str((ex_req or {}).get("student_brain_profile_v1") or (ex_req or {}).get("student_reasoning_mode") or "")
    )
    return profile != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1


__all__ = [
    "student_rm_trace_mandate_begin_v1",
    "student_rm_trace_mandate_emit_active_v1",
    "student_rm_trace_mandate_reset_v1",
    "student_rm_wiring_mandate_active_v1",
]
