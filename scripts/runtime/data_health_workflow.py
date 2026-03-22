#!/usr/bin/env python3
"""DATA runtime workflow: SQLite + gateway + Ollama checks; logs to system_health_logs; optional forced-failure alert."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import os
import uuid
import urllib.request
from datetime import datetime, timezone

from _db import connect, ensure_schema, seed_agents
from _ollama import ollama_base_url
from _paths import default_sqlite_path, repo_root


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _http_ok(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {getattr(r, 'status', 200)}"
    except Exception as e:
        return False, str(e)


def _ollama_tags_ok(base: str, timeout: float = 5.0) -> tuple[bool, str]:
    url = f"{base.rstrip('/')}/api/tags"
    return _http_ok(url, timeout=timeout)


def run(
    db_path: Path,
    gateway_url: str,
    ollama_base: str,
    force_failure_url: str | None,
    source_agent: str = "DATA",
) -> int:
    root = repo_root()
    conn = connect(db_path)
    try:
        ensure_schema(conn, root)
        seed_agents(conn)
    except Exception as e:
        print(f"schema/seed error: {e}", file=sys.stderr)
        return 2

    checks: list[tuple[str, str, bool, str]] = []

    # SQLite
    try:
        conn.execute("SELECT 1").fetchone()
        checks.append(("sqlite", "sqlite://blackbox.db", True, "SELECT 1 ok"))
    except Exception as e:
        checks.append(("sqlite", "sqlite://blackbox.db", False, str(e)))

    gw = gateway_url if gateway_url.endswith("/") else gateway_url + "/"
    ok_g, msg_g = _http_ok(gw)
    checks.append(("gateway", gw.rstrip("/"), ok_g, msg_g))

    ok_o, msg_o = _ollama_tags_ok(ollama_base)
    checks.append(("ollama", f"{ollama_base}/api/tags", ok_o, msg_o))

    now = _utc_now()
    for name, target, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        conn.execute(
            """
            INSERT INTO system_health_logs (
              id, checked_at, target, check_type, status, summary, evidence, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                now,
                target,
                name,
                status,
                detail[:2000],
                json.dumps({"source_agent": source_agent}, ensure_ascii=False),
                now,
            ),
        )
    conn.commit()

    # Forced failure: alert only (three health rows remain sqlite/gateway/ollama)
    if force_failure_url:
        ok_f, msg_f = _http_ok(force_failure_url, timeout=2.0)
        if not ok_f:
            conn.execute(
                """
                INSERT INTO alerts (id, source_agent, severity, channel, message, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    source_agent,
                    "warning",
                    None,
                    json.dumps(
                        {"kind": "forced_failure_probe", "target": force_failure_url, "detail": msg_f},
                        ensure_ascii=False,
                    )[:4000],
                    "open",
                    now,
                ),
            )
            conn.commit()
        else:
            print(
                "warning: forced-failure URL unexpectedly succeeded; no alert written",
                file=sys.stderr,
            )

    conn.close()

    out = {
        "checks": [
            {"name": c[0], "target": c[1], "ok": c[2], "detail": c[3]} for c in checks
        ],
        "forced_failure_probe": force_failure_url,
        "db": str(db_path),
    }
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DATA runtime: health checks → SQLite")
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default BLACKBOX_SQLITE_PATH or repo data/sqlite/blackbox.db)",
    )
    p.add_argument(
        "--gateway-url",
        default=os.environ.get("GATEWAY_HEALTH_URL", "http://127.0.0.1:18789/"),
        help="Gateway base URL (GET)",
    )
    p.add_argument(
        "--ollama-base",
        default=None,
        help="Ollama base (default from OLLAMA_BASE_URL or ~/.openclaw/openclaw.json)",
    )
    p.add_argument(
        "--force-failure-url",
        default="http://127.0.0.1:59999/",
        help="HTTP probe expected to fail (alert if connection fails)",
    )
    p.add_argument(
        "--no-forced-failure",
        action="store_true",
        help="Skip forced-failure probe and alert",
    )
    args = p.parse_args(argv)

    db = args.db or default_sqlite_path()
    oll = args.ollama_base or ollama_base_url()
    ff = None if args.no_forced_failure else (args.force_failure_url or None)
    return run(db, args.gateway_url, oll, ff)


if __name__ == "__main__":
    raise SystemExit(main())
