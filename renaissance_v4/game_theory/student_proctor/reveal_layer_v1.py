"""
Directive 04 — ``reveal_v1`` join layer.

Sanctioned post-decision join of a validated ``student_output_v1`` snapshot and Referee truth
(:class:`OutcomeRecord` → ``referee_truth_v1``). Does not mutate Referee data or replay outcomes.
``referee_truth_v1`` is projected only from :class:`OutcomeRecord` (Directive **05** proof:
``test_directive_d5_referee_immutability_v1``).

**Not** an execution path: no orders, fusion, or manifest side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    SCHEMA_REVEAL_V1,
    validate_reveal_v1,
    validate_student_output_v1,
)

COMPARISON_SCHEMA_HINT_V1 = "reveal_comparison_v1"


def outcome_record_to_referee_truth_v1(outcome: OutcomeRecord) -> dict[str, Any]:
    """
    Map Referee closed-trade record to ``referee_truth_v1`` (structured, Replay-sourced fields only).

    Keys are a superset of validator-required ``trade_id``, ``symbol``, ``pnl``.
    """
    return {
        "trade_id": outcome.trade_id,
        "symbol": outcome.symbol,
        "direction": outcome.direction,
        "pnl": float(outcome.pnl),
        "mfe": float(outcome.mfe),
        "mae": float(outcome.mae),
        "exit_reason": outcome.exit_reason,
        "entry_time_ms": int(outcome.entry_time),
        "exit_time_ms": int(outcome.exit_time),
        "entry_price": float(outcome.entry_price),
        "exit_price": float(outcome.exit_price),
    }


def build_comparison_v1(
    student_output: dict[str, Any],
    referee_truth_v1: dict[str, Any],
) -> dict[str, Any]:
    """
    Referee-grounded comparison scalars (v1). Does not invent economics; uses Student + Referee dicts only.
    """
    sd = student_output.get("direction")
    rd = referee_truth_v1.get("direction")
    sd_s = sd.lower().strip() if isinstance(sd, str) and sd.strip() else None
    rd_s = rd.lower().strip() if isinstance(rd, str) and str(rd).strip() else None
    if sd_s is None or rd_s is None:
        direction_match: bool | None = None
    else:
        direction_match = sd_s == rd_s
    pnl = referee_truth_v1.get("pnl")
    try:
        pnl_f = float(pnl) if pnl is not None else 0.0
    except (TypeError, ValueError):
        pnl_f = 0.0
    return {
        "schema": COMPARISON_SCHEMA_HINT_V1,
        "direction_match": direction_match,
        "referee_pnl_positive": pnl_f > 0.0,
    }


def build_reveal_v1_from_outcome_and_student(
    *,
    student_output: dict[str, Any],
    outcome: OutcomeRecord,
    revealed_at_utc: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Build ``reveal_v1``: embedded Student snapshot + ``referee_truth_v1`` from :class:`OutcomeRecord`.

    Enforces ``student_output['graded_unit_id'] == outcome.trade_id``. Never rewrites Referee numbers.

    Returns ``(reveal, [])`` or ``(None, errors)``.
    """
    errs: list[str] = []
    so_errs = validate_student_output_v1(student_output)
    if so_errs:
        return None, ["student_output invalid: " + "; ".join(so_errs)]

    gid = student_output.get("graded_unit_id")
    if not isinstance(gid, str) or not gid.strip():
        return None, ["student_output missing graded_unit_id"]
    if gid.strip() != outcome.trade_id:
        return None, [
            f"graded_unit_id {gid!r} must equal outcome.trade_id {outcome.trade_id!r}"
        ]

    if revealed_at_utc is None:
        revealed_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rt = outcome_record_to_referee_truth_v1(outcome)
    comp = build_comparison_v1(student_output, rt)
    doc: dict[str, Any] = {
        "schema": SCHEMA_REVEAL_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_id": outcome.trade_id,
        "student_output": student_output,
        "referee_truth_v1": rt,
        "comparison_v1": comp,
        "revealed_at_utc": revealed_at_utc,
    }
    rv = validate_reveal_v1(doc)
    if rv:
        return None, rv
    return doc, []


__all__ = [
    "COMPARISON_SCHEMA_HINT_V1",
    "build_comparison_v1",
    "build_reveal_v1_from_outcome_and_student",
    "outcome_record_to_referee_truth_v1",
]
