#!/usr/bin/env python3
"""
Terminal UI: header = preflight-style health checks; body = Pyth (Hermes) SOL/USD oracle view.

This is an **operator surface** — not an order entry or execution terminal. JUPv3 policy uses
Binance for the baseline axis; Pyth is oracle context / tape (see baseline_chain_validate docs).

Usage (from repo root):

  PYTHONPATH=scripts/runtime python3 scripts/operator/preflight_pyth_tui.py

Environment (optional):
  BLACKBOX_MARKET_DATA_PATH — if set and file exists, shows latest market_ticks row age vs wall clock.
  MARKET_TICK_SYMBOL        — default SOL-USD
  PYTH_SOL_USD_FEED_ID      — default Crypto.SOL/USD feed id (hex, no 0x)

Exit: Ctrl+C
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_DEFAULT_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
_HERMES_LATEST = "https://hermes.pyth.network/v2/updates/price/latest"
_BINANCE_PING = "https://api.binance.com/api/v3/ping"
_BINANCE_KLINES = "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=1"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _http_code(url: str, timeout: float = 12.0) -> tuple[int | None, str]:
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "blackbox-preflight-tui"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), ""
    except urllib.error.HTTPError as e:
        return e.code, str(e.reason)
    except Exception as e:
        return None, str(e)


def _binance_ping() -> CheckResult:
    code, err = _http_code(_BINANCE_PING)
    if code == 200:
        return CheckResult("Binance /api/v3/ping", True, f"HTTP {code}")
    if code is None:
        return CheckResult("Binance /api/v3/ping", False, err or "request failed")
    return CheckResult("Binance /api/v3/ping", False, f"HTTP {code}" + (f" ({err})" if err else ""))


def _binance_klines() -> CheckResult:
    code, err = _http_code(_BINANCE_KLINES)
    if code != 200:
        if code is None:
            return CheckResult("Binance klines SOLUSDT 5m", False, err or "request failed")
        return CheckResult("Binance klines SOLUSDT 5m", False, f"HTTP {code}")
    try:
        req = urllib.request.Request(_BINANCE_KLINES, headers={"User-Agent": "blackbox-preflight-tui"})
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            raw = resp.read(4).decode("utf-8", errors="replace")
        if raw.startswith("["):
            return CheckResult("Binance klines (body)", True, "JSON array")
        return CheckResult("Binance klines (body)", False, "not a JSON array")
    except Exception as e:
        return CheckResult("Binance klines (body)", False, str(e))


def _hermes_pyth() -> tuple[CheckResult, dict[str, Any]]:
    fid = (os.environ.get("PYTH_SOL_USD_FEED_ID") or _DEFAULT_FEED).strip()
    url = f"{_HERMES_LATEST}?ids[]={fid}&parsed=true"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "blackbox-preflight-tui"})
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return CheckResult("Hermes Pyth latest (parsed)", False, str(e)), {}
    parsed = body.get("parsed") if isinstance(body, dict) else None
    if not isinstance(parsed, list) or not parsed:
        return CheckResult("Hermes Pyth latest (parsed)", False, "empty parsed[]"), {}
    return CheckResult("Hermes Pyth latest (parsed)", True, "OK"), {"parsed": parsed, "feed_id": fid}


def _parse_pyth_price(parsed: list[dict[str, Any]]) -> dict[str, Any]:
    p0 = parsed[0]
    pr = p0.get("price") or {}
    try:
        price_i = int(pr["price"])
        conf_i = int(pr["conf"])
        expo = int(pr["expo"])
        pub = int(pr["publish_time"])
    except (KeyError, TypeError, ValueError):
        return {}
    scale = 10.0**expo
    return {
        "price": float(price_i) * scale,
        "conf": float(conf_i) * scale,
        "publish_time": pub,
        "feed_id": p0.get("id", ""),
    }


def _market_db_tick() -> CheckResult:
    raw = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()
    sym = (os.environ.get("MARKET_TICK_SYMBOL") or "SOL-USD").strip() or "SOL-USD"
    if not raw:
        return CheckResult("SQLite market_ticks (optional)", True, "BLACKBOX_MARKET_DATA_PATH unset — skipped")
    p = Path(raw)
    if not p.is_file():
        return CheckResult("SQLite market_ticks (optional)", True, f"no file {p} — skipped")
    try:
        conn = sqlite3.connect(str(p))
        try:
            row = conn.execute(
                """
                SELECT primary_price, primary_publish_time, inserted_at
                FROM market_ticks
                WHERE symbol = ?
                ORDER BY inserted_at DESC, id DESC
                LIMIT 1
                """,
                (sym,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return CheckResult("SQLite market_ticks", False, str(e))
    if row is None:
        return CheckResult("SQLite market_ticks", False, f"no rows for {sym}")
    price, pub, ins_at = row
    now = time.time()
    age = None
    if pub is not None:
        try:
            age = now - float(int(pub))
        except (TypeError, ValueError):
            pass
    age_s = f"publish_age ~{age:.0f}s" if age is not None else "publish_age n/a"
    ok = age is None or age < 120.0
    return CheckResult(
        "SQLite market_ticks (latest)",
        ok,
        f"{sym} price={price}  {age_s}" + ("" if ok else "  (stale?)"),
    )


def _docker_seanv3() -> CheckResult:
    try:
        out = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "seanv3"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return CheckResult("Docker seanv3 (optional)", True, "docker CLI missing — skipped")
    except subprocess.TimeoutExpired:
        return CheckResult("Docker seanv3 (optional)", True, "timeout — skipped")
    if out.returncode != 0:
        return CheckResult("Docker seanv3 (optional)", True, "container absent — skipped")
    running = (out.stdout or "").strip().lower() == "true"
    if running:
        return CheckResult("Docker seanv3", True, "Running")
    return CheckResult("Docker seanv3 (optional)", True, "not running — skipped")


def _run_checks(hermes_extra: dict[str, Any]) -> tuple[list[CheckResult], dict[str, Any]]:
    checks: list[CheckResult] = []
    checks.append(_binance_ping())
    checks.append(_binance_klines())
    h_check, extra = _hermes_pyth()
    checks.append(h_check)
    hermes_extra.clear()
    hermes_extra.update(extra)
    checks.append(_market_db_tick())
    checks.append(_docker_seanv3())
    return checks, hermes_extra


def _header_table(checks: list[CheckResult]) -> Table:
    t = Table(box=box.ROUNDED, expand=True, show_header=True, header_style="bold")
    t.add_column("Check", ratio=2)
    t.add_column("Status", ratio=1)
    t.add_column("Detail", ratio=3)
    for c in checks:
        status = Text("OK", style="bold green") if c.ok else Text("FAIL", style="bold red")
        if not c.ok and "optional" in c.name.lower() and "skipped" in c.detail.lower():
            status = Text("—", style="dim")
        t.add_row(c.name, status, c.detail)
    return t


def _main_panel(parsed: list[dict[str, Any]] | None, now_ts: float) -> Panel:
    note = (
        "[dim]Oracle tape (Hermes). JUPv3 policy baseline is Binance klines; use this for "
        "oracle context / cross-check, not as the sole trade axis.[/dim]"
    )
    if not parsed:
        return Panel(
            Group(Text("No Pyth parsed payload yet.", style="yellow"), Text.from_markup(note)),
            title="Trade / oracle window (Pyth SOL/USD)",
            border_style="yellow",
        )
    q = _parse_pyth_price(parsed)
    if not q:
        return Panel(
            Group(Text("Could not parse Pyth price fields.", style="red"), Text.from_markup(note)),
            title="Trade / oracle window (Pyth SOL/USD)",
            border_style="red",
        )
    pub = q["publish_time"]
    wall_age = now_ts - float(pub) if pub else None
    rel = (q["conf"] / q["price"]) if q["price"] else 0.0
    body_txt = "\n".join(
        [
            f"[bold cyan]SOL/USD[/bold]  [bold white]{q['price']:.4f}[/bold]  USD",
            f"Confidence band: ±{q['conf']:.6f}  ({rel * 100:.4f}% of price)",
            (
                f"Publish time (unix): {pub}   wall age: ~{wall_age:.1f}s"
                if wall_age is not None
                else f"Publish: {pub}"
            ),
            f"Feed id: {q.get('feed_id', '')[:20]}…",
            "",
            note,
        ]
    )
    return Panel(
        Text.from_markup(body_txt),
        title="Trade / oracle window (Pyth SOL/USD)",
        border_style="green",
    )


def main() -> None:
    console = Console()
    hermes_bucket: dict[str, Any] = {}
    refresh = float(os.environ.get("BLACKBOX_TUI_REFRESH_SEC", "2.0"))

    def render() -> Group:
        checks, _ = _run_checks(hermes_bucket)
        parsed = hermes_bucket.get("parsed") if isinstance(hermes_bucket.get("parsed"), list) else None
        now_ts = time.time()
        ht = _header_table(checks)
        strict_ok = all(c.ok for c in checks)
        banner = (
            "[bold green]ALL ACTIVE — checks passing[/bold green]"
            if strict_ok
            else "[bold red]DEGRADED — fix failing checks before relying on runtime[/bold red]"
        )
        top = Panel(ht, title=f"[bold]{banner}[/bold]", subtitle="Preflight strip (Binance + Hermes + optional DB/Docker)", border_style="green" if strict_ok else "red")
        body = _main_panel(parsed, now_ts)
        return Group(top, body)

    console.print("[dim]BLACK BOX — preflight + Pyth oracle TUI  (Ctrl+C to exit)[/dim]\n")
    with Live(render(), console=console, refresh_per_second=min(1.0 / max(refresh, 0.25), 30.0)) as live:
        try:
            while True:
                time.sleep(refresh)
                live.update(render())
        except KeyboardInterrupt:
            console.print("\n[dim]Exited.[/dim]")


if __name__ == "__main__":
    main()
