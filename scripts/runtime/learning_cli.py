#!/usr/bin/env python3
"""
Phase 4.5 — List, summarize, and report on execution insights (`execution_feedback_v1`).

Run from repo: python3 scripts/runtime/learning_cli.py <command> ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from learning_visibility.insight_query import fetch_insights
from learning_visibility.insight_summary import summarize_insights
from learning_visibility.report_generator import generate_report


def _add_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--insight-kind", help="Filter by insight_kind enum value")
    p.add_argument("--type", dest="insight_type", choices=("success", "failure"), help="Filter by insight.type")
    p.add_argument("--request-id", help="Filter by linked_request_id")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Learning visibility (Phase 4.5)")
    sub = p.add_subparsers(dest="cmd", required=True)

    li = sub.add_parser("list_insights", help="List recent execution feedback rows as JSON")
    _add_filters(li)
    li.add_argument("--limit", type=int, default=100, help="Max rows (default 100)")

    su = sub.add_parser("summarize_insights", help="Aggregate counts JSON")
    _add_filters(su)
    su.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap rows after filters (default: no cap)",
    )

    gr = sub.add_parser("generate_report", help="Human-readable summary from aggregates")
    _add_filters(gr)
    gr.add_argument("--limit", type=int, default=None, help="Cap rows after filters (default: no cap)")

    args = p.parse_args(argv)

    def _fetch(lim: int | None) -> list:
        return fetch_insights(
            limit=lim,
            insight_kind=args.insight_kind,
            insight_type=args.insight_type,
            request_id=args.request_id,
        )

    if args.cmd == "list_insights":
        rows = _fetch(args.limit)
        print(json.dumps(rows, indent=2))
        return 0

    if args.cmd == "summarize_insights":
        rows = _fetch(args.limit)
        summary = summarize_insights(rows)
        print(json.dumps(summary, indent=2))
        return 0

    if args.cmd == "generate_report":
        rows = _fetch(args.limit)
        summary = summarize_insights(rows)
        print(generate_report(summary))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
