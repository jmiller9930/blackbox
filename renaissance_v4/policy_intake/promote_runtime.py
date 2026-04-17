"""
Build / promote a passing intake submission into a deployable runtime artifact (Path A).

Used by the Kitchen dashboard API so operators do not need manual manifest/registry edits.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from renaissance_v4.execution_targets import normalize_execution_target
from renaissance_v4.kitchen_policy_registry import ensure_runtime_policy_allowlisted
from renaissance_v4.policy_intake.kitchen_policy_manifest import (
    canonical_runtime_artifact_sha256,
    upsert_manifest_entry,
)
from renaissance_v4.policy_intake.storage import read_json, submission_dir


def _find_intake_ts(repo: Path, submission_id: str) -> Path | None:
    raw = submission_dir(repo, submission_id) / "raw"
    if not raw.is_dir():
        return None
    for name in sorted(raw.iterdir()):
        if not name.is_file():
            continue
        if name.name.startswith("original_") and name.suffix.lower() == ".ts":
            return name
    for name in sorted(raw.iterdir()):
        if name.is_file() and name.suffix.lower() == ".ts":
            return name
    return None


def _esbuild(ts: Path, out_mjs: Path) -> None:
    out_mjs.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "npm_config_yes": "true"}
    r = subprocess.run(
        [
            "npx",
            "-y",
            "esbuild@0.20.2",
            str(ts),
            "--bundle",
            "--format=esm",
            "--platform=neutral",
            f"--outfile={out_mjs}",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if r.returncode != 0 or not out_mjs.is_file():
        msg = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
        raise RuntimeError(f"esbuild failed: {msg[:8000]}")


def generate_deployed_runtime_policy_id(submission_id: str, candidate_policy_id: str = "") -> str:
    """
    Stable, unique deployment id for manifest + registry (jupiter|blackbox).

    Format: jup_intake_<short_hash>_<safe_suffix> — keeps length reasonable and avoids collisions.
    """
    sid = str(submission_id or "").strip()
    cid = str(candidate_policy_id or "").strip()
    h = hashlib.sha256(f"{sid}|{cid}".encode()).hexdigest()[:14]
    safe = re.sub(r"[^a-z0-9_]", "_", (sid + "_" + cid).lower())[:36].strip("_")
    if not safe:
        safe = "sub"
    base = f"jup_intake_{h}_{safe}"
    return base[:64]


def promote_intake_submission_to_runtime(
    repo: Path,
    submission_id: str,
    execution_target: str | None = None,
    *,
    deployed_runtime_policy_id: str | None = None,
    allowlist_registry: bool = True,
    skip_esbuild: bool = False,
) -> dict[str, Any]:
    """
    Build ``artifacts/evaluator.mjs``, upsert manifest, optionally allowlist registry.

    Returns a structured dict including ``deployed_runtime_policy_id`` and ``content_sha256``.
    """
    repo = repo.resolve()
    sid = str(submission_id).strip()
    rep_path = submission_dir(repo, sid) / "report" / "intake_report.json"
    rep = read_json(rep_path)
    if not isinstance(rep, dict) or not rep.get("pass"):
        return {"ok": False, "error": "intake_missing_or_not_passing", "submission_id": sid}
    cid = str(rep.get("candidate_policy_id") or "").strip()
    rep_et = normalize_execution_target(str(rep.get("execution_target") or "jupiter"))
    et = normalize_execution_target(execution_target) if execution_target is not None else rep_et
    if et != rep_et:
        return {
            "ok": False,
            "error": "execution_target_mismatch",
            "execution_target_requested": et,
            "execution_target_intake": rep_et,
        }
    if et not in ("jupiter", "blackbox"):
        return {"ok": False, "error": "unsupported_execution_target", "execution_target": et}

    pid = (deployed_runtime_policy_id or "").strip() or generate_deployed_runtime_policy_id(sid, cid)

    ts_path = _find_intake_ts(repo, sid)
    art_dir = submission_dir(repo, sid) / "artifacts"
    out_mjs = art_dir / "evaluator.mjs"

    if not skip_esbuild:
        if ts_path is None or not ts_path.is_file():
            return {
                "ok": False,
                "error": "no_typescript_under_raw",
                "detail": "Place original_<name>.ts under raw/ or pass skip_esbuild if evaluator.mjs exists.",
                "submission_id": sid,
            }
        try:
            _esbuild(ts_path, out_mjs)
        except Exception as e:
            return {"ok": False, "error": "esbuild_failed", "detail": str(e)[:2000], "submission_id": sid}
    elif not out_mjs.is_file():
        return {"ok": False, "error": "evaluator_missing", "detail": "skip_esbuild but artifacts/evaluator.mjs missing", "submission_id": sid}

    content_sha = canonical_runtime_artifact_sha256(repo, sid)
    if not content_sha:
        return {"ok": False, "error": "could_not_compute_content_sha256", "submission_id": sid}

    entry = {
        "execution_target": et,
        "deployed_runtime_policy_id": pid,
        "submission_id": sid,
        "content_sha256": content_sha,
    }
    try:
        upsert_manifest_entry(repo, entry)
    except ValueError as e:
        return {"ok": False, "error": "manifest_upsert_failed", "detail": str(e)[:500], "submission_id": sid}

    allow_st = "skipped"
    if allowlist_registry:
        ok_a, st = ensure_runtime_policy_allowlisted(repo, et, pid)
        if not ok_a:
            return {
                "ok": False,
                "error": "registry_allowlist_failed",
                "detail": st,
                "deployed_runtime_policy_id": pid,
                "submission_id": sid,
            }
        allow_st = st

    return {
        "ok": True,
        "schema": "kitchen_promote_runtime_result_v1",
        "submission_id": sid,
        "candidate_policy_id": cid,
        "execution_target": et,
        "deployed_runtime_policy_id": pid,
        "content_sha256": content_sha,
        "evaluator_path": str(out_mjs.relative_to(repo)),
        "registry_allowlist": allow_st,
    }
