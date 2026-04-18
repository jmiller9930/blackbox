"""Pattern game web: hypothesis required on parallel POST by default."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.web_app import create_app


def _mp() -> str:
    root = Path(__file__).resolve().parents[1]
    p = root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not p.is_file():
        return ""
    return str(p)


def test_parallel_start_rejects_missing_hypothesis(monkeypatch: pytest.MonkeyPatch) -> None:
    mp = _mp()
    if not mp:
        pytest.skip("baseline manifest missing")
    app = create_app()
    monkeypatch.delenv("PATTERN_GAME_REQUIRE_HYPOTHESIS", raising=False)
    client = app.test_client()
    bad = json.dumps([{"scenario_id": "noh", "manifest_path": mp}])
    r = client.post(
        "/api/run-parallel/start",
        data=json.dumps({"scenarios_json": bad, "max_workers": 1}),
        content_type="application/json",
    )
    assert r.status_code == 400
    j = r.get_json()
    assert j.get("ok") is False
    assert "hypothesis" in (j.get("error") or "").lower()


def test_parallel_start_accepts_hypothesis(monkeypatch: pytest.MonkeyPatch) -> None:
    mp = _mp()
    if not mp:
        pytest.skip("baseline manifest missing")
    app = create_app()
    monkeypatch.delenv("PATTERN_GAME_REQUIRE_HYPOTHESIS", raising=False)
    client = app.test_client()
    good = json.dumps(
        [
            {
                "scenario_id": "okh",
                "manifest_path": mp,
                "agent_explanation": {"hypothesis": "Completes replay."},
            }
        ]
    )
    r = client.post(
        "/api/run-parallel/start",
        data=json.dumps({"scenarios_json": good, "max_workers": 1}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json().get("ok") is True
