from __future__ import annotations

import argparse

from foreman_v2.app import run_loop, run_once
from foreman_v2.config import load_config
from foreman_v2.control import operator_broadcast, operator_route, print_status, terminate_runtime


def main() -> None:
    parser = argparse.ArgumentParser(description="Foreman v2 broker runtime")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("loop", help="Run broker loop (default)")
    sub.add_parser("once", help="Run one broker cycle and exit")
    sub.add_parser("status", help="Show runtime and workflow status snapshot")
    sub.add_parser("terminate", help="Stop running broker loop process")

    route_p = sub.add_parser("route", help="Send operator message to one actor")
    route_p.add_argument("--actor", choices=["developer", "architect"], required=True)
    route_p.add_argument("--message", required=True)

    bc_p = sub.add_parser("broadcast", help="Send operator message to both actors")
    bc_p.add_argument("--message", required=True)

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
    if args.command == "route":
        sent, detail = operator_route(cfg, args.actor, args.message)
        print(f"foreman_v2: route actor={args.actor} sent={sent} detail={detail}")
        return
    if args.command == "broadcast":
        result = operator_broadcast(cfg, args.message)
        print(f"foreman_v2: broadcast result={result}")
        return
    run_loop(cfg)


if __name__ == "__main__":
    main()

