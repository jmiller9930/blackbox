"""Read-only context for one approval artifact (no pipeline/pattern mutation)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from learning_core.approval_model import get_approval


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def fetch_approval_context(conn: sqlite3.Connection, approval_id: str) -> dict[str, Any]:
    """Linked remediation, validation, analysis, pattern, simulation — read-only."""
    ap = get_approval(conn, approval_id)
    if not ap:
        return {}
    rid = ap["source_remediation_id"]
    prev_rf = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        cand = conn.execute(
            "SELECT * FROM remediation_candidates WHERE remediation_id = ?",
            (rid,),
        ).fetchone()
        vr = conn.execute(
            "SELECT * FROM validation_runs WHERE run_id = ?",
            (ap["validation_run_id"],),
        ).fetchone()
        an = conn.execute(
            "SELECT * FROM validation_outcome_analyses WHERE validation_run_id = ?",
            (ap["validation_run_id"],),
        ).fetchone()
        pat = None
        if ap.get("pattern_id"):
            pat = conn.execute(
                "SELECT * FROM remediation_patterns WHERE pattern_id = ?",
                (ap["pattern_id"],),
            ).fetchone()
        sim = conn.execute(
            "SELECT * FROM remediation_execution_simulations WHERE execution_simulation_id = ?",
            (ap["simulation_id"],),
        ).fetchone()
        sim_policy: dict[str, Any] = {}
        if sim:
            try:
                d = json.loads(str(sim["policy_json"] or "{}"))
                sim_policy = d if isinstance(d, dict) else {}
            except Exception:
                sim_policy = {}

        return {
            "approval": ap,
            "remediation_candidate": _row_dict(cand) if cand else None,
            "validation_run": _row_dict(vr) if vr else None,
            "outcome_analysis": _row_dict(an) if an else None,
            "pattern": _row_dict(pat) if pat else None,
            "simulation": _row_dict(sim) if sim else None,
            "simulation_policy_summary": {
                "would_allow_real_execution": sim_policy.get("would_allow_real_execution"),
                "approval_required": sim_policy.get("approval_required"),
                "execution_blocked_reason": sim_policy.get("execution_blocked_reason"),
            },
        }
    finally:
        conn.row_factory = prev_rf
