#!/usr/bin/env python3
"""
Validate NDE staging JSONL against domain_config + training/config.yaml staging path.

Deploy: /data/NDE/tools/validate_training_dataset.py

Usage:
  python3 validate_training_dataset.py --nde-root /data/NDE --domain secops
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nde_validation_lib import validate_training_dataset_for_domain


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate NDE training staging JSONL")
    ap.add_argument("--nde-root", type=Path, required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--staging", type=Path, default=None, help="Override staging JSONL path")
    args = ap.parse_args()

    nde = args.nde_root.resolve()
    staging = args.staging.resolve() if args.staging else None
    ok, detail, errs = validate_training_dataset_for_domain(nde, args.domain, staging_path=staging)
    out = {"ok": ok, "domain": args.domain, "detail": detail, "errors": errs}
    print(json.dumps(out, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
