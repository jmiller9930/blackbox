"""Phase 5.4 (continued) — Layer 3 routing for :class:`CandidateTradeV1`.

Persists trade candidates as approval rows (separate from remediation ``approvals``).
Same lifecycle as Twig 6: PENDING → APPROVED | REJECTED | DEFERRED; APPROVED may EXPIRE.

Layer 4 must call :func:`assert_trade_execution_eligible` before any execution intent;
this module does not emit execution.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from market_data.candidate_trade import CandidateTradeV1, validate_candidate_trade_v1

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"
STATUS_DEFERRED = "DEFERRED"

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def candidate_trade_fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ensure_trade_candidate_approval_schema(conn: sqlite3.Connection) -> None:
    """Idempotent DDL for ``trade_candidate_approvals`` (sandbox / any SQLite)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trade_candidate_approvals (
          approval_id TEXT PRIMARY KEY,
          candidate_payload_json TEXT NOT NULL,
          candidate_fingerprint TEXT NOT NULL,
          candidate_expires_at_iso TEXT NOT NULL,
          symbol TEXT NOT NULL,
          participant_id TEXT NOT NULL,
          requested_by TEXT NOT NULL,
          approved_by TEXT,
          approval_timestamp TEXT,
          expiration_timestamp TEXT,
          status TEXT NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'DEFERRED')),
          created_at TEXT NOT NULL,
          decision_note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trade_approvals_participant
          ON trade_candidate_approvals(participant_id, status, created_at);
        """
    )
    conn.commit()


def submit_candidate_trade_for_approval(
    conn: sqlite3.Connection,
    candidate: CandidateTradeV1,
    *,
    requested_by: str,
) -> dict[str, Any]:
    """Insert **PENDING** trade approval; stores canonical candidate JSON. No execution."""
    validate_candidate_trade_v1(candidate)
    ensure_trade_candidate_approval_schema(conn)
    payload = candidate.to_dict()
    fp = candidate_trade_fingerprint(payload)
    aid = str(uuid.uuid4())
    now = _iso(_utc_now())
    conn.execute(
        """
        INSERT INTO trade_candidate_approvals (
          approval_id, candidate_payload_json, candidate_fingerprint, candidate_expires_at_iso,
          symbol, participant_id, requested_by, approved_by, approval_timestamp, expiration_timestamp,
          status, created_at, decision_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, NULL)
        """,
        (
            aid,
            json.dumps(payload, separators=(",", ":"), default=str),
            fp,
            candidate.expires_at_iso.strip(),
            candidate.symbol.strip(),
            candidate.participant_scope.participant_id.strip(),
            requested_by.strip(),
            STATUS_PENDING,
            now,
        ),
    )
    conn.commit()
    return get_trade_candidate_approval(conn, aid) or {}


def _maybe_expire_l3(conn: sqlite3.Connection, approval_id: str) -> None:
    row = conn.execute(
        "SELECT status, expiration_timestamp FROM trade_candidate_approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        return
    status, exp = str(row[0]), row[1]
    if status != STATUS_APPROVED or not exp:
        return
    exp_dt = _parse_iso(str(exp))
    if exp_dt and _utc_now() >= exp_dt:
        conn.execute(
            "UPDATE trade_candidate_approvals SET status = ? WHERE approval_id = ?",
            (STATUS_EXPIRED, approval_id),
        )
        conn.commit()


def get_trade_candidate_approval(conn: sqlite3.Connection, approval_id: str) -> dict[str, Any] | None:
    _maybe_expire_l3(conn, approval_id)
    row = conn.execute(
        """
        SELECT approval_id, candidate_payload_json, candidate_fingerprint, candidate_expires_at_iso,
               symbol, participant_id, requested_by, approved_by, approval_timestamp, expiration_timestamp,
               status, created_at, decision_note
        FROM trade_candidate_approvals WHERE approval_id = ?
        """,
        (approval_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "approval_id": str(row[0]),
        "candidate_payload_json": str(row[1]),
        "candidate_fingerprint": str(row[2]),
        "candidate_expires_at_iso": str(row[3]),
        "symbol": str(row[4]),
        "participant_id": str(row[5]),
        "requested_by": str(row[6]),
        "approved_by": row[7],
        "approval_timestamp": row[8],
        "expiration_timestamp": row[9],
        "status": str(row[10]),
        "created_at": str(row[11]),
        "decision_note": row[12],
    }


def list_trade_candidate_approvals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_trade_candidate_approval_schema(conn)
    ids = [
        str(r[0])
        for r in conn.execute(
            "SELECT approval_id FROM trade_candidate_approvals ORDER BY datetime(created_at) DESC"
        ).fetchall()
    ]
    out: list[dict[str, Any]] = []
    for aid in ids:
        row = get_trade_candidate_approval(conn, aid)
        if row:
            out.append(row)
    return out


def approve_trade_pending(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    approved_by: str,
    ttl_hours: int = 168,
    decision_note: str | None = None,
) -> dict[str, Any]:
    """PENDING → APPROVED. Sets Layer 3 ``expiration_timestamp``. Does not execute."""
    ensure_trade_candidate_approval_schema(conn)
    row = conn.execute(
        "SELECT status FROM trade_candidate_approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"trade approval_id not found: {approval_id}")
    if str(row[0]) != STATUS_PENDING:
        raise ValueError(f"invalid transition: status is {row[0]}, expected PENDING")

    now = _utc_now()
    exp = now + timedelta(hours=max(0, int(ttl_hours)))
    ts = _iso(now)
    exp_s = _iso(exp)
    note = (decision_note or "").strip() or None
    conn.execute(
        """
        UPDATE trade_candidate_approvals SET
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
    return get_trade_candidate_approval(conn, approval_id) or {}


