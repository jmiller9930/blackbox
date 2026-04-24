"""Ask DATA operator feedback JSONL, rollup signals, and HTTP feedback route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.ask_data_explainer import ask_data_answer, build_ask_data_bundle_v1
from renaissance_v4.game_theory.ask_data_operator_feedback_v1 import (
    append_ask_data_feedback_telemetry_v1,
    append_ask_data_interaction_telemetry_v1,
    question_fingerprint_v1,
    rollup_operator_feedback_for_fingerprint_v1,
)
from renaissance_v4.game_theory.web_app import create_app


@pytest.fixture
def flask_client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_question_fingerprint_stable() -> None:
    a = question_fingerprint_v1("  What  does\nPML do?  ")
    b = question_fingerprint_v1("what does pml do?")
    assert a == b
    assert len(a) == 64


def test_rollup_counts_feedback_for_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "fb.jsonl"
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK_PATH", str(log))
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK", "1")
    fp = question_fingerprint_v1("hello rollup")
    append_ask_data_interaction_telemetry_v1(
        interaction_id="aa",
        question_fingerprint=fp,
        job_id=None,
        ask_data_route="pml_lightweight",
        answer_source="llm",
        job_resolution="no_job",
        question_len=5,
        path=log,
    )
    append_ask_data_feedback_telemetry_v1(
        interaction_id="aa",
        question_fingerprint=fp,
        rating="up",
        tags=["ok"],
        note="",
        path=log,
    )
    r = rollup_operator_feedback_for_fingerprint_v1(fp, path=log)
    assert r["enabled"] is True
    assert r["prior_feedback_count"] == 1
    assert r["rating_counts"]["up"] == 1
    assert "ok" in r["top_tags"]


def test_ask_data_answer_logs_interaction_and_returns_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "fb.jsonl"
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK_PATH", str(log))
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK", "1")
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    q = "What does PML do exactly for tests?"
    bundle = build_ask_data_bundle_v1(
        barney_facts=None,
        scorecard_snapshot=None,
        ui_context={},
        operator_strategy_state=None,
        job_resolution="no_job",
    )
    out = ask_data_answer(q, bundle, job_id=None)
    assert out["ok"] is True
    assert out.get("interaction_id")
    assert out.get("question_fingerprint") == question_fingerprint_v1(q)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event"] == "interaction"
    assert row["interaction_id"] == out["interaction_id"]


def test_http_ask_data_then_feedback_409_duplicate(
    flask_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = tmp_path / "httpfb.jsonl"
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK_PATH", str(log))
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK", "1")
    monkeypatch.setenv("ASK_DATA_USE_LLM", "0")
    r = flask_client.post(
        "/api/ask-data",
        json={"question": "What does PML do?"},
        content_type="application/json",
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    iid = j.get("interaction_id")
    assert iid
    r2 = flask_client.post(
        "/api/ask-data/feedback",
        json={"interaction_id": iid, "rating": "up", "tags": ["ui"]},
        content_type="application/json",
    )
    assert r2.status_code == 200
    r3 = flask_client.post(
        "/api/ask-data/feedback",
        json={"interaction_id": iid, "rating": "down"},
        content_type="application/json",
    )
    assert r3.status_code == 409


def test_http_feedback_unknown_interaction_404(flask_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK_PATH", str(tmp_path / "x.jsonl"))
    monkeypatch.setenv("ASK_DATA_OPERATOR_FEEDBACK", "1")
    r = flask_client.post(
        "/api/ask-data/feedback",
        json={"interaction_id": "deadbeef" * 2, "rating": "neutral"},
        content_type="application/json",
    )
    assert r.status_code == 404
