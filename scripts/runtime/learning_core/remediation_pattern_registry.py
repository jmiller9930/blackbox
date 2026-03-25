"""4.6.3.2 Part B Twig 4.5 — validated remediation pattern registry (sandbox-only).

Knowledge artifacts derived from sandbox validation outcomes. **Not** executable instructions,
**not** live approval, **not** operational authorization — see module doc on validated_pattern.

Patterns are stored only in the validation sandbox DB (separate tables from production runtime).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from learning_core.validation_outcome_analysis import (
    OUTCOME_INSUFFICIENT_EVIDENCE,
    OUTCOME_REJECTED_FUNCTIONAL,
    OUTCOME_REJECTED_REGRESSION,
    OUTCOME_REJECTED_STABILITY,
    OUTCOME_VALIDATED_SUCCESS,
    get_persisted_outcome_analysis,
)

# --- Clarification (mandatory): validated_pattern does NOT mean live-approved or executable. ---
# It means: validated under sandbox conditions, supported by deterministic evidence,
# eligible for controlled analysis / future consideration only.

STATUS_CANDIDATE = "candidate_pattern"
STATUS_VALIDATED = "validated_pattern"
STATUS_REJECTED = "rejected_pattern"
STATUS_DEPRECATED = "deprecated_pattern"

PatternStatus = Literal[
    "candidate_pattern", "validated_pattern", "rejected_pattern", "deprecated_pattern"
]

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATUS_CANDIDATE: {STATUS_VALIDATED, STATUS_REJECTED},
    STATUS_VALIDATED: {STATUS_DEPRECATED},
    STATUS_REJECTED: set(),
    STATUS_DEPRECATED: set(),
}

_REJECTION_OUTCOMES = frozenset(
    {
        OUTCOME_REJECTED_FUNCTIONAL,
        OUTCOME_REJECTED_REGRESSION,
        OUTCOME_REJECTED_STABILITY,
        OUTCOME_INSUFFICIENT_EVIDENCE,
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _evidence_json_non_empty(evidence_summary_json: str) -> bool:
    try:
        d = json.loads(evidence_summary_json or "{}")
        if not isinstance(d, dict) or not d:
            return False
        raw = json.dumps(d, sort_keys=True, ensure_ascii=False)
        return len(raw.strip()) >= 12
    except Exception:
        return False


def _failure_modes_for_outcome(outcome_category: str, failure_class: str) -> list[str]:
    if outcome_category in _REJECTION_OUTCOMES:
        return [outcome_category, f"failure_class={failure_class or '(empty)'}"]
    return []


def _stability_hint(outcome_category: str, validation_result: str) -> str:
    if validation_result == "pass" and outcome_category == OUTCOME_VALIDATED_SUCCESS:
        return "sandbox_validation_pass"
    if outcome_category in _REJECTION_OUTCOMES:
        return f"sandbox_outcome_{outcome_category}"
    return "unknown"


@dataclass(frozen=True)
class RemediationPattern:
    pattern_id: str
    source_remediation_id: str
    validation_run_id: str
    outcome_analysis_id: str
    outcome_category: str
    validation_evidence_summary_json: str
    failure_modes_json: str
    pattern_status: str
    created_at: str
    updated_at: str
    version: int
    validation_success_count: int
    last_seen_at: str | None
    stability_hint: str


def _row_to_pattern(row: tuple[Any, ...]) -> RemediationPattern:
    return RemediationPattern(
        pattern_id=str(row[0]),
        source_remediation_id=str(row[1]),
        validation_run_id=str(row[2]),
        outcome_analysis_id=str(row[3]),
        outcome_category=str(row[4]),
        validation_evidence_summary_json=str(row[5]),
        failure_modes_json=str(row[6]),
        pattern_status=str(row[7]),
        created_at=str(row[8]),
        updated_at=str(row[9]),
        version=int(row[10] or 1),
        validation_success_count=int(row[11] or 0),
        last_seen_at=str(row[12]) if row[12] is not None else None,
        stability_hint=str(row[13] or ""),
    )


def _append_history(conn: sqlite3.Connection, pattern_id: str, from_s: str, to_s: str, notes: str = "") -> None:
    conn.execute(
        """
        INSERT INTO remediation_pattern_history (pattern_id, from_status, to_status, changed_at, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (pattern_id, from_s, to_s, _utc_now(), notes[:2048]),
    )