def reject_trade_pending(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    approved_by: str,
    decision_note: str | None = None,
) -> dict[str, Any]:
    """PENDING → REJECTED."""
    ensure_trade_candidate_approval_schema(conn)
    row = conn.execute(
        "SELECT status FROM trade_candidate_approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"trade approval_id not found: {approval_id}")
    if str(row[0]) != STATUS_PENDING:
        raise ValueError(f"invalid transition: status is {row[0]}, expected PENDING")

    now = _iso(_utc_now())
    note = (decision_note or "").strip() or None
    conn.execute(
        """
        UPDATE trade_candidate_approvals SET
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
    return get_trade_candidate_approval(conn, approval_id) or {}


def defer_trade_pending(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    approved_by: str,
    decision_note: str | None = None,
) -> dict[str, Any]:
    """PENDING → DEFERRED."""
    ensure_trade_candidate_approval_schema(conn)
    row = conn.execute(
        "SELECT status FROM trade_candidate_approvals WHERE approval_id = ?",
        (approval_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"trade approval_id not found: {approval_id}")
    if str(row[0]) != STATUS_PENDING:
        raise ValueError(f"invalid transition: status is {row[0]}, expected PENDING")

    now = _iso(_utc_now())
    note = (decision_note or "").strip() or None
    conn.execute(
        """
        UPDATE trade_candidate_approvals SET
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
    return get_trade_candidate_approval(conn, approval_id) or {}


def assert_trade_execution_eligible(conn: sqlite3.Connection, approval_id: str) -> dict[str, Any]:
    """Layer 4 gate: **APPROVED**, Layer 3 not expired, candidate ``expires_at`` not passed.

    Raises ``ValueError`` if execution must not proceed. Does not perform execution.
    """
    ensure_trade_candidate_approval_schema(conn)
    row = get_trade_candidate_approval(conn, approval_id)
    if not row:
        raise ValueError("trade_execution_ineligible:unknown_approval_id")
    st = row["status"]
    if st != STATUS_APPROVED:
        raise ValueError(f"trade_execution_ineligible:status={st}")
    exp_l3 = _parse_iso(str(row.get("expiration_timestamp") or ""))
    if exp_l3 and _utc_now() >= exp_l3:
        raise ValueError("trade_execution_ineligible:layer3_expired")
    cexp = _parse_iso(str(row.get("candidate_expires_at_iso") or ""))
    if cexp and _utc_now() >= cexp:
        raise ValueError("trade_execution_ineligible:candidate_expired")
    return row


def execution_intent_would_emit(*, conn: sqlite3.Connection, approval_id: str) -> bool:
    """Harness helper: ``True`` only when :func:`assert_trade_execution_eligible` would pass."""
    try:
        assert_trade_execution_eligible(conn, approval_id)
    except ValueError:
        return False
    return True
