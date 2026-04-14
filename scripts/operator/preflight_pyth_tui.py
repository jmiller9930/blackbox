#!/usr/bin/env python3
"""
**SeanV3 operator TUI** — primary terminal shell for SeanV3 initiative: header = active **policy** slot
+ preflight checks; body = Pyth (Hermes) SOL/USD oracle context. Not a BlackBox pod UI.

**Policy registry:** ``scripts/operator/policy_registry.json``. Override path with ``SEANV3_POLICY_REGISTRY``
(or legacy ``BLACKBOX_POLICY_REGISTRY``). Policies describe optional TS entry paths and dataset modes for
the SeanV3 stack; **this TUI does not execute** strategy code — run ``node <entry>`` elsewhere if needed.

Use ``--menu`` for a picker dialog (prompt_toolkit), or ``--policy <id>`` / ``SEANV3_ACTIVE_POLICY_ID``.

Usage (from repo root):

  PYTHONPATH=scripts/runtime python3 scripts/operator/preflight_pyth_tui.py
  PYTHONPATH=scripts/runtime python3 scripts/operator/preflight_pyth_tui.py --menu

Environment (optional):
  SEANV3_POLICY_REGISTRY / SEANV3_ACTIVE_POLICY_ID  (preferred; BLACKBOX_* names still accepted)
  BLACKBOX_MARKET_DATA_PATH or SEAN_MARKET_DATA_PATH — optional SQLite tick check when dataset mode is env
  MARKET_TICK_SYMBOL          — default SOL-USD
  PYTH_SOL_USD_FEED_ID        — default Crypto.SOL/USD feed id (hex, no 0x)
  PYTH_HERMES_BASE_URL        — Hermes origin (default https://hermes.pyth.network); alias HERMES_PYTH_BASE_URL
  BINANCE_API_BASE_URL        — Binance REST origin (default https://api.binance.com); host routing per VPN/README.md
  BLACKBOX_BINANCE_KLINE_SYMBOL / BINANCE_SYMBOL — spot symbol for klines smoke (default SOLUSDT)
  TLS: prefer ``pip install certifi`` if you see CERTIFICATE_VERIFY_FAILED on macOS; or set
  SSL_CERT_FILE / REQUESTS_CA_BUNDLE to a CA bundle; last resort for lab/VPN inspection:
  SEANV3_SSL_INSECURE=1 (disables TLS verification — not for production).
  SEANV3_AUTO_INIT_LEDGER_DB=0 — do not create an empty capture/sean_parity.db when missing.
  SEAN_PAPER_STARTING_BALANCE_USD — fallback if analog_meta.paper_starting_balance_usd missing (default 1000)
  SEANV3_TUI_TRADE_ROWS — max rows in Trade window table (default 20, max 50)
  SEANV3_TUI_PARITY_ROWS — max rows in Sean vs BlackBox parity table (default 18, max 40)
  SEANV3_CANONICAL_SYMBOL — sym column (default SOL-PERP)
  BLACKBOX_EXECUTION_LEDGER_PATH — SQLite for baseline ``execution_trades`` (default repo data/sqlite/execution_ledger.db)

Exit: Ctrl+C
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME = str(_REPO_ROOT / "scripts" / "runtime")
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)

from market_data.public_data_urls import (  # noqa: E402
    binance_klines_url,
    binance_ping_url,
    hermes_price_latest_parsed_url,
)

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_DEFAULT_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"

_BB_LANE = "baseline"
_BB_STRATEGY = "baseline"
# Relative entry-price tolerance for "MATCH" (fractional drift allowed).
_PARITY_PRICE_REL_TOL = 0.005


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return _script_dir().parents[2]


def _default_registry_path() -> Path:
    raw = (os.environ.get("SEANV3_POLICY_REGISTRY") or os.environ.get("BLACKBOX_POLICY_REGISTRY") or "").strip()
    if raw:
        return Path(raw).resolve()
    return _script_dir() / "policy_registry.json"


def load_policy_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Policy registry not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    policies = data.get("policies")
    if not isinstance(policies, list) or not policies:
        raise ValueError("Registry must contain a non-empty 'policies' array")
    return data


def _env_market_data_path() -> str:
    return (os.environ.get("SEAN_MARKET_DATA_PATH") or os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()


def resolve_effective_market_data_path(repo_root: Path, policy: dict[str, Any]) -> str | None:
    """Return SQLite path string for market_ticks check, or None to skip / use env-only messaging."""
    ds = policy.get("dataset")
    if not isinstance(ds, dict):
        return _env_market_data_path() or None
    mode = (ds.get("mode") or "env").strip().lower()
    if mode == "isolated":
        rel = (ds.get("sqlite_relative") or "").strip()
        if not rel:
            return None
        return str((repo_root / rel).resolve())
    # env | shared
    return _env_market_data_path() or None


def resolve_entry_path(repo_root: Path, policy: dict[str, Any]) -> Path | None:
    ent = policy.get("entry")
    if ent is None or not str(ent).strip():
        return None
    return (repo_root / str(ent).strip()).resolve()


def pick_policy_interactive(
    policies: list[dict[str, Any]],
    current_id: str | None,
) -> str | None:
    from prompt_toolkit.shortcuts import radiolist_dialog

    values = [(str(p["id"]), str(p.get("label") or p["id"])) for p in policies if p.get("id")]
    default = current_id if current_id in {v[0] for v in values} else (values[0][0] if values else None)
    result = radiolist_dialog(
        title="Active policy",
        text="Choose registry policy (dataset + entry are shown in the TUI header).",
        values=values,
        default=default,
    ).run()
    return result


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _ssl_context() -> ssl.SSLContext:
    if (os.environ.get("SEANV3_SSL_INSECURE") or "").strip().lower() in ("1", "true", "yes"):
        return ssl._create_unverified_context()
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


def _binance_spot_symbol() -> str:
    return (
        os.environ.get("BLACKBOX_BINANCE_KLINE_SYMBOL")
        or os.environ.get("BINANCE_SYMBOL")
        or "SOLUSDT"
    ).strip().upper() or "SOLUSDT"


def _http_code(url: str, timeout: float = 12.0) -> tuple[int | None, str]:
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "seanv3-operator-tui"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.getcode(), ""
    except urllib.error.HTTPError as e:
        return e.code, str(e.reason)
    except Exception as e:
        return None, str(e)


def _binance_ping() -> CheckResult:
    code, err = _http_code(binance_ping_url())
    if code == 200:
        return CheckResult("Binance /api/v3/ping", True, f"HTTP {code}")
    if code is None:
        return CheckResult("Binance /api/v3/ping", False, err or "request failed")
    return CheckResult("Binance /api/v3/ping", False, f"HTTP {code}" + (f" ({err})" if err else ""))


def _binance_klines() -> CheckResult:
    sym = _binance_spot_symbol()
    klines_url = binance_klines_url(symbol=sym, interval="5m", limit=1)
    label = f"Binance klines {sym} 5m"
    code, err = _http_code(klines_url)
    if code != 200:
        if code is None:
            return CheckResult(label, False, err or "request failed")
        return CheckResult(label, False, f"HTTP {code}")
    try:
        req = urllib.request.Request(klines_url, headers={"User-Agent": "seanv3-operator-tui"})
        with urllib.request.urlopen(req, timeout=12.0, context=_ssl_context()) as resp:
            raw = resp.read(4).decode("utf-8", errors="replace")
        if raw.startswith("["):
            return CheckResult("Binance klines (body)", True, "JSON array")
        return CheckResult("Binance klines (body)", False, "not a JSON array")
    except Exception as e:
        return CheckResult("Binance klines (body)", False, str(e))


def _hermes_pyth() -> tuple[CheckResult, dict[str, Any]]:
    fid = (os.environ.get("PYTH_SOL_USD_FEED_ID") or _DEFAULT_FEED).strip()
    url = hermes_price_latest_parsed_url(fid)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "seanv3-operator-tui"})
        with urllib.request.urlopen(req, timeout=12.0, context=_ssl_context()) as resp:
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


def _market_db_tick(market_data_path: str | None = None) -> CheckResult:
    raw = (market_data_path or "").strip() if market_data_path is not None else _env_market_data_path()
    sym = (os.environ.get("MARKET_TICK_SYMBOL") or "SOL-USD").strip() or "SOL-USD"
    if not raw:
        return CheckResult("SQLite market_ticks (optional)", True, "SEAN_MARKET_DATA_PATH unset — skipped")
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


def _run_checks(
    hermes_extra: dict[str, Any],
    *,
    market_data_path: str | None = None,
) -> tuple[list[CheckResult], dict[str, Any]]:
    checks: list[CheckResult] = []
    checks.append(_binance_ping())
    checks.append(_binance_klines())
    h_check, extra = _hermes_pyth()
    checks.append(h_check)
    hermes_extra.clear()
    hermes_extra.update(extra)
    checks.append(_market_db_tick(market_data_path))
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
        "[dim]Oracle tape (Hermes). SeanV3 bar baseline is Binance; use this panel for oracle context.[/dim]"
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
            f"[bold cyan]SOL/USD[/bold cyan]  [bold white]{q['price']:.4f}[/bold white]  USD",
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


def _default_sean_sqlite(repo_root: Path) -> Path:
    raw = (os.environ.get("SEANV3_SQLITE_PATH") or "").strip()
    if raw:
        return Path(raw).resolve()
    return (repo_root / "vscode-test" / "seanv3" / "capture" / "sean_parity.db").resolve()


def _paper_starting_usd(conn: sqlite3.Connection) -> float:
    try:
        row = conn.execute(
            "SELECT v FROM analog_meta WHERE k = ?",
            ("paper_starting_balance_usd",),
        ).fetchone()
        if row and row[0] is not None:
            v = float(str(row[0]).strip())
            if v > 0:
                return v
    except (sqlite3.Error, ValueError, TypeError):
        pass
    raw = (os.environ.get("SEAN_PAPER_STARTING_BALANCE_USD") or "1000").strip()
    try:
        v = float(raw)
        return v if v > 0 else 1000.0
    except ValueError:
        return 1000.0


def _unrealized_usd(entry: float, mark: float, size: float, side: str) -> float:
    sd = str(side).lower()
    if sd == "long":
        return (mark - entry) * size
    if sd == "short":
        return (entry - mark) * size
    return 0.0


def _sean_ledger_panel(repo_root: Path, mark_usd: float | None = None) -> Panel:
    p = _default_sean_sqlite(repo_root)
    if not p.is_file():
        return Panel(
            Text.from_markup(f"[dim]SeanV3 DB not found: {p}[/dim]"),
            title="SeanV3 paper ledger (testing)",
            border_style="dim",
        )
    try:
        conn = sqlite3.connect(str(p))
        try:
            n = int(conn.execute("SELECT COUNT(*) FROM sean_paper_trades").fetchone()[0])
            last = conn.execute(
                "SELECT gross_pnl_usd, result_class, side FROM sean_paper_trades ORDER BY id DESC LIMIT 1"
            ).fetchone()
            pos = conn.execute(
                "SELECT side, entry_price, size_notional_sol FROM sean_paper_position WHERE id=1"
            ).fetchone()
            total = conn.execute("SELECT COALESCE(SUM(gross_pnl_usd),0) FROM sean_paper_trades").fetchone()[0]
            starting = _paper_starting_usd(conn)
        finally:
            conn.close()
    except sqlite3.Error as e:
        return Panel(Text(str(e), style="red"), title="SeanV3 paper ledger (testing)", border_style="red")
    realized = float(total)
    unreal = 0.0
    open_line = "Open: flat"
    if pos and pos[0] and str(pos[0]) != "flat" and mark_usd is not None:
        try:
            entry = float(pos[1])
            size = float(pos[2] or 1.0)
            unreal = _unrealized_usd(entry, float(mark_usd), size, str(pos[0]))
            open_line = f"Open: {pos[0]} @ {pos[1]}  notional_sol≈{size:g}  mtm≈{unreal:+.4f} USD (Hermes mark)"
        except (TypeError, ValueError):
            open_line = f"Open: {pos[0]} @ {pos[1]}"
    elif pos and pos[0] and str(pos[0]) != "flat":
        open_line = f"Open: {pos[0]} @ {pos[1]}  (set Hermes OK for mtm)"
    equity = starting + realized + unreal
    lines = [
        "[bold]Paper account (simulated — not real funds)[/bold]",
        f"Starting balance: {starting:.2f} USD  (SEAN_PAPER_STARTING_BALANCE_USD / analog_meta)",
        f"Realized P&L: {realized:+.4f} USD  |  Closed trades: {n}",
        f"[bold]Equity (est.): {equity:.4f} USD[/bold]  (= starting + realized + unrealized mtm)",
    ]
    if last:
        lines.append(f"Last closed: {last[2]} {last[1]} pnl={last[0]}")
    lines.append(open_line)
    lines.append(f"DB: {p}")
    return Panel(
        Text.from_markup("\n".join(lines)),
        title="SeanV3 paper ledger (testing)",
        border_style="cyan",
    )


def _format_iso_utc_short(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        s = str(iso).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, TypeError):
        return str(iso)[:22] + ("…" if len(str(iso)) > 22 else "")


def _truncate_mid(s: str | None, n: int = 32) -> str:
    if not s:
        return "—"
    t = str(s).strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def _exit_reason_from_meta(meta_json: str | None) -> str:
    if not meta_json:
        return "—"
    try:
        o = json.loads(meta_json)
        if isinstance(o, dict):
            r = o.get("exit_reason") or o.get("exitReason")
            if r:
                return str(r)[:24]
    except json.JSONDecodeError:
        pass
    return "—"


def _default_execution_ledger_path(repo_root: Path) -> Path:
    raw = (os.environ.get("BLACKBOX_EXECUTION_LEDGER_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root / "data" / "sqlite" / "execution_ledger.db").resolve()


def _parse_ts_sort(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        s = str(iso).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


def _side_norm(s: str | None) -> str:
    return str(s or "").strip().lower()


def _price_drift_ok(a: object | None, b: object | None, rel: float = _PARITY_PRICE_REL_TOL) -> bool:
    try:
        fa = float(a)  # type: ignore[arg-type]
        fb = float(b)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True
    if not math.isfinite(fa) or not math.isfinite(fb):
        return True
    if fa <= 0 or fb <= 0:
        return abs(fa - fb) < 1e-9
    return abs(fa - fb) / max(fa, fb) <= rel


def _fetch_bb_baseline_by_mid(ledger_path: Path, max_distinct: int) -> dict[str, dict[str, Any]]:
    if not ledger_path.is_file():
        return {}
    try:
        conn = sqlite3.connect(str(ledger_path))
    except sqlite3.Error:
        return {}
    try:
        cur = conn.execute(
            """
            SELECT market_event_id, side, entry_time, entry_price, size, trade_id, exit_time, created_at_utc
            FROM execution_trades
            WHERE lane = ? AND strategy_id = ?
            ORDER BY created_at_utc DESC
            """,
            (_BB_LANE, _BB_STRATEGY),
        )
        out: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            mid = str(row[0] or "").strip()
            if not mid or mid in out:
                continue
            out[mid] = {
                "side": row[1],
                "entry_time": row[2],
                "entry_price": row[3],
                "size": row[4],
                "trade_id": row[5],
                "exit_time": row[6],
                "created_at_utc": row[7],
            }
            if len(out) >= max_distinct:
                break
        return out
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def _fetch_sean_maps_for_parity(sean_db: Path, max_distinct: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    """Closed trades (latest id per entry_market_event_id) + optional open position row."""
    if not sean_db.is_file():
        return {}, None
    closed: dict[str, dict[str, Any]] = {}
    open_row: dict[str, Any] | None = None
    pos: tuple[Any, ...] | None = None
    try:
        conn = sqlite3.connect(str(sean_db))
        try:
            rows = conn.execute(
                """
                SELECT entry_market_event_id, side, entry_time_utc, entry_price, size_notional_sol, id, exit_time_utc
                FROM sean_paper_trades
                ORDER BY id DESC
                """
            ).fetchall()
            for r in rows:
                mid = str(r[0] or "").strip()
                if not mid or mid in closed:
                    continue
                closed[mid] = {
                    "kind": "closed",
                    "side": r[1],
                    "entry_time": r[2],
                    "entry_price": r[3],
                    "size": r[4],
                    "sean_id": r[5],
                    "exit_time": r[6],
                }
                if len(closed) >= max_distinct * 2:
                    break
            pos = conn.execute(
                "SELECT side, entry_market_event_id, opened_at_utc, entry_price, size_notional_sol "
                "FROM sean_paper_position WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}, None

    if pos and _side_norm(pos[0]) not in ("", "flat") and str(pos[1] or "").strip():
        omid = str(pos[1]).strip()
        open_row = {
            "kind": "open",
            "side": pos[0],
            "entry_time": pos[2],
            "entry_price": pos[3],
            "size": pos[4],
            "entry_market_event_id": omid,
        }
        # Open position is the live truth for this bar; overlay same mid if present.
        closed[omid] = open_row

    return closed, open_row


def _fmt_parity_side_cell(rec: dict[str, Any] | None) -> str:
    if not rec:
        return "[dim]—[/dim]"
    side = _side_norm(rec.get("side"))
    ep = rec.get("entry_price")
    et = rec.get("entry_time")
    kind = rec.get("kind")
    try:
        px = f"{float(ep):.4f}" if ep is not None else "?"
    except (TypeError, ValueError):
        px = "?"
    tshort = _format_iso_utc_short(str(et) if et else None)
    tag = " [dim]open[/dim]" if kind == "open" else ""
    return f"{side or '?'} @ {px} · {tshort}{tag}"


def _parity_match_text(sean: dict[str, Any] | None, bb: dict[str, Any] | None) -> Text:
    if sean and bb:
        ss = _side_norm(sean.get("side"))
        bs = _side_norm(bb.get("side"))
        if ss != bs:
            return Text("SIDE mismatch", style="bold red")
        if not _price_drift_ok(sean.get("entry_price"), bb.get("entry_price")):
            return Text("MATCH (entry px drift)", style="bold yellow")
        return Text("MATCH", style="bold green")
    if sean and not bb:
        return Text("Sean only — no BB row", style="bold red")
    if bb and not sean:
        return Text("BlackBox only — no Sean row", style="bold red")
    return Text("—", style="dim")


def _parity_panel(repo_root: Path) -> Panel:
    """
    Side-by-side parity: same market_event_id should show a trade on Sean and baseline BlackBox.
    Rows = union of recent mids (sorted by latest entry time).
    """
    raw_lim = (os.environ.get("SEANV3_TUI_PARITY_ROWS") or "18").strip()
    try:
        max_rows = max(3, min(40, int(raw_lim)))
    except ValueError:
        max_rows = 18
    max_fetch = max(max_rows * 3, 48)

    sean_db = _default_sean_sqlite(repo_root)
    ledger = _default_execution_ledger_path(repo_root)

    sean_map, _open = _fetch_sean_maps_for_parity(sean_db, max_fetch)
    bb_map = _fetch_bb_baseline_by_mid(ledger, max_fetch)

    if not sean_db.is_file() and not ledger.is_file():
        return Panel(
            Text("[dim]Parity: no Sean DB and no execution ledger — set paths / run stacks.[/dim]"),
            title="Parity (Sean V3 vs BlackBox baseline)",
            border_style="dim",
        )

    all_mids: set[str] = set(sean_map.keys()) | set(bb_map.keys())
    if not all_mids:
        return Panel(
            Text(
                "[dim]No trades yet — parity rows appear when sean_paper_trades or "
                "execution_trades (baseline) have market_event_id values.[/dim]"
            ),
            title="Parity (Sean V3 vs BlackBox baseline)",
            border_style="dim",
        )

    def sort_key(mid: str) -> float:
        s = sean_map.get(mid)
        b = bb_map.get(mid)
        ts = 0.0
        if s:
            ts = max(ts, _parse_ts_sort(str(s.get("entry_time") or "")))
        if b:
            ts = max(ts, _parse_ts_sort(str(b.get("entry_time") or b.get("created_at_utc") or "")))
        return ts

    ordered = sorted(all_mids, key=sort_key, reverse=True)[:max_rows]

    tbl = Table(
        box=box.ROUNDED,
        expand=True,
        show_header=True,
        header_style="bold",
        title="[bold]One bar = one decision key (market_event_id)[/bold]",
        caption=(
            f"[dim]Sean: {sean_db.name} · BlackBox ledger: {ledger.name} · "
            f"baseline lane/strategy · entry px tol ±{_PARITY_PRICE_REL_TOL * 100:.1f}%[/dim]"
        ),
    )
    tbl.add_column("market_event_id", overflow="ellipsis", no_wrap=False)
    tbl.add_column("Sean V3", overflow="ellipsis", no_wrap=False)
    tbl.add_column("BlackBox (baseline)", overflow="ellipsis", no_wrap=False)
    tbl.add_column("Parity", overflow="ellipsis", no_wrap=False)

    for mid in ordered:
        s = sean_map.get(mid)
        b = bb_map.get(mid)
        sm = _fmt_parity_side_cell(s)
        bm = _fmt_parity_side_cell(b) if b else "[dim]—[/dim]"
        pm = _parity_match_text(s, b)
        tbl.add_row(_truncate_mid(mid, 44), Text.from_markup(sm), Text.from_markup(bm), pm)

    return Panel(
        tbl,
        title="Parity (Sean V3 vs BlackBox baseline)",
        subtitle="[dim]Green MATCH = same bar + same side; red = missing row or side mismatch[/dim]",
        border_style="magenta",
    )


def _recent_closed_trades_panel(repo_root: Path) -> Panel:
    """One row per closed trade from sean_paper_trades (baseline-style accounting)."""
    p = _default_sean_sqlite(repo_root)
    if not p.is_file():
        return Panel(
            Text("[dim]No SQLite — run SeanV3 container to populate capture/sean_parity.db[/dim]"),
            title="Recent paper trades (closed)",
            border_style="dim",
        )
    raw_lim = (os.environ.get("SEANV3_TUI_TRADE_ROWS") or "20").strip()
    try:
        limit = max(1, min(50, int(raw_lim)))
    except ValueError:
        limit = 20
    sym = (os.environ.get("SEANV3_CANONICAL_SYMBOL") or os.environ.get("CANONICAL_SYMBOL") or "SOL-PERP").strip() or "SOL-PERP"
    try:
        conn = sqlite3.connect(str(p))
        try:
            rows = conn.execute(
                """
                SELECT id, engine_id, side, entry_time_utc, exit_time_utc,
                       entry_price, exit_price, size_notional_sol, gross_pnl_usd,
                       result_class, entry_market_event_id, metadata_json
                FROM sean_paper_trades
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return Panel(Text(str(e), style="red"), title="Recent paper trades (closed)", border_style="red")

    if not rows:
        return Panel(
            Text("[dim]No closed trades yet — engine opens/closes per Jupiter_3 + lifecycle.[/dim]"),
            title="Recent paper trades (closed)",
            border_style="dim",
        )

    tbl = Table(
        box=box.ROUNDED,
        expand=True,
        show_header=True,
        header_style="bold",
        title=f"[bold]Last {len(rows)} closed trade(s) — paper[/bold]",
        caption="[dim]trade_id = sean_<rowid>; compare timing with BlackBox via market_event_id / UTC[/dim]",
    )
    for h in (
        "trade_id",
        "exit (UTC)",
        "entry (UTC)",
        "sym",
        "side",
        "entry px",
        "exit px",
        "size",
        "PnL USD",
        "result",
        "exit detail",
        "market_event_id",
    ):
        tbl.add_column(h, overflow="ellipsis", no_wrap=False)

    for r in rows:
        (
            tid,
            _engine_id,
            side,
            et,
            xt,
            epx,
            xpx,
            sz,
            gross,
            rc,
            emid,
            meta,
        ) = r
        trade_id = f"sean_{tid}"
        g = float(gross)
        pnl_cell: Text | str
        if g > 1e-9:
            pnl_cell = Text(f"{g:+.4f}", style="bold green")
        elif g < -1e-9:
            pnl_cell = Text(f"{g:+.4f}", style="bold red")
        else:
            pnl_cell = Text(f"{g:+.4f}", style="dim")

        tbl.add_row(
            trade_id,
            _format_iso_utc_short(xt),
            _format_iso_utc_short(et),
            sym,
            str(side),
            f"{float(epx):.4f}",
            f"{float(xpx):.4f}",
            f"{float(sz):.4f}",
            pnl_cell,
            str(rc),
            _exit_reason_from_meta(meta),
            _truncate_mid(emid, 40),
        )

    return Panel(
        tbl,
        title="Trade window (ledger rows)",
        subtitle="[dim]SeanV3 sean_paper_trades · mode=paper[/dim]",
        border_style="blue",
    )


