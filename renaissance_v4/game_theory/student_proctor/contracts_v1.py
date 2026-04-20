"""
Student–Proctor contract freeze (Directive 01).

Versioned JSON-serializable artifacts:

* ``student_output_v1`` — shadow Student decision (no execution authority).
* ``reveal_v1`` — sanctioned join of Student output + Referee truth post-decision.
* ``student_learning_record_v1`` — persistent learning row for cross-run retrieval.

Graded unit v1: **closed trade** (see ``GRADED_UNIT_TYPE_V1``).
"""

from __future__ import annotations

import re
from typing import Any

CONTRACT_VERSION_STUDENT_PROCTOR_V1 = 1

# v1: one Student episode == one closed trade (OutcomeRecord / trade_id) unless architect changes.
GRADED_UNIT_TYPE_V1 = "closed_trade"

SCHEMA_STUDENT_OUTPUT_V1 = "student_output_v1"
SCHEMA_REVEAL_V1 = "reveal_v1"
SCHEMA_STUDENT_LEARNING_RECORD_V1 = "student_learning_record_v1"

_DIRECTIONS = frozenset({"long", "short", "flat"})

# Keys that must **not** appear anywhere in a **pre-reveal** decision packet (leakage prevention v1).
# Conservative list — refine per architect if false positives appear in real packets.
# Exposed as PRE_REVEAL_FORBIDDEN_KEYS_V1 for operators / tests.
_FORBIDDEN_KEYS_PRE_REVEAL_V1: frozenset[str] = frozenset(
    {
        "pnl",
        "mfe",
        "mae",
        "exit_time",
        "exit_price",
        "exit_reason",
        "wins",
        "losses",
        "win_rate",
        "cumulative_pnl",
        "expectancy",
        "binary_scorecard",
        "validation_checksum",
        "referee_truth",
        "referee_flashcard",
        "reveal_v1",
        "outcome_record",
        "graded_reveal_payload",
    }
)

PRE_REVEAL_FORBIDDEN_KEYS_V1: frozenset[str] = _FORBIDDEN_KEYS_PRE_REVEAL_V1

_UUID_LOOSE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _err(msg: str) -> list[str]:
    return [msg]


def _is_uuid(s: str) -> bool:
    return bool(_UUID_LOOSE.match(s.strip()))


