"""Parallel batch cancel: cancel_check + HTTP cancel route."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from renaissance_v4.game_theory.parallel_runner import ParallelBatchCancelledError, run_scenarios_parallel
from renaissance_v4.game_theory.web_app import create_app


def _manifest() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "configs" / "manifests" / "baseline_v1_recipe.json"


def test_cancel_check_aborts_before_workers_finish() -> None:
    m = _manifest()
    if not m.is_file():
        pytest.skip("baseline manifest missing")
    scenarios = [
        {"scenario_id": "cx_a", "manifest_path": str(m)},
        {"scenario_id": "cx_b", "manifest_path": str(m)},
    ]
    with pytest.raises(ParallelBatchCancelledError) as ei:
        run_scenarios_parallel(
            scenarios,
            max_workers=2,
            experience_log_path=None,
            cancel_check=lambda: True,
        )
    assert isinstance(ei.value.partial_results, list)


def test_post_cancel_unknown_job_returns_404() -> None:
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.post("/api/run-parallel/cancel/deadbeefdeadbeefdeadbeefdeadbeef")
    assert r.status_code == 404


def test_post_cancel_non_running_returns_400() -> None:
    from renaissance_v4.game_theory import web_app as wa

    app = create_app()
    app.config["TESTING"] = True
    jid = "a" * 32
    with wa._JOBS_LOCK:
        wa._JOBS[jid] = {
            "status": "done",
            "created": time.time(),
            "total": 1,
            "completed": 1,
            "cancel_requested": False,
        }
    try:
        with app.test_client() as c:
            r = c.post(f"/api/run-parallel/cancel/{jid}")
        assert r.status_code == 400
        body = r.get_json()
        assert body.get("ok") is False
    finally:
        with wa._JOBS_LOCK:
            wa._JOBS.pop(jid, None)


def test_post_cancel_running_sets_flag() -> None:
    from renaissance_v4.game_theory import web_app as wa

    app = create_app()
    app.config["TESTING"] = True
    jid = "b" * 32
    with wa._JOBS_LOCK:
        wa._JOBS[jid] = {
            "status": "running",
            "created": time.time(),
            "total": 2,
            "completed": 0,
            "cancel_requested": False,
        }
    try:
        with app.test_client() as c:
            r = c.post(f"/api/run-parallel/cancel/{jid}")
        assert r.status_code == 200
        body = r.get_json()
        assert body.get("ok") is True
        with wa._JOBS_LOCK:
            assert wa._JOBS[jid].get("cancel_requested") is True
    finally:
        with wa._JOBS_LOCK:
            wa._JOBS.pop(jid, None)
