"""4.6.3.2 Part B Twig 4.4 — validation outcome analysis (sandbox-only, deterministic).

Reads `validation_runs` rows and produces structured analyses. Does not execute remediation,
does not integrate with DATA output paths, and does not grant live approval.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

# Documented, deterministic outcome categories (Twig 4.4).
OUTCOME_VALIDATED_SUCCESS = "validated_success"
OUTCOME_REJECTED_FUNCTIONAL = "rejected_functional"
OUTCOME_REJECTED_REGRESSION = "rejected_regression"
OUTCOME_REJECTED_STABILITY = "rejected_stability"
OUTCOME_INSUFFICIENT_EVIDENCE = "insufficient_evidence"

OUTCOME_CATEGORIES: tuple[str, ...] = (
    OUTCOME_VALIDATED_SUCCESS,
    OUTCOME_REJECTED_FUNCTIONAL,
    OUTCOME_REJECTED_REGRESSION,
    OUTCOME_REJECTED_STABILITY,
    OUTCOME_INSUFFICIENT_EVIDENCE,
)

_RETENTION_DISCLAIMER = (
    "Diagnostic analysis only; not live-approved remediation; does not trigger execution "
    "or bypass lifecycle controls."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_outcome_category(
    *,
    validation_result: str,
    failure_class: str,
    failure_reason: str,
) -> str:
    """
    Map sandbox validation row fields to a single outcome category (deterministic).
    """
    vr = (validation_result or "").strip().lower()
    fc = (failure_class or "").strip().lower()
    fr = (failure_reason or "").strip()

    if vr == "pass":
        return OUTCOME_VALIDATED_SUCCESS
    if vr != "fail":
        return OUTCOME_INSUFFICIENT_EVIDENCE

    if fc == "functional":
        return OUTCOME_REJECTED_FUNCTIONAL
    if fc == "regression":
        return OUTCOME_REJECTED_REGRESSION
    if fc == "stability":
        return OUTCOME_REJECTED_STABILITY

    # Unknown fail shape or empty class — treat as insufficient structured evidence.
    if not fc and not fr:
        return OUTCOME_INSUFFICIENT_EVIDENCE
    return OUTCOME_INSUFFICIENT_EVIDENCE


def _parse_state(blob: str) -> dict[str, Any]:
    try:
        d = json.loads(blob or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def build_before_after_summary(before_state: dict[str, Any], after_state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic comparison summary from sandbox snapshots (no LLM)."""
    be = int(before_state.get("error_count", 0) or 0)
    ae = int(after_state.get("error_count", 0) or 0)
    bm = float(before_state.get("metric_score", 0.0) or 0.0)
    am = float(after_state.get("metric_score", 0.0) or 0.0)
    reg = bool(after_state.get("regression_detected", False))
    stable = bool(after_state.get("stable_window", True))
    return {
        "error_count_before": be,
        "error_count_after": ae,
        "error_count_delta": ae - be,
        "metric_score_before": bm,
        "metric_score_after": am,
        "metric_score_delta": am - bm,
        "regression_detected": reg,
        "stable_window": stable,
    }


def build_evidence_summary(
    *,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    outcome_category: str,
    validation_result: str,
    failure_class: str,
    failure_reason: str,
) -> dict[str, Any]:
    """
    Concise, explainable evidence derived only from structured sandbox fields.
    """
    summary = build_before_after_summary(before_state, after_state)
    delta_e = summary["error_count_delta"]
    delta_m = summary["metric_score_delta"]

    if delta_e < 0:
        what_changed = f"error_count decreased by {abs(delta_e)}"
    elif delta_e > 0:
        what_changed = f"error_count increased by {delta_e}"
    else:
        what_changed = "error_count unchanged"

    if delta_m > 0:
        what_improved = f"metric_score increased by {delta_m:.4f}"
    elif delta_m < 0:
        what_improved = f"metric_score decreased by {abs(delta_m):.4f}"
    else:
        what_improved = "metric_score unchanged"

    parts: list[str] = []
    if summary["regression_detected"]:
        parts.append("regression_detected=true")
    if not summary["stable_window"]:
        parts.append("stable_window=false")
    if validation_result == "fail" and failure_class:
        parts.append(f"failure_class={failure_class}")
    what_failed = "; ".join(parts) if parts else "none"

    rationale = (
        f"validation_result={validation_result}; outcome_category={outcome_category}; "
        f"failure_class={failure_class or '(empty)'}; failure_reason={failure_reason or '(empty)'}"
    )

    return {
        "what_changed": what_changed,
        "what_improved": what_improved,
        "what_failed": what_failed,
        "classification_rationale": rationale,
        "retention_boundary": _RETENTION_DISCLAIMER,
        "structured_comparison": summary,
    }


def _fetch_validation_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT run_id, remediation_id, before_state_json, after_state_json, result,
               failure_reason, failure_class, created_at
        FROM validation_runs
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "run_id": str(row[0]),
        "remediation_id": str(row[1]),
        "before_state_json": str(row[2]),
        "after_state_json": str(row[3]),
        "result": str(row[4]),
        "failure_reason": str(row[5] or ""),
        "failure_class": str(row[6] or ""),
        "created_at": str(row[7]),
    }


