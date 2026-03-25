"""4.6.3.2 Part B Twig 4.2 — remediation candidate ingestion + registry boundary."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from learning_core.remediation_validation import (
    get_candidate,
    ingest_remediation_candidate,
    open_validation_sandbox,
)


def test_ingest_valid_deterministic_with_metadata_and_issue_link(tmp_path: Path) -> None:
    conn = open_validation_sandbox(tmp_path / "s.db")
    rid = ingest_remediation_candidate(
        conn,
        source_type="deterministic",
        description="Address repeated connectivity errors in poller",
        proposed_action="Suggestion only: increase backoff and cap retries",
        supporting_evidence=["connectivity_error_signals=2", "payload:connection refused"],
        source_metadata={
            "detection_id": "det-001",
            "related_issue_id": "iss-uuid-1",
            "timestamp": "2026-03-25T12:00:00Z",
        },
        related_issue_id="iss-uuid-1",
    )
    rec = get_candidate(conn, rid)
    assert rec is not None
    assert rec.lifecycle_state == "candidate"
    assert rec.source_type == "deterministic"
    assert rec.related_issue_id == "iss-uuid-1"
    assert rec.source_metadata.get("detection_id") == "det-001"


def test_ingest_llm_source_tagging(tmp_path: Path) -> None:
    conn = open_validation_sandbox(tmp_path / "s.db")
    rid = ingest_remediation_candidate(
        conn,
        source_type="llm_generated",
        description="LLM-suggested infra tweak",
        proposed_action="Suggestion only: review config reload order",
        supporting_evidence=["llm_candidate_v1"],
        source_label="optional_llm",
    )
    rec = get_candidate(conn, rid)
    assert rec is not None
    assert rec.source_type == "llm_generated"
    assert rec.source == "optional_llm"


def test_ingest_rejects_empty_action(tmp_path: Path) -> None:
    conn = open_validation_sandbox(tmp_path / "s.db")
    with pytest.raises(ValueError, match="proposed_action"):
        ingest_remediation_candidate(
            conn,
            source_type="deterministic",
            description="x",
            proposed_action="   ",
            supporting_evidence=["ev1"],
        )


def test_ingest_rejects_empty_evidence(tmp_path: Path) -> None:
    conn = open_validation_sandbox(tmp_path / "s.db")
    with pytest.raises(ValueError, match="supporting_evidence"):
        ingest_remediation_candidate(
            conn,
            source_type="deterministic",
            description="x",
            proposed_action="y",
            supporting_evidence=[],
        )


def test_ingest_duplicate_issue_plus_action_rejected(tmp_path: Path) -> None:
    conn = open_validation_sandbox(tmp_path / "s.db")
    ingest_remediation_candidate(
        conn,
        source_type="deterministic",
        description="first",
        proposed_action="Suggestion only: same fix text",
        supporting_evidence=["a"],
        related_issue_id="issue-42",
    )
    with pytest.raises(ValueError, match="duplicate"):
        ingest_remediation_candidate(
            conn,
            source_type="human_provided",
            description="second try",
            proposed_action="Suggestion only: same fix text",
            supporting_evidence=["b"],
            related_issue_id="issue-42",
        )


def test_sandbox_only_no_production_tables(tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"
    pconn = sqlite3.connect(prod)
    pconn.execute("CREATE TABLE IF NOT EXISTS prod_only (id INTEGER)")
    pconn.commit()
    sconn = open_validation_sandbox(tmp_path / "sand.db")
    ingest_remediation_candidate(
        sconn,
        source_type="deterministic",
        description="z",
        proposed_action="act",
        supporting_evidence=["e"],
    )
    tables = {r[0] for r in pconn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "remediation_candidates" not in tables
