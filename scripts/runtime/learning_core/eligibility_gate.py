"""4.6.3.7 — Execution eligibility gate (sandbox SQLite only).

Read-only evaluation of whether an APPROVED remediation context satisfies strict
preconditions for a hypothetical future execution layer. Does **not** execute,
mutate infrastructure, alter approvals, or integrate with messaging.

See docs/architect/design/execution_eligibility_gate.md.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from learning_core.approval_model import STATUS_APPROVED, STATUS_EXPIRED

ELIGIBLE = "ELIGIBLE"
INELIGIBLE = "INELIGIBLE"
EXPIRED = "EXPIRED"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_policy(policy_json: str) -> dict[str, Any]:
    try:
        d = json.loads(policy_json or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _policy_requires_no_real_execution(policy: dict[str, Any]) -> bool:
    return policy.get("would_allow_real_execution") is False


def _load_approval_row(conn: sqlite3.Connection, approval_id: str) -> dict[str, Any] | None:
    """Read approval without calling get_approval (no approval-layer expiry side effects)."""
    row = conn.execute(
        """
        SELECT approval_id, source_remediation_id, validation_run_id, simulation_id,
               status, expiration_timestamp, confidence_score, risk_level
        FROM approvals WHERE approval_id = ?
        """,
        (approval_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "approval_id": str(row[0]),
        "source_remediation_id": str(row[1]),
        "validation_run_id": str(row[2]),
        "simulation_id": str(row[3]),
        "status": str(row[4]),
        "expiration_timestamp": row[5],
        "confidence_score": row[6],
        "risk_level": row[7],
    }


def _approval_time_expired(ap: dict[str, Any], *, now: datetime) -> bool:
    exp = _parse_iso_ts(str(ap["expiration_timestamp"]) if ap.get("expiration_timestamp") else None)
    if exp is None:
        return False
    return now >= exp


def evaluate_eligibility(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    evaluated_by: str = "eligibility_evaluator_v1",
) -> dict[str, Any]:
    """
    Persist one eligibility evaluation row. Does not modify approvals, validation, or simulations.
    """
    now_dt = _utc_now()
    now_s = _iso(now_dt)
    eb = (evaluated_by or "eligibility_evaluator_v1").strip() or "eligibility_evaluator_v1"

    ap = _load_approval_row(conn, approval_id.strip())
    if ap is None:
        return _persist_ineligible(
            conn,
            approval_id=approval_id.strip(),
            source_remediation_id="",
            validation_run_id="",
            simulation_id="",
            evaluated_at=now_s,
            evaluated_by=eb,
            reason="approval_not_found",
            confidence_score=None,
            risk_level=None,
        )

    src = ap["source_remediation_id"]
    vrun = ap["validation_run_id"]
    sim_id = ap["simulation_id"]
    st = ap["status"]

    def _fail(reason: str) -> dict[str, Any]:
        return _persist_ineligible(
            conn,
            approval_id=ap["approval_id"],
            source_remediation_id=src,
            validation_run_id=vrun,
            simulation_id=sim_id,
            evaluated_at=now_s,
            evaluated_by=eb,
            reason=reason,
            confidence_score=ap.get("confidence_score"),
            risk_level=str(ap["risk_level"]) if ap.get("risk_level") is not None else None,
        )

    if st == STATUS_EXPIRED:
        return _fail("approval_status_expired")
    if st != STATUS_APPROVED:
        return _fail("approval_not_approved")
    if _approval_time_expired(ap, now=now_dt):
        return _fail("approval_time_expired")

    vr = conn.execute(
        """
        SELECT run_id, remediation_id, result
        FROM validation_runs WHERE run_id = ?
        """,
        (vrun,),
    ).fetchone()
    if not vr:
        return _persist_ineligible(
            conn,
            approval_id=ap["approval_id"],
            source_remediation_id=src,
            validation_run_id=vrun,
            simulation_id=sim_id,
            evaluated_at=now_s,
            evaluated_by=eb,
            reason="validation_run_not_found",
            confidence_score=ap.get("confidence_score"),
            risk_level=str(ap["risk_level"]) if ap.get("risk_level") is not None else None,
        )
    if str(vr[1]) != src:
        return _fail("validation_remediation_mismatch")
    if str(vr[2]).lower() != "pass":
        return _fail("validation_not_pass")

    sim = conn.execute(
        """
        SELECT execution_simulation_id, remediation_id, policy_json
        FROM remediation_execution_simulations WHERE execution_simulation_id = ?
        """,
        (sim_id,),
    ).fetchone()
    if not sim:
        return _persist_ineligible(
            conn,
            approval_id=ap["approval_id"],
            source_remediation_id=src,
            validation_run_id=vrun,
            simulation_id=sim_id,
            evaluated_at=now_s,
            evaluated_by=eb,
            reason="simulation_not_found",
            confidence_score=ap.get("confidence_score"),
            risk_level=str(ap["risk_level"]) if ap.get("risk_level") is not None else None,
        )
    if str(sim[1]) != src:
        return _fail("simulation_remediation_mismatch")

    policy = _parse_policy(str(sim[2] or "{}"))
    if not _policy_requires_no_real_execution(policy):
        return _fail("simulation_policy_must_have_would_allow_real_execution_false")

    exp_s = str(ap["expiration_timestamp"]) if ap.get("expiration_timestamp") else None
    eid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO eligibility (
          eligibility_id, approval_id, source_remediation_id, validation_run_id, simulation_id,
          eligibility_status, evaluated_at, expires_at, evaluated_by, confidence_score, risk_level,
          ineligibility_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            eid,
            ap["approval_id"],
            src,
            vrun,
            sim_id,
            ELIGIBLE,
            now_s,
            exp_s,
            eb,
            ap.get("confidence_score"),
            str(ap["risk_level"]) if ap.get("risk_level") is not None else None,
        ),
    )
    conn.commit()
    return {
        "ok": True,
        "persisted": True,
        "eligibility_id": eid,
        "eligibility_status": ELIGIBLE,
        "approval_id": ap["approval_id"],
        "source_remediation_id": src,
        "validation_run_id": vrun,
        "simulation_id": sim_id,
        "evaluated_at": now_s,
        "expires_at": exp_s,
        "evaluated_by": eb,
        "confidence_score": ap.get("confidence_score"),
        "risk_level": ap.get("risk_level"),
        "ineligibility_reason": None,
    }


def _persist_ineligible(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    source_remediation_id: str,
    validation_run_id: str,
    simulation_id: str,
    evaluated_at: str,
    evaluated_by: str,
    reason: str,
    confidence_score: Any,
    risk_level: str | None,
) -> dict[str, Any]:
    eid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO eligibility (
          eligibility_id, approval_id, source_remediation_id, validation_run_id, simulation_id,
          eligibility_status, evaluated_at, expires_at, evaluated_by, confidence_score, risk_level,
          ineligibility_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
        """,
        (
            eid,
            approval_id,
            source_remediation_id or "",
            validation_run_id or "",
            simulation_id or "",
            INELIGIBLE,
            evaluated_at,
            evaluated_by,
            confidence_score,
            risk_level,
            reason,
        ),
    )
    conn.commit()
    return {
        "ok": True,
        "persisted": True,
        "eligibility_id": eid,
        "eligibility_status": INELIGIBLE,
        "approval_id": approval_id,
        "source_remediation_id": source_remediation_id,
        "validation_run_id": validation_run_id,
        "simulation_id": simulation_id,
        "evaluated_at": evaluated_at,
        "expires_at": None,
        "evaluated_by": evaluated_by,
        "confidence_score": confidence_score,
        "risk_level": risk_level,
        "ineligibility_reason": reason,
    }


