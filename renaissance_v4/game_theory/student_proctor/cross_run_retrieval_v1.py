"""
Directive 06 — Cross-run retrieval into the **legal** pre-reveal decision packet.

Loads prior ``student_learning_record_v1`` rows from the Student Learning Store, matches by
``context_signature_v1.signature_key``, and projects **pre-reveal-safe** slices (no forbidden outcome
key names) into ``retrieved_student_experience_v1``.

**GT_DIRECTIVE_018:** slice count is **capped** (env ``PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES`` or
explicit arg); matches are attached **newest-first** before capping.

Does **not** touch replay, fusion, or execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1,
    SCHEMA_STUDENT_RETRIEVAL_SLICE_V1,
    validate_pre_reveal_bundle_v1,
    validate_student_learning_record_v1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import (
    build_student_decision_packet_v1,
    validate_student_decision_packet_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    list_student_learning_records_by_signature_key,
)
from renaissance_v4.game_theory.student_proctor.student_learning_loop_governance_v1 import (
    resolved_max_retrieval_slices_v1,
)


def project_student_learning_record_to_retrieval_slice_v1(
    record: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Project a validated learning row into ``student_retrieval_slice_v1``.

    **Omits** ``referee_outcome_subset`` / ``alignment_flags_v1`` (can contain forbidden keys like
    ``pnl``). Retains prior ``student_output`` (already no-leak) + identifiers for matching.
    """
    errs = validate_student_learning_record_v1(record)
    if errs:
        return None, errs

    so = record.get("student_output")
    if not isinstance(so, dict) or validate_student_output_v1(so):
        return None, ["student_output missing or invalid in learning record"]

    ctx = record.get("context_signature_v1")
    sk = ""
    if isinstance(ctx, dict) and ctx.get("signature_key") is not None:
        sk = str(ctx.get("signature_key", ""))

    rob = record.get("referee_outcome_subset")
    sym_hint: str | None = None
    if isinstance(rob, dict):
        s = rob.get("symbol")
        if isinstance(s, str) and s.strip():
            sym_hint = s.strip()

    sl: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_RETRIEVAL_SLICE_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "source_record_id": record["record_id"],
        "source_run_id": record["run_id"],
        "prior_graded_unit_id": record["graded_unit_id"],
        "signature_key": sk,
        "prior_student_output": so,
    }
    if sym_hint:
        sl["prior_symbol_hint"] = sym_hint

    pre = validate_pre_reveal_bundle_v1(sl)
    if pre:
        return None, pre
    return sl, []


def build_student_decision_packet_v1_with_cross_run_retrieval(
    *,
    db_path: Path | str,
    symbol: str,
    decision_open_time_ms: int,
    store_path: Path | str,
    retrieval_signature_key: str,
    max_retrieval_slices: int | None = None,
    table: str | None = None,
    max_bars_in_packet: int = 10_000,
    notes: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Build a causal decision packet and attach matching prior-experience slices (same signature key).

    If no rows match, ``retrieved_student_experience_v1`` is an empty list.

    ``max_retrieval_slices`` — pass ``None`` to use **GT_DIRECTIVE_018** env
    ``PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES`` (default 8, max 128). Matching rows are attached
    **newest-first** (last appended in the store wins priority) up to the cap.
    """
    kwargs: dict[str, Any] = {
        "db_path": db_path,
        "symbol": symbol,
        "decision_open_time_ms": decision_open_time_ms,
        "max_bars_in_packet": max_bars_in_packet,
    }
    if table is not None:
        kwargs["table"] = table
    if notes is not None:
        kwargs["notes"] = notes

    base, err = build_student_decision_packet_v1(**kwargs)
    if err:
        return None, err

    matches = list_student_learning_records_by_signature_key(
        store_path, retrieval_signature_key
    )
    # Newest-first: JSONL append order means later lines are more recent.
    matches = list(reversed(matches))
    cap = resolved_max_retrieval_slices_v1(max_retrieval_slices)
    slices: list[dict[str, Any]] = []
    for rec in matches[:cap]:
        sl, _perr = project_student_learning_record_to_retrieval_slice_v1(rec)
        if sl is not None:
            slices.append(sl)

    out = {
        **base,
        FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1: slices,
    }
    perrs = validate_student_decision_packet_v1(out)
    if perrs:
        return None, "decision packet with retrieval failed: " + "; ".join(perrs)
    return out, None


__all__ = [
    "build_student_decision_packet_v1_with_cross_run_retrieval",
    "project_student_learning_record_to_retrieval_slice_v1",
]