def analyze_validation_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """
    Build a structured analysis artifact for one validation run (read-only; does not persist).
    """
    row = _fetch_validation_run(conn, run_id)
    if row is None:
        raise LookupError(f"validation run not found: {run_id}")

    before_state = _parse_state(row["before_state_json"])
    after_state = _parse_state(row["after_state_json"])
    outcome = classify_outcome_category(
        validation_result=row["result"],
        failure_class=row["failure_class"],
        failure_reason=row["failure_reason"],
    )
    before_after = build_before_after_summary(before_state, after_state)
    evidence = build_evidence_summary(
        before_state=before_state,
        after_state=after_state,
        outcome_category=outcome,
        validation_result=row["result"],
        failure_class=row["failure_class"],
        failure_reason=row["failure_reason"],
    )

    return {
        "remediation_id": row["remediation_id"],
        "validation_run_id": row["run_id"],
        "validation_result": row["result"],
        "failure_class": row["failure_class"],
        "failure_reason": row["failure_reason"],
        "outcome_category": outcome,
        "before_after_comparison_summary": before_after,
        "evidence_summary": evidence,
        "analysis_timestamp": _utc_now(),
        "source_validation_created_at": row["created_at"],
    }


def _prior_run_count(conn: sqlite3.Connection, remediation_id: str, run_id: str) -> int:
    row = conn.execute("SELECT created_at FROM validation_runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        return 0
    created_at = str(row[0])
    n = conn.execute(
        """
        SELECT COUNT(*) FROM validation_runs
        WHERE remediation_id = ?
          AND datetime(created_at) < datetime(?)
        """,
        (remediation_id, created_at),
    ).fetchone()
    return int(n[0] or 0)


def persist_outcome_analysis(conn: sqlite3.Connection, analysis: dict[str, Any]) -> str:
    """Store analysis in sandbox `validation_outcome_analyses` (does not promote lifecycle)."""
    aid = str(uuid.uuid4())
    run_id = str(analysis["validation_run_id"])
    rem_id = str(analysis["remediation_id"])
    prior = _prior_run_count(conn, rem_id, run_id)
    conn.execute(
        """
        INSERT INTO validation_outcome_analyses (
          analysis_id, validation_run_id, remediation_id, validation_result,
          outcome_category, failure_class, failure_reason,
          before_after_summary_json, evidence_summary_json, analysis_timestamp, prior_run_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            aid,
            run_id,
            rem_id,
            str(analysis["validation_result"]),
            str(analysis["outcome_category"]),
            str(analysis.get("failure_class") or ""),
            str(analysis.get("failure_reason") or ""),
            json.dumps(analysis["before_after_comparison_summary"], sort_keys=True, ensure_ascii=False),
            json.dumps(analysis["evidence_summary"], sort_keys=True, ensure_ascii=False),
            str(analysis["analysis_timestamp"]),
            prior,
        ),
    )
    conn.commit()
    return aid


def analyze_and_persist(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    """Analyze one run and persist the analysis row (sandbox DB only)."""
    analysis = analyze_validation_run(conn, run_id)
    aid = persist_outcome_analysis(conn, analysis)
    analysis["analysis_id"] = aid
    return analysis


def list_recent_analyses_for_remediation(
    conn: sqlite3.Connection,
    remediation_id: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Minimal trend hook: recent analyses for one remediation, newest first (sandbox only)."""
    lim = max(1, min(int(limit), 100))
    rows = conn.execute(
        """
        SELECT analysis_id, validation_run_id, outcome_category, validation_result,
               analysis_timestamp, prior_run_count
        FROM validation_outcome_analyses
        WHERE remediation_id = ?
        ORDER BY datetime(analysis_timestamp) DESC, analysis_id DESC
        LIMIT ?
        """,
        (remediation_id, lim),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "analysis_id": str(r[0]),
                "validation_run_id": str(r[1]),
                "outcome_category": str(r[2]),
                "validation_result": str(r[3]),
                "analysis_timestamp": str(r[4]),
                "prior_run_count": int(r[5] or 0),
            }
        )
    return out


def get_persisted_outcome_analysis(conn: sqlite3.Connection, analysis_id: str) -> dict[str, Any] | None:
    """Load a row from `validation_outcome_analyses` (Twig 4.4). Returns None if missing."""
    row = conn.execute(
        """
        SELECT analysis_id, validation_run_id, remediation_id, validation_result,
               outcome_category, failure_class, failure_reason,
               before_after_summary_json, evidence_summary_json, analysis_timestamp, prior_run_count
        FROM validation_outcome_analyses
        WHERE analysis_id = ?
        """,
        (analysis_id,),
    ).fetchone()
    if not row:
        return None
    try:
        before_after = json.loads(str(row[7] or "{}"))
        if not isinstance(before_after, dict):
            before_after = {}
    except Exception:
        before_after = {}
    try:
        evidence = json.loads(str(row[8] or "{}"))
        if not isinstance(evidence, dict):
            evidence = {}
    except Exception:
        evidence = {}
    return {
        "analysis_id": str(row[0]),
        "validation_run_id": str(row[1]),
        "remediation_id": str(row[2]),
        "validation_result": str(row[3]),
        "outcome_category": str(row[4]),
        "failure_class": str(row[5] or ""),
        "failure_reason": str(row[6] or ""),
        "before_after_comparison_summary": before_after,
        "evidence_summary": evidence,
        "analysis_timestamp": str(row[9]),
        "prior_run_count": int(row[10] or 0),
    }
