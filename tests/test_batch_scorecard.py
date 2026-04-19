"""Append-only batch scorecard JSONL + timing payload."""

from __future__ import annotations

from pathlib import Path

import pytest

from renaissance_v4.game_theory.batch_scorecard import (
    compute_batch_score_percentages,
    format_batch_scorecard_for_prompt,
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
        results=[
            {"ok": True, "scenario_id": "a", "referee_session": "WIN"},
            {"ok": False, "scenario_id": "b", "referee_session": "ERROR"},
        ],
        session_log_batch_dir="/tmp/logs/batch_x",
        error=None,
        path=p,
    )
    assert timing["total_processed"] == 2
    assert timing["duration_sec"] == 5.0
    assert timing["run_ok_pct"] == 50.0
    assert timing["referee_win_pct"] == 100.0
    rows = read_batch_scorecard_recent(10, path=p)
    assert len(rows) == 1
    assert rows[0]["job_id"] == "abc123"
    assert rows[0]["ok_count"] == 1
    assert rows[0]["failed_count"] == 1
    assert rows[0]["status"] == "done"
    assert rows[0]["run_ok_pct"] == 50.0
    assert rows[0]["referee_win_pct"] == 100.0
    assert rows[0].get("avg_trade_win_pct") is None
    assert rows[0].get("trade_win_rate_n") == 0


def test_compute_batch_score_percentages_win_loss() -> None:
    p = compute_batch_score_percentages(
        [
            {"ok": True, "referee_session": "WIN"},
            {"ok": True, "referee_session": "LOSS"},
            {"ok": False, "referee_session": "ERROR"},
        ]
    )
    assert p["run_ok_pct"] == 66.7  # 2 of 3, rounded to one decimal
    assert p["referee_win_pct"] == 50.0
    assert p["referee_wins"] == 1
    assert p["referee_losses"] == 1
    assert p["avg_trade_win_pct"] is None
    assert p["trade_win_rate_n"] == 0


def test_compute_batch_score_percentages_avg_trade_win() -> None:
    p = compute_batch_score_percentages(
        [
            {"ok": True, "referee_session": "WIN", "summary": {"win_rate": 0.344, "trades": 5}},
            {"ok": True, "referee_session": "WIN", "summary": {"win_rate": 0.5, "trades": 3}},
        ]
    )
    assert p["avg_trade_win_pct"] == 42.2  # mean of 34.4% and 50%
    assert p["trade_win_rate_n"] == 2


def test_record_error_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "sc.jsonl"
    monkeypatch.setattr("renaissance_v4.game_theory.batch_scorecard.time.time", lambda: 100.0)
    timing = record_parallel_batch_finished(
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
    assert timing["run_ok_pct"] == 0.0
    assert timing["referee_win_pct"] is None
    rows = read_batch_scorecard_recent(5, path=p)
    assert rows[0]["status"] == "error"
    assert rows[0]["total_processed"] == 0
    assert rows[0]["run_ok_pct"] == 0.0
    assert rows[0]["referee_win_pct"] is None
    assert rows[0].get("avg_trade_win_pct") is None


def test_format_batch_scorecard_for_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "batch_scorecard.jsonl"
    monkeypatch.setattr("renaissance_v4.game_theory.batch_scorecard.time.time", lambda: 200.0)
    record_parallel_batch_finished(
        job_id="job99",
        started_at_utc="2030-03-01T10:00:00Z",
        start_unix=100.0,
        total_scenarios=4,
        workers_used=4,
        results=[{"ok": True}],
        session_log_batch_dir=None,
        error=None,
        path=p,
    )
    s = format_batch_scorecard_for_prompt(limit=5, max_chars=8000, path=p)
    assert "Pattern game batch scorecard" in s
    assert "job99" in s
    assert "ok=1" in s
    assert "run_ok=" in s and "%" in s
    assert "workers=4" in s
