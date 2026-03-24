#!/usr/bin/env python3
"""
Phase 3.2 — Anna conversational analyst v1: trader text → structured anna_analysis_v1.

Implementation lives in `anna_modules.py` (Phase 3.4 modular layers). This file is the CLI entrypoint.

Pipeline: intent → context check → contextual memory (SQLite) → deterministic playbook → optional local LLM (Ollama/Qwen when `ANNA_USE_LLM=1`). No Telegram in this module; read-only concept retrieval from `data/concepts/registry.json` (Phase 3.6). No execution.
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
    try_load_decision_context,
    try_load_trend,
)

def analyze_to_dict(
    db_path: Path,
    input_text: str,
    *,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
    store: bool,
) -> dict[str, Any]:
    """Programmatic entry (e.g. Telegram). Returns structured result; does not print."""
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)

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

    out: dict[str, Any] = {"anna_analysis": analysis, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = analysis["generated_at"]
        title = f"[Anna Analysis] {now[:19]}Z"
        desc = json.dumps({"anna_analysis": analysis}, ensure_ascii=False, indent=2)
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

    return out


def run(
    db_path: Path,
    input_text: str,
    *,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
    store: bool,
) -> int:
    out = analyze_to_dict(
        db_path,
        input_text,
        use_snapshot=use_snapshot,
        use_ctx=use_ctx,
        use_trend=use_trend,
        use_policy=use_policy,
        store=store,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 3.2 — Anna analyst v1 (structured, rule-based, no execution)",
    )
    p.add_argument(
        "input_text",
        nargs="+",
        help="Trader-language input (quote multiple words as one shell argument or separate words)",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-market-snapshot",
        action="store_true",
        help="Load latest [Market Snapshot] task (market_snapshot_v1)",
    )
    p.add_argument(
        "--use-latest-decision-context",
        action="store_true",
        help="Load latest [Decision Context] task (decision_context_v1)",
    )
    p.add_argument(
        "--use-latest-trend",
        action="store_true",
        help="Load latest [System Trend] task (system_trend_v1)",
    )
    p.add_argument(
        "--use-latest-policy",
        action="store_true",
        help="Load latest [Guardrail Policy] task (guardrail_policy_v1)",
    )
    p.add_argument("--store", action="store_true", help="Persist anna_analysis as [Anna Analysis] task")
    args = p.parse_args(argv)
    text = " ".join(args.input_text).strip()
    if not text:
        print(json.dumps({"error": "empty input_text"}, indent=2), file=sys.stderr)
        return 2
    db = args.db or default_sqlite_path()
    return run(
        db,
        text,
        use_snapshot=args.use_latest_market_snapshot,
        use_ctx=args.use_latest_decision_context,
        use_trend=args.use_latest_trend,
        use_policy=args.use_latest_policy,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
