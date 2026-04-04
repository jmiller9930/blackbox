"""SQLite execution ledger — parallel trades with full identity (strategy_id, lane, mode, market_event_id)."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from modules.anna_training.store import utc_now_iso

RESERVED_STRATEGY_BASELINE = "baseline"
VALID_LANES = frozenset({"baseline", "anna"})
VALID_MODES = frozenset({"live", "paper", "paper_stub"})
SCHEMA_VERSION = "execution_trade_v1"
# Float tolerance when comparing caller-supplied pnl_usd to derived (economic modes only).
PNL_EPSILON = 1e-6


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_execution_ledger_path() -> Path:
    env = os.environ.get("BLACKBOX_EXECUTION_LEDGER_PATH")
    if env:
        return Path(env).expanduser()
    return _repo_root() / "data" / "sqlite" / "execution_ledger.db"


def is_economic_mode(mode: str | None) -> bool:
    """``live`` / ``paper`` rows carry verifiable P&amp;L; ``paper_stub`` does not (synthetic / excluded)."""
    return (mode or "").strip().lower() in ("live", "paper")


def compute_pnl_usd(*, entry_price: float, exit_price: float, size: float, side: str) -> float:
    """
    Index-style P&amp;L in USD: long ``(exit-entry)*size``, short ``(entry-exit)*size``.
    """
    sd = (side or "").strip().lower()
    if sd not in ("long", "short"):
        raise ValueError("side must be 'long' or 'short'")
    ep = float(entry_price)
    xp = float(exit_price)
    sz = float(size)
    if sz <= 0:
        raise ValueError("size must be positive")
    if sd == "long":
        return (xp - ep) * sz
    return (ep - xp) * sz


def _pnl_close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return math.isfinite(a) and math.isfinite(b) and abs(float(a) - float(b)) <= PNL_EPSILON


def _migrate_add_trace_id_column(conn: sqlite3.Connection) -> None:
    """Add ``trace_id`` to ``execution_trades`` (links to ``decision_traces``)."""
    cur = conn.execute("PRAGMA table_info(execution_trades)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "trace_id" in cols:
        return
    conn.execute("ALTER TABLE execution_trades ADD COLUMN trace_id TEXT")


def _migrate_execution_trades_paper_stub_mode(conn: sqlite3.Connection) -> None:
    """Allow ``paper_stub`` in ``mode`` CHECK (existing DBs created before that value)."""
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='execution_trades'"
    )
    row = cur.fetchone()
    sql = (row[0] or "") if row else ""
    if "paper_stub" in sql:
        return
    conn.executescript(
        """
        BEGIN;
        DROP INDEX IF EXISTS idx_execution_trades_market_event;
        DROP INDEX IF EXISTS idx_execution_trades_strategy;
        DROP INDEX IF EXISTS idx_execution_trades_lane_mode;
        DROP INDEX IF EXISTS idx_execution_trades_trace_id;
        CREATE TABLE execution_trades__new (
          trade_id TEXT PRIMARY KEY,
          strategy_id TEXT NOT NULL,
          lane TEXT NOT NULL CHECK (lane IN ('baseline', 'anna')),
          mode TEXT NOT NULL CHECK (mode IN ('live', 'paper', 'paper_stub')),
          market_event_id TEXT NOT NULL,
          symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          side TEXT,
          entry_time TEXT,
          entry_price REAL,
          size REAL,
          exit_time TEXT,
          exit_price REAL,
          exit_reason TEXT,
          pnl_usd REAL,
          context_snapshot_json TEXT,
          notes TEXT,
          trace_id TEXT,
          schema_version TEXT NOT NULL DEFAULT 'execution_trade_v1',
          created_at_utc TEXT NOT NULL
        );
        INSERT INTO execution_trades__new (
          trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
          side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
          pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
        )
        SELECT
          trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
          side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
          pnl_usd, context_snapshot_json, notes,
          trace_id,
          schema_version, created_at_utc
        FROM execution_trades;
        DROP TABLE execution_trades;
        ALTER TABLE execution_trades__new RENAME TO execution_trades;
        CREATE INDEX IF NOT EXISTS idx_execution_trades_market_event
          ON execution_trades (market_event_id);
        CREATE INDEX IF NOT EXISTS idx_execution_trades_strategy
          ON execution_trades (strategy_id, created_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_execution_trades_lane_mode
          ON execution_trades (lane, mode, created_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_execution_trades_trace_id
          ON execution_trades (trace_id);
        COMMIT;
        """
    )


def _migrate_decision_traces_table(conn: sqlite3.Connection, root: Path) -> None:
    sql = root / "data" / "sqlite" / "schema_decision_trace.sql"
    if not sql.is_file():
        raise FileNotFoundError(sql)
    conn.executescript(sql.read_text(encoding="utf-8"))


def _migrate_strategy_registry_qel_columns(conn: sqlite3.Connection) -> None:
    """Quantitative Evaluation Layer — lifecycle columns on strategy_registry."""
    cur = conn.execute("PRAGMA table_info(strategy_registry)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "lifecycle_state" not in cols:
        conn.execute(
            "ALTER TABLE strategy_registry ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'experiment'"
        )
    if "parent_strategy_id" not in cols:
        conn.execute("ALTER TABLE strategy_registry ADD COLUMN parent_strategy_id TEXT")
    if "qel_updated_at_utc" not in cols:
        conn.execute("ALTER TABLE strategy_registry ADD COLUMN qel_updated_at_utc TEXT")


def _migrate_qel_schema(conn: sqlite3.Connection, root: Path) -> None:
    """QEL tables (survival tests, evaluation runs, lifecycle audit)."""
    qel = root / "data" / "sqlite" / "schema_qel.sql"
    if qel.is_file():
        conn.executescript(qel.read_text(encoding="utf-8"))
    _migrate_strategy_registry_qel_columns(conn)


def _strict_trade_identity() -> bool:
    return (os.environ.get("ANNA_STRICT_TRADE_IDENTITY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def connect_ledger(db_path: Path | None = None) -> sqlite3.Connection:
    p = db_path or default_execution_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(p)


def ensure_execution_ledger_schema(conn: sqlite3.Connection, root: Path | None = None) -> None:
    root = root or _repo_root()
    sql = root / "data" / "sqlite" / "schema_execution_ledger.sql"
    if not sql.is_file():
        raise FileNotFoundError(sql)
    conn.executescript(sql.read_text(encoding="utf-8"))
    conn.commit()
    _migrate_add_trace_id_column(conn)
    _migrate_execution_trades_paper_stub_mode(conn)
    _migrate_decision_traces_table(conn, root)
    _migrate_qel_schema(conn, root)
    conn.commit()


def _validate_lane_strategy(lane: str, strategy_id: str) -> None:
    lane = (lane or "").strip().lower()
    sid = (strategy_id or "").strip()
    if lane not in VALID_LANES:
        raise ValueError(f"lane must be one of {sorted(VALID_LANES)}")
    if lane == "baseline" and sid != RESERVED_STRATEGY_BASELINE:
        raise ValueError("lane=baseline requires strategy_id=baseline")
    if lane == "anna" and sid == RESERVED_STRATEGY_BASELINE:
        raise ValueError("strategy_id baseline is reserved for lane=baseline only")


def _resolve_pnl_and_validate(
    *,
    mode: str,
    lane: str,
    side: str | None,
    entry_price: float | None,
    exit_price: float | None,
    size: float | None,
    pnl_usd: float | None,
    context_snapshot: dict[str, Any] | None,
) -> float | None:
    """Returns ``pnl_usd`` to persist (never authoritative from a mismatched caller hint)."""
    if mode == "paper_stub":
        if lane != "anna":
            raise ValueError("paper_stub is only valid for lane=anna")
        if pnl_usd is not None:
            raise ValueError(
                "paper_stub must not set pnl_usd — store synthetic outcome in context_snapshot only"
            )
        ctx = dict(context_snapshot or {})
        if not (ctx.get("synthetic") is True or ctx.get("paper_stub") is True):
            raise ValueError(
                "paper_stub requires context_snapshot with synthetic=True or paper_stub=True"
            )
        return None

    # Economic modes: derive from trade facts; optional caller pnl_usd must match or raise.
    side_n = (side or "").strip().lower()
    if side_n not in ("long", "short"):
        raise ValueError("side must be 'long' or 'short' for live/paper trades")
    if entry_price is None or exit_price is None or size is None:
        raise ValueError("entry_price, exit_price, and size are required for live/paper trades")
    computed = compute_pnl_usd(
        entry_price=float(entry_price),
        exit_price=float(exit_price),
        size=float(size),
        side=side_n,
    )
    if pnl_usd is not None and not _pnl_close(float(pnl_usd), computed):
        raise ValueError(
            f"pnl_usd mismatch: given {pnl_usd!r} but derived from trade facts is {computed!r}"
        )
    return computed


def append_execution_trade(
    *,
    strategy_id: str,
    lane: str,
    mode: str,
    market_event_id: str,
    symbol: str,
    timeframe: str,
    trade_id: str | None = None,
    trace_id: str | None = None,
    side: str | None = None,
    entry_time: str | None = None,
    entry_price: float | None = None,
    size: float | None = None,
    exit_time: str | None = None,
    exit_price: float | None = None,
    exit_reason: str | None = None,
    pnl_usd: float | None = None,
    context_snapshot: dict[str, Any] | None = None,
    notes: str | None = None,
    db_path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Persist one trade row. **PnL is never taken as authoritative** for ``live``/``paper``:
    it is recomputed from ``entry_price``, ``exit_price``, ``size``, and ``side``.
    If a ``pnl_usd`` hint is provided and does not match the derivation, raises ``ValueError``.

    ``paper_stub`` (``lane=anna`` only): ``pnl_usd`` is stored as **NULL**; synthetic economics
    live only in ``context_snapshot`` (must include ``synthetic`` or ``paper_stub`` flag).
    """
    _validate_lane_strategy(lane, strategy_id)
    mode = (mode or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}")
    if lane == "baseline" and mode not in ("live", "paper"):
        raise ValueError("baseline lane requires mode live or paper")
    if lane == "anna" and mode == "live":
        raise ValueError("Anna lane is paper-only until policy changes")
    if lane == "anna" and mode not in ("paper", "paper_stub"):
        raise ValueError("Anna lane requires mode paper or paper_stub")
    if mode == "paper_stub" and lane != "anna":
        raise ValueError("paper_stub is only valid for lane=anna")

    mid = (market_event_id or "").strip()
    if not mid:
        raise ValueError("market_event_id is required")
    sym = (symbol or "").strip()
    tf = (timeframe or "").strip()
    if _strict_trade_identity():
        for name, val in (
            ("symbol", sym),
            ("timeframe", tf),
            ("entry_time", entry_time),
            ("exit_time", exit_time),
            ("exit_reason", exit_reason),
        ):
            if not val:
                raise ValueError(f"ANNA_STRICT_TRADE_IDENTITY: {name} required")
        if mode != "paper_stub":
            if entry_price is None or exit_price is None or size is None or not (side or "").strip():
                raise ValueError(
                    "ANNA_STRICT_TRADE_IDENTITY: entry_price, exit_price, size, side required for live/paper"
                )

    final_pnl = _resolve_pnl_and_validate(
        mode=mode,
        lane=lane,
        side=side,
        entry_price=entry_price,
        exit_price=exit_price,
        size=size,
        pnl_usd=pnl_usd,
        context_snapshot=context_snapshot,
    )

    tid = (trade_id or "").strip() or str(uuid.uuid4())
    ctx_json = json.dumps(context_snapshot, ensure_ascii=False) if context_snapshot else None

    created = utc_now_iso()
    trid = (trace_id or "").strip() or None

    row = {
        "trade_id": tid,
        "strategy_id": strategy_id.strip(),
        "lane": lane.strip().lower(),
        "mode": mode,
        "market_event_id": mid,
        "symbol": sym,
        "timeframe": tf,
        "side": (side or "").strip().lower() or None,
        "entry_time": entry_time,
        "entry_price": entry_price,
        "size": size,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": (exit_reason or "").strip() or None,
        "pnl_usd": final_pnl,
        "context_snapshot_json": ctx_json,
        "notes": (notes or "").strip() or None,
        "trace_id": trid,
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": created,
    }

    own_conn = conn is None
    conn = conn or connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        conn.execute(
            """
            INSERT INTO execution_trades (
              trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
              side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
              pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["trade_id"],
                row["strategy_id"],
                row["lane"],
                row["mode"],
                row["market_event_id"],
                row["symbol"],
                row["timeframe"],
                row["side"],
                row["entry_time"],
                row["entry_price"],
                row["size"],
                row["exit_time"],
                row["exit_price"],
                row["exit_reason"],
                row["pnl_usd"],
                row["context_snapshot_json"],
                row["notes"],
                row["trace_id"],
                row["schema_version"],
                row["created_at_utc"],
            ),
        )
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()
    return row


def scan_execution_ledger_pnl_integrity(
    *,
    db_path: Path | None = None,
    limit_examples: int = 20,
) -> dict[str, Any]:
    """
    Scan ``execution_trades`` for rows where ``pnl_usd`` is not consistent with stored trade facts.

    - ``live`` / ``paper``: must have ``entry_price``, ``exit_price``, ``size``, ``side`` and
      ``pnl_usd`` equal to :func:`compute_pnl_usd`.
    - ``paper_stub``: ``pnl_usd`` must be **NULL** (synthetic economics only in JSON); non-null
      must match derivation if facts are complete.

    Returns counts plus example violation dicts.
    """
    conn = connect_ledger(db_path)
    violations: list[dict[str, Any]] = []
    economic_ok = 0
    stub_ok = 0
    total_rows = 0
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
            FROM execution_trades
            ORDER BY created_at_utc ASC, trade_id ASC
            """
        )
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        total_rows = len(rows)
        for r in rows:
            row = dict(zip(cols, r))
            mode = (row.get("mode") or "").strip().lower()
            if mode == "paper_stub":
                stored = row.get("pnl_usd")
                if stored is None:
                    stub_ok += 1
                    continue
                ep, xp, sz, sd = row.get("entry_price"), row.get("exit_price"), row.get("size"), row.get("side")
                if ep is None or xp is None or sz is None or not (sd or "").strip():
                    violations.append(
                        {
                            "trade_id": row.get("trade_id"),
                            "reason": "paper_stub_non_null_pnl_incomplete_facts",
                            "stored_pnl_usd": stored,
                        }
                    )
                    continue
                try:
                    exp = compute_pnl_usd(
                        entry_price=float(ep),
                        exit_price=float(xp),
                        size=float(sz),
                        side=str(sd),
                    )
                except ValueError as e:
                    violations.append(
                        {
                            "trade_id": row.get("trade_id"),
                            "reason": f"paper_stub_derivation_error:{e}",
                            "stored_pnl_usd": stored,
                        }
                    )
                    continue
                if not _pnl_close(float(stored), exp):
                    violations.append(
                        {
                            "trade_id": row.get("trade_id"),
                            "reason": "paper_stub_pnl_mismatch",
                            "stored_pnl_usd": stored,
                            "expected_pnl_usd": exp,
                        }
                    )
                else:
                    stub_ok += 1
                continue

            if mode not in ("live", "paper"):
                continue
            ep, xp, sz, sd = row.get("entry_price"), row.get("exit_price"), row.get("size"), row.get("side")
            stored = row.get("pnl_usd")
            if ep is None or xp is None or sz is None or not (sd or "").strip():
                violations.append(
                    {
                        "trade_id": row.get("trade_id"),
                        "reason": "economic_trade_missing_facts",
                        "mode": mode,
                        "entry_price": ep,
                        "exit_price": xp,
                        "size": sz,
                        "side": sd,
                        "stored_pnl_usd": stored,
                    }
                )
                continue
            try:
                exp = compute_pnl_usd(
                    entry_price=float(ep),
                    exit_price=float(xp),
                    size=float(sz),
                    side=str(sd),
                )
            except ValueError as e:
                violations.append(
                    {
                        "trade_id": row.get("trade_id"),
                        "reason": f"derivation_error:{e}",
                        "mode": mode,
                        "stored_pnl_usd": stored,
                    }
                )
                continue
            if stored is None or not _pnl_close(float(stored), exp):
                violations.append(
                    {
                        "trade_id": row.get("trade_id"),
                        "reason": "economic_pnl_mismatch_or_null",
                        "mode": mode,
                        "stored_pnl_usd": stored,
                        "expected_pnl_usd": exp,
                    }
                )
                continue
            economic_ok += 1
    finally:
        conn.close()

    return {
        "ledger_path": str(db_path or default_execution_ledger_path()),
        "total_rows": total_rows,
        "violation_count": len(violations),
        "economic_ok_count": economic_ok,
        "paper_stub_ok_count": stub_ok,
        "examples": violations[: max(0, int(limit_examples))],
    }


def query_trades_by_market_event_id(
    market_event_id: str,
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
            FROM execution_trades
            WHERE market_event_id = ?
            ORDER BY created_at_utc ASC, trade_id ASC
            """,
            (market_event_id.strip(),),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def query_trades_by_strategy(
    strategy_id: str,
    *,
    limit: int = 500,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
            FROM execution_trades
            WHERE strategy_id = ?
            ORDER BY created_at_utc DESC, trade_id DESC
            LIMIT ?
            """,
            (strategy_id.strip(), int(limit)),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def sync_strategy_registry_from_catalog(conn: sqlite3.Connection) -> int:
    """Upsert rows from ``strategy_catalog`` + reserved baseline. Returns count written."""
    from modules.anna_training.strategy_catalog import load_strategy_catalog

    cur = conn.execute("PRAGMA table_info(strategy_registry)")
    has_lifecycle = any(str(r[1]) == "lifecycle_state" for r in cur.fetchall())
    now = utc_now_iso()
    n = 0
    rows = list(load_strategy_catalog())
    rows.append(
        {
            "id": RESERVED_STRATEGY_BASELINE,
            "title": "Sean baseline (reserved)",
            "description": "Baseline execution mechanics; lane=baseline only.",
        }
    )
    for s in rows:
        sid = str(s.get("id") or "").strip()
        if not sid:
            continue
        src = "catalog" if sid != RESERVED_STRATEGY_BASELINE else "reserved"
        title = str(s.get("title") or "")[:500]
        desc = str(s.get("description") or "")[:2000]
        if has_lifecycle:
            conn.execute(
                """
                INSERT INTO strategy_registry (
                  strategy_id, title, description, registered_at_utc, source,
                  lifecycle_state, parent_strategy_id, qel_updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, 'experiment', NULL, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                  title = excluded.title,
                  description = excluded.description
                """,
                (sid, title, desc, now, src, now),
            )
        else:
            conn.execute(
                """
                INSERT INTO strategy_registry (strategy_id, title, description, registered_at_utc, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                  title = excluded.title,
                  description = excluded.description
                """,
                (sid, title, desc, now, src),
            )
        n += 1
    conn.commit()
    return n
