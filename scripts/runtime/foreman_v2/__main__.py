from __future__ import annotations

import argparse
import json

from foreman_v2.app import run_loop, run_once
from foreman_v2.config import load_config
from foreman_v2.control import (
    actor_report,
    bind_sessions,
    doctor,
    operator_broadcast,
    operator_route,
    print_status,
    reconcile,
    reset_to_canonical,
    stick_sync,
    terminate_runtime,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Foreman v2 broker runtime")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("loop", help="Run broker loop (default)")
    sub.add_parser("once", help="Run one broker cycle and exit")
    sub.add_parser("status", help="Show runtime and workflow status snapshot")
    sub.add_parser("terminate", help="Stop running broker loop process")
    sub.add_parser("doctor", help="Validate live env + session preflight")
    sub.add_parser("bind-sessions", help="Auto-bind non-main live sessions into .env.foreman_v2")
    sub.add_parser("reconcile", help="Recompute canonical runtime state and sync talking stick")
    reset_p = sub.add_parser("reset", help="Reset runtime to canonical state")
    reset_p.add_argument("--to-canonical", action="store_true", help="Reset to canonical state and clear stale lock")
    sub.add_parser("stick-sync", help="Sync talking stick holder with current runtime state")

    route_p = sub.add_parser("route", help="Send operator message to one actor")
    route_p.add_argument("--actor", choices=["developer", "architect"], required=True)
    route_p.add_argument("--message", required=True)

    bc_p = sub.add_parser("broadcast", help="Send operator message to both actors")
    bc_p.add_argument("--message", required=True)
    rep_p = sub.add_parser("report", help="Record actor progress status for orchestration")
    rep_p.add_argument("--actor", choices=["developer", "architect"], required=True)
    rep_p.add_argument(
        "--status",
        choices=["received", "started", "in_progress", "blocked", "ready_for_handoff", "success", "failed"],
        required=True,
    )
    rep_p.add_argument("--step", default="")
    rep_p.add_argument("--detail", default="")

    args = parser.parse_args()
    cfg = load_config()

    if args.command == "once":
        st = run_once(cfg)
        print(
            f"foreman_v2: state={st.bridge_state} actor={st.next_actor} "
            f"proof={st.proof_status} reason={st.last_transition_reason}"
        )
        return
    if args.command == "status":
        print_status(cfg)
        return
    if args.command == "terminate":
        ok, detail = terminate_runtime(cfg)
        print(f"foreman_v2: terminate sent={ok} detail={detail}")
        return
    if args.command == "doctor":
        ok, checks = doctor(cfg)
        print(json.dumps({"ok": ok, "checks": checks}, indent=2, ensure_ascii=True))
        return
    if args.command == "bind-sessions":
        ok, detail = bind_sessions(cfg)
        print(f"foreman_v2: bind-sessions ok={ok} detail={detail}")
        return
    if args.command == "reconcile":
        st = reconcile(cfg)
        print(
            f"foreman_v2: reconcile state={st.bridge_state} actor={st.next_actor} "
            f"proof={st.proof_status} reason={st.last_transition_reason}"
        )
        return
    if args.command == "reset":
        if not args.to_canonical:
            print("foreman_v2: reset requires --to-canonical")
            return
        st = reset_to_canonical(cfg)
        print(
            f"foreman_v2: reset state={st.bridge_state} actor={st.next_actor} "
            f"proof={st.proof_status} reason={st.last_transition_reason}"
        )
        return
    if args.command == "stick-sync":
        payload = stick_sync(cfg)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return
    if args.command == "route":
        sent, detail = operator_route(cfg, args.actor, args.message)
        print(f"foreman_v2: route actor={args.actor} sent={sent} detail={detail}")
        return
    if args.command == "broadcast":
        result = operator_broadcast(cfg, args.message)
        print(f"foreman_v2: broadcast result={result}")
        return
    if args.command == "report":
        payload = actor_report(cfg, actor=args.actor, status=args.status, detail=args.detail, step=args.step)
        print(json.dumps(payload, ensure_ascii=True))
        return
    run_loop(cfg)


if __name__ == "__main__":
    main()

