#!/usr/bin/env python3
"""
Build clawbot_demo/events.txt from paired baseline+Anna rows in execution_ledger.db,
then POST sequential-learning start (new_run). Run on primary host with repo + DB.

  BLACKBOX_REPO_ROOT=~/blackbox python3 scripts/runtime/bootstrap_clawbot_sequential_demo.py
  python3 scripts/runtime/bootstrap_clawbot_sequential_demo.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

DEFAULT_STRATEGY = "jupiter_supertrend_ema_rsi_atr_v1"
DEFAULT_TEST_ID = "clawbot_demo_w10"
EVENT_LIMIT = 24


def _repo() -> Path:
    return Path(os.environ.get("BLACKBOX_REPO_ROOT", os.getcwd())).resolve()


def paired_event_ids(ledger: Path, strategy_id: str, limit: int) -> list[str]:
    conn = sqlite3.connect(str(ledger))
    try:
        cur = conn.execute(
            """
            SELECT DISTINCT a.market_event_id
            FROM execution_trades a
            INNER JOIN execution_trades b ON a.market_event_id = b.market_event_id
            WHERE a.lane = 'anna' AND a.strategy_id = ?
              AND b.lane = 'baseline' AND b.strategy_id = 'baseline'
            ORDER BY a.market_event_id
            LIMIT ?
            """,
            (strategy_id, limit),
        )
        return [str(r[0]) for r in cur.fetchall() if r[0]]
    finally:
        conn.close()


def _as_api_path(p: Path, repo: Path, container_prefix: str | None) -> str:
    """Paths the API container resolves (usually /repo/...) vs host checkout paths."""
    resolved = str(p.resolve())
    if container_prefix:
        try:
            rel = p.resolve().relative_to(repo.resolve())
        except ValueError:
            rel = Path(resolved).name
            return f"{container_prefix.rstrip('/')}/data/sequential_engine/clawbot_demo/{rel}"
        return f"{container_prefix.rstrip('/')}/" + str(rel).replace("\\", "/")
    return resolved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="only write events.txt")
    ap.add_argument("--strategy-id", default=os.environ.get("CLAWBOT_DEMO_STRATEGY_ID") or DEFAULT_STRATEGY)
    ap.add_argument("--test-id", default=os.environ.get("CLAWBOT_DEMO_TEST_ID") or DEFAULT_TEST_ID)
    ap.add_argument(
        "--ledger",
        default=os.environ.get("BLACKBOX_EXECUTION_LEDGER_PATH", "").strip() or "",
    )
    ap.add_argument("--market-db", default="")
    ap.add_argument(
        "--api-base",
        default=os.environ.get("CLAWBOT_DEMO_API_BASE", "https://127.0.0.1"),
        help="API origin (host: https://127.0.0.1 via nginx; inside api container: http://127.0.0.1:8080).",
    )
    ap.add_argument(
        "--container-prefix",
        default=os.environ.get("CLAWBOT_API_CONTAINER_REPO", "").strip() or None,
        help="If set (e.g. /repo), path fields in JSON use this prefix so the API container can open files.",
    )
    args = ap.parse_args()

    repo = _repo()
    demo_dir = repo / "data" / "sequential_engine" / "clawbot_demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    cal_path = demo_dir / "calibration.json"
    events_path = demo_dir / "events.txt"

    ledger = Path(args.ledger) if args.ledger.strip() else repo / "data" / "sqlite" / "execution_ledger.db"
    if not ledger.is_file():
        print(f"ledger not found: {ledger}", file=sys.stderr)
        return 1

    ids = paired_event_ids(ledger, args.strategy_id, EVENT_LIMIT)
    if len(ids) < 1:
        print("no paired market_event_id rows for strategy — cannot demo", file=sys.stderr)
        return 1

    events_path.write_text("\n".join(ids) + "\n", encoding="utf-8")
    print(f"wrote {len(ids)} lines -> {events_path}")

    if args.dry_run:
        return 0

    market_db = Path((args.market_db or "").strip() or str(repo / "data" / "sqlite" / "market_data.db"))
    art_dir = repo / "data" / "sequential_engine"
    cp = args.container_prefix
    body = {
        "start_mode": "new_run",
        "test_id": args.test_id,
        "strategy_id": args.strategy_id,
        "calibration_path": _as_api_path(cal_path, repo, cp),
        "events_file_path": _as_api_path(events_path, repo, cp),
        "ledger_db_path": _as_api_path(ledger, repo, cp),
        "market_db_path": _as_api_path(market_db, repo, cp),
        "artifacts_dir": _as_api_path(art_dir, repo, cp),
    }
    url = f"{args.api_base.rstrip('/')}/api/v1/sequential-learning/control/start"
    print("POST", url)
    r = subprocess.run(
        [
            "curl",
            "-skS",
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(body),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return r.returncode
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        print("non-json response", file=sys.stderr)
        return 1
    if not out.get("ok"):
        print("start failed", out, file=sys.stderr)
        return 1
    print("start_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
