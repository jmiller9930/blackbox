#!/usr/bin/env python3
"""
Write a frozen exam manifest for promotion gates (checksum + version pin).

Use for any JSONL exam/holdout bundle so eval reports can cite an immutable fingerprint.

Usage:
  python3 training/frozen_exam_manifest.py \\
    --exam-jsonl holdout.jsonl \\
    --exam-version finquant_agentic_holdout_v20260502 \\
    --bundle-role primary_promotion_gate \\
    --out manifests/frozen_exam_finquant_v1.json

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: Path) -> int:
    n = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            n += chunk.count(b"\n")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Frozen exam manifest (checksum pin)")
    ap.add_argument("--exam-jsonl", type=Path, required=True)
    ap.add_argument("--exam-version", type=str, required=True)
    ap.add_argument(
        "--bundle-role",
        type=str,
        default="primary_promotion_gate",
        help="e.g. primary_promotion_gate | exploratory_regression",
    )
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    p = args.exam_jsonl.resolve()
    if not p.is_file():
        raise SystemExit(f"missing exam JSONL: {p}")

    digest = _sha256_file(p)
    nbytes = p.stat().st_size
    lines = _line_count(p)

    manifest = {
        "schema": "frozen_exam_manifest_v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exam_version": args.exam_version,
        "bundle_role": args.bundle_role,
        "artifact_path": str(p),
        "sha256": digest,
        "byte_size": nbytes,
        "line_count": lines,
        "notes": [
            "Promotion decisions MUST record this sha256 next to eval outputs.",
            "If exam JSONL changes, bump exam_version and regenerate manifest.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "sha256": digest, "lines": lines}, indent=2))


if __name__ == "__main__":
    main()
