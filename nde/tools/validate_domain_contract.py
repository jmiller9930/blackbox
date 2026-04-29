#!/usr/bin/env python3
"""
Verify NDE domain layout contract (domain_config, training/config.yaml, eval JSONs, staging dir).

Deploy: /data/NDE/tools/validate_domain_contract.py

Usage:
  python3 validate_domain_contract.py --nde-root /data/NDE --domain secops
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nde_validation_lib import validate_domain_contract


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate NDE domain contract paths")
    ap.add_argument("--nde-root", type=Path, required=True)
    ap.add_argument("--domain", required=True)
    args = ap.parse_args()

    nde = args.nde_root.resolve()
    ok, errs, detail = validate_domain_contract(nde, args.domain)
    out = {"ok": ok, "domain": args.domain, "detail": detail, "errors": errs}
    print(json.dumps(out, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
