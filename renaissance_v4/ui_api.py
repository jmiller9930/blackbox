"""
Read-only + governed job payloads for RenaissanceV4 dashboard API.

Paths are resolved under the repo root (BLACKBOX_REPO_ROOT / api mount).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BASELINE_TAG = "RenaissanceV4_baseline_v1"


def _repo_root(repo: Path) -> Path:
    return repo.resolve()


def rv4_paths(repo: Path) -> dict[str, Path]:
    r = _repo_root(repo)
    rv4 = r / "renaissance_v4"
    return {
        "root": rv4,
        "reports": rv4 / "reports",
        "state": rv4 / "state",
        "baseline_md": rv4 / "reports" / "baseline_v1.md",
        "diag_post": rv4 / "reports" / "diagnostic_quality_post_DV013.md",
        "correction_q": rv4 / "reports" / "correction_quality_v1.md",
        "baseline_det": rv4 / "state" / "baseline_deterministic.json",
        "baseline_mc": rv4 / "state" / "baseline_monte_carlo_summary.json",
        "experiment_index": rv4 / "state" / "experiment_index.json",
        "job_queue": rv4 / "state" / "ui_job_queue.json",
        "experiments_dir": rv4 / "reports" / "experiments",
    }


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _git_rev_parse(repo: Path) -> str | None:
    import subprocess

    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (p.stdout or "").strip() or None
    except OSError:
        return None


def build_baseline_payload(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    p = rv4_paths(repo)
    det = _read_json(p["baseline_det"]) or {}
    mc = _read_json(p["baseline_mc"]) or {}
    deterministic = det.get("deterministic") if isinstance(det, dict) else {}
    if not deterministic and isinstance(mc, dict):
        deterministic = mc.get("deterministic") or {}

    git_head = _git_rev_parse(repo)
    md_exists = p["baseline_md"].is_file()

    return {
        "schema": "renaissance_v4_ui_baseline_v1",
        "baseline_tag": BASELINE_TAG,
        "commit_hint": git_head,
        "reports": {
            "baseline_v1_md": str(p["baseline_md"].relative_to(repo)) if md_exists else None,
            "diagnostic_post_dv013": str(p["diag_post"].relative_to(repo)) if p["diag_post"].is_file() else None,
            "correction_quality_v1": str(p["correction_q"].relative_to(repo)) if p["correction_q"].is_file() else None,
        },
        "deterministic": deterministic if isinstance(deterministic, dict) else {},
        "monte_carlo_reference_present": bool(mc) and isinstance(mc.get("monte_carlo"), dict),
        "monte_carlo_summary_keys": list(mc.get("monte_carlo", {}).keys()) if isinstance(mc, dict) else [],
        "raw_monte_carlo_meta": {
            "generated_at": mc.get("generated_at") if isinstance(mc, dict) else None,
            "git_head": mc.get("git_head") if isinstance(mc, dict) else None,
        }
        if isinstance(mc, dict)
        else {},
    }


def build_experiments_list_payload(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    p = rv4_paths(repo)
    idx = _read_json(p["experiment_index"])
    jobs = _read_json(p["job_queue"])
    experiments: list[dict[str, Any]] = []
    if isinstance(idx, dict) and isinstance(idx.get("experiments"), list):
        experiments = list(idx["experiments"])

    # Merge queue status by experiment_id
    job_by_exp: dict[str, dict[str, Any]] = {}
    if isinstance(jobs, dict) and isinstance(jobs.get("jobs"), list):
        for j in jobs["jobs"]:
            if isinstance(j, dict) and j.get("experiment_id"):
                job_by_exp[str(j["experiment_id"])] = j

    rows: list[dict[str, Any]] = []
    for e in experiments:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("experiment_id", ""))
        jq = job_by_exp.get(eid, {})
        rows.append(
            {
                "experiment_id": eid,
                "status": e.get("status", "unknown"),
                "stage": jq.get("stage") or ("complete" if e.get("status") == "complete" else "—"),
                "subsystem": e.get("subsystem", ""),
                "recommendation": e.get("recommendation", ""),
                "created_at": e.get("created_at", ""),
                "branch": e.get("branch", ""),
                "commit_hash": e.get("commit_hash", ""),
            }
        )

    # Synthetic queue rows for jobs not in index
    seen = {r["experiment_id"] for r in rows}
    for eid, j in job_by_exp.items():
        if eid not in seen:
            rows.append(
                {
                    "experiment_id": eid,
                    "status": j.get("status", "pending"),
                    "stage": j.get("stage", "queued"),
                    "subsystem": j.get("action", ""),
                    "recommendation": "",
                    "created_at": j.get("created_at", ""),
                    "branch": "",
                    "commit_hash": "",
                }
            )

    return {
        "schema": "renaissance_v4_ui_experiments_v1",
        "baseline_tag": BASELINE_TAG,
        "experiments": rows,
        "jobs": jobs.get("jobs", []) if isinstance(jobs, dict) else [],
    }


def build_experiment_detail_payload(repo: Path, experiment_id: str) -> dict[str, Any]:
    repo = repo.resolve()
    p = rv4_paths(repo)
    idx = _read_json(p["experiment_index"])
    hit: dict[str, Any] | None = None
    if isinstance(idx, dict) and isinstance(idx.get("experiments"), list):
        for e in idx["experiments"]:
            if isinstance(e, dict) and str(e.get("experiment_id")) == experiment_id:
                hit = dict(e)
                break

    det_path = p["state"] / f"deterministic_{experiment_id}.json"
    mc_path = p["state"] / f"monte_carlo_{experiment_id}_summary.json"
    exp_md = p["experiments_dir"] / f"experiment_{experiment_id}.md"
    rob_md = p["reports"] / "robustness" / f"robustness_{experiment_id}.md"
    mc_md = p["reports"] / "monte_carlo" / f"monte_carlo_{experiment_id}.md"

    det_j = _read_json(det_path) if det_path.is_file() else None
    mc_j = _read_json(mc_path) if mc_path.is_file() else None

    return {
        "schema": "renaissance_v4_ui_experiment_detail_v1",
        "experiment_id": experiment_id,
        "index": hit,
        "deterministic": det_j.get("deterministic") if isinstance(det_j, dict) else None,
        "monte_carlo": mc_j.get("monte_carlo") if isinstance(mc_j, dict) else None,
        "recommendation": (hit or {}).get("recommendation") if hit else None,
        "report_paths": {
            "experiment_md": str(exp_md.relative_to(repo)) if exp_md.is_file() else None,
            "robustness_md": str(rob_md.relative_to(repo)) if rob_md.is_file() else None,
            "monte_carlo_md": str(mc_md.relative_to(repo)) if mc_md.is_file() else None,
        },
    }


def validate_job_action(action: str) -> bool:
    return action in {"baseline_mc", "compare", "example_flow"}


def validate_experiment_id(eid: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_.-]{4,64}$", eid))


def validate_candidate_trades_path(repo: Path, rel: str) -> Path | None:
    """Only allow paths under renaissance_v4/reports/experiments/."""
    repo = repo.resolve()
    rel = rel.strip().replace("\\", "/")
    if ".." in rel or rel.startswith("/"):
        return None
    p = (repo / rel).resolve()
    exp_root = (repo / "renaissance_v4" / "reports" / "experiments").resolve()
    try:
        p.relative_to(exp_root)
    except ValueError:
        return None
    if not p.is_file() or p.suffix.lower() != ".json":
        return None
    return p
