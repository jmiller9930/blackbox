"""4.6.3.2 Part B Twig 4.3 — manual detection->ingestion->validation pipeline."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from learning_core.data_issue_detection import build_issue_suggestion, detect_infra_issues
from learning_core.remediation_validation import ingest_remediation_candidate, open_validation_sandbox, run_validation


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_pipeline_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS validation_pipeline_runs (
          run_id TEXT PRIMARY KEY,
          started_at TEXT NOT NULL,
          completed_at TEXT,
          status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
          stage TEXT NOT NULL,
          summary_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS validation_pipeline_trace (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT NOT NULL,
          issue_id TEXT,
          remediation_id TEXT,
          validation_result TEXT,
          error_json TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY (run_id) REFERENCES validation_pipeline_runs(run_id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()


@dataclass(frozen=True)
class PipelineResult:
    ok: bool
    run_id: str
    stage: str
    traces: list[dict[str, Any]]
    error: dict[str, Any] | None = None


def run_remediation_validation_pipeline(
    *,
    runtime_conn: sqlite3.Connection,
    sandbox_db_path: Path,
    execution_state: dict[str, Any] | None = None,
    issue_limit: int = 10,
    force_fail_issue_ids: set[str] | None = None,
) -> PipelineResult:
    """
    Manual invocation only (tests/CLI harness). Not wired to DATA output/runtime.
    """
    sandbox_conn = open_validation_sandbox(sandbox_db_path)
    _ensure_pipeline_tables(sandbox_conn)
    run_id = str(uuid.uuid4())
    now = _utc_now()
    sandbox_conn.execute(
        """
        INSERT INTO validation_pipeline_runs (run_id, started_at, status, stage, summary_json)
        VALUES (?, ?, 'running', 'detect', '{}')
        """,
        (run_id, now),
    )
    sandbox_conn.commit()

    issues = detect_infra_issues(runtime_conn)[: int(max(0, issue_limit))]
    traces: list[dict[str, Any]] = []
    state = execution_state or {"execution_sensitive": False}

    for issue in issues:
        issue_id = str(issue.get("issue_id") or "")
        suggestion = build_issue_suggestion(issue, execution_state=state)
        try:
            remediation_id = ingest_remediation_candidate(
                sandbox_conn,
                source_type="deterministic",
                description=str(issue.get("message") or "Detected infrastructure issue"),
                proposed_action=str(suggestion.get("suggested_fix") or "").strip(),
                supporting_evidence=list(issue.get("supporting_evidence") or []),
                source_metadata={
                    "detection_id": issue_id,
                    "timestamp": str(issue.get("timestamp") or ""),
                },
                related_issue_id=issue_id or None,
            )
        except Exception as exc:
            err = {"kind": "ingestion_error", "message": str(exc), "issue_id": issue_id}
            sandbox_conn.execute(
                """
                INSERT INTO validation_pipeline_trace
                (run_id, issue_id, remediation_id, validation_result, error_json, created_at)
                VALUES (?, ?, NULL, NULL, ?, ?)
                """,
                (run_id, issue_id or None, json.dumps(err, ensure_ascii=False), _utc_now()),
            )
            sandbox_conn.execute(
                """
                UPDATE validation_pipeline_runs
                SET completed_at = ?, status = 'failed', stage = 'ingest', summary_json = ?
                WHERE run_id = ?
                """,
                (_utc_now(), json.dumps({"traces": traces, "error": err}, ensure_ascii=False), run_id),
            )
            sandbox_conn.commit()
            return PipelineResult(ok=False, run_id=run_id, stage="ingest", traces=traces, error=err)

        before_state = {"error_count": 1, "metric_score": 1.0}
        forced_fail = issue_id in (force_fail_issue_ids or set())
        after_state = {
            "error_count": 1 if forced_fail else 0,
            "metric_score": 0.9 if forced_fail else 1.1,
            "regression_detected": bool(forced_fail),
            "stable_window": not forced_fail,
        }
        validation = run_validation(
            sandbox_conn,
            remediation_id=remediation_id,
            before_state=before_state,
            after_state=after_state,
        )
        trace = {
            "issue_id": issue_id,
            "remediation_id": remediation_id,
            "validation_result": str(validation.get("result") or ""),
            "timestamp": _utc_now(),
        }
        traces.append(trace)
        sandbox_conn.execute(
            """
            INSERT INTO validation_pipeline_trace
            (run_id, issue_id, remediation_id, validation_result, error_json, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (run_id, issue_id or None, remediation_id, trace["validation_result"], trace["timestamp"]),
        )
        sandbox_conn.commit()

    sandbox_conn.execute(
        """
        UPDATE validation_pipeline_runs
        SET completed_at = ?, status = 'completed', stage = 'complete', summary_json = ?
        WHERE run_id = ?
        """,
        (_utc_now(), json.dumps({"traces": traces}, ensure_ascii=False), run_id),
    )
    sandbox_conn.commit()
    return PipelineResult(ok=True, run_id=run_id, stage="complete", traces=traces, error=None)
