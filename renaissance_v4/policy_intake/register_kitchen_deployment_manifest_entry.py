#!/usr/bin/env python3
"""Append a Path A deployment manifest entry (CI / operator tooling)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from renaissance_v4.policy_intake.kitchen_policy_manifest import append_manifest_entry


def main() -> int:
    p = argparse.ArgumentParser(description="Register a Kitchen deployment manifest entry (Path A).")
    p.add_argument("--repo", type=Path, default=Path.cwd(), help="BlackBox repo root")
    p.add_argument("--execution-target", required=True, choices=("jupiter", "blackbox"))
    p.add_argument("--deployed-runtime-policy-id", required=True)
    p.add_argument("--submission-id", required=True)
    p.add_argument("--content-sha256", required=True, help="64-char hex (canonical raw policy bytes)")
    args = p.parse_args()
    try:
        append_manifest_entry(
            args.repo,
            {
                "execution_target": args.execution_target,
                "deployed_runtime_policy_id": str(args.deployed_runtime_policy_id).strip(),
                "submission_id": str(args.submission_id).strip(),
                "content_sha256": str(args.content_sha256).strip().lower(),
            },
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
