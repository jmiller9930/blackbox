"""Append-only batch scorecard JSONL + timing payload."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.batch_scorecard import (
    read_batch_scorecard_recent,
    record_parallel_batch_finished,
)


def test_record_success_and_read_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "batch_scorecard.jsonl"
    t0 = 1_000_000.0
    monkeypatch.setattr("renaissance_v4.game_theory.batch_scorecard.time.time", lambda: t0 + 5.0)
    timing = record_parallel_batch_finished(
        job_id="abc123",
        started_at_utc="2030-01-01T12:00:00Z",
        start_unix=t0,
        total_scenarios=2,
        workers_used=2,
        results=[{"ok": True, "scenario_id": "a"}, {"ok": False, "scenario_id": "b"}],
        session_log_batch_dir="/tmp/logs/batch_x",
        error=None,
        path=p,
    )
    assert timing["total_processed"] == 2
    assert timing["duration_sec"] == 5.0
    rows = read_batch_scorecard_recent(10, path=p)
    assert len(rows) == 1
    assert rows[0]["job_id"] == "abc123"
    assert rows[0]["ok_count"] == 1
    assert rows[0]["failed_count"] == 1
    assert rows[0]["status"] == "done"


def test_record_error_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "sc.jsonl"
    monkeypatch.setattr("renaissance_v4.game_theory.batch_scorecard.time.time", lambda: 100.0)
    record_parallel_batch_finished(
        job_id="e1",
        started_at_utc="2030-01-02T00:00:00Z",
        start_unix=95.0,
        total_scenarios=3,
        workers_used=1,
        results=None,
        session_log_batch_dir=None,
        error="RuntimeError: boom",
        path=p,
    )
    rows = read_batch_scorecard_recent(5, path=p)
    assert rows[0]["status"] == "error"
    assert rows[0]["total_processed"] == 0
