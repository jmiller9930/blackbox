#!/usr/bin/env python3
"""
Execution plane CLI (mock): create request, approve/reject, run, kill switch.

Phase 4.4: `run_execution` returns execution result plus outcome + insight (see learning_loop).

Run from repo: python3 scripts/runtime/execution_cli.py <command> ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from execution_plane.approval_manager import (
    approve_request,
    create_request,
    get_request,
    latest_request_id,
    reject_request,
)
from execution_plane.execution_engine import run_execution
from execution_plane.kill_switch import (
    disable as ks_disable,
    enable as ks_enable,
    is_active as ks_is_active,
    toggle as ks_toggle,
)


def _rid(args: argparse.Namespace) -> str | None:
    if getattr(args, "request_id", None):
        return args.request_id
    # No --request-id (optionally --latest): resolve to most recent request
    return latest_request_id()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Execution plane (mock; Phase 4.4 feedback)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create_execution_request", help="Create execution_request_v1 from optional proposal JSON")
    c.add_argument("--proposal-json", type=Path, help="Path to anna_proposal_v1 JSON")

    a = sub.add_parser("approve_execution_request", help="Approve a pending request")
    g = a.add_mutually_exclusive_group(required=False)
    g.add_argument("--request-id", dest="request_id")
    g.add_argument("--latest", action="store_true")

    a.add_argument("--approver-id", default="human-approver", help="Approver identifier")

    r = sub.add_parser("reject_execution_request", help="Reject a pending request")
    g2 = r.add_mutually_exclusive_group(required=False)
    g2.add_argument("--request-id", dest="request_id")
    g2.add_argument("--latest", action="store_true")
    r.add_argument("--approver-id", default="human-approver")

    x = sub.add_parser("run_execution", help="Run mock execution (requires approval unless blocked)")
    g3 = x.add_mutually_exclusive_group(required=False)
    g3.add_argument("--request-id", dest="request_id")
    g3.add_argument("--latest", action="store_true")

    k = sub.add_parser("toggle_kill_switch", help="Toggle kill switch (blocks all execution when on)")
    k.add_argument("--on", action="store_true")
    k.add_argument("--off", action="store_true")

    q = sub.add_parser("kill_switch_status", help="Print kill switch state as JSON")
    g4 = sub.add_parser("get", help="Get one request by id")
    g4.add_argument("--request-id", required=True)

    args = p.parse_args(argv)

    if args.cmd == "create_execution_request":
        prop = None
        if args.proposal_json:
            prop = json.loads(args.proposal_json.read_text(encoding="utf-8"))
        out = create_request(prop)
        print(json.dumps(out, indent=2))
        return 0

    if args.cmd == "approve_execution_request":
        rid = _rid(args)
        if not rid:
            print(json.dumps({"error": "missing request id or --latest"}, indent=2))
            return 1
        req = approve_request(rid, args.approver_id)
        print(json.dumps(req or {"error": "not found", "request_id": rid}, indent=2))
        return 0 if req else 1

    if args.cmd == "reject_execution_request":
        rid = _rid(args)
        if not rid:
            print(json.dumps({"error": "missing request id or --latest"}, indent=2))
            return 1
        req = reject_request(rid, args.approver_id)
        print(json.dumps(req or {"error": "not found", "request_id": rid}, indent=2))
        return 0 if req else 1

    if args.cmd == "run_execution":
        rid = _rid(args)
        if not rid:
            print(json.dumps({"error": "missing request id or --latest"}, indent=2))
            return 1
        out = run_execution(rid)
        print(json.dumps(out, indent=2))
        return 0

    if args.cmd == "toggle_kill_switch":
        if args.on:
            ks_enable()
        elif args.off:
            ks_disable()
        else:
            ks_toggle()
        print(json.dumps({"kill_switch_active": ks_is_active()}, indent=2))
        return 0

    if args.cmd == "kill_switch_status":
        print(json.dumps({"kill_switch_active": ks_is_active()}, indent=2))
        return 0

    if args.cmd == "get":
        req = get_request(args.request_id)
        print(json.dumps(req or {"error": "not found"}, indent=2))
        return 0 if req else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
