"""
GT_DIRECTIVE_018 — Student **learning loop governance** (v1 operational controls).

First shippable slice: bounded cross-run retrieval (max slices, configurable via env) and
**newest-first** attachment order so the packet does not silently prefer stale memory rows.

Future slices (directive text): memory quality filters, H1–H4 / NO_TRADE contracts, strict P coupling,
anti–narrative-echo-chamber metrics — not all implemented in code v1.
"""

from __future__ import annotations

import os


def resolved_max_retrieval_slices_v1(explicit_cap: int | None) -> int:
    """
    Hard cap on ``retrieved_student_experience_v1`` list length for one decision packet.

    Callers may pass an explicit cap; otherwise ``PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES``
    is parsed (default **8**, clamped **0–128**). Invalid env values fall back to **8**.
    """
    if explicit_cap is not None:
        return max(0, min(128, int(explicit_cap)))
    raw = (os.environ.get("PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES") or "").strip()
    if not raw:
        return 8
    try:
        n = int(raw)
    except ValueError:
        return 8
    return max(0, min(128, n))


def learning_loop_governance_audit_v1(*, max_retrieval_slices_resolved: int) -> dict[str, object]:
    """Small blob merged into ``student_loop_seam_audit_v1`` for operator visibility."""
    return {
        "schema": "student_learning_loop_governance_v1",
        "max_retrieval_slices_resolved": int(max_retrieval_slices_resolved),
        "retrieval_attachment_order_v1": "newest_first",
    }


__all__ = [
    "learning_loop_governance_audit_v1",
    "resolved_max_retrieval_slices_v1",
]
