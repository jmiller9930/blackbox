"""4.6.3.2 Part B Twig 4.1/4.2 — remediation validation sandbox (non-live)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from _paths import default_sqlite_path

SourceType = Literal["deterministic", "llm_generated", "human_provided"]

_STATES = {"candidate", "under_test", "validated", "rejected"}
_MAX_DESCRIPTION = 8192
_MAX_PROPOSED_ACTION = 4096
_MAX_EVIDENCE_ITEMS = 50
_MAX_EVIDENCE_ITEM_LEN = 2048
_MAX_METADATA_JSON = 16384
_ALLOWED: dict[str, set[str]] = {
    "candidate": {"under_test"},
    "under_test": {"validated", "rejected"},
    "validated": set(),
    "rejected": set(),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _assert_transition(from_state: str, to_state: str) -> None:
    if to_state not in _ALLOWED.get(from_state, set()):
        raise ValueError(f"invalid remediation transition: {from_state} -> {to_state}")


def _is_production_db(path: Path) -> bool:
    try:
        return path.resolve() == default_sqlite_path().resolve()
    except Exception:
        return False


def assert_non_production_sqlite_path(path: Path | str) -> None:
    """
    Refuse the production runtime SQLite path (same rule as open_validation_sandbox).
    Exposed for playground callers that must not import _paths directly.
    """
    p = Path(path).expanduser()
    if _is_production_db(p):
        raise ValueError("path must not be production runtime SQLite (BLACKBOX_SQLITE_PATH)")


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table.replace("_", "").isalnum():
        raise ValueError("invalid table name for introspection")
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {str(r[1]) for r in cur.fetchall()}


def _migrate_remediation_candidates(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='remediation_candidates'"
    ).fetchone()
    if not row:
        return
    cols = _table_columns(conn, "remediation_candidates")
    if not cols:
        return
    if "source_type" not in cols:
        conn.execute(
            "ALTER TABLE remediation_candidates ADD COLUMN source_type TEXT NOT NULL DEFAULT 'deterministic'"
        )
    if "source_metadata_json" not in cols:
        conn.execute(
            "ALTER TABLE remediation_candidates ADD COLUMN source_metadata_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "related_issue_id" not in cols:
        conn.execute("ALTER TABLE remediation_candidates ADD COLUMN related_issue_id TEXT")
    if "ingestion_key" not in cols:
        conn.execute("ALTER TABLE remediation_candidates ADD COLUMN ingestion_key TEXT")
    conn.commit()


def _migrate_approvals_source_remediation_id(conn: sqlite3.Connection) -> None:
    """Sandbox-only: align legacy approvals.remediation_id with design field source_remediation_id."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='approvals'"
    ).fetchone()
    if not row:
        return
    cols = _table_columns(conn, "approvals")
    if "remediation_id" in cols and "source_remediation_id" not in cols:
        conn.execute("ALTER TABLE approvals RENAME COLUMN remediation_id TO source_remediation_id")
        conn.commit()


