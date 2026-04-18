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
        if j.get("status") == "done":
            assert j.get("result", {}).get("ok") is True
            return
        if j.get("status") == "error":
            raise AssertionError(j.get("error"))
        time.sleep(0.25)
    raise AssertionError("job did not finish in time")


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
