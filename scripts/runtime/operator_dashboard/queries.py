"""Read-only SELECT helpers for Layer 2 dashboard. No writes."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

STAGE_ORDER = ("DETECT", "SUGGEST", "INGEST", "VALIDATE", "ANALYZE", "PATTERN", "SIMULATE")


def _na(v: Any) -> str:
    if v is None:
        return "N/A"
    s = str(v).strip()
    return s if s else "N/A"


def _parse_json_obj(s: str | None) -> dict[str, Any]:
    if not s:
        return {}
    try:
        o = json.loads(s)
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def _evidence_nonempty(evidence_json: str | None) -> bool:
    try:
        arr = json.loads(evidence_json or "[]")
        return isinstance(arr, list) and len(arr) > 0
    except Exception:
        return False


def _build_stages_for_candidate(
    cand: sqlite3.Row,
    vr: sqlite3.Row | None,
    an: sqlite3.Row | None,
    pat: sqlite3.Row | None,
    sim: sqlite3.Row | None,
) -> list[dict[str, Any]]:
    rid = str(cand["remediation_id"])
    detect_ok = bool(cand["related_issue_id"]) or _evidence_nonempty(str(cand["evidence_json"] or ""))
    suggest_ok = bool(str(cand["proposed_action"] or "").strip())
    ingest_ok = True
    val_ok = vr is not None
    an_ok = an is not None
    pat_ok = pat is not None
    sim_ok = sim is not None

    def st(name: str, ok: bool, ts: str | None) -> dict[str, Any]:
        return {"name": name, "status": "complete" if ok else "missing", "timestamp": _na(ts)}

    return [
        st("DETECT", detect_ok, str(cand["created_at"]) if detect_ok else None),
        st("SUGGEST", suggest_ok, str(cand["created_at"]) if suggest_ok else None),
        st("INGEST", ingest_ok, str(cand["created_at"])),
        st("VALIDATE", val_ok, str(vr["created_at"]) if vr else None),
        st("ANALYZE", an_ok, str(an["analysis_timestamp"]) if an else None),
        st("PATTERN", pat_ok, str(pat["created_at"]) if pat else None),
        st("SIMULATE", sim_ok, str(sim["simulation_timestamp"]) if sim else None),
    ]


def fetch_pipeline_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM remediation_candidates
        ORDER BY datetime(created_at) DESC
        """
    )
    out: list[dict[str, Any]] = []
    for cand in cur.fetchall():
        rid = str(cand["remediation_id"])
        vr = conn.execute(
            """
            SELECT * FROM validation_runs
            WHERE remediation_id = ?
            ORDER BY datetime(created_at) DESC, run_id DESC
            LIMIT 1
            """,
            (rid,),
        ).fetchone()
        vrun_id = str(vr["run_id"]) if vr else None
        an = None
        if vrun_id:
            an = conn.execute(
                "SELECT * FROM validation_outcome_analyses WHERE validation_run_id = ? LIMIT 1",
                (vrun_id,),
            ).fetchone()
        pat = conn.execute(
            """
            SELECT * FROM remediation_patterns
            WHERE source_remediation_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (rid,),
        ).fetchone()
        sim = conn.execute(
            """
            SELECT * FROM remediation_execution_simulations
            WHERE remediation_id = ?
            ORDER BY datetime(simulation_timestamp) DESC, execution_simulation_id DESC
            LIMIT 1
            """,
            (rid,),
        ).fetchone()
        stages = _build_stages_for_candidate(cand, vr, an, pat, sim)
        complete = sum(1 for s in stages if s["status"] == "complete")
        out.append(
            {
                "run_id": rid,
                "remediation_id": rid,
                "stages": stages,
                "stages_complete": complete,
                "stages_total": len(STAGE_ORDER),
                "last_activity": _na(
                    sim and str(sim["simulation_timestamp"])
                    or (pat and str(pat["updated_at"]))
                    or (an and str(an["analysis_timestamp"]))
                    or (vr and str(vr["created_at"]))
                    or str(cand["updated_at"])
                ),
            }
        )
    return out


def fetch_validation_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT run_id, remediation_id, before_state_json, after_state_json,
               result, failure_reason, failure_class, confidence, created_at
        FROM validation_runs
        ORDER BY datetime(created_at) DESC
        """
    )
    rows: list[dict[str, Any]] = []
    for r in cur.fetchall():
        before = _parse_json_obj(str(r["before_state_json"] or ""))
        after = _parse_json_obj(str(r["after_state_json"] or ""))
        rows.append(
            {
                "run_id": str(r["run_id"]),
                "remediation_id": str(r["remediation_id"]),
                "result": str(r["result"]),
                "failure_class": _na(r["failure_class"]),
                "failure_reason": _na(r["failure_reason"]),
                "before_summary": _na(json.dumps(before)[:500] if before else None),
                "after_summary": _na(json.dumps(after)[:500] if after else None),
                "confidence": r["confidence"],
                "created_at": str(r["created_at"]),
            }
        )
    return rows


