"""Tests for memory-aware hunter batch suggestions."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.hunter_planner import (
    SCHEMA_V1,
    build_hunter_suggestion,
    resolve_repo_root,
)
from renaissance_v4.game_theory.web_app import create_app


def test_resolve_repo_root_points_at_blackbox() -> None:
    root = resolve_repo_root()
    assert (root / "renaissance_v4" / "game_theory").is_dir()


def test_build_hunter_suggestion_ok_structure(tmp_path: Path) -> None:
    repo = resolve_repo_root()
    out = build_hunter_suggestion(repo_root=repo)
    assert out["ok"] is True
    assert out["schema"] == SCHEMA_V1
    assert isinstance(out["scenarios"], list)
    assert len(out["scenarios"]) == 4
    ids = [s["scenario_id"] for s in out["scenarios"]]
    assert len(ids) == len(set(ids))
    for s in out["scenarios"]:
        assert s.get("manifest_path")
        assert s.get("agent_explanation", {}).get("hypothesis")
    assert "rationale_markdown" in out
    assert isinstance(out.get("warnings"), list)


def test_build_hunter_suggestion_manifest_missing(tmp_path: Path) -> None:
    bad = tmp_path / "empty_repo"
    bad.mkdir()
    out = build_hunter_suggestion(repo_root=bad)
    assert out["ok"] is False
    assert "error" in out


def test_ladder_rotates_with_log_length(tmp_path: Path) -> None:
    repo = resolve_repo_root()
    sc = tmp_path / "batch_scorecard.jsonl"
    retro = tmp_path / "retro.jsonl"
    sc.write_text("", encoding="utf-8")
    retro.write_text("", encoding="utf-8")
    a = build_hunter_suggestion(repo_root=repo, scorecard_path=sc, retrospective_path=retro)
    sc.write_text(json.dumps({"schema": "x", "status": "done"}) + "\n", encoding="utf-8")
    b = build_hunter_suggestion(repo_root=repo, scorecard_path=sc, retrospective_path=retro)
    assert a["ladder_round_base"] != b["ladder_round_base"] or a["ladder_round"] != b["ladder_round"]


def test_api_suggest_hunters() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/suggest-hunters")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    assert j.get("schema") == SCHEMA_V1
    assert len(j.get("scenarios", [])) == 4


def test_tight_bias_from_retrospective(tmp_path: Path) -> None:
    repo = resolve_repo_root()
    retro = tmp_path / "retro.jsonl"
    retro.write_text(
        json.dumps(
            {
                "schema": "pattern_game_retrospective_v1",
                "utc": "2026-01-01T00:00:00Z",
                "what_observed": "x",
                "what_to_try_next": "try tighter stops next",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sc = tmp_path / "sc.jsonl"
    sc.write_text("", encoding="utf-8")
    out = build_hunter_suggestion(repo_root=repo, scorecard_path=sc, retrospective_path=retro)
    assert out["ok"] is True
    assert out["bias"] == "tight"
    assert out["ladder_round"] == 1
