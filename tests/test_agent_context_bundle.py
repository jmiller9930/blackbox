"""Agent context bundle — opt-in repo docs in Anna prompts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.agent_context_bundle import build_context_prefix

_REPO = Path(__file__).resolve().parents[1]


def test_build_context_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANNA_CONTEXT_PROFILE", raising=False)
    assert build_context_prefix(_REPO) == ""


def test_build_context_none_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "none")
    assert build_context_prefix(_REPO) == ""


def test_build_context_includes_pattern_game_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "pattern_game")
    s = build_context_prefix(_REPO)
    assert "GAME_SPEC_INDICATOR_PATTERN_V1" in s
    assert "fusion_engine.py" in s
    assert "fuse_signal_results" in s
    assert "REPOSITORY CONTEXT" in s


def test_build_context_includes_policy_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "policy")
    s = build_context_prefix(_REPO)
    assert "policy_package_standard" in s
    assert "REPOSITORY CONTEXT" in s


def test_build_context_retrospective_appends_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log = tmp_path / "retrospective_log.jsonl"
    log.write_text(
        json.dumps(
            {
                "schema": "pattern_game_retrospective_v1",
                "utc": "2030-06-01T12:00:00Z",
                "what_observed": "Baseline run finished.",
                "what_to_try_next": "Compare ATR grid next batch.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "retrospective")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.retrospective_log.default_retrospective_log_jsonl",
        lambda: log,
    )
    s = build_context_prefix(_REPO)
    assert "RETROSPECTIVE LOG" in s
    assert "Compare ATR grid" in s


def test_build_context_scorecard_appends_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log = tmp_path / "batch_scorecard.jsonl"
    log.write_text(
        '{"schema":"pattern_game_batch_scorecard_v1","job_id":"x1","status":"done",'
        '"started_at_utc":"2030-01-01T00:00:00Z","ended_at_utc":"2030-01-01T00:01:00Z",'
        '"duration_sec":60,"total_scenarios":2,"total_processed":2,"ok_count":2,"failed_count":0,"workers_used":2}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "scorecard")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.batch_scorecard.default_batch_scorecard_jsonl",
        lambda: log,
    )
    s = build_context_prefix(_REPO)
    assert "BATCH SCORECARD" in s
    assert "x1" in s
    assert "workers=2" in s


def test_build_context_all_includes_retro_and_scorecard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Token ``all`` loads docs plus retrospective + scorecard blocks."""
    retro = tmp_path / "retrospective_log.jsonl"
    retro.write_text(
        '{"schema":"pattern_game_retrospective_v1","utc":"2030-01-01T00:00:00Z",'
        '"what_observed":"seen","what_to_try_next":"try wider"}\n',
        encoding="utf-8",
    )
    sc = tmp_path / "batch_scorecard.jsonl"
    sc.write_text(
        '{"schema":"pattern_game_batch_scorecard_v1","job_id":"j1","status":"done",'
        '"ended_at_utc":"2030-02-01T00:00:00Z","total_scenarios":2,"total_processed":2,'
        '"ok_count":2,"failed_count":0,"workers_used":2}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "all")
    monkeypatch.setenv("ANNA_VISIBLE_WINDOW", "0")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.retrospective_log.default_retrospective_log_jsonl",
        lambda: retro,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.batch_scorecard.default_batch_scorecard_jsonl",
        lambda: sc,
    )
    s = build_context_prefix(_REPO)
    assert "GAME_SPEC_INDICATOR_PATTERN_V1" in s
    assert "policy_package_standard" in s
    assert "RETROSPECTIVE LOG" in s
    assert "try wider" in s
    assert "BATCH SCORECARD" in s
    assert "j1" in s


def test_build_context_visible_window_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "visible_window")
    monkeypatch.setenv("ANNA_VISIBLE_WINDOW", "1")
    p = tmp_path / "db.sqlite3"
    with sqlite3.connect(p) as conn:
        conn.execute(
            """CREATE TABLE market_bars_5m (
                symbol TEXT, open_time INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL
            )"""
        )
        conn.execute(
            "INSERT INTO market_bars_5m VALUES (?,?,?,?,?,?,?)",
            ("SOLUSDT", 1_700_000_000_000, 100.0, 101.0, 99.0, 100.5, 1234.0),
        )
        conn.commit()
    monkeypatch.setattr("renaissance_v4.utils.db.DB_PATH", p)
    s = build_context_prefix(_REPO)
    assert "ANNA PERCEPTION" in s
    assert "Visibility contract" in s
    assert "100.5" in s


def test_build_context_pattern_game_and_scorecard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log = tmp_path / "batch_scorecard.jsonl"
    log.write_text(
        '{"schema":"pattern_game_batch_scorecard_v1","job_id":"y2","status":"done",'
        '"ended_at_utc":"2030-02-01T00:00:00Z","total_scenarios":1,"total_processed":1,'
        '"ok_count":1,"failed_count":0,"workers_used":1}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ANNA_CONTEXT_PROFILE", "pattern_game,scorecard")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.batch_scorecard.default_batch_scorecard_jsonl",
        lambda: log,
    )
    s = build_context_prefix(_REPO)
    assert "GAME_SPEC_INDICATOR_PATTERN_V1" in s
    assert "BATCH SCORECARD" in s
    assert "y2" in s
