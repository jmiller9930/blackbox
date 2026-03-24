#!/usr/bin/env python3
"""DATA runtime: health checks → system_health_logs; optional watchdog with alert dedupe."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def collect_checks(
    conn: sqlite3.Connection,
    gateway_url: str,
    ollama_base: str,
    force_failure_url: str | None,
) -> list[tuple[str, str, bool, str]]:
    checks: list[tuple[str, str, bool, str]] = []

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

    if force_failure_url:
        ok_f, msg_f = _http_ok(force_failure_url, timeout=2.0)
        checks.append(("forced_failure_probe", force_failure_url, ok_f, msg_f))

    return checks


def insert_health_logs(
    conn,
    checks: list[tuple[str, str, bool, str]],
    now: str,
    source_agent: str,
) -> None:
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


def _insert_alert(
    conn,
    source_agent: str,
    check_name: str,
    target: str,
    detail: str,
    now: str,
) -> None:
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
                {
                    "kind": "health_check_failure",
                    "check": check_name,
                    "target": target,
                    "detail": detail[:1500],
                },
                ensure_ascii=False,
            )[:4000],
            "open",
            now,
        ),
    )


def apply_alerts_one_shot(
    conn,
    checks: list[tuple[str, str, bool, str]],
    now: str,
    source_agent: str,
) -> None:
    """Phase 1.7 behavior: only forced_failure_probe writes an alert when it fails."""
    for name, target, ok, detail in checks:
        if name != "forced_failure_probe":
            continue
        if ok:
            return
        _insert_alert(conn, source_agent, name, target, detail, now)
        return


def apply_alerts_watchdog(
    conn,
    checks: list[tuple[str, str, bool, str]],
    now: str,
    source_agent: str,
    last_ok: dict[str, bool],
) -> list[str]:
    """
    Alert only on transition to FAIL (prev is not False) or first observation of FAIL (prev missing).
    If still FAIL, dedupe (no duplicate alert).
    Returns list of check names that alerted.
    """
    alerted: list[str] = []
    for name, target, ok, detail in checks:
        prev = last_ok.get(name)
        last_ok[name] = ok
        if ok:
            continue
        if prev is False:
            continue
        _insert_alert(conn, source_agent, name, target, detail, now)
        alerted.append(name)
    return alerted


def run_once(
    db_path: Path,
    gateway_url: str,
    ollama_base: str,
    force_failure_url: str | None,
    source_agent: str = "DATA",
    *,
    watch_mode: bool = False,
    last_ok: dict[str, bool] | None = None,
) -> tuple[int, dict[str, bool], list[str]]:
    """
    Returns (exit_code, updated last_ok, alerts_emitted).
    """
    root = repo_root()
    conn = connect(db_path)
    try:
        ensure_schema(conn, root)
        seed_agents(conn)
    except Exception as e:
        print(f"schema/seed error: {e}", file=sys.stderr)
        return 2, {}, []

    if last_ok is None:
        last_ok = {}

    checks = collect_checks(conn, gateway_url, ollama_base, force_failure_url)
    now = _utc_now()
    insert_health_logs(conn, checks, now, source_agent)

    alerts: list[str] = []
    if watch_mode:
        alerts = apply_alerts_watchdog(conn, checks, now, source_agent, last_ok)
    else:
        apply_alerts_one_shot(conn, checks, now, source_agent)
        for name, _t, ok, _d in checks:
            if name == "forced_failure_probe":
                if not ok:
                    alerts.append("forced_failure_probe")
                else:
                    print(
                        "warning: forced-failure URL unexpectedly succeeded; no alert written",
                        file=sys.stderr,
                    )
                break

    conn.commit()
    conn.close()

    out = {
        "checks": [
            {"name": c[0], "target": c[1], "ok": c[2], "detail": c[3]} for c in checks
        ],
        "forced_failure_probe": force_failure_url,
        "db": str(db_path),
        "watch_mode": watch_mode,
        "alerts_emitted": alerts,
    }
    print(json.dumps(out, indent=2))
    return 0, last_ok, alerts


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
        help="Ollama base (default from OLLAMA_BASE_URL, else http://127.0.0.1:11434)",
    )
    p.add_argument(
        "--force-failure-url",
        default="http://127.0.0.1:59999/",
        help="HTTP probe expected to fail (one-shot: alert each run if fail; watchdog: dedupe)",
    )
    p.add_argument(
        "--no-forced-failure",
        action="store_true",
        help="Skip forced-failure probe",
    )
    p.add_argument(
        "--watchdog",
        action="store_true",
        help="Run checks on an interval until SIGINT/SIGTERM; alerts deduped on sustained failure",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=60.0,
        metavar="SEC",
        help="Seconds between watchdog iterations (default: 60)",
    )
    p.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        metavar="N",
        help="Stop after N iterations (0 = unlimited; watchdog only)",
    )
    args = p.parse_args(argv)

    db = args.db or default_sqlite_path()
    oll = args.ollama_base or ollama_base_url()
    ff = None if args.no_forced_failure else (args.force_failure_url or None)
    if ff == "":
        ff = None

    if not args.watchdog:
        code, _, _ = run_once(
            db,
            args.gateway_url,
            oll,
            ff,
            watch_mode=False,
        )
        return code

    stop = False

    def _handle(sig: int, _frame) -> None:
        nonlocal stop
        stop = True
        print(f"\nwatchdog stopping (signal {sig})", file=sys.stderr)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    last_ok: dict[str, bool] = {}
    iteration = 0
    while not stop:
        iteration += 1
        print(
            json.dumps({"event": "watchdog_iteration", "n": iteration, "ts": _utc_now()}),
            file=sys.stderr,
        )
        code, last_ok, alerts = run_once(
            db,
            args.gateway_url,
            oll,
            ff,
            watch_mode=True,
            last_ok=last_ok,
        )
        if code != 0:
            return code
        if args.max_iterations and iteration >= args.max_iterations:
            break
        if stop:
            break
        time.sleep(max(0.5, args.interval))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