def _collect_string_keys(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Return (dotted_path, key) for every string key in dicts (recursive)."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            path = f"{prefix}.{k}" if prefix else k
            out.append((path, k))
            out.extend(_collect_string_keys(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_collect_string_keys(v, f"{prefix}[{i}]"))
    return out


def validate_pre_reveal_bundle_v1(bundle: Any) -> list[str]:
    """
    Ensure **pre-reveal** payloads contain none of the forbidden keys (recursive key-name check).

    **Boundary:** A legal pre-reveal packet describes **causal market / context / memory hooks**
    only. It must not embed Referee outcome fields for the pending graded unit or session summaries
    that substitute for flashcards.

    Returns empty list if valid; otherwise human-readable violation messages.
    """
    if not isinstance(bundle, dict):
        return _err("pre_reveal bundle must be a dict")
    forbidden_lower = {x.lower() for x in _FORBIDDEN_KEYS_PRE_REVEAL_V1}
    msgs: list[str] = []
    for path, key in _collect_string_keys(bundle):
        if key.lower() in forbidden_lower:
            msgs.append(f"forbidden pre_reveal key {key!r} at {path}")
    return msgs


def validate_student_output_v1(doc: Any) -> list[str]:
    """Validate ``student_output_v1`` — shadow Student decision."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("student_output_v1 must be a dict")
    if doc.get("schema") != SCHEMA_STUDENT_OUTPUT_V1:
        errs.append(f"schema must be {SCHEMA_STUDENT_OUTPUT_V1!r}")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    gut = doc.get("graded_unit_type")
    if gut != GRADED_UNIT_TYPE_V1:
        errs.append(f"graded_unit_type must be {GRADED_UNIT_TYPE_V1!r} for v1")
    guid = doc.get("graded_unit_id")
    if not isinstance(guid, str) or not guid.strip():
        errs.append("graded_unit_id must be a non-empty string (trade_id for closed_trade)")
    dam = doc.get("decision_at_ms")
    if not isinstance(dam, int):
        errs.append("decision_at_ms must be int (Unix ms)")
    if not isinstance(doc.get("act"), bool):
        errs.append("act must be bool")
    d = doc.get("direction")
    if d is not None and (not isinstance(d, str) or d.lower() not in _DIRECTIONS):
        errs.append("direction must be one of long|short|flat or null")
    pr = doc.get("pattern_recipe_ids")
    if not isinstance(pr, list) or not all(isinstance(x, str) for x in pr):
        errs.append("pattern_recipe_ids must be a list[str]")
    conf = doc.get("confidence_01")
    if not isinstance(conf, (int, float)) or not 0.0 <= float(conf) <= 1.0:
        errs.append("confidence_01 must be a number in [0, 1]")
    rt = doc.get("reasoning_text")
    if rt is not None and not isinstance(rt, str):
        errs.append("reasoning_text must be str or null")
    sdr = doc.get("student_decision_ref")
    if not isinstance(sdr, str) or not _is_uuid(sdr):
        errs.append("student_decision_ref must be a UUID string")

    # student_output_v1 must never smuggle flashcard fields (forbidden keys anywhere on doc)
    pre = validate_pre_reveal_bundle_v1(doc)
    errs.extend(pre)
    return errs


def validate_reveal_v1(doc: Any) -> list[str]:
    """Validate ``reveal_v1`` — post-decision join (Student + Referee truth)."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("reveal_v1 must be a dict")
    if doc.get("schema") != SCHEMA_REVEAL_V1:
        errs.append(f"schema must be {SCHEMA_REVEAL_V1!r}")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    if not isinstance(doc.get("graded_unit_id"), str) or not str(doc.get("graded_unit_id")).strip():
        errs.append("graded_unit_id required")
    so = doc.get("student_output")
    if not isinstance(so, dict):
        errs.append("student_output must be embedded dict")
    else:
        errs.extend(validate_student_output_v1(so))
    rt = doc.get("referee_truth_v1")
    if not isinstance(rt, dict):
        errs.append("referee_truth_v1 must be a dict")
    else:
        for k in ("trade_id", "symbol", "pnl"):
            if k not in rt:
                errs.append(f"referee_truth_v1 must contain {k!r}")
    comp = doc.get("comparison_v1")
    if not isinstance(comp, dict):
        errs.append("comparison_v1 must be a dict")
    if not isinstance(doc.get("revealed_at_utc"), str) or not doc.get("revealed_at_utc"):
        errs.append("revealed_at_utc must be non-empty ISO8601 string")
    # Reveal **may** contain pnl etc. — do not run pre_reveal on full reveal doc
    return errs


def validate_student_learning_record_v1(doc: Any) -> list[str]:
    """Validate ``student_learning_record_v1`` for append-only store."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return _err("student_learning_record_v1 must be a dict")
    if doc.get("schema") != SCHEMA_STUDENT_LEARNING_RECORD_V1:
        errs.append(f"schema must be {SCHEMA_STUDENT_LEARNING_RECORD_V1!r}")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    for k in ("record_id", "created_utc", "run_id", "graded_unit_id"):
        v = doc.get(k)
        if not isinstance(v, str) or not str(v).strip():
            errs.append(f"{k} must be non-empty string")
    if not isinstance(doc.get("context_signature_v1"), dict):
        errs.append("context_signature_v1 must be a dict")
    if not isinstance(doc.get("student_output"), dict):
        errs.append("student_output must be a dict")
    else:
        errs.extend(validate_student_output_v1(doc["student_output"]))
    if not isinstance(doc.get("referee_outcome_subset"), dict):
        errs.append("referee_outcome_subset must be a dict")
    if not isinstance(doc.get("alignment_flags_v1"), dict):
        errs.append("alignment_flags_v1 must be a dict")
    return errs


def legal_example_student_output_v1() -> dict[str, Any]:
    """Minimal valid ``student_output_v1`` for tests and docs."""
    return {
        "schema": SCHEMA_STUDENT_OUTPUT_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_type": GRADED_UNIT_TYPE_V1,
        "graded_unit_id": "trade_example_001",
        "decision_at_ms": 1_700_000_000_000,
        "act": True,
        "direction": "long",
        "pattern_recipe_ids": ["trend_continuation"],
        "confidence_01": 0.65,
        "reasoning_text": "Hypothesis: continuation in line with cookbook.",
        "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000",
    }


def illegal_pre_reveal_bundle_example_v1() -> dict[str, Any]:
    """Bundle that must fail ``validate_pre_reveal_bundle_v1`` (leaked outcome key)."""
    return {
        "schema": "pre_reveal_decision_packet_v1",
        "graded_unit_id": "trade_x",
        "bars_context": {"close": 101.2},
        "pnl": 12.34,
    }


def legal_example_reveal_v1() -> dict[str, Any]:
    """Minimal valid ``reveal_v1`` (Student snapshot + Referee truth)."""
    so = legal_example_student_output_v1()
    return {
        "schema": SCHEMA_REVEAL_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_id": so["graded_unit_id"],
        "student_output": so,
        "referee_truth_v1": {
            "trade_id": so["graded_unit_id"],
            "symbol": "SOLUSDT",
            "direction": "long",
            "pnl": 4.2,
            "mfe": 8.0,
            "mae": 2.1,
            "exit_reason": "take_profit",
        },
        "comparison_v1": {"direction_match": True, "quality_note": "stub"},
        "revealed_at_utc": "2026-04-20T16:00:00Z",
    }


def legal_example_student_learning_record_v1() -> dict[str, Any]:
    """Minimal valid ``student_learning_record_v1``."""
    so = legal_example_student_output_v1()
    return {
        "schema": SCHEMA_STUDENT_LEARNING_RECORD_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "record_id": "660e8400-e29b-41d4-a716-446655440001",
        "created_utc": "2026-04-20T16:00:00Z",
        "run_id": "run_example_abc",
        "graded_unit_id": so["graded_unit_id"],
        "manifest_sha256": None,
        "strategy_id": "renaissance_baseline_v1_stack",
        "context_signature_v1": {"schema": "context_signature_v1", "signature_key": "demo"},
        "student_output": so,
        "referee_outcome_subset": {"pnl": 4.2, "exit_reason": "take_profit"},
        "alignment_flags_v1": {"direction_aligned": True},
    }
