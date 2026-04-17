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
from pathlib import Path

from renaissance_v4.policy_intake.promote_runtime import promote_intake_submission_to_runtime
from renaissance_v4.policy_intake.storage import read_json, submission_dir


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

    art_dir = submission_dir(repo, sid) / "artifacts"
    out_mjs = art_dir / "evaluator.mjs"

    if args.dry_run:
        from renaissance_v4.policy_intake.kitchen_policy_manifest import canonical_runtime_artifact_sha256

        print(f"repo={repo}")
        print(f"submission_id={sid}")
        print(f"evaluator_out={out_mjs}")
        if out_mjs.is_file():
            print(f"canonical_sha256={canonical_runtime_artifact_sha256(repo, sid)}")
        return 0

    r = promote_intake_submission_to_runtime(
        repo,
        sid,
        execution_target=et,
        deployed_runtime_policy_id=pid,
        allowlist_registry=bool(args.allowlist_registry),
        skip_esbuild=bool(args.skip_esbuild),
    )
    if not r.get("ok"):
        print(f"promote: {r.get('error')} {r.get('detail', '')}", file=sys.stderr)
        return 1

    if args.allowlist_registry:
        print(f"allowlist: {r.get('registry_allowlist')}")

    print(f"ok: evaluator={out_mjs}")
    print(f"content_sha256={r.get('content_sha256')}")
    print(f"manifest entry: {et} {pid} submission={sid}")
    print("Next: git add manifest/registry/submission artifacts; commit; deploy; assign via Kitchen or Jupiter API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
