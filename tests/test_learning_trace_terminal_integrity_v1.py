"""learning_trace_terminal_integrity_v1 — trace-only authority vs sealed counts for Terminal."""

from __future__ import annotations

import json

from renaissance_v4.game_theory.learning_trace_events_v1 import (
    SCHEMA_EVENT,
    count_learning_trace_terminal_integrity_v1,
)


def _line(job_id: str, stage: str) -> str:
    ev = {
        "schema": SCHEMA_EVENT,
        "schema_version": 1,
        "job_id": job_id,
        "fingerprint": None,
        "stage": stage,
        "timestamp_utc": "2026-04-27T12:00:00Z",
        "status": "pass",
        "summary": "x",
        "evidence_payload": {},
        "producer": "test",
    }
    return json.dumps(ev, separators=(",", ":")) + "\n"


def test_count_authority_matches_sealed(tmp_path) -> None:
    p = tmp_path / "learning_trace_events_v1.jsonl"
    jid = "a" * 32
    p.write_text(
        _line(jid, "student_decision_authority_v1")
        + _line(jid, "student_output_sealed")
        + _line(jid, "student_decision_authority_v1")
        + _line(jid, "student_output_sealed")
        + _line("otherjob", "student_output_sealed"),
        encoding="utf-8",
    )
    out = count_learning_trace_terminal_integrity_v1(jid, path=p)
    assert out["student_decision_authority_v1_count"] == 2
    assert out["student_output_sealed_count"] == 2
    assert out["integrity_ok"] is True


def test_count_mismatch(tmp_path) -> None:
    p = tmp_path / "t.jsonl"
    jid = "b" * 32
    p.write_text(
        _line(jid, "student_decision_authority_v1")
        + _line(jid, "student_decision_authority_v1")
        + _line(jid, "student_output_sealed"),
        encoding="utf-8",
    )
    out = count_learning_trace_terminal_integrity_v1(jid, path=p)
    assert out["student_decision_authority_v1_count"] == 2
    assert out["student_output_sealed_count"] == 1
    assert out["integrity_ok"] is False