def _maybe_expire_eligible_row(conn: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    """ELIGIBLE + past expires_at → persist EXPIRED (lifecycle transition)."""
    if row.get("eligibility_status") != ELIGIBLE:
        return row
    exp = _parse_iso_ts(str(row["expires_at"]) if row.get("expires_at") else None)
    if exp is None:
        return row
    if _utc_now() < exp:
        return row
    eid = str(row["eligibility_id"])
    conn.execute(
        """
        UPDATE eligibility SET eligibility_status = ? WHERE eligibility_id = ? AND eligibility_status = ?
        """,
        (EXPIRED, eid, ELIGIBLE),
    )
    conn.commit()
    row = dict(row)
    row["eligibility_status"] = EXPIRED
    row["expired_by_time"] = True
    return row


def get_eligibility_record(conn: sqlite3.Connection, eligibility_id: str) -> dict[str, Any] | None:
    """Return eligibility row; apply ELIGIBLE→EXPIRED when past expires_at."""
    row = conn.execute(
        """
        SELECT eligibility_id, approval_id, source_remediation_id, validation_run_id, simulation_id,
               eligibility_status, evaluated_at, expires_at, evaluated_by, confidence_score, risk_level,
               ineligibility_reason
        FROM eligibility WHERE eligibility_id = ?
        """,
        (eligibility_id.strip(),),
    ).fetchone()
    if not row:
        return None
    out: dict[str, Any] = {
        "eligibility_id": str(row[0]),
        "approval_id": str(row[1]),
        "source_remediation_id": str(row[2]),
        "validation_run_id": str(row[3]),
        "simulation_id": str(row[4]),
        "eligibility_status": str(row[5]),
        "evaluated_at": str(row[6]),
        "expires_at": row[7],
        "evaluated_by": str(row[8]),
        "confidence_score": row[9],
        "risk_level": row[10],
        "ineligibility_reason": row[11],
    }
    out = _maybe_expire_eligible_row(conn, out)
    out.setdefault("expired_by_time", False)
    return out
