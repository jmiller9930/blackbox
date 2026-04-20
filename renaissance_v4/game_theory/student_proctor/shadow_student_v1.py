"""
Directive 03 — Shadow Student output (stub).

Consumes a **legal** ``student_decision_packet_v1`` and emits ``student_output_v1``.

**Shadow-only:** this module does not import replay, fusion, or order logic. Callers may run it
offline or beside Referee code; it must never be wired as an order authority.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Sequence

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    GRADED_UNIT_TYPE_V1,
    SCHEMA_STUDENT_OUTPUT_V1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
    validate_student_decision_packet_v1,
)

# Stable namespace for deterministic UUID decisions (same inputs → same student_decision_ref).
_SHADOW_UUID_NS = uuid.UUID("9e8a7c6b-5d4e-3f2a-1b0c-9d8e7f6a5b4c")


def _direction_from_bars(bars: list[dict[str, Any]]) -> str | None:
    """Heuristic from last two closes — causal only; no external truth."""
    if len(bars) < 2:
        return None
    c_prev = float(bars[-2].get("close") or 0.0)
    c_last = float(bars[-1].get("close") or 0.0)
    if c_last > c_prev:
        return "long"
    if c_last < c_prev:
        return "short"
    return "flat"


def emit_shadow_stub_student_output_v1(
    packet: dict[str, Any],
    *,
    graded_unit_id: str,
    decision_at_ms: int | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Build ``student_output_v1`` from a pre-built decision packet.

    Stub policy (deterministic, causal-bar-only):

    - ``act`` is true when there are at least two bars in the packet (enough for a delta).
    - ``direction`` from last vs previous close; null if fewer than two bars.
    - ``student_decision_ref``: UUIDv5 over (graded_unit_id, decision_at_ms).

    Returns ``(output, [])`` on success, or ``(None, errors)`` when validation fails.
    """
    pkt_errs = validate_student_decision_packet_v1(packet)
    if pkt_errs:
        return None, ["decision packet invalid: " + "; ".join(pkt_errs)]

    t = decision_at_ms if decision_at_ms is not None else int(packet["decision_open_time_ms"])
    bars = packet.get("bars_inclusive_up_to_t") or []
    if not isinstance(bars, list):
        return None, ["bars_inclusive_up_to_t must be list"]

    direction = _direction_from_bars(bars)
    act = len(bars) >= 2
    conf = 0.55 if act else 0.0
    ref_seed = f"shadow_stub_v1:{graded_unit_id}:{t}"
    decision_ref = str(uuid.uuid5(_SHADOW_UUID_NS, ref_seed))

    out: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_OUTPUT_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_type": GRADED_UNIT_TYPE_V1,
        "graded_unit_id": str(graded_unit_id),
        "decision_at_ms": int(t),
        "act": act,
        "direction": direction,
        "pattern_recipe_ids": ["shadow_stub_v1"],
        "confidence_01": conf,
        "reasoning_text": "shadow_stub_v1: causal OHLCV delta only (Directive 03).",
        "student_decision_ref": decision_ref,
    }
    errs = validate_student_output_v1(out)
    if errs:
        return None, errs
    return out, []


def shadow_stub_student_outputs_for_outcomes(
    outcomes: Sequence[OutcomeRecord],
    *,
    db_path: Any,
    decision_time_ms: Callable[[OutcomeRecord], int] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    For each closed trade (graded unit), build a causal packet at **entry** time and emit stub output.

    **Offline / analytic:** does not affect replay. ``decision_time_ms`` defaults to ``entry_time``.
    Returns ``(outputs, errors)`` — if any step fails, ``errors`` is non-empty (outputs may be partial).
    """
    errs_out: list[str] = []
    outputs: list[dict[str, Any]] = []

    def _time(o: OutcomeRecord) -> int:
        if decision_time_ms is not None:
            return int(decision_time_ms(o))
        return int(o.entry_time)

    for o in outcomes:
        pkt, err = build_student_decision_packet_v1(
            db_path=db_path,
            symbol=o.symbol,
            decision_open_time_ms=_time(o),
        )
        if err or pkt is None:
            errs_out.append(f"{o.trade_id}: packet {err!r}")
            continue
        so, e2 = emit_shadow_stub_student_output_v1(pkt, graded_unit_id=o.trade_id, decision_at_ms=_time(o))
        if e2 or so is None:
            errs_out.append(f"{o.trade_id}: output {'; '.join(e2)}")
            continue
        outputs.append(so)

    return outputs, errs_out