def register_pattern_from_outcome_analysis(conn: sqlite3.Connection, outcome_analysis_id: str) -> str:
    """
    Create one pattern row linked to a persisted Twig 4.4 analysis (no auto-promotion to validated).

    - validated_success -> candidate_pattern (promote via promote_candidate_to_validated_pattern explicitly)
    - rejected_* / insufficient_evidence -> rejected_pattern (terminal)
    """
    row = get_persisted_outcome_analysis(conn, outcome_analysis_id)
    if row is None:
        raise LookupError(f"outcome analysis not found: {outcome_analysis_id}")

    oc = str(row["outcome_category"])
    ev_json = json.dumps(row["evidence_summary"], sort_keys=True, ensure_ascii=False)
    if not _evidence_json_non_empty(ev_json):
        raise ValueError("evidence_summary must be non-empty JSON for pattern registration")

    run_id = str(row["validation_run_id"])
    rem_id = str(row["remediation_id"])
    vr = conn.execute(
        "SELECT result FROM validation_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if not vr:
        raise LookupError(f"validation run missing for analysis: {run_id}")

    if oc == OUTCOME_VALIDATED_SUCCESS:
        if str(vr[0]).lower() != "pass":
            raise ValueError("validated_success analysis must reference a passing validation_run")
        status = STATUS_CANDIDATE
    elif oc in _REJECTION_OUTCOMES:
        status = STATUS_REJECTED
    else:
        raise ValueError(f"unsupported outcome_category for registry: {oc}")

    fm = json.dumps(_failure_modes_for_outcome(oc, str(row.get("failure_class") or "")), ensure_ascii=False)
    pid = str(uuid.uuid4())
    now = _utc_now()
    last_seen = str(row["analysis_timestamp"])
    vcount = 1 if str(vr[0]).lower() == "pass" else 0
    stab = _stability_hint(oc, str(row["validation_result"]))

    conn.execute(
        """
        INSERT INTO remediation_patterns (
          pattern_id, source_remediation_id, validation_run_id, outcome_analysis_id,
          outcome_category, validation_evidence_summary_json, failure_modes_json,
          pattern_status, created_at, updated_at, version,
          validation_success_count, last_seen_at, stability_hint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pid,
            rem_id,
            run_id,
            outcome_analysis_id,
            oc,
            ev_json,
            fm,
            status,
            now,
            now,
            1,
            vcount,
            last_seen,
            stab,
        ),
    )
    conn.commit()
    return pid


def promote_candidate_to_validated_pattern(conn: sqlite3.Connection, pattern_id: str) -> RemediationPattern:
    """
    Explicit promotion only. Does NOT grant live execution rights — sandbox-validated knowledge only.

    Preconditions: candidate_pattern, linked analysis outcome validated_success, passing run, non-empty evidence.
    """
    pat = get_pattern(conn, pattern_id)
    if pat is None:
        raise LookupError(f"pattern not found: {pattern_id}")
    if pat.pattern_status != STATUS_CANDIDATE:
        raise ValueError(f"promotion requires {STATUS_CANDIDATE}, got {pat.pattern_status}")

    row = get_persisted_outcome_analysis(conn, pat.outcome_analysis_id)
    if row is None:
        raise LookupError("linked outcome analysis missing")
    if str(row["outcome_category"]) != OUTCOME_VALIDATED_SUCCESS:
        raise ValueError("promotion requires outcome_category validated_success")
    if str(row["validation_result"]).lower() != "pass":
        raise ValueError("promotion requires validation_result pass on linked analysis")
    if not _evidence_json_non_empty(pat.validation_evidence_summary_json):
        raise ValueError("promotion requires non-empty validation_evidence_summary_json")

    run = conn.execute(
        "SELECT result FROM validation_runs WHERE run_id = ?",
        (pat.validation_run_id,),
    ).fetchone()
    if not run or str(run[0]).lower() != "pass":
        raise ValueError("promotion requires passing validation_run")

    now = _utc_now()
    new_v = pat.version + 1
    conn.execute(
        """
        UPDATE remediation_patterns
        SET pattern_status = ?, updated_at = ?, version = ?
        WHERE pattern_id = ?
        """,
        (STATUS_VALIDATED, now, new_v, pattern_id),
    )
    _append_history(conn, pattern_id, STATUS_CANDIDATE, STATUS_VALIDATED, "explicit_promote_sandbox_knowledge_only")
    conn.commit()
    out = get_pattern(conn, pattern_id)
    assert out is not None
    return out


def deprecate_validated_pattern(conn: sqlite3.Connection, pattern_id: str, notes: str = "") -> RemediationPattern:
    """validated_pattern -> deprecated_pattern only."""
    pat = get_pattern(conn, pattern_id)
    if pat is None:
        raise LookupError(f"pattern not found: {pattern_id}")
    if pat.pattern_status != STATUS_VALIDATED:
        raise ValueError(f"deprecation requires {STATUS_VALIDATED}, got {pat.pattern_status}")
    if STATUS_DEPRECATED not in _ALLOWED_TRANSITIONS.get(pat.pattern_status, set()):
        raise ValueError("invalid transition to deprecated")

    now = _utc_now()
    new_v = pat.version + 1
    conn.execute(
        """
        UPDATE remediation_patterns
        SET pattern_status = ?, updated_at = ?, version = ?
        WHERE pattern_id = ?
        """,
        (STATUS_DEPRECATED, now, new_v, pattern_id),
    )
    _append_history(conn, pattern_id, STATUS_VALIDATED, STATUS_DEPRECATED, notes or "deprecated")
    conn.commit()
    out = get_pattern(conn, pattern_id)
    assert out is not None
    return out


def reject_candidate_pattern(conn: sqlite3.Connection, pattern_id: str, notes: str = "") -> RemediationPattern:
    """candidate_pattern -> rejected_pattern (allowed transition)."""
    pat = get_pattern(conn, pattern_id)
    if pat is None:
        raise LookupError(f"pattern not found: {pattern_id}")
    if pat.pattern_status != STATUS_CANDIDATE:
        raise ValueError(f"reject requires {STATUS_CANDIDATE}, got {pat.pattern_status}")

    now = _utc_now()
    new_v = pat.version + 1
    conn.execute(
        """
        UPDATE remediation_patterns
        SET pattern_status = ?, updated_at = ?, version = ?
        WHERE pattern_id = ?
        """,
        (STATUS_REJECTED, now, new_v, pattern_id),
    )
    _append_history(conn, pattern_id, STATUS_CANDIDATE, STATUS_REJECTED, notes or "candidate_rejected")
    conn.commit()
    out = get_pattern(conn, pattern_id)
    assert out is not None
    return out


def get_pattern(conn: sqlite3.Connection, pattern_id: str) -> RemediationPattern | None:
    row = conn.execute(
        """
        SELECT pattern_id, source_remediation_id, validation_run_id, outcome_analysis_id,
               outcome_category, validation_evidence_summary_json, failure_modes_json,
               pattern_status, created_at, updated_at, version,
               validation_success_count, last_seen_at, stability_hint
        FROM remediation_patterns
        WHERE pattern_id = ?
        """,
        (pattern_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_pattern(row)


def list_patterns(
    conn: sqlite3.Connection,
    *,
    pattern_status: str | None = None,
    limit: int = 100,
) -> list[RemediationPattern]:
    """Diagnostics / reporting only — does not execute or feed DATA output."""
    lim = max(1, min(int(limit), 500))
    if pattern_status:
        rows = conn.execute(
            """
            SELECT pattern_id, source_remediation_id, validation_run_id, outcome_analysis_id,
                   outcome_category, validation_evidence_summary_json, failure_modes_json,
                   pattern_status, created_at, updated_at, version,
                   validation_success_count, last_seen_at, stability_hint
            FROM remediation_patterns
            WHERE pattern_status = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (pattern_status, lim),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT pattern_id, source_remediation_id, validation_run_id, outcome_analysis_id,
                   outcome_category, validation_evidence_summary_json, failure_modes_json,
                   pattern_status, created_at, updated_at, version,
                   validation_success_count, last_seen_at, stability_hint
            FROM remediation_patterns
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    return [_row_to_pattern(r) for r in rows]


def pattern_is_rejected_and_never_reusable(pat: RemediationPattern) -> bool:
    """Rejected patterns are retained for diagnostics but never eligible for constructive reuse."""
    return pat.pattern_status == STATUS_REJECTED


def pattern_is_sandbox_validated_knowledge_not_execution_approval(pat: RemediationPattern) -> bool:
    """
    True if status is validated_pattern: denotes sandbox-validated knowledge artifact only.
    Does NOT imply permission to execute, modify systems, or bypass policy gates.
    """
    return pat.pattern_status == STATUS_VALIDATED

