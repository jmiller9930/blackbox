"""Pattern game: scorecard truncate vs engine learning reset boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.batch_scorecard import truncate_batch_scorecard_jsonl
from renaissance_v4.game_theory.pattern_game_operator_reset import (
    RESET_PATTERN_GAME_LEARNING_CONFIRM,
    reset_pattern_game_engine_learning_state_v1,
)
from renaissance_v4.game_theory.web_app import create_app


def test_truncate_batch_scorecard_jsonl_only_target_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "batch_scorecard.jsonl"
    p.write_text('{"job_id":"x"}\n', encoding="utf-8")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.batch_scorecard.default_batch_scorecard_jsonl",
        lambda: p,
    )
    out = truncate_batch_scorecard_jsonl()
    assert out.resolve() == p.resolve()
    assert p.read_text() == ""


def test_reset_learning_wrong_confirm() -> None:
    out = reset_pattern_game_engine_learning_state_v1(confirm="nope")
    assert out["ok"] is False
    assert "error" in out


def test_reset_learning_truncates_and_unlinks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exp = tmp_path / "experience_log.jsonl"
    rm = tmp_path / "run_memory.jsonl"
    sig = tmp_path / "context_signature_memory.jsonl"
    gh = tmp_path / "groundhog_memory_bundle.json"
    for f in (exp, rm, sig):
        f.write_text('{"k":1}\n', encoding="utf-8")
    gh.write_text('{"schema":"pattern_game_memory_bundle_v1"}', encoding="utf-8")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.pattern_game_operator_reset.default_experience_log_jsonl",
        lambda: exp,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.pattern_game_operator_reset.default_run_memory_jsonl",
        lambda: rm,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.context_signature_memory.default_memory_path",
        lambda: sig,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.groundhog_memory.groundhog_bundle_path",
        lambda: gh,
    )
    out = reset_pattern_game_engine_learning_state_v1(confirm=RESET_PATTERN_GAME_LEARNING_CONFIRM)
    assert out["ok"] is True
    assert exp.read_text() == ""
    assert rm.read_text() == ""
    assert sig.read_text() == ""
    assert not gh.is_file()


def test_api_batch_scorecard_clear_requires_confirm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "batch_scorecard.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.batch_scorecard.default_batch_scorecard_jsonl",
        lambda: p,
    )
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.post("/api/batch-scorecard/clear", data=json.dumps({}), content_type="application/json")
    assert r.status_code == 400
    r2 = c.post("/api/batch-scorecard/clear", data=json.dumps({"confirm": True}), content_type="application/json")
    assert r2.status_code == 200
    assert p.read_text() == ""


def test_api_reset_learning_requires_exact_phrase(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exp = tmp_path / "e.jsonl"
    exp.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(
        "renaissance_v4.game_theory.pattern_game_operator_reset.default_experience_log_jsonl",
        lambda: exp,
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.pattern_game_operator_reset.default_run_memory_jsonl",
        lambda: tmp_path / "r.jsonl",
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.context_signature_memory.default_memory_path",
        lambda: tmp_path / "s.jsonl",
    )
    monkeypatch.setattr(
        "renaissance_v4.game_theory.groundhog_memory.groundhog_bundle_path",
        lambda: tmp_path / "g.json",
    )
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.post(
        "/api/pattern-game/reset-learning",
        data=json.dumps({"confirm": "wrong"}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "x" in exp.read_text()


def test_truncate_context_signature_memory_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from renaissance_v4.game_theory.context_signature_memory import truncate_context_signature_memory_store

    p = tmp_path / "context_signature_memory.jsonl"
    p.write_text('{"a": 1}\n', encoding="utf-8")
    monkeypatch.setattr("renaissance_v4.game_theory.context_signature_memory.default_memory_path", lambda: p)
    out = truncate_context_signature_memory_store()
    assert out["ok"] is True
    assert out["action"] == "truncated"
    assert p.read_text() == ""


def test_api_groundhog_memory_clear(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gh = tmp_path / "groundhog_memory_bundle.json"
    gh.write_text('{"schema": "pattern_game_memory_bundle_v1"}', encoding="utf-8")
    monkeypatch.setattr("renaissance_v4.game_theory.groundhog_memory.groundhog_bundle_path", lambda: gh)
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.post("/api/groundhog-memory/clear", data=json.dumps({}), content_type="application/json")
    assert r.status_code == 400
    r2 = c.post(
        "/api/groundhog-memory/clear",
        data=json.dumps({"confirm": True}),
        content_type="application/json",
    )
    assert r2.status_code == 200
    j = r2.get_json()
    assert j["ok"] is True
    assert j["action"] == "deleted"
    assert not gh.is_file()


def test_api_context_signature_memory_clear(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sig = tmp_path / "context_signature_memory.jsonl"
    sig.write_text('{"line": 1}\n', encoding="utf-8")
    monkeypatch.setattr("renaissance_v4.game_theory.context_signature_memory.default_memory_path", lambda: sig)
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    r = c.post("/api/context-signature-memory/clear", data=json.dumps({}), content_type="application/json")
    assert r.status_code == 400
    r2 = c.post(
        "/api/context-signature-memory/clear",
        data=json.dumps({"confirm": True}),
        content_type="application/json",
    )
    assert r2.status_code == 200
    j = r2.get_json()
    assert j["ok"] is True
    assert j["action"] == "truncated"
    assert sig.read_text() == ""
