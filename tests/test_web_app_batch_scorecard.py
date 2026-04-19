"""Pattern game web: batch scorecard API."""

from __future__ import annotations

import time

from renaissance_v4.game_theory.web_app import _JOBS, _JOBS_LOCK, create_app


def test_batch_scorecard_get_empty() -> None:
    app = create_app()
    c = app.test_client()
    r = c.get("/api/batch-scorecard?limit=5")
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ok") is True
    assert "path" in j
    assert "entries" in j
    assert isinstance(j["entries"], list)


def test_batch_scorecard_merges_inflight_running_job() -> None:
    """In-flight parallel jobs appear before JSONL lines so operators see start time."""
    jid = "test_inflight_scorecard_job_01"
    with _JOBS_LOCK:
        _JOBS[jid] = {
            "status": "running",
            "created": time.time(),
            "started_at_utc": "2026-04-17T12:00:00+00:00",
            "total": 3,
            "completed": 1,
            "workers_used": 2,
            "last_scenario_id": None,
            "last_ok": None,
            "last_message": None,
            "error": None,
            "result": None,
            "batch_timing": None,
            "telemetry_dir": "",
            "telemetry_context_echo": None,
        }
    try:
        app = create_app()
        c = app.test_client()
        r = c.get("/api/batch-scorecard?limit=10")
        assert r.status_code == 200
        j = r.get_json()
        assert j.get("ok") is True
        assert j.get("inflight_batches", 0) >= 1
        hit = next((e for e in j["entries"] if e.get("job_id") == jid), None)
        assert hit is not None
        assert hit.get("status") == "running"
        assert hit.get("scorecard_inflight") is True
        assert hit.get("started_at_utc")
        assert hit.get("total_scenarios") == 3
        assert hit.get("total_processed") == 1
    finally:
        with _JOBS_LOCK:
            _JOBS.pop(jid, None)
