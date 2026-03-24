#!/usr/bin/env python3
"""
Phase 3.3 — Anna proposal builder: anna_analysis_v1 → anna_proposal_v1 (validation-loop bridge).

Core logic: `anna_modules.py` (proposal shaping layer). This file is the CLI entrypoint.

Deterministic; paper-only; no Telegram, no registry load, no schema migration, no trades.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from anna_modules.analysis import build_analysis
from anna_modules.input_adapter import (
    load_latest_guardrail_policy,
    load_latest_market_snapshot,
    load_latest_stored_anna_analysis,
    try_load_decision_context,
    try_load_trend,
)
from anna_modules.proposal import assemble_anna_proposal_v1


def run_live_build(
    db_path: Path,
    input_text: str,
    *,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
) -> tuple[dict[str, Any], list[str]]:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)
    extra_notes: list[str] = []
    market, market_err = (None, None)
    ctx, ctx_err = (None, None)
    trend, trend_err = (None, None)
    policy, policy_err = (None, None)
    try:
        if use_snapshot:
            market, market_err = load_latest_market_snapshot(conn)
        if use_ctx:
            ctx, ctx_err = try_load_decision_context(conn)
        if use_trend:
            trend, trend_err = try_load_trend(conn)
        if use_policy:
            policy, policy_err = load_latest_guardrail_policy(conn)

        analysis = build_analysis(
            input_text,
            market=market,
            market_err=market_err,
            ctx=ctx,
            ctx_err=ctx_err,
            trend=trend,
            trend_err=trend_err,
            policy=policy,
            policy_err=policy_err,
            use_snapshot=use_snapshot,
            use_ctx=use_ctx,
            use_trend=use_trend,
            use_policy=use_policy,
            conn=conn,
        )
        if trend and not trend_err:
            analysis["notes"].append(
                f"System trend window_size={trend.get('window_size')} (loaded)."
            )
    finally:
        conn.close()
    extra_notes.extend(analysis.get("notes") or [])
    return analysis, extra_notes


def run(
    db_path: Path,
    *,
    input_text: str | None,
    use_stored: bool,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
    store: bool,
) -> int:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)

    source_task_id: str | None = None
    extra_notes: list[str] = []
    analysis: dict[str, Any]

    try:
        if use_stored:
            tid, anna, err = load_latest_stored_anna_analysis(conn)
            conn.close()
            conn = None  # type: ignore
            if err or not anna:
                print(json.dumps({"error": err or "missing analysis"}, indent=2), file=sys.stderr)
                return 3
            source_task_id = tid
            analysis = anna
        else:
            if not input_text or not input_text.strip():
                conn.close()
                conn = None  # type: ignore
                print(json.dumps({"error": "input_text required unless --use-latest-stored-anna-analysis"}, indent=2), file=sys.stderr)
                return 2
            conn.close()
            conn = None  # type: ignore
            analysis, extra_notes = run_live_build(
                db_path,
                input_text.strip(),
                use_snapshot=use_snapshot,
                use_ctx=use_ctx,
                use_trend=use_trend,
                use_policy=use_policy,
            )
    finally:
        if conn:
            conn.close()

    proposal = assemble_anna_proposal_v1(analysis, source_task_id=source_task_id, extra_notes=extra_notes)
    out: dict[str, Any] = {"anna_proposal": proposal, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = proposal["generated_at"]
        title = f"[Anna Proposal] {now[:19]}Z"
        desc = json.dumps({"anna_proposal": proposal}, ensure_ascii=False, indent=2)
        conn.execute(
            """
            INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, "anna", title, desc, "completed", "normal", now, now),
        )
        conn.commit()
        conn.close()
        out["stored_task_id"] = tid

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 3.3 — Anna analysis → anna_proposal_v1 (validation bridge)",
    )
    p.add_argument(
        "input_text",
        nargs="*",
        default=[],
        help="Trader text for live Anna build (omit if --use-latest-stored-anna-analysis)",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-anna-analysis",
        action="store_true",
        help="Use latest [Anna Analysis] task instead of live build",
    )
    p.add_argument("--use-latest-market-snapshot", action="store_true")
    p.add_argument("--use-latest-decision-context", action="store_true")
    p.add_argument("--use-latest-trend", action="store_true")
    p.add_argument("--use-latest-policy", action="store_true")
    p.add_argument("--store", action="store_true", help="Persist as [Anna Proposal] completed task")
    args = p.parse_args(argv)
    text = " ".join(args.input_text).strip() if args.input_text else ""
    db = args.db or default_sqlite_path()
    return run(
        db,
        input_text=text or None,
        use_stored=args.use_latest_stored_anna_analysis,
        use_snapshot=args.use_latest_market_snapshot,
        use_ctx=args.use_latest_decision_context,
        use_trend=args.use_latest_trend,
        use_policy=args.use_latest_policy,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
