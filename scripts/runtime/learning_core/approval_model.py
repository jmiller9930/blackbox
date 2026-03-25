"""Twig 6 — approval artifact persistence (sandbox SQLite only).

Does NOT execute remediation, mutate infrastructure, or integrate with runtime dispatch.
See docs/architect/design/twig6_approval_model.md.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from learning_core.remediation_pattern_registry import get_pattern
from learning_core.remediation_validation import get_candidate

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"
STATUS_DEFERRED = "DEFERRED"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_policy(policy_json: str) -> dict[str, Any]:
    try:
        d = json.loads(policy_json or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _policy_requires_no_real_execution(policy: dict[str, Any]) -> bool:
    """Current phase: approval eligibility requires would_allow_real_execution is False."""
    return policy.get("would_allow_real_execution") is False


def _risk_level_for_pattern(conn: sqlite3.Connection, pattern_id: str | None) -> str:
    if not pattern_id:
        return "medium"
    pat = get_pattern(conn, pattern_id)
    if pat is None:
        return "medium"
    if pat.pattern_status in ("rejected_pattern", "deprecated_pattern"):
        return "high"
    if pat.pattern_status == "candidate_pattern":
        return "medium"
    if pat.pattern_status == "validated_pattern":
        return "low"
    return "medium"


def resolve_eligibility(conn: sqlite3.Connection, source_remediation_id: str) -> dict[str, Any]:
    """
    Find latest PASS validation + latest simulation for source_remediation_id (approval artifact).
    Enforces simulation policy would_allow_real_execution == False.
    Returns dict with validation_run_id, simulation_id, pattern_id, confidence_score, risk_level.
    """
    if get_candidate(conn, source_remediation_id) is None:
        raise ValueError(f"source_remediation_id not found: {source_remediation_id}")

    row_v = conn.execute(
        """
        SELECT run_id, confidence FROM validation_runs
        WHERE remediation_id = ? AND result = 'pass'
        ORDER BY datetime(created_at) DESC, run_id DESC
        LIMIT 1
        """,
        (source_remediation_id,),
    ).fetchone()
    if not row_v:
        raise ValueError("no PASS validation run for this source_remediation_id")

    validation_run_id = str(row_v[0])
    confidence_score = float(row_v[1]) if row_v[1] is not None else None

    row_s = conn.execute(
        """
        SELECT execution_simulation_id, pattern_id, policy_json
        FROM remediation_execution_simulations
        WHERE remediation_id = ?
        ORDER BY datetime(simulation_timestamp) DESC, execution_simulation_id DESC
        LIMIT 1
        """,
        (source_remediation_id,),
    ).fetchone()
    if not row_s:
        raise ValueError("no execution simulation for this source_remediation_id")

    simulation_id = str(row_s[0])
    pattern_id = str(row_s[1]) if row_s[1] else None
    policy = _parse_policy(str(row_s[2] or "{}"))
    if not _policy_requires_no_real_execution(policy):
        raise ValueError(
            "simulation policy must show would_allow_real_execution: False for approval eligibility in this phase"
        )

    risk_level = _risk_level_for_pattern(conn, pattern_id)

    return {
        "validation_run_id": validation_run_id,
        "simulation_id": simulation_id,
        "pattern_id": pattern_id,
        "confidence_score": confidence_score,
        "risk_level": risk_level,
    }


def create_approval_request(
    conn: sqlite3.Connection,
    *,
    source_remediation_id: str,
    requested_by: str,
) -> dict[str, Any]:
    """Insert PENDING approval after eligibility checks. No execution side effects."""
    ev = resolve_eligibility(conn, source_remediation_id)
    aid = str(uuid.uuid4())
    now = _iso(_utc_now())
    conn.execute(
        """
        INSERT INTO approvals (
          approval_id, source_remediation_id, pattern_id, validation_run_id, simulation_id,
          requested_by, approved_by, approval_timestamp, expiration_timestamp,
          status, confidence_score, risk_level, created_at, decision_note
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, NULL)
        """,
        (
            aid,
            source_remediation_id,
            ev["pattern_id"],
            ev["validation_run_id"],
            ev["simulation_id"],
            requested_by,
            STATUS_PENDING,
            ev["confidence_score"],
            ev["risk_level"],
            now,
        ),
    )
    conn.commit()
    return get_approval(conn, aid) or {}


def _maybe_expired(conn: sqlite3.Connection, approval_id: str) -> None:
    row = conn.execute(
        "SELECT status, expiration_timestamp FROM approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        return
    status, exp = str(row[0]), row[1]
    if status != STATUS_APPROVED or not exp:
        return
    try:
        exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
    except Exception:
        return
    if _utc_now() >= exp_dt:
        conn.execute(
            "UPDATE approvals SET status = ? WHERE approval_id = ?",
            (STATUS_EXPIRED, approval_id),
        )
        conn.commit()


def get_approval(conn: sqlite3.Connection, approval_id: str) -> dict[str, Any] | None:
    _maybe_expired(conn, approval_id)
    row = conn.execute(
        """
        SELECT approval_id, source_remediation_id, pattern_id, validation_run_id, simulation_id,
               requested_by, approved_by, approval_timestamp, expiration_timestamp,
               status, confidence_score, risk_level, created_at, decision_note
        FROM approvals WHERE approval_id = ?
        """,
        (approval_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "approval_id": str(row[0]),
        "source_remediation_id": str(row[1]),
        "pattern_id": row[2],
        "validation_run_id": str(row[3]),
        "simulation_id": str(row[4]),
        "requested_by": str(row[5]),
        "approved_by": row[6],
        "approval_timestamp": row[7],
        "expiration_timestamp": row[8],
        "status": str(row[9]),
        "confidence_score": row[10],
        "risk_level": row[11],
        "created_at": str(row[12]),
        "decision_note": row[13],
    }


def list_approvals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """All approval rows (calls get_approval per id for expiry side effect on APPROVED)."""
    ids = [
        str(r[0])
        for r in conn.execute("SELECT approval_id FROM approvals ORDER BY datetime(created_at) DESC").fetchall()
    ]
    out: list[dict[str, Any]] = []
    for aid in ids:
        row = get_approval(conn, aid)
        if row:
            out.append(row)
    return out


def approve_pending(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    approved_by: str,
    ttl_hours: int = 168,
    decision_note: str | None = None,
) -> dict[str, Any]:
    """PENDING → APPROVED. Sets expiration_timestamp. Does not execute anything."""
    row = conn.execute(
        "SELECT status FROM approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"approval_id not found: {approval_id}")
    if str(row[0]) != STATUS_PENDING:
        raise ValueError(f"invalid transition: status is {row[0]}, expected PENDING")

    now = _utc_now()
    exp = now + timedelta(hours=max(0, int(ttl_hours)))
    ts = _iso(now)
    exp_s = _iso(exp)
    note = (decision_note or "").strip() or None
    conn.execute(
        """
        UPDATE approvals SET
          status = ?,
          approved_by = ?,
          approval_timestamp = ?,
          expiration_timestamp = ?,
          decision_note = ?
        WHERE approval_id = ?
        """,
        (STATUS_APPROVED, approved_by, ts, exp_s, note, approval_id),
    )
    conn.commit()
    out = get_approval(conn, approval_id)
    return out or {}


def reject_pending(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    approved_by: str,
    decision_note: str | None = None,
) -> dict[str, Any]:
    """PENDING → REJECTED."""
    row = conn.execute(
        "SELECT status FROM approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"approval_id not found: {approval_id}")
    if str(row[0]) != STATUS_PENDING:
        raise ValueError(f"invalid transition: status is {row[0]}, expected PENDING")

    now = _iso(_utc_now())
    note = (decision_note or "").strip() or None
    conn.execute(
        """
        UPDATE approvals SET
          status = ?,
          approved_by = ?,
          approval_timestamp = ?,
          expiration_timestamp = NULL,
          decision_note = ?
        WHERE approval_id = ?
        """,
        (STATUS_REJECTED, approved_by, now, note, approval_id),
    )
    conn.commit()
    out = get_approval(conn, approval_id)
    return out or {}


def defer_pending(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    approved_by: str,
    decision_note: str | None = None,
) -> dict[str, Any]:
    """PENDING → DEFERRED. Audited hold; does not execute or mutate pipeline artifacts."""
    row = conn.execute(
        "SELECT status FROM approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"approval_id not found: {approval_id}")
    if str(row[0]) != STATUS_PENDING:
        raise ValueError(f"invalid transition: status is {row[0]}, expected PENDING")

    now = _iso(_utc_now())
    note = (decision_note or "").strip() or None
    conn.execute(
        """
        UPDATE approvals SET
          status = ?,
          approved_by = ?,
          approval_timestamp = ?,
          expiration_timestamp = NULL,
          decision_note = ?
        WHERE approval_id = ?
        """,
        (STATUS_DEFERRED, approved_by, now, note, approval_id),
    )
    conn.commit()
    out = get_approval(conn, approval_id)
    return out or {}