def fetch_outcome_analyses(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT analysis_id, validation_run_id, remediation_id, outcome_category,
               evidence_summary_json, validation_result, analysis_timestamp
        FROM validation_outcome_analyses
        ORDER BY datetime(analysis_timestamp) DESC
        """
    )
    rows: list[dict[str, Any]] = []
    for r in cur.fetchall():
        ev = _parse_json_obj(str(r["evidence_summary_json"] or "{}"))
        ev_line = _na(json.dumps(ev)[:800] if ev else None)
        rows.append(
            {
                "analysis_id": str(r["analysis_id"]),
                "validation_run_id": str(r["validation_run_id"]),
                "remediation_id": str(r["remediation_id"]),
                "outcome_category": str(r["outcome_category"]),
                "validation_result": str(r["validation_result"]),
                "evidence_summary": ev_line,
                "analysis_timestamp": str(r["analysis_timestamp"]),
            }
        )
    return rows


def fetch_patterns(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT pattern_id, source_remediation_id, validation_run_id, outcome_analysis_id,
               pattern_status, created_at, updated_at
        FROM remediation_patterns
        ORDER BY datetime(updated_at) DESC
        """
    )
    return [
        {
            "pattern_id": str(r["pattern_id"]),
            "source_remediation_id": str(r["source_remediation_id"]),
            "validation_run_id": str(r["validation_run_id"]),
            "outcome_analysis_id": str(r["outcome_analysis_id"]),
            "pattern_status": str(r["pattern_status"]),
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"]),
        }
        for r in cur.fetchall()
    ]


def fetch_simulations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT execution_simulation_id, pattern_id, remediation_id, result,
               failure_reason, failure_class, rollback_attempted, rollback_success,
               simulation_timestamp, policy_json
        FROM remediation_execution_simulations
        ORDER BY datetime(simulation_timestamp) DESC
        """
    )
    rows: list[dict[str, Any]] = []
    for r in cur.fetchall():
        pol = _parse_json_obj(str(r["policy_json"] or "{}"))
        rows.append(
            {
                "execution_simulation_id": str(r["execution_simulation_id"]),
                "pattern_id": str(r["pattern_id"]),
                "remediation_id": str(r["remediation_id"]),
                "result": str(r["result"]),
                "failure_class": _na(r["failure_class"]),
                "failure_reason": _na(r["failure_reason"]),
                "blocked_reason": _na(pol.get("execution_blocked_reason")),
                "approval_required": pol.get("approval_required"),
                "would_allow_real_execution": pol.get("would_allow_real_execution"),
                "rollback_attempted": bool(r["rollback_attempted"]),
                "rollback_success": bool(r["rollback_success"]),
                "simulation_timestamp": str(r["simulation_timestamp"]),
            }
        )
    return rows


def fetch_approvals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT approval_id, source_remediation_id, pattern_id, status,
               requested_by, approved_by, approval_timestamp, expiration_timestamp,
               created_at, risk_level, confidence_score, decision_note
        FROM approvals
        ORDER BY datetime(created_at) DESC
        """
    )
    return [
        {
            "approval_id": str(r["approval_id"]),
            "source_remediation_id": str(r["source_remediation_id"]),
            "pattern_id": r["pattern_id"],
            "status": str(r["status"]),
            "requested_by": str(r["requested_by"]),
            "approved_by": _na(r["approved_by"]),
            "approval_timestamp": _na(r["approval_timestamp"]),
            "expiration_timestamp": _na(r["expiration_timestamp"]),
            "created_at": str(r["created_at"]),
            "risk_level": _na(r["risk_level"]),
            "confidence_score": r["confidence_score"],
            "decision_note": _na(r["decision_note"]),
        }
        for r in cur.fetchall()
    ]

