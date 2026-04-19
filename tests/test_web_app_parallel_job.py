"""Pattern game web: async parallel job start + status."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from renaissance_v4.game_theory.web_app import create_app


def _manifest_path() -> str:
    root = Path(__file__).resolve().parents[1]
    p = root / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    if not p.is_file():
        pytest.skip("baseline manifest missing")
    return str(p)


def test_run_parallel_start_and_status() -> None:
    app = create_app()
    app.config["TESTING"] = True
    mp = _manifest_path()
    scenarios_json = json.dumps(
        [
            {
                "scenario_id": "job_test",
                "manifest_path": mp,
                "agent_explanation": {
                    "hypothesis": "Smoke test: baseline manifest completes one replay on lab data.",
                },
            }
        ],
    )
    client = app.test_client()
    st = client.post(
        "/api/run-parallel/start",
        data=json.dumps({"scenarios_json": scenarios_json, "max_workers": 1}),
        content_type="application/json",
    )
    assert st.status_code == 200
    data = st.get_json()
    assert data.get("ok") is True
    assert data.get("total") == 1
    job_id = data["job_id"]

    for _ in range(120):
        r = client.get(f"/api/run-parallel/status/{job_id}")
        assert r.status_code == 200
        j = r.get_json()
        assert "telemetry_context_echo" in j
        assert j["telemetry_context_echo"].get("learning_path_mode") == "baseline_replay_only"
        assert j["telemetry_context_echo"].get("candidate_search_active") is False
        ra = client.get(f"/api/run-status/{job_id}")
        assert ra.status_code == 200
        ja = ra.get_json()
        assert ja.get("status") == j.get("status")
        assert ja.get("telemetry_context_echo", {}).get("learning_path_mode") == "baseline_replay_only"
        assert "telemetry" in j and j["telemetry"].get("schema") == "pattern_game_live_telemetry_v1"
        if j.get("status") == "done":
            assert j.get("result", {}).get("ok") is True
            telem = j.get("telemetry") or {}
            scenarios = telem.get("scenarios") or []
            assert isinstance(scenarios, list)
            if scenarios:
                snap = scenarios[0]
                assert int(snap.get("decision_windows_processed") or 0) >= 0
            return
        if j.get("status") == "error":
            raise AssertionError(j.get("error"))
        time.sleep(0.25)
    raise AssertionError("job did not finish in time")


def test_run_parallel_start_rejects_empty_custom_scenarios() -> None:
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    r = client.post(
        "/api/run-parallel/start",
        data=json.dumps(
            {
                "operator_recipe_id": "custom",
                "scenarios_json": "[]",
                "max_workers": 1,
            }
        ),
        content_type="application/json",
    )
    assert r.status_code == 400
    j = r.get_json()
    assert j.get("ok") is False
    assert "No runnable scenarios" in (j.get("error") or "")


def test_run_parallel_start_returns_correct_total_for_multi_scenario() -> None:
    app = create_app()
    app.config["TESTING"] = True
    mp = _manifest_path()
    three = [
        {
            "scenario_id": f"multi_{i}",
            "manifest_path": mp,
            "agent_explanation": {"hypothesis": f"h{i}"},
        }
        for i in range(3)
    ]
    scenarios_json = json.dumps(three)
    client = app.test_client()
    st = client.post(
        "/api/run-parallel/start",
        data=json.dumps({"scenarios_json": scenarios_json, "max_workers": 2}),
        content_type="application/json",
    )
    assert st.status_code == 200
    data = st.get_json()
    assert data.get("ok") is True
    assert data.get("total") == 3
    job_id = data["job_id"]
    r = client.get(f"/api/run-parallel/status/{job_id}")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("total") == 3
