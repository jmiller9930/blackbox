#!/usr/bin/env python3
"""Sandbox-only approval CLI (Twig 6). learning_core imports only — no runtime dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parent
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from learning_core.approval_model import (
    approve_pending,
    create_approval_request,
    defer_pending,
    get_approval,
    reject_pending,
)
from learning_core.remediation_validation import assert_non_production_sqlite_path, open_validation_sandbox


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Twig 6 — approval records (sandbox DB only). Does not execute remediation.",
        prog="approval_cli",
    )
    parser.add_argument(
        "--sandbox-db",
        type=Path,
        required=True,
        help="Sandbox SQLite path (same as validation sandbox; not production).",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true", help="Create PENDING approval request")
    g.add_argument(
        "--approve",
        action="store_true",
        dest="approve_decision",
        help="Transition PENDING → APPROVED",
    )
    g.add_argument(
        "--reject",
        action="store_true",
        dest="reject_decision",
        help="Transition PENDING → REJECTED",
    )
    g.add_argument(
        "--defer",
        action="store_true",
        dest="defer_decision",
        help="Transition PENDING → DEFERRED",
    )
    g.add_argument("--status", action="store_true", help="Show approval record (applies expiration)")

    parser.add_argument(
        "--source-remediation-id",
        type=str,
        default=None,
        dest="source_remediation_id",
        help="Remediation candidate id (approval artifact: source_remediation_id)",
    )
    parser.add_argument("--approval-id", type=str, default=None)
    parser.add_argument("--requested-by", type=str, default="cli_operator")
    parser.add_argument("--approved-by", type=str, default=None)
    parser.add_argument("--ttl-hours", type=int, default=168)

    args = parser.parse_args()

    assert_non_production_sqlite_path(args.sandbox_db)
    conn = open_validation_sandbox(args.sandbox_db)

    try:
        if args.create:
            if not args.source_remediation_id:
                print(json.dumps({"ok": False, "error": "FAIL: --source-remediation-id required"}))
                raise SystemExit(2)
            try:
                out = create_approval_request(
                    conn,
                    source_remediation_id=args.source_remediation_id.strip(),
                    requested_by=(args.requested_by or "cli_operator").strip(),
                )
                print(json.dumps({"ok": True, "approval": out}, sort_keys=True, default=str))
            except ValueError as e:
                print(json.dumps({"ok": False, "error": str(e)}, sort_keys=True))
                raise SystemExit(1) from e
            raise SystemExit(0)

        aid = (args.approval_id or "").strip()
        if not aid:
            print(json.dumps({"ok": False, "error": "FAIL: --approval-id required"}))
            raise SystemExit(2)

        if args.status:
            row = get_approval(conn, aid)
            if not row:
                print(json.dumps({"ok": False, "error": "approval_id not found"}))
                raise SystemExit(1)
            print(json.dumps({"ok": True, "approval": row}, sort_keys=True, default=str))
            raise SystemExit(0)

        approver = (args.approved_by or "").strip()
        if not approver:
            print(json.dumps({"ok": False, "error": "FAIL: --approved-by required"}))
            raise SystemExit(2)

        if args.approve_decision:
            try:
                out = approve_pending(
                    conn,
                    approval_id=aid,
                    approved_by=approver,
                    ttl_hours=args.ttl_hours,
                )
                print(json.dumps({"ok": True, "approval": out}, sort_keys=True, default=str))
            except ValueError as e:
                print(json.dumps({"ok": False, "error": str(e)}, sort_keys=True))
                raise SystemExit(1) from e
            raise SystemExit(0)

        if args.reject_decision:
            try:
                out = reject_pending(conn, approval_id=aid, approved_by=approver)
                print(json.dumps({"ok": True, "approval": out}, sort_keys=True, default=str))
            except ValueError as e:
                print(json.dumps({"ok": False, "error": str(e)}, sort_keys=True))
                raise SystemExit(1) from e
            raise SystemExit(0)

        if args.defer_decision:
            try:
                out = defer_pending(conn, approval_id=aid, approved_by=approver)
                print(json.dumps({"ok": True, "approval": out}, sort_keys=True, default=str))
            except ValueError as e:
                print(json.dumps({"ok": False, "error": str(e)}, sort_keys=True))
                raise SystemExit(1) from e
            raise SystemExit(0)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