def _policy_panel(
    policy: dict[str, Any],
    *,
    repo_root: Path,
    effective_db: str | None,
    entry_resolved: Path | None,
) -> Panel:
    pid = policy.get("id", "?")
    label = policy.get("label", pid)
    kind = policy.get("kind", "builtin")
    ds = policy.get("dataset") if isinstance(policy.get("dataset"), dict) else {}
    mode = (ds.get("mode") or "?") if ds else "env"
    db_line = effective_db or "[dim](none — tick check skipped or optional)[/dim]"
    if effective_db and Path(effective_db).is_file():
        db_line = f"[green]{effective_db}[/green]"
    elif effective_db:
        db_line = f"[yellow]{effective_db}[/yellow] [dim](file not created yet)[/dim]"

    ent_line = "[dim]—[/dim]"
    if entry_resolved is not None:
        exists = entry_resolved.is_file()
        ent_line = (
            f"[green]{entry_resolved}[/green]" if exists else f"[yellow]{entry_resolved}[/yellow] [dim](missing)[/dim]"
        )
        ent_line += "\n[dim]Run separately: `node " + str(entry_resolved) + "` (TUI does not execute strategies.)[/dim]"

    body = "\n".join(
        [
            f"[bold]{label}[/bold]  [dim]({pid})[/dim]  kind={kind}  dataset_mode={mode}",
            f"Effective SQLite for tick check: {db_line}",
            f"Strategy entry: {ent_line}",
        ]
    )
    return Panel(
        Text.from_markup(body),
        title="[bold]Active policy[/bold] (registry — not a GUI dropdown; use --menu)",
        border_style="cyan",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Preflight + Pyth operator TUI with policy registry.")
    p.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Path to policy_registry.json (default: beside this script or SEANV3_POLICY_REGISTRY)",
    )
    p.add_argument("--policy", type=str, default=None, help="Policy id from registry")
    p.add_argument("--list-policies", action="store_true", help="Print policy ids and exit")
    p.add_argument("--menu", action="store_true", help="Interactive policy picker before the TUI")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    args = _parse_args(argv)
    repo_root = _repo_root()
    reg_path = args.registry.resolve() if args.registry else _default_registry_path()

    try:
        reg = load_policy_registry(reg_path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Failed to load policy registry {reg_path}: {e}", file=sys.stderr)
        sys.exit(1)

    policies: list[dict[str, Any]] = [x for x in reg.get("policies", []) if isinstance(x, dict) and x.get("id")]

    if args.list_policies:
        for pol in policies:
            print(f"{pol['id']}\t{pol.get('label', '')}")
        return

    env_policy = (
        os.environ.get("SEANV3_ACTIVE_POLICY_ID") or os.environ.get("BLACKBOX_ACTIVE_POLICY_ID") or ""
    ).strip()
    want = (args.policy or env_policy or "").strip()
    if not want and policies:
        want = str(policies[0]["id"])

    current = next((p for p in policies if str(p["id"]) == want), None)
    if current is None:
        print(f"Unknown policy id {want!r}. Use --list-policies.", file=sys.stderr)
        sys.exit(1)

    if args.menu:
        picked = pick_policy_interactive(policies, current["id"])
        if picked is None:
            print("Cancelled.", file=sys.stderr)
            sys.exit(1)
        nxt = next((p for p in policies if str(p["id"]) == picked), None)
        if nxt is None:
            sys.exit(1)
        current = nxt

    effective_db = resolve_effective_market_data_path(repo_root, current)
    entry_path = resolve_entry_path(repo_root, current)

    console = Console()
    hermes_bucket: dict[str, Any] = {}
    refresh = float(
        os.environ.get("SEANV3_TUI_REFRESH_SEC") or os.environ.get("BLACKBOX_TUI_REFRESH_SEC") or "2.0"
    )

    def render() -> Group:
        checks, _ = _run_checks(hermes_bucket, market_data_path=effective_db)
        parsed = hermes_bucket.get("parsed") if isinstance(hermes_bucket.get("parsed"), list) else None
        now_ts = time.time()
        q_oracle = _parse_pyth_price(parsed) if parsed else None
        mark = float(q_oracle["price"]) if q_oracle and q_oracle.get("price") is not None else None
        pol = _policy_panel(current, repo_root=repo_root, effective_db=effective_db, entry_resolved=entry_path)
        sean_p = _sean_ledger_panel(repo_root, mark_usd=mark)
        trades_tbl = _recent_closed_trades_panel(repo_root)
        ht = _header_table(checks)
        strict_ok = all(c.ok for c in checks)
        banner = (
            "[bold green]ALL ACTIVE — checks passing[/bold green]"
            if strict_ok
            else "[bold red]DEGRADED — fix failing checks before relying on runtime[/bold red]"
        )
        top = Panel(
            ht,
            title=f"[bold]{banner}[/bold]",
            subtitle="Preflight strip (Binance + Hermes + optional DB/Docker)",
            border_style="green" if strict_ok else "red",
        )
        body = _main_panel(parsed, now_ts)
        parity = _parity_panel(repo_root)
        return Group(pol, sean_p, parity, trades_tbl, top, body)

    console.print(
        "[dim]SeanV3 operator TUI — preflight + policy + Pyth  "
        "(Ctrl+C to exit | --menu | SEANV3_ACTIVE_POLICY_ID)[/dim]\n"
    )
    with Live(render(), console=console, refresh_per_second=min(1.0 / max(refresh, 0.25), 30.0)) as live:
        try:
            while True:
                time.sleep(refresh)
                live.update(render())
        except KeyboardInterrupt:
            console.print("\n[dim]Exited.[/dim]")


if __name__ == "__main__":
    main()
