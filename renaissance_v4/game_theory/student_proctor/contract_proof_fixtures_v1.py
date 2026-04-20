"""
Named proof fixtures for Directive 01 — contract validation and leakage (architect review).

Each ``*_valid`` / ``*_invalid`` pair documents expected validator behavior in tests.
"""

from __future__ import annotations

from typing import Any

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    GRADED_UNIT_TYPE_V1,
    SCHEMA_REVEAL_V1,
    SCHEMA_STUDENT_LEARNING_RECORD_V1,
    SCHEMA_STUDENT_OUTPUT_V1,
    legal_example_student_output_v1,
)


def student_output_v1_valid_proof() -> dict[str, Any]:
    """Passes ``validate_student_output_v1`` — canonical legal document."""
    return legal_example_student_output_v1()


def student_output_v1_invalid_proof_structure() -> dict[str, Any]:
    """
    Fails validation: **structural** — ``contract_version`` wrong (not leakage).
    Demonstrates validator enforces schema/version, not accept-all.
    """
    bad = dict(legal_example_student_output_v1())
    bad["contract_version"] = 99
    return bad


def reveal_v1_valid_proof() -> dict[str, Any]:
    """Passes ``validate_reveal_v1`` — embedding legal student_output + referee_truth_v1."""
    so = legal_example_student_output_v1()
    return {
        "schema": SCHEMA_REVEAL_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_id": so["graded_unit_id"],
        "student_output": so,
        "referee_truth_v1": {
            "trade_id": so["graded_unit_id"],
            "symbol": "SOLUSDT",
            "pnl": -1.0,
        },
        "comparison_v1": {},
        "revealed_at_utc": "2026-01-01T00:00:00Z",
    }


def reveal_v1_invalid_proof_structure() -> dict[str, Any]:
    """
    Fails validation: **structural** — ``referee_truth_v1`` missing required key ``pnl``.
    Reveal may contain pnl inside referee_truth; validator requires shape.
    """
    so = legal_example_student_output_v1()
    return {
        "schema": SCHEMA_REVEAL_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "graded_unit_id": so["graded_unit_id"],
        "student_output": so,
        "referee_truth_v1": {
            "trade_id": so["graded_unit_id"],
            "symbol": "SOLUSDT",
            # missing pnl on purpose
        },
        "comparison_v1": {},
        "revealed_at_utc": "2026-01-01T00:00:00Z",
    }


def student_learning_record_v1_valid_proof() -> dict[str, Any]:
    """Passes ``validate_student_learning_record_v1``."""
    so = legal_example_student_output_v1()
    return {
        "schema": SCHEMA_STUDENT_LEARNING_RECORD_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "record_id": "770e8400-e29b-41d4-a716-446655440002",
        "created_utc": "2026-04-20T16:00:00Z",
        "run_id": "run_proof_xyz",
        "graded_unit_id": so["graded_unit_id"],
        "context_signature_v1": {},
        "student_output": so,
        "referee_outcome_subset": {"pnl": 0.0},
        "alignment_flags_v1": {},
    }


def student_learning_record_v1_invalid_proof_structure() -> dict[str, Any]:
    """
    Fails validation: **structural** — ``alignment_flags_v1`` must be dict, not list.
    """
    base = student_learning_record_v1_valid_proof()
    bad = dict(base)
    bad["alignment_flags_v1"] = []
    return bad