def open_validation_sandbox(db_path: Path) -> sqlite3.Connection:
    """
    Open isolated SQLite store for remediation validation.
    Refuses production runtime DB path by design.
    """
    p = Path(db_path).expanduser()
    if _is_production_db(p):
        raise ValueError("sandbox path must not be production runtime SQLite path")
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS remediation_candidates (
          remediation_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          source_type TEXT NOT NULL CHECK (source_type IN ('deterministic', 'llm_generated', 'human_provided')),
          description TEXT NOT NULL,
          proposed_action TEXT NOT NULL,
          lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('candidate', 'under_test', 'validated', 'rejected')),
          evidence_json TEXT NOT NULL DEFAULT '[]',
          source_metadata_json TEXT NOT NULL DEFAULT '{}',
          related_issue_id TEXT,
          ingestion_key TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS validation_runs (
          run_id TEXT PRIMARY KEY,
          remediation_id TEXT NOT NULL,
          before_state_json TEXT NOT NULL,
          after_state_json TEXT NOT NULL,
          result TEXT NOT NULL CHECK (result IN ('pass', 'fail')),
          failure_reason TEXT NOT NULL DEFAULT '',
          failure_class TEXT NOT NULL DEFAULT '',
          confidence REAL,
          created_at TEXT NOT NULL,
          FOREIGN KEY (remediation_id) REFERENCES remediation_candidates(remediation_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_validation_runs_remediation
          ON validation_runs(remediation_id, created_at);

        CREATE TABLE IF NOT EXISTS validation_outcome_analyses (
          analysis_id TEXT PRIMARY KEY,
          validation_run_id TEXT NOT NULL UNIQUE,
          remediation_id TEXT NOT NULL,
          validation_result TEXT NOT NULL,
          outcome_category TEXT NOT NULL,
          failure_class TEXT NOT NULL DEFAULT '',
          failure_reason TEXT NOT NULL DEFAULT '',
          before_after_summary_json TEXT NOT NULL,
          evidence_summary_json TEXT NOT NULL,
          analysis_timestamp TEXT NOT NULL,
          prior_run_count INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY (validation_run_id) REFERENCES validation_runs(run_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_outcome_analyses_remediation
          ON validation_outcome_analyses(remediation_id, analysis_timestamp);

        CREATE TABLE IF NOT EXISTS remediation_patterns (
          pattern_id TEXT PRIMARY KEY,
          source_remediation_id TEXT NOT NULL,
          validation_run_id TEXT NOT NULL,
          outcome_analysis_id TEXT NOT NULL UNIQUE,
          outcome_category TEXT NOT NULL,
          validation_evidence_summary_json TEXT NOT NULL,
          failure_modes_json TEXT NOT NULL DEFAULT '[]',
          pattern_status TEXT NOT NULL CHECK (pattern_status IN (
            'candidate_pattern', 'validated_pattern', 'rejected_pattern', 'deprecated_pattern'
          )),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 1,
          validation_success_count INTEGER NOT NULL DEFAULT 0,
          last_seen_at TEXT,
          stability_hint TEXT NOT NULL DEFAULT '',
          FOREIGN KEY (validation_run_id) REFERENCES validation_runs(run_id) ON DELETE CASCADE,
          FOREIGN KEY (outcome_analysis_id) REFERENCES validation_outcome_analyses(analysis_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_remediation_patterns_status
          ON remediation_patterns(pattern_status, created_at);

        CREATE TABLE IF NOT EXISTS remediation_pattern_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          pattern_id TEXT NOT NULL,
          from_status TEXT NOT NULL,
          to_status TEXT NOT NULL,
          changed_at TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '',
          FOREIGN KEY (pattern_id) REFERENCES remediation_patterns(pattern_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS remediation_execution_simulations (
          execution_simulation_id TEXT PRIMARY KEY,
          pattern_id TEXT NOT NULL,
          remediation_id TEXT NOT NULL,
          simulated_action_description TEXT NOT NULL,
          result TEXT NOT NULL CHECK (result IN ('success', 'fail')),
          failure_reason TEXT NOT NULL DEFAULT '',
          failure_class TEXT NOT NULL DEFAULT '',
          rollback_attempted INTEGER NOT NULL CHECK (rollback_attempted IN (0, 1)),
          rollback_success INTEGER NOT NULL CHECK (rollback_success IN (0, 1)),
          simulation_timestamp TEXT NOT NULL,
          policy_json TEXT NOT NULL DEFAULT '{}',
          validation_context_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY (pattern_id) REFERENCES remediation_patterns(pattern_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_remediation_exec_sim_pattern
          ON remediation_execution_simulations(pattern_id, simulation_timestamp);

        CREATE TABLE IF NOT EXISTS approvals (
          approval_id TEXT PRIMARY KEY,
          source_remediation_id TEXT NOT NULL,
          pattern_id TEXT,
          validation_run_id TEXT NOT NULL,
          simulation_id TEXT NOT NULL,
          requested_by TEXT NOT NULL,
          approved_by TEXT,
          approval_timestamp TEXT,
          expiration_timestamp TEXT,
          status TEXT NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
          confidence_score REAL,
          risk_level TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY (source_remediation_id) REFERENCES remediation_candidates(remediation_id) ON DELETE CASCADE,
          FOREIGN KEY (validation_run_id) REFERENCES validation_runs(run_id) ON DELETE CASCADE,
          FOREIGN KEY (simulation_id) REFERENCES remediation_execution_simulations(execution_simulation_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_approvals_source_remediation
          ON approvals(source_remediation_id, status, created_at);
        """
    )
    conn.commit()
    _migrate_remediation_candidates(conn)
    _migrate_approvals_source_remediation_id(conn)
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_remediation_ingestion_key
          ON remediation_candidates(ingestion_key)
          WHERE ingestion_key IS NOT NULL
        """
    )
    conn.commit()
    return conn


@dataclass(frozen=True)
class RemediationCandidate:
    remediation_id: str
    source: str
    source_type: str
    description: str
    proposed_action: str
    lifecycle_state: str
    evidence: list[str]
    source_metadata: dict[str, Any]
    related_issue_id: str | None
    created_at: str
    updated_at: str
    version: int


def _legacy_source_to_type(source: str) -> SourceType:
    s = (source or "").strip().lower()
    if s in ("llm", "llm_generated"):
        return "llm_generated"
    if s in ("human", "human_provided"):
        return "human_provided"
    return "deterministic"


def _sanitize_metadata(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}
    out: dict[str, Any] = {}
    for k, v in meta.items():
        ks = str(k).strip()
        if not ks or len(ks) > 128:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[ks] = v
        elif isinstance(v, list) and len(v) <= 20:
            out[ks] = [str(x)[:256] for x in v]
    raw = json.dumps(out, sort_keys=True, ensure_ascii=False)
    if len(raw) > _MAX_METADATA_JSON:
        raise ValueError("source_metadata exceeds max JSON size")
    return out


def _validate_ingestion_inputs(
    *,
    source_type: str,
    description: str,
    proposed_action: str,
    supporting_evidence: list[str],
) -> None:
    if source_type not in ("deterministic", "llm_generated", "human_provided"):
        raise ValueError(f"invalid source_type: {source_type}")
    desc = (description or "").strip()
    action = (proposed_action or "").strip()
    if not desc:
        raise ValueError("description is required")
    if len(desc) > _MAX_DESCRIPTION:
        raise ValueError("description exceeds max length")
    if not action:
        raise ValueError("proposed_action must not be empty")
    if len(action) > _MAX_PROPOSED_ACTION:
        raise ValueError("proposed_action exceeds max length")
    if not supporting_evidence:
        raise ValueError("supporting_evidence must contain at least one entry")
    if len(supporting_evidence) > _MAX_EVIDENCE_ITEMS:
        raise ValueError("too many supporting_evidence items")
    for i, ev in enumerate(supporting_evidence):
        es = (ev or "").strip()
        if not es:
            raise ValueError(f"supporting_evidence[{i}] is empty")
        if len(es) > _MAX_EVIDENCE_ITEM_LEN:
            raise ValueError(f"supporting_evidence[{i}] exceeds max length")


def _ingestion_dedup_key(*, related_issue_id: str | None, proposed_action: str) -> str | None:
    if not related_issue_id:
        return None
    base = f"{related_issue_id.strip()}\n{proposed_action.strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def ingest_remediation_candidate(
    conn: sqlite3.Connection,
    *,
    source_type: SourceType,
    description: str,
    proposed_action: str,
    supporting_evidence: list[str],
    source_label: str | None = None,
    source_metadata: dict[str, Any] | None = None,
    related_issue_id: str | None = None,
) -> str:
    """
    Twig 4.2 — controlled registry ingress: candidates enter as lifecycle_state=candidate only.
    No auto-promotion; no DATA output; sandbox DB only.
    """
    _validate_ingestion_inputs(
        source_type=source_type,
        description=description,
        proposed_action=proposed_action,
        supporting_evidence=list(supporting_evidence),
    )
    meta = _sanitize_metadata(source_metadata)
    if related_issue_id is not None:
        rid = str(related_issue_id).strip()
        if not rid or len(rid) > 512:
            raise ValueError("related_issue_id invalid")
        related_issue_id = rid
    label = (source_label or source_type).strip() or source_type
    ingestion_key = _ingestion_dedup_key(related_issue_id=related_issue_id, proposed_action=proposed_action)
    if ingestion_key:
        row = conn.execute(
            "SELECT remediation_id FROM remediation_candidates WHERE ingestion_key = ?",
            (ingestion_key,),
        ).fetchone()
        if row:
            raise ValueError(f"duplicate remediation candidate for issue+action: {row[0]}")

    rid = str(uuid.uuid4())
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO remediation_candidates (
          remediation_id, source, source_type, description, proposed_action, lifecycle_state,
          evidence_json, source_metadata_json, related_issue_id, ingestion_key,
          created_at, updated_at, version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            label,
            source_type,
            description.strip(),
            proposed_action.strip(),
            "candidate",
            json.dumps(list(supporting_evidence), ensure_ascii=False),
            json.dumps(meta, ensure_ascii=False),
            related_issue_id,
            ingestion_key,
            now,
            now,
            1,
        ),
    )
    conn.commit()
    return rid


def create_candidate(
    conn: sqlite3.Connection,
    *,
    source: str,
    description: str,
    proposed_action: str,
    evidence: list[str] | None = None,
) -> str:
    """Legacy path: maps source string to source_type; delegates to ingest_remediation_candidate."""
    st = _legacy_source_to_type(source)
    ev = list(evidence or [])
    if not ev:
        ev = ["(ingested via create_candidate)"]
    return ingest_remediation_candidate(
        conn,
        source_type=st,
        description=description,
        proposed_action=proposed_action,
        supporting_evidence=ev,
        source_label=source,
    )


def get_candidate(conn: sqlite3.Connection, remediation_id: str) -> RemediationCandidate | None:
    row = conn.execute(
        """
        SELECT remediation_id, source, source_type, description, proposed_action, lifecycle_state,
               evidence_json, source_metadata_json, related_issue_id, created_at, updated_at, version
        FROM remediation_candidates
        WHERE remediation_id = ?
        """,
        (remediation_id,),
    ).fetchone()
    if not row:
        return None
    st = str(row[2] or "deterministic")
    meta_raw = row[7]
    try:
        meta = json.loads(str(meta_raw or "{}"))
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    return RemediationCandidate(
        remediation_id=str(row[0]),
        source=str(row[1]),
        source_type=st,
        description=str(row[3]),
        proposed_action=str(row[4]),
        lifecycle_state=str(row[5]),
        evidence=list(json.loads(str(row[6] or "[]"))),
        source_metadata=meta,
        related_issue_id=str(row[8]) if row[8] is not None else None,
        created_at=str(row[9]),
        updated_at=str(row[10]),
        version=int(row[11] or 1),
    )


def transition_candidate(
    conn: sqlite3.Connection,
    *,
    remediation_id: str,
    to_state: str,
    notes: str = "",
) -> RemediationCandidate:
    if to_state not in _STATES:
        raise ValueError(f"invalid remediation state: {to_state}")
    rec = get_candidate(conn, remediation_id)
    if rec is None:
        raise LookupError(f"remediation candidate not found: {remediation_id}")
    _assert_transition(rec.lifecycle_state, to_state)
    now = _utc_now()
    next_version = rec.version + 1
    evidence = list(rec.evidence)
    if notes:
        evidence.append(f"transition_note:{notes}")
    conn.execute(
        """
        UPDATE remediation_candidates
        SET lifecycle_state = ?, updated_at = ?, evidence_json = ?, version = ?
        WHERE remediation_id = ?
        """,
        (to_state, now, json.dumps(evidence), next_version, remediation_id),
    )
    conn.commit()
    updated = get_candidate(conn, remediation_id)
    assert updated is not None
    return updated


def _classify_failure(*, error_resolved: bool, regression_detected: bool, stable_window: bool) -> str:
    if not error_resolved:
        return "functional"
    if regression_detected:
        return "regression"
    if not stable_window:
        return "stability"
    return ""


def run_validation(
    conn: sqlite3.Connection,
    *,
    remediation_id: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic sandbox-only validation run.
    No live execution: caller provides simulated before/after snapshots.
    """
    rec = get_candidate(conn, remediation_id)
    if rec is None:
        raise LookupError(f"remediation candidate not found: {remediation_id}")
    if rec.lifecycle_state == "candidate":
        rec = transition_candidate(conn, remediation_id=remediation_id, to_state="under_test", notes="validation_start")
    if rec.lifecycle_state not in {"under_test", "validated", "rejected"}:
        raise ValueError(f"unexpected lifecycle state: {rec.lifecycle_state}")

    before_errors = int(before_state.get("error_count", 0) or 0)
    after_errors = int(after_state.get("error_count", 0) or 0)
    regression_detected = bool(after_state.get("regression_detected", False))
    stable_window = bool(after_state.get("stable_window", True))
    metric_improved = float(after_state.get("metric_score", 0.0) or 0.0) >= float(
        before_state.get("metric_score", 0.0) or 0.0
    )
    error_resolved = after_errors < before_errors
    passed = bool(error_resolved and (not regression_detected) and stable_window and metric_improved)
    failure_class = _classify_failure(
        error_resolved=error_resolved,
        regression_detected=regression_detected,
        stable_window=stable_window,
    )
    reason = "" if passed else f"validation_failed:{failure_class}"
    confidence = 0.9 if passed else 0.55
    run_id = str(uuid.uuid4())
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO validation_runs (
          run_id, remediation_id, before_state_json, after_state_json, result,
          failure_reason, failure_class, confidence, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            remediation_id,
            json.dumps(before_state, sort_keys=True),
            json.dumps(after_state, sort_keys=True),
            "pass" if passed else "fail",
            reason,
            failure_class,
            confidence,
            now,
        ),
    )
    target_state = "validated" if passed else "rejected"
    current = get_candidate(conn, remediation_id)
    assert current is not None
    if current.lifecycle_state == "under_test":
        transition_candidate(conn, remediation_id=remediation_id, to_state=target_state, notes=reason or "validated")
    conn.commit()
    return {
        "run_id": run_id,
        "remediation_id": remediation_id,
        "result": "pass" if passed else "fail",
        "failure_reason": reason,
        "failure_class": failure_class,
        "confidence": confidence,
        "before_state": dict(before_state),
        "after_state": dict(after_state),
    }
