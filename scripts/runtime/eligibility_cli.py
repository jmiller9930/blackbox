#!/usr/bin/env python3
"""Execution eligibility gate CLI (sandbox DB only). Does not execute remediation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parent
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from learning_core.eligibility_gate import evaluate_eligibility, get_eligibility_record
from learning_core.remediation_validation import assert_non_production_sqlite_path, open_validation_sandbox


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execution eligibility gate (sandbox SQLite only). Read-only evaluation; no execution.",
        prog="eligibility",
    )
    parser.add_argument(
        "--sandbox-db",
        type=Path,
        required=True,
        help="Sandbox SQLite path (same as validation sandbox; not production).",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--evaluate", action="store_true", help="Evaluate eligibility for an approval_id")
    g.add_argument("--status", action="store_true", help="Show eligibility record by eligibility_id")

    parser.add_argument("--approval-id", type=str, default=None)
    parser.add_argument("--eligibility-id", type=str, default=None)
    parser.add_argument(
        "--evaluated-by",
        type=str,
        default="eligibility_evaluator_v1",
        help="Principal recorded on the eligibility row (evaluate only).",
    )

    args = parser.parse_args()

    assert_non_production_sqlite_path(args.sandbox_db)
    conn = open_validation_sandbox(args.sandbox_db)

    try:
        if args.evaluate:
            aid = (args.approval_id or "").strip()
            if not aid:
                print(json.dumps({"ok": False, "error": "FAIL: --approval-id required"}))
                raise SystemExit(2)
            out = evaluate_eligibility(
                conn,
                approval_id=aid,
                evaluated_by=(args.evaluated_by or "eligibility_evaluator_v1").strip(),
            )
            print(json.dumps(out, sort_keys=True, default=str))
            raise SystemExit(0 if out.get("ok") else 1)

        eid = (args.eligibility_id or "").strip()
        if not eid:
            print(json.dumps({"ok": False, "error": "FAIL: --eligibility-id required"}))
            raise SystemExit(2)
        row = get_eligibility_record(conn, eid)
        if not row:
            print(json.dumps({"ok": False, "error": "eligibility_id not found"}))
            raise SystemExit(1)
        print(json.dumps({"ok": True, "eligibility": row}, sort_keys=True, default=str))
        raise SystemExit(0)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
