"""
Exam unit state machine — **Directive GT_DIRECTIVE_003** / architecture **§11.1**, **§3** ordering.

Pure transition logic + optional in-process store for dev APIs. **Not** durable persistence yet.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExamPhase(str, Enum):
    """Ordered phases per STUDENT_PATH_EXAM §3 (strict reveal ordering)."""

    CREATED = "created"
    OPENING_SHOWN = "opening_shown"
    HYPOTHESES_H1_H3 = "hypotheses_h1_h3"
    H4_COMPLETE = "h4_complete"
    DECISION_A_SEALED = "decision_a_sealed"
    DOWNSTREAM_RELEASED = "downstream_released"
    DECISION_B_COMPLETE = "decision_b_complete"
    COMPLETE = "complete"
    INVALID = "invalid"


@dataclass
class TransitionRecord:
    event: str
    payload: dict[str, Any]
    phase_after: str
    ok: bool
    error: str | None = None


@dataclass
class ExamUnitState:
    exam_unit_id: str
    exam_pack_id: str | None
    exam_pack_version: str | None
    phase: ExamPhase = ExamPhase.CREATED
    enter: bool | None = None
    history: list[TransitionRecord] = field(default_factory=list)

    def _invalidate(self, reason: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.phase = ExamPhase.INVALID
        rec = TransitionRecord(
            event=event,
            payload=payload,
            phase_after=self.phase.value,
            ok=False,
            error=reason,
        )
        self.history.append(rec)
        return {"ok": False, "error": reason, "phase": self.phase.value}

    def apply(self, event: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        """
        Apply one lifecycle event. **Forward-only**; forbidden order → **INVALID** unit (§11.1).
        """
        p = dict(payload or {})

        def ok_rec() -> dict[str, Any]:
            rec = TransitionRecord(
                event=event,
                payload=p,
                phase_after=self.phase.value,
                ok=True,
                error=None,
            )
            self.history.append(rec)
            return {"ok": True, "phase": self.phase.value, "exam_unit_id": self.exam_unit_id}

        if self.phase == ExamPhase.INVALID:
            return {"ok": False, "error": "unit_already_invalid", "phase": ExamPhase.INVALID.value}

        if self.phase == ExamPhase.COMPLETE:
            return self._invalidate("unit_already_complete_no_mutations", event, p)

        if event == "open_window_shown":
            if self.phase != ExamPhase.CREATED:
                return self._invalidate("forbidden_transition_open_window_not_from_created", event, p)
            self.phase = ExamPhase.OPENING_SHOWN
            return ok_rec()

        if event == "hypotheses_h1_h3_recorded":
            if self.phase != ExamPhase.OPENING_SHOWN:
                return self._invalidate("forbidden_transition_hypotheses_requires_opening_shown", event, p)
            self.phase = ExamPhase.HYPOTHESES_H1_H3
            return ok_rec()

        if event == "h4_completed":
            if self.phase != ExamPhase.HYPOTHESES_H1_H3:
                return self._invalidate("forbidden_transition_h4_requires_hypotheses", event, p)
            self.phase = ExamPhase.H4_COMPLETE
            return ok_rec()

        if event == "decision_a_sealed":
            if self.phase != ExamPhase.H4_COMPLETE:
                return self._invalidate("forbidden_transition_seal_a_requires_h4", event, p)
            ent = p.get("enter")
            if not isinstance(ent, bool):
                return self._invalidate("decision_a_sealed_requires_boolean_enter", event, p)
            self.enter = ent
            self.phase = ExamPhase.DECISION_A_SEALED
            return ok_rec()

        if event == "downstream_released":
            if self.phase != ExamPhase.DECISION_A_SEALED:
                return self._invalidate("forbidden_transition_downstream_before_seal_a", event, p)
            if self.enter is not True:
                return self._invalidate("downstream_only_when_enter_true", event, p)
            self.phase = ExamPhase.DOWNSTREAM_RELEASED
            return ok_rec()

        if event == "decision_b_complete":
            if self.enter is True:
                if self.phase != ExamPhase.DOWNSTREAM_RELEASED:
                    return self._invalidate("forbidden_transition_decision_b_requires_downstream", event, p)
            else:
                if self.phase != ExamPhase.DECISION_A_SEALED:
                    return self._invalidate("forbidden_transition_decision_b_no_trade_requires_seal_a", event, p)
            self.phase = ExamPhase.DECISION_B_COMPLETE
            return ok_rec()

        if event == "complete_unit":
            if self.phase != ExamPhase.DECISION_B_COMPLETE:
                return self._invalidate("forbidden_transition_complete_requires_decision_b", event, p)
            self.phase = ExamPhase.COMPLETE
            return ok_rec()

        return self._invalidate(f"unknown_event:{event}", event, p)


_UNITS: dict[str, ExamUnitState] = {}
_LOCK = threading.Lock()


def create_exam_unit_v1(
    *,
    exam_pack_id: str | None = None,
    exam_pack_version: str | None = None,
    exam_unit_id: str | None = None,
) -> ExamUnitState:
    uid = (exam_unit_id or "").strip() or uuid.uuid4().hex
    with _LOCK:
        if uid in _UNITS:
            raise ValueError(f"exam_unit_id already exists: {uid!r}")
        u = ExamUnitState(
            exam_unit_id=uid,
            exam_pack_id=exam_pack_id,
            exam_pack_version=exam_pack_version,
        )
        _UNITS[uid] = u
    return u


def get_exam_unit_v1(exam_unit_id: str) -> ExamUnitState | None:
    with _LOCK:
        return _UNITS.get(exam_unit_id.strip())


def exam_unit_to_public_dict(u: ExamUnitState) -> dict[str, Any]:
    return {
        "schema": "exam_unit_state_v1",
        "exam_unit_id": u.exam_unit_id,
        "exam_pack_id": u.exam_pack_id,
        "exam_pack_version": u.exam_pack_version,
        "phase": u.phase.value,
        "enter": u.enter,
        "history": [
            {
                "event": h.event,
                "payload": h.payload,
                "phase_after": h.phase_after,
                "ok": h.ok,
                "error": h.error,
            }
            for h in u.history
        ],
    }


def reset_exam_units_for_tests_v1() -> None:
    """Test helper — clear in-memory store."""
    with _LOCK:
        _UNITS.clear()


def apply_exam_unit_transition_v1(
    exam_unit_id: str, event: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Apply one event to stored unit; ``not_found`` if id missing."""
    u = get_exam_unit_v1(exam_unit_id)
    if u is None:
        return {"ok": False, "error": "exam_unit_not_found", "exam_unit_id": exam_unit_id}
    return u.apply(event, payload)


__all__ = [
    "ExamPhase",
    "ExamUnitState",
    "apply_exam_unit_transition_v1",
    "create_exam_unit_v1",
    "exam_unit_to_public_dict",
    "get_exam_unit_v1",
    "reset_exam_units_for_tests_v1",
]
