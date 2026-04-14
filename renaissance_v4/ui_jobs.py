"""
Governed background jobs for RenaissanceV4 robustness runner (dashboard-triggered).

Runs subprocesses under repo root; does not execute trading or mutate baseline code.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.ui_api import (
    validate_candidate_trades_path,
    validate_experiment_id,
    validate_manifest_path,
)

_job_lock = threading.Lock()
_worker_started = False


def _queue_path(repo: Path) -> Path:
    return repo / "renaissance_v4" / "state" / "ui_job_queue.json"


def load_queue(repo: Path) -> dict[str, Any]:
    p = _queue_path(repo)
    if not p.is_file():
        return {"schema": "renaissance_v4_ui_job_queue_v1", "jobs": []}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"schema": "renaissance_v4_ui_job_queue_v1", "jobs": []}
    except (json.JSONDecodeError, OSError):
        return {"schema": "renaissance_v4_ui_job_queue_v1", "jobs": []}


def save_queue(repo: Path, data: dict[str, Any]) -> None:
    p = _queue_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def enqueue(
    repo: Path,
    *,
    action: str,
    experiment_id: str | None,
    candidate_trades_rel: str | None = None,
    manifest_rel: str | None = None,
) -> dict[str, Any]:
    q = load_queue(repo)
    jobs = list(q.get("jobs") or [])
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    job = {
        "job_id": job_id,
        "action": action,
        "experiment_id": experiment_id,
        "candidate_trades": candidate_trades_rel,
        "candidate_trades_rel": candidate_trades_rel,
        "manifest_rel": manifest_rel,
        "status": "queued",
        "stage": "queued",
        "created_at": now,
        "updated_at": now,
        "message": "",
        "exit_code": None,
    }
    jobs.append(job)
    q["jobs"] = jobs
    save_queue(repo, q)
    _ensure_worker(repo)
    return job


def _run_job(repo: Path, job: dict[str, Any]) -> None:
    job_id = job["job_id"]
    action = str(job.get("action") or "")
    exp = job.get("experiment_id")
    py = os.environ.get("PYTHON") or "python3"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    env["PYTHONUNBUFFERED"] = "1"

    def upd(**kwargs: Any) -> None:
        q = load_queue(repo)
        for j in q.get("jobs") or []:
            if isinstance(j, dict) and j.get("job_id") == job_id:
                j.update(kwargs)
                j["updated_at"] = datetime.now(timezone.utc).isoformat()
                break
        save_queue(repo, q)

    upd(status="running", stage="replay", message="starting subprocess")

    cmd: list[str]
    if action == "baseline_mc":
        cmd = [
            py,
            "-m",
            "renaissance_v4.research.robustness_runner",
            "baseline-mc",
            "--seed",
            "42",
            "--n-sims",
            "5000",
        ]
    elif action == "example_flow":
        cmd = [
            py,
            "-m",
            "renaissance_v4.research.robustness_runner",
            "example-flow",
            "--seed",
            "42",
            "--n-sims",
            "2000",
        ]
    elif action == "compare":
        if not exp or not validate_experiment_id(str(exp)):
            upd(status="failed", stage="failed", message="invalid experiment_id", exit_code=-1)
            return
        ct = job.get("candidate_trades")
        if not ct:
            upd(status="failed", stage="failed", message="missing candidate_trades", exit_code=-1)
            return
        vp = validate_candidate_trades_path(repo, str(ct))
        if not vp:
            upd(status="failed", stage="failed", message="invalid candidate_trades path", exit_code=-1)
            return
        rel = str(vp.relative_to(repo))
        cmd = [
            py,
            "-m",
            "renaissance_v4.research.robustness_runner",
            "compare",
            "--experiment-id",
            str(exp),
            "--candidate-trades",
            rel,
            "--seed",
            "42",
            "--n-sims",
            "5000",
        ]
    elif action == "compare_manifest":
        if not exp or not validate_experiment_id(str(exp)):
            upd(status="failed", stage="failed", message="invalid experiment_id", exit_code=-1)
            return
        mr = job.get("manifest_rel") or job.get("manifest")
        if not mr:
            upd(status="failed", stage="failed", message="missing manifest path", exit_code=-1)
            return
        vp = validate_manifest_path(repo, str(mr))
        if not vp:
            upd(status="failed", stage="failed", message="invalid manifest path", exit_code=-1)
            return
        mrel = str(vp.relative_to(repo))
        cmd = [
            py,
            "-m",
            "renaissance_v4.research.robustness_runner",
            "compare-manifest",
            "--experiment-id",
            str(exp),
            "--manifest",
            mrel,
            "--seed",
            "42",
            "--n-sims",
            "5000",
        ]
    else:
        upd(status="failed", stage="failed", message="unknown action", exit_code=-1)
        return

    upd(
        stage="monte_carlo"
        if action in {"baseline_mc", "example_flow", "compare", "compare_manifest"}
        else "running"
    )
    try:
        r = subprocess.run(
            cmd,
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=7200,
            check=False,
        )
        tail = (r.stderr or "")[-4000:] + "\n" + (r.stdout or "")[-4000:]
        ok = r.returncode == 0
        upd(
            status="complete" if ok else "failed",
            stage="complete" if ok else "failed",
            message=tail.strip()[-1500:] if tail else ("ok" if ok else "nonzero exit"),
            exit_code=r.returncode,
        )
    except subprocess.TimeoutExpired:
        upd(status="failed", stage="failed", message="timeout", exit_code=-2)
    except subprocess.SubprocessError as e:
        upd(status="failed", stage="failed", message=str(e)[:500], exit_code=-3)


def _worker_loop(repo: Path) -> None:
    while True:
        time.sleep(1.0)
        with _job_lock:
            q = load_queue(repo)
            jobs = list(q.get("jobs") or [])
            next_job = None
            for j in jobs:
                if isinstance(j, dict) and j.get("status") == "queued":
                    next_job = j
                    break
            if not next_job:
                continue
            jcopy = dict(next_job)
        _run_job(repo, jcopy)


def _ensure_worker(repo: Path) -> None:
    global _worker_started
    if _worker_started:
        return
    with _job_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker_loop, args=(repo,), daemon=True)
        t.start()
        _worker_started = True
