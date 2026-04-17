#!/usr/bin/env python3
"""
Path A — turn a **passing** intake submission into a deployable Jupiter runtime artifact:

1. Bundle ``raw/original_*.ts`` (or first ``raw/*.ts``) with esbuild → ``artifacts/evaluator.mjs``
2. Register (upsert) ``kitchen_policy_deployment_manifest_v1.json`` using the **evaluator** sha256
   (aligned with ``artifact_policy_loader.mjs`` and ``canonical_runtime_artifact_sha256``).
3. Optionally append ``deployed_runtime_policy_id`` to ``kitchen_policy_registry_v1`` allowlist.

Requires: ``npx`` + network for esbuild (same as policy intake API image).

Example::

  python3 renaissance_v4/policy_intake/promote_intake_submission_to_jupiter_runtime.py \\
    --repo . \\
    --submission-id 69933ea3a779444a959bc5fa \\
    --deployed-runtime-policy-id jup_partner_alpha_v1 \\
    --allowlist-registry

Then: commit manifest + registry (+ submission ``artifacts/`` if tracked), deploy to clawbot, assign via Kitchen or ``POST /api/v1/jupiter/active-policy``.
"""

from __future__ import annotations

# Repo root on ``sys.path`` so ``python3 renaissance_v4/policy_intake/<this>.py`` works.
import sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import argparse
import os
import subprocess
from pathlib import Path

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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build evaluator.mjs + register Kitchen deployment manifest (Path A)."
    )
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="BlackBox repo root")
    ap.add_argument("--submission-id", required=True)
    ap.add_argument(
        "--deployed-runtime-policy-id",
        required=True,
        help="Stable id (e.g. jup_partner_foo_v1); must match SeanV3 manifest + registry allowlist.",
    )
    ap.add_argument(
        "--execution-target",
        default="jupiter",
        choices=("jupiter", "blackbox"),
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths and hashes only; do not write files or manifest.",
    )
    ap.add_argument(
        "--allowlist-registry",
        action="store_true",
        help="Append deployed_runtime_policy_id to runtime_policies for this target if missing.",
    )
    ap.add_argument(
        "--skip-esbuild",
        action="store_true",
        help="Skip esbuild; only upsert manifest + allowlist (evaluator.mjs must already exist).",
    )
    args = ap.parse_args()
    repo = args.repo.resolve()
    sid = str(args.submission_id).strip()
    pid = str(args.deployed_runtime_policy_id).strip()
    et = str(args.execution_target).strip().lower()

    rep_path = submission_dir(repo, sid) / "report" / "intake_report.json"
    rep = read_json(rep_path)
    if not isinstance(rep, dict) or not rep.get("pass"):
        print(f"promote: intake missing or not passing: {rep_path}", file=sys.stderr)
        return 1

    ts_path = _find_intake_ts(repo, sid)
    art_dir = submission_dir(repo, sid) / "artifacts"
    out_mjs = art_dir / "evaluator.mjs"

    if args.dry_run:
        print(f"repo={repo}")
        print(f"submission_id={sid}")
        print(f"ts_path={ts_path}")
        print(f"evaluator_out={out_mjs}")
        if out_mjs.is_file():
            print(f"canonical_sha256={canonical_runtime_artifact_sha256(repo, sid)}")
        return 0

    if not args.skip_esbuild:
        if ts_path is None or not ts_path.is_file():
            print(
                "promote: no TypeScript under raw/ — place original_<name>.ts or use --skip-esbuild "
                f"if evaluator.mjs already exists.",
                file=sys.stderr,
            )
            return 1
        try:
            _esbuild(ts_path, out_mjs)
        except Exception as e:
            print(f"promote: {e}", file=sys.stderr)
            return 1
    elif not out_mjs.is_file():
        print("promote: --skip-esbuild but artifacts/evaluator.mjs missing", file=sys.stderr)
        return 1

    content_sha = canonical_runtime_artifact_sha256(repo, sid)
    if not content_sha:
        print("promote: could not compute canonical sha256", file=sys.stderr)
        return 1

    entry = {
        "execution_target": et,
        "deployed_runtime_policy_id": pid,
        "submission_id": sid,
        "content_sha256": content_sha,
    }
    try:
        upsert_manifest_entry(repo, entry)
    except ValueError as e:
        print(f"promote: manifest: {e}", file=sys.stderr)
        return 1

    if args.allowlist_registry:
        ok, st = ensure_runtime_policy_allowlisted(repo, et, pid)
        if not ok:
            print(f"promote: allowlist failed: {st}", file=sys.stderr)
            return 1
        print(f"allowlist: {st}")

    print(f"ok: evaluator={out_mjs}")
    print(f"content_sha256={content_sha}")
    print(f"manifest entry: {et} {pid} submission={sid}")
    print("Next: git add manifest/registry/submission artifacts; commit; deploy; assign via Kitchen or Jupiter API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
