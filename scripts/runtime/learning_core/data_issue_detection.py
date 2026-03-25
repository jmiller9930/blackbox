"""4.6.3.2 Part B Step 3 — DATA issue detection + suggestions (non-executable)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from anna_modules.util import utc_now
from learning_core.data_execution_aware import evaluate_action_safety


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _mk_issue(
    *,
    category: str,
    severity: str,
    confidence: float,
    evidence: list[str],
    message: str,
) -> dict[str, Any]:
    return {
        "issue_id": str(uuid.uuid4()),
        "category": category,
        "severity": severity,
        "confidence": float(confidence),
        "timestamp": utc_now(),
        "supporting_evidence": list(evidence),
        "message": message,
    }


def detect_infra_issues(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    error_window: int = 50,
) -> list[dict[str, Any]]:
    """
    Deterministic, explainable issue detection from existing runtime records.
    Detection only; no mutation.
    """
    now_dt = now or _now_dt()
    issues: list[dict[str, Any]] = []

    # 1) repeated errors in recent events
    rows = conn.execute(
        """
        SELECT id, event_type, severity, payload
        FROM system_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(error_window),),
    ).fetchall()
    error_rows = [r for r in rows if str(r[2] or "").lower() in ("error", "critical")]
    if len(error_rows) >= 3:
        issues.append(
            _mk_issue(
                category="system",
                severity="medium",
                confidence=0.8,
                evidence=[f"error_events_last_{error_window}={len(error_rows)}"],
                message="Repeated error-level events detected in recent system_events window.",
            )
        )

    # 2) connectivity / failed connection signals in payload text
    bad_tokens = ("connection refused", "http_error", "timeout", "unreachable")
    conn_hits = 0
    for r in rows:
        payload = str(r[3] or "").lower()
        if any(t in payload for t in bad_tokens):
            conn_hits += 1
    if conn_hits > 0:
        issues.append(
            _mk_issue(
                category="connectivity",
                severity="medium" if conn_hits < 3 else "high",
                confidence=0.75,
                evidence=[f"connectivity_error_signals={conn_hits}"],
                message="Connectivity failure signals detected in recent event payloads.",
            )
        )

    # 3) database lock signals
    lock_hits = 0
    for r in rows:
        payload = str(r[3] or "").lower()
        if "database is locked" in payload or "sqlite_busy" in payload:
            lock_hits += 1
    if lock_hits > 0:
        issues.append(
            _mk_issue(
                category="database",
                severity="high" if lock_hits >= 2 else "medium",
                confidence=0.85,
                evidence=[f"db_lock_signals={lock_hits}"],
                message="Database lock/contended access signals detected.",
            )
        )

    # 4) stale market snapshot
    row = conn.execute(
        """
        SELECT updated_at
        FROM tasks
        WHERE title LIKE '[Market Snapshot]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if row:
        snap_dt = _parse_iso(str(row[0]))
        if snap_dt is not None:
            age_hours = (now_dt - snap_dt).total_seconds() / 3600.0
            if age_hours > 6:
                issues.append(
                    _mk_issue(
                        category="ingestion",
                        severity="medium",
                        confidence=0.7,
                        evidence=[f"market_snapshot_age_hours={age_hours:.2f}"],
                        message="Latest market snapshot appears stale.",
                    )
                )
    else:
        issues.append(
            _mk_issue(
                category="ingestion",
                severity="low",
                confidence=0.6,
                evidence=["market_snapshot_missing"],
                message="No market snapshot found in tasks table.",
            )
        )
    return issues


def classify_issue_action(issue: dict[str, Any]) -> str:
    category = str(issue.get("category") or "").lower()
    severity = str(issue.get("severity") or "").lower()
    if category == "database" and severity in ("medium", "high"):
        return "restart_service"
    if category in ("connectivity", "ingestion"):
        return "reload_config"
    if category == "system":
        return "read_health"
    return "read_metrics"


def build_issue_suggestion(
    issue: dict[str, Any],
    *,
    execution_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Structured, non-executable suggestion artifact.
    Includes defer/report decision from execution-aware safety layer.
    """
    action = classify_issue_action(issue)
    safety = evaluate_action_safety(action_name=action, state_snapshot=execution_state)
    category = str(issue.get("category") or "").lower()
    causes: list[str]
    if category == "database":
        causes = ["contention", "long transaction", "lock escalation"]
    elif category == "connectivity":
        causes = ["endpoint unreachable", "transient network fault", "service outage"]
    elif category == "ingestion":
        causes = ["upstream feed lag", "poller interruption", "stalled pipeline"]
    else:
        causes = ["repeated runtime errors", "component instability"]
    return {
        "issue_id": str(issue.get("issue_id") or ""),
        "suggestion_source": "deterministic",
        "llm_generated": False,
        "suggested_fix": f"Suggestion only: consider action '{action}' after safety checks.",
        "possible_causes": causes,
        "recommended_next_step": (
            "report_issue_and_defer"
            if bool(safety.get("defer"))
            else "report_issue_non_disruptive_followup"
        ),
        "safety": safety,
    }
