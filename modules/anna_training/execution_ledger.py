"""SQLite execution ledger — parallel trades with full identity (strategy_id, lane, mode, market_event_id)."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from modules.anna_training.store import utc_now_iso

RESERVED_STRATEGY_BASELINE = "baseline"
# Baseline Jupiter policy slot (operator dropdown) — persisted in ``baseline_operator_kv``.
BASELINE_POLICY_SLOT_JUP_V2 = "jup_v2"
BASELINE_POLICY_SLOT_JUP_V3 = "jup_v3"
BASELINE_POLICY_SLOT_JUP_V4 = "jup_v4"
# Hardened selector: only these slots map to evaluators and signal_mode. Adding a new policy
# requires a new slot constant, bridge branch, and evaluator wiring — not a silent string.
VALID_BASELINE_JUPITER_POLICY_SLOTS: frozenset[str] = frozenset(
    {BASELINE_POLICY_SLOT_JUP_V2, BASELINE_POLICY_SLOT_JUP_V3, BASELINE_POLICY_SLOT_JUP_V4}
)
BASELINE_OPERATOR_KV_JUPITER_POLICY_SLOT = "baseline_jupiter_policy_slot"
# policy_activation_log.slot for baseline Jupiter policy family (one active row for this slot name).
POLICY_ACTIVATION_SLOT_BASELINE_JUPITER = "baseline_jupiter"
# policy_evaluations.signal_mode — one distinct string per engine (historic v1 label = Jupiter_2).
SIGNAL_MODE_JUPITER_2 = "sean_jupiter_v1"
SIGNAL_MODE_JUPITER_3 = "sean_jupiter_v3"
SIGNAL_MODE_JUPITER_4 = "sean_jupiter_v4"
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
    _migrate_decision_traces_learning_proof_columns(conn)


def _migrate_decision_traces_learning_proof_columns(conn: sqlite3.Connection) -> None:
    """MIT learning-proof directive: memory attribution + join keys on decision_traces."""
    cur = conn.execute("PRAGMA table_info(decision_traces)")
    cols = {str(r[1]) for r in cur.fetchall()}
    stmts: list[str] = []
    if "retrieved_memory_ids_json" not in cols:
        stmts.append(
            "ALTER TABLE decision_traces ADD COLUMN retrieved_memory_ids_json "
            "TEXT NOT NULL DEFAULT '[]'"
        )
    if "memory_used" not in cols:
        stmts.append(
            "ALTER TABLE decision_traces ADD COLUMN memory_used INTEGER NOT NULL DEFAULT 0"
        )
    if "decision_summary" not in cols:
        stmts.append("ALTER TABLE decision_traces ADD COLUMN decision_summary TEXT")
    if "baseline_action_json" not in cols:
        stmts.append("ALTER TABLE decision_traces ADD COLUMN baseline_action_json TEXT")
    if "anna_action_json" not in cols:
        stmts.append("ALTER TABLE decision_traces ADD COLUMN anna_action_json TEXT")
    if "memory_ablation_off" not in cols:
        stmts.append(
            "ALTER TABLE decision_traces ADD COLUMN memory_ablation_off INTEGER NOT NULL DEFAULT 0"
        )
    if "learning_proof_schema" not in cols:
        stmts.append(
            "ALTER TABLE decision_traces ADD COLUMN learning_proof_schema TEXT "
            "DEFAULT 'learning_proof_v1'"
        )
    for s in stmts:
        conn.execute(s)


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


def _migrate_strategy_registry_sequential_columns(conn: sqlite3.Connection) -> None:
    """Sequential learning driver — snapshot JSON on strategy_registry."""
    cur = conn.execute("PRAGMA table_info(strategy_registry)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "sequential_learning_snapshot_json" not in cols:
        conn.execute(
            "ALTER TABLE strategy_registry ADD COLUMN sequential_learning_snapshot_json TEXT"
        )


def _migrate_sequential_learning_schema(conn: sqlite3.Connection, root: Path) -> None:
    """Sequential learning SPRT audit table + strategy_registry columns."""
    sl = root / "data" / "sqlite" / "schema_sequential_learning.sql"
    if sl.is_file():
        conn.executescript(sl.read_text(encoding="utf-8"))
    _migrate_strategy_registry_sequential_columns(conn)


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


def _migrate_policy_evaluation_schema(conn: sqlite3.Connection, root: Path) -> None:
    pe = root / "data" / "sqlite" / "schema_policy_evaluation.sql"
    if pe.is_file():
        conn.executescript(pe.read_text(encoding="utf-8"))
    _migrate_policy_evaluation_lineage_columns(conn)


def _migrate_policy_evaluation_lineage_columns(conn: sqlite3.Connection) -> None:
    """DV-ARCH-023-B: policy lineage on policy_evaluations."""
    cur = conn.execute("PRAGMA table_info(policy_evaluations)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "policy_id" not in cols:
        conn.execute("ALTER TABLE policy_evaluations ADD COLUMN policy_id TEXT")
    if "policy_version" not in cols:
        conn.execute("ALTER TABLE policy_evaluations ADD COLUMN policy_version TEXT")
    if "slot" not in cols:
        conn.execute("ALTER TABLE policy_evaluations ADD COLUMN slot TEXT")


def _migrate_policy_activation_schema(conn: sqlite3.Connection, root: Path) -> None:
    """DV-ARCH-023-A: policy_activation_log + execution lineage columns."""
    pa = root / "data" / "sqlite" / "schema_policy_activation.sql"
    if pa.is_file():
        conn.executescript(pa.read_text(encoding="utf-8"))


def _migrate_execution_trades_lineage_columns(conn: sqlite3.Connection) -> None:
    """DV-ARCH-023-B: policy lineage + originating market event on execution_trades."""
    cur = conn.execute("PRAGMA table_info(execution_trades)")
    cols = {str(r[1]) for r in cur.fetchall()}
    if "policy_id" not in cols:
        conn.execute("ALTER TABLE execution_trades ADD COLUMN policy_id TEXT")
    if "policy_version" not in cols:
        conn.execute("ALTER TABLE execution_trades ADD COLUMN policy_version TEXT")
    if "slot" not in cols:
        conn.execute("ALTER TABLE execution_trades ADD COLUMN slot TEXT")
    if "originating_market_event_id" not in cols:
        conn.execute(
            "ALTER TABLE execution_trades ADD COLUMN originating_market_event_id TEXT"
        )


def _migrate_position_events_schema(conn: sqlite3.Connection, root: Path) -> None:
    pe = root / "data" / "sqlite" / "schema_position_events.sql"
    if pe.is_file():
        conn.executescript(pe.read_text(encoding="utf-8"))


def _migrate_baseline_jupiter_open_positions(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='baseline_jupiter_open_positions'"
    )
    if cur.fetchone():
        return
    conn.execute(
        """
        CREATE TABLE baseline_jupiter_open_positions (
          position_key TEXT PRIMARY KEY,
          trade_id TEXT NOT NULL,
          state_json TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL
        )
        """
    )


def _migrate_baseline_operator_kv(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='baseline_operator_kv'"
    )
    if cur.fetchone():
        return
    conn.execute(
        """
        CREATE TABLE baseline_operator_kv (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL
        )
        """
    )


def baseline_jupiter_open_position_key(
    *,
    symbol: str,
    timeframe: str,
    mode: str,
    policy_slot: str | None = None,
) -> str:
    """Baseline open-position key. Prefer ``policy_slot`` (jup_v2 / jup_v3 / jup_v4) so policies do not share state."""
    sym = (symbol or "SOL-PERP").strip() or "SOL-PERP"
    tf = (timeframe or "5m").strip() or "5m"
    m = (mode or "paper").strip().lower() or "paper"
    ps = (policy_slot or "").strip()
    if ps:
        return f"baseline|{sym}|{tf}|{m}|{ps}"
    return f"baseline|{sym}|{tf}|{m}"


def normalize_baseline_jupiter_policy_slot(raw: str | None) -> str | None:
    """Map operator/env strings to **jup_v2** / **jup_v3** / **jup_v4**; unknown → ``None`` (fail closed)."""
    v = (raw or "").strip().lower()
    if not v:
        return None
    if v in (BASELINE_POLICY_SLOT_JUP_V4, "jup_v4", "v4", "jupiter_4"):
        return BASELINE_POLICY_SLOT_JUP_V4
    if v in (BASELINE_POLICY_SLOT_JUP_V3, "jup_v3", "v3", "jupiter_3"):
        return BASELINE_POLICY_SLOT_JUP_V3
    if v in (BASELINE_POLICY_SLOT_JUP_V2, "jup_v2", "v2", "jupiter_2"):
        return BASELINE_POLICY_SLOT_JUP_V2
    return None


def policy_uses_binance_strategy_bars(policy_slot: str | None) -> bool:
    """JUPv3 and JUPv4 read OHLCV from ``binance_strategy_bars_5m``."""
    ps = normalize_baseline_jupiter_policy_slot((policy_slot or "").strip())
    return ps in (BASELINE_POLICY_SLOT_JUP_V3, BASELINE_POLICY_SLOT_JUP_V4)


def _warn_invalid_baseline_policy_slot(source: str, raw: str) -> None:
    print(
        f"execution_ledger: ignoring invalid baseline Jupiter policy slot from {source}: {raw!r} "
        f"(allowed aliases resolve to {sorted(VALID_BASELINE_JUPITER_POLICY_SLOTS)})",
        file=sys.stderr,
        flush=True,
    )


def _legacy_baseline_jupiter_policy_slot_from_kv_env(conn: sqlite3.Connection) -> str:
    """
    Operator / deploy selection from ``baseline_operator_kv`` and env (no activation log).

    Order: ``baseline_operator_kv`` when set and parseable, then env
    ``BASELINE_JUPITER_POLICY_SLOT``, then **jup_v2**.
    """
    try:
        row = conn.execute(
            "SELECT value FROM baseline_operator_kv WHERE key = ?",
            (BASELINE_OPERATOR_KV_JUPITER_POLICY_SLOT,),
        ).fetchone()
        if row and str(row[0]).strip():
            raw = str(row[0]).strip()
            ps = normalize_baseline_jupiter_policy_slot(raw)
            if ps is not None:
                return ps
            _warn_invalid_baseline_policy_slot("baseline_operator_kv", raw)
    except sqlite3.OperationalError:
        pass
    ev_raw = os.environ.get("BASELINE_JUPITER_POLICY_SLOT")
    if ev_raw and str(ev_raw).strip():
        ev = normalize_baseline_jupiter_policy_slot(ev_raw)
        if ev is not None:
            return ev
        _warn_invalid_baseline_policy_slot("BASELINE_JUPITER_POLICY_SLOT", str(ev_raw).strip())
    return BASELINE_POLICY_SLOT_JUP_V2


def get_baseline_jupiter_policy_slot(conn: sqlite3.Connection) -> str:
    """
    Operator-facing baseline Jupiter policy (dashboard / KV): **immediate** selection.

    For **execution** (evaluator + lineage), use
    :func:`resolve_baseline_jupiter_policy_for_execution` so pending activations do not apply
    until the next closed 5m boundary.
    """
    return _legacy_baseline_jupiter_policy_slot_from_kv_env(conn)


def _policy_activation_table_ready(conn: sqlite3.Connection) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='policy_activation_log'"
    )
    return cur.fetchone() is not None


def baseline_jupiter_policy_lineage(policy_slot: str) -> tuple[str, str]:
    """Return ``(policy_id, policy_version)`` (catalog id + policy engine id) for a normalized slot."""
    ps = normalize_baseline_jupiter_policy_slot(policy_slot)
    if ps is None:
        raise ValueError(f"unknown baseline Jupiter policy slot {policy_slot!r}")
    if ps == BASELINE_POLICY_SLOT_JUP_V4:
        from modules.anna_training.jupiter_4_sean_policy import CATALOG_ID, POLICY_ENGINE_ID

        return (CATALOG_ID, POLICY_ENGINE_ID)
    if ps == BASELINE_POLICY_SLOT_JUP_V3:
        from modules.anna_training.jupiter_3_sean_policy import CATALOG_ID, POLICY_ENGINE_ID

        return (CATALOG_ID, POLICY_ENGINE_ID)
    from modules.anna_training.jupiter_2_sean_policy import CATALOG_ID, POLICY_ENGINE_ID

    return (CATALOG_ID, POLICY_ENGINE_ID)


def baseline_slot_from_policy_lineage(policy_id: str | None, policy_version: str | None) -> str | None:
    """Map stored lineage ids back to **jup_v2** / **jup_v3** / **jup_v4**."""
    pid = (policy_id or "").strip()
    if pid == "jupiter_4_sean_perps_v1":
        return BASELINE_POLICY_SLOT_JUP_V4
    if pid == "jupiter_3_sean_perps_v1":
        return BASELINE_POLICY_SLOT_JUP_V3
    if pid == "jupiter_2_sean_perps_v1":
        return BASELINE_POLICY_SLOT_JUP_V2
    pver = (policy_version or "").strip().lower()
    if "jupiter_4" in pver or pver == "jupiter_4":
        return BASELINE_POLICY_SLOT_JUP_V4
    if "jupiter_3" in pver or pver == "jupiter_3":
        return BASELINE_POLICY_SLOT_JUP_V3
    if "jupiter_2" in pver or pver == "jupiter_2":
        return BASELINE_POLICY_SLOT_JUP_V2
    return None


def resolve_baseline_jupiter_policy_for_execution(conn: sqlite3.Connection) -> str:
    """
    Effective baseline Jupiter policy for **evaluation** (respects activation log).

    If ``policy_activation_log`` is empty, matches :func:`get_baseline_jupiter_policy_slot`.
    If there is an **active** row, its lineage wins.
    If there is only **pending**, returns ``previous_baseline_policy_slot`` captured at assignment.
    """
    ensure_execution_ledger_schema(conn)
    if not _policy_activation_table_ready(conn):
        return _legacy_baseline_jupiter_policy_slot_from_kv_env(conn)
    n = conn.execute("SELECT COUNT(*) FROM policy_activation_log").fetchone()
    if not n or int(n[0]) == 0:
        return _legacy_baseline_jupiter_policy_slot_from_kv_env(conn)
    row = conn.execute(
        """
        SELECT policy_id, policy_version FROM policy_activation_log
        WHERE slot = ? AND activation_state = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,),
    ).fetchone()
    if row:
        mapped = baseline_slot_from_policy_lineage(str(row[0] or ""), str(row[1] or ""))
        if mapped:
            return mapped
        return _legacy_baseline_jupiter_policy_slot_from_kv_env(conn)
    prow = conn.execute(
        """
        SELECT previous_baseline_policy_slot FROM policy_activation_log
        WHERE slot = ? AND activation_state = 'pending'
        ORDER BY id ASC
        LIMIT 1
        """,
        (POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,),
    ).fetchone()
    if prow and str(prow[0] or "").strip():
        ps = normalize_baseline_jupiter_policy_slot(str(prow[0]).strip())
        if ps is not None:
            return ps
    return _legacy_baseline_jupiter_policy_slot_from_kv_env(conn)


def pending_baseline_jupiter_target_slot(conn: sqlite3.Connection) -> str | None:
    """If a **pending** activation exists, return its target **jup_v2** / **jup_v3** / **jup_v4**."""
    if not _policy_activation_table_ready(conn):
        return None
    row = conn.execute(
        """
        SELECT policy_id, policy_version FROM policy_activation_log
        WHERE slot = ? AND activation_state = 'pending'
        ORDER BY id ASC
        LIMIT 1
        """,
        (POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,),
    ).fetchone()
    if not row:
        return None
    return baseline_slot_from_policy_lineage(str(row[0] or ""), str(row[1] or ""))


def baseline_jupiter_policy_slot_for_market_data(conn: sqlite3.Connection) -> str:
    """
    Bar feed + operator preview tiles: **pending** target (if any), else execution-effective slot.

    Keeps Binance vs Pyth alignment with the policy the operator queued or that is running.
    """
    ensure_execution_ledger_schema(conn)
    p = pending_baseline_jupiter_target_slot(conn)
    if p:
        return p
    return resolve_baseline_jupiter_policy_for_execution(conn)


def next_pending_activation_effective_on_iso(created_at_utc: str) -> str:
    """First closed-bar open UTC when a pending row created at ``created_at_utc`` may activate."""
    floor_utc_to_5m_open, FIVE_MINUTES, parse_iso_zulu_to_utc = _import_canonical_time()
    import sys

    rt = Path(__file__).resolve().parents[2] / "scripts" / "runtime"
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))
    from market_data.canonical_time import format_candle_open_iso_z  # noqa: PLC0415

    dt = parse_iso_zulu_to_utc(created_at_utc)
    eligible = floor_utc_to_5m_open(dt) + FIVE_MINUTES
    return format_candle_open_iso_z(eligible)


def baseline_jupiter_policy_activation_api_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Response payload for POST / baseline-jupiter-policy (current, pending, next boundary)."""
    ensure_execution_ledger_schema(conn)
    exec_slot = resolve_baseline_jupiter_policy_for_execution(conn)
    pid_a, pver_a = baseline_jupiter_policy_lineage(exec_slot)
    current_active_policy = {
        "policy_id": pid_a,
        "policy_version": pver_a,
        "slot": POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
    }
    pending_policy: dict[str, str] | None = None
    effective_on: str | None = None
    if _policy_activation_table_ready(conn):
        row = conn.execute(
            """
            SELECT policy_id, policy_version, slot, created_at_utc
            FROM policy_activation_log
            WHERE slot = ? AND activation_state = 'pending'
            ORDER BY id ASC
            LIMIT 1
            """,
            (POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,),
        ).fetchone()
        if row:
            pending_policy = {
                "policy_id": str(row[0] or ""),
                "policy_version": str(row[1] or ""),
                "slot": str(row[2] or ""),
            }
            cre = str(row[3] or "")
            if cre:
                try:
                    effective_on = next_pending_activation_effective_on_iso(cre)
                except ValueError:
                    effective_on = None
    return {
        "current_active_policy": current_active_policy,
        "pending_policy": pending_policy,
        "effective_on": effective_on,
        "effective_baseline_policy_slot": exec_slot,
    }


def enqueue_baseline_jupiter_policy_activation(
    conn: sqlite3.Connection,
    *,
    policy_id: str,
    policy_version: str,
    slot: str,
    assigned_by: str = "api",
) -> None:
    """
    Insert a **pending** activation only — does **not** update ``baseline_operator_kv`` or activate.

    Canonicalizes ``policy_id`` / ``policy_version`` via known baseline slots.
    """
    slot_n = (slot or "").strip()
    if slot_n != POLICY_ACTIVATION_SLOT_BASELINE_JUPITER:
        raise ValueError(
            f"slot must be {POLICY_ACTIVATION_SLOT_BASELINE_JUPITER!r} for baseline Jupiter activation"
        )
    mapped = baseline_slot_from_policy_lineage(policy_id.strip(), policy_version.strip())
    if mapped is None:
        raise ValueError("unrecognized policy_id / policy_version for baseline Jupiter activation")
    pid_c, pver_c = baseline_jupiter_policy_lineage(mapped)
    ensure_execution_ledger_schema(conn)
    if not _policy_activation_table_ready(conn):
        raise ValueError("policy_activation_log is not available")
    eff = resolve_baseline_jupiter_policy_for_execution(conn)
    ts = utc_now_iso()
    ab = (assigned_by or "").strip() or "api"
    conn.execute(
        """
        UPDATE policy_activation_log
        SET activation_state = 'superseded'
        WHERE slot = ? AND activation_state = 'pending'
        """,
        (POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,),
    )
    conn.execute(
        """
        INSERT INTO policy_activation_log (
          policy_id, policy_version, slot, activation_state,
          activation_effective_at_utc, activation_market_event_id,
          assigned_by, created_at_utc, previous_baseline_policy_slot
        ) VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?, ?)
        """,
        (
            pid_c,
            pver_c,
            POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
            ab,
            ts,
            eff,
        ),
    )


def _import_canonical_time() -> tuple[Any, Any, Any]:
    import sys

    rt = Path(__file__).resolve().parents[2] / "scripts" / "runtime"
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))
    from market_data.canonical_time import (  # noqa: PLC0415
        FIVE_MINUTES,
        floor_utc_to_5m_open,
        parse_iso_zulu_to_utc,
    )

    return floor_utc_to_5m_open, FIVE_MINUTES, parse_iso_zulu_to_utc


def apply_baseline_jupiter_policy_activation_at_bar(
    conn: sqlite3.Connection,
    *,
    market_event_id: str,
    candle_open_utc: str,
) -> None:
    """
    If a **pending** row is due (first closed 5m bar at/after next boundary from ``created_at_utc``),
    supersede the current **active** (if any) and mark the row **active**.
    """
    if not _policy_activation_table_ready(conn):
        return
    mid = (market_event_id or "").strip()
    co = (candle_open_utc or "").strip()
    if not mid or not co:
        return
    floor_utc_to_5m_open, FIVE_MINUTES, parse_iso_zulu_to_utc = _import_canonical_time()
    try:
        bar_open = parse_iso_zulu_to_utc(co)
    except ValueError:
        return
    while True:
        cur = conn.execute(
            """
            SELECT id, created_at_utc FROM policy_activation_log
            WHERE slot = ? AND activation_state = 'pending'
            ORDER BY id ASC
            LIMIT 1
            """,
            (POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,),
        )
        pend = cur.fetchone()
        if not pend:
            return
        pid, created_s = int(pend[0]), str(pend[1] or "")
        try:
            created_dt = parse_iso_zulu_to_utc(created_s)
        except ValueError:
            return
        eligible_open = floor_utc_to_5m_open(created_dt) + FIVE_MINUTES
        if bar_open < eligible_open:
            return
        conn.execute(
            """
            UPDATE policy_activation_log
            SET activation_state = 'superseded'
            WHERE slot = ? AND activation_state = 'active'
            """,
            (POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,),
        )
        eff = utc_now_iso()
        conn.execute(
            """
            UPDATE policy_activation_log
            SET activation_state = 'active',
                activation_effective_at_utc = ?,
                activation_market_event_id = ?
            WHERE id = ?
            """,
            (co, mid, pid),
        )
        row = conn.execute(
            "SELECT policy_id, policy_version FROM policy_activation_log WHERE id = ?",
            (pid,),
        ).fetchone()
        if row:
            slot_eff = baseline_slot_from_policy_lineage(str(row[0] or ""), str(row[1] or ""))
            if slot_eff:
                conn.execute(
                    """
                    INSERT INTO baseline_operator_kv (key, value, updated_at_utc)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at_utc = excluded.updated_at_utc
                    """,
                    (BASELINE_OPERATOR_KV_JUPITER_POLICY_SLOT, slot_eff, eff),
                )


def set_baseline_jupiter_policy_slot(
    conn: sqlite3.Connection,
    policy_slot: str,
    *,
    assigned_by: str = "operator",
) -> None:
    """Persist operator policy slot in KV; schedule **pending** activation (tests / legacy helpers)."""
    ps = normalize_baseline_jupiter_policy_slot(policy_slot)
    if ps is None:
        raise ValueError(
            f"policy_slot must be one of {sorted(VALID_BASELINE_JUPITER_POLICY_SLOTS)} "
            f"(or aliases jupiter_2/jupiter_3/jupiter_4, v2/v3/v4); got {policy_slot!r}"
        )
    ensure_execution_ledger_schema(conn)
    pid, pver = baseline_jupiter_policy_lineage(ps)
    if _policy_activation_table_ready(conn):
        enqueue_baseline_jupiter_policy_activation(
            conn,
            policy_id=pid,
            policy_version=pver,
            slot=POLICY_ACTIVATION_SLOT_BASELINE_JUPITER,
            assigned_by=assigned_by,
        )
    ts = utc_now_iso()
    conn.execute(
        """
        INSERT INTO baseline_operator_kv (key, value, updated_at_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at_utc = excluded.updated_at_utc
        """,
        (BASELINE_OPERATOR_KV_JUPITER_POLICY_SLOT, ps, ts),
    )


def signal_mode_for_baseline_policy_slot(policy_slot: str) -> str:
    """Map **normalized** slot to ``policy_evaluations.signal_mode``. Unknown slot → ``ValueError``."""
    ps = normalize_baseline_jupiter_policy_slot(policy_slot)
    if ps is None:
        raise ValueError(
            f"unknown baseline Jupiter policy slot {policy_slot!r}; "
            f"must normalize to one of {sorted(VALID_BASELINE_JUPITER_POLICY_SLOTS)}"
        )
    if ps == BASELINE_POLICY_SLOT_JUP_V4:
        return SIGNAL_MODE_JUPITER_4
    if ps == BASELINE_POLICY_SLOT_JUP_V3:
        return SIGNAL_MODE_JUPITER_3
    return SIGNAL_MODE_JUPITER_2


def baseline_jupiter_policy_label_for_slot(policy_slot: str) -> str:
    """Operator-facing short label for dashboard / bundle (``JUPv2`` / ``JUPv3`` / ``JUPv4``)."""
    ps = normalize_baseline_jupiter_policy_slot(policy_slot)
    if ps == BASELINE_POLICY_SLOT_JUP_V4:
        return "JUPv4"
    if ps == BASELINE_POLICY_SLOT_JUP_V3:
        return "JUPv3"
    if ps == BASELINE_POLICY_SLOT_JUP_V2:
        return "JUPv2"
    return "JUPv2"


def baseline_jupiter_policy_tag_from_signal_mode(signal_mode: str | None) -> str:
    """Derive strip/table tag from ``policy_evaluations.signal_mode``."""
    sm = (signal_mode or "").strip()
    if sm == SIGNAL_MODE_JUPITER_4:
        return "JUPv4"
    if sm == SIGNAL_MODE_JUPITER_3:
        return "JUPv3"
    return "JUPv2"


def baseline_jupiter_policy_tag_from_signal_mode_optional(signal_mode: str | None) -> str | None:
    """
    Map ``policy_evaluations.signal_mode`` to strip label, or ``None`` when missing / unknown.

    Unknown non-empty strings return ``None`` (not JUPv2) so the UI shows em dash instead of a false v2.
    """
    sm = (signal_mode or "").strip()
    if not sm:
        return None
    if sm == SIGNAL_MODE_JUPITER_4:
        return "JUPv4"
    if sm == SIGNAL_MODE_JUPITER_3:
        return "JUPv3"
    if sm == SIGNAL_MODE_JUPITER_2:
        return "JUPv2"
    return None


def entry_policy_authority_from_signal_features(sf: dict[str, Any] | None) -> str:
    """
    Classify **which evaluator produced the entry** from persisted ``signal_features_snapshot``
    (``BaselineOpenPosition`` / policy row ``open_position``), not the operator's current slot.

    Returns one of: ``jupiter_2_sean``, ``jupiter_3_sean``, ``jupiter_4_sean``, ``unknown``.
    """
    if not isinstance(sf, dict) or not sf:
        return "unknown"
    parity = str(sf.get("parity") or "").lower()
    if "jupiter_4" in parity:
        return "jupiter_4_sean"
    if "jupiter_3" in parity:
        return "jupiter_3_sean"
    if "jupiter_2" in parity:
        return "jupiter_2_sean"
    cat = str(sf.get("catalog_id") or "").lower()
    if "jupiter_4" in cat:
        return "jupiter_4_sean"
    if "jupiter_3" in cat:
        return "jupiter_3_sean"
    if "jupiter_2" in cat:
        return "jupiter_2_sean"
    pe = str(sf.get("policy_engine") or "").lower()
    if "jupiter_4" in pe or "jupiter_4" in str(sf.get("policy_version") or "").lower():
        return "jupiter_4_sean"
    if "jupiter_3" in pe or "jupiter_3" in str(sf.get("policy_version") or "").lower():
        return "jupiter_3_sean"
    jg4 = sf.get("jupiter_v4_gates")
    if isinstance(jg4, dict) and str(jg4.get("schema") or "") == "jupiter_v4_gates_v1":
        return "jupiter_4_sean"
    jg = sf.get("jupiter_v3_gates")
    if isinstance(jg, dict) and str(jg.get("schema") or "") == "jupiter_v3_gates_v1":
        return "jupiter_3_sean"
    return "unknown"


def baseline_entry_policy_label_for_authority(authority: str) -> str:
    """Short operator label for the **entry** bar (distinct from the live selector chip)."""
    a = (authority or "").strip().lower()
    if a == "jupiter_4_sean":
        return "JUPv4"
    if a == "jupiter_3_sean":
        return "JUPv3"
    if a == "jupiter_2_sean":
        return "Jupiter_2 Sean"
    return "Policy (unknown)"


def lookup_baseline_jupiter_open_state_json(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    timeframe: str,
    mode: str,
) -> tuple[str | None, str | None]:
    """
    Return ``(state_json, position_key)`` for the active policy slot, then legacy unsuffixed key.
    """
    slot = resolve_baseline_jupiter_policy_for_execution(conn)
    pk_new = baseline_jupiter_open_position_key(
        symbol=symbol, timeframe=timeframe, mode=mode, policy_slot=slot
    )
    raw = fetch_baseline_jupiter_open_state_json(conn, position_key=pk_new)
    if raw:
        return raw, pk_new
    pk_legacy = baseline_jupiter_open_position_key(symbol=symbol, timeframe=timeframe, mode=mode)
    raw2 = fetch_baseline_jupiter_open_state_json(conn, position_key=pk_legacy)
    if raw2:
        return raw2, pk_legacy
    return None, None


def fetch_baseline_policy_evaluation_for_market_event(
    conn: sqlite3.Connection,
    market_event_id: str,
    *,
    lane: str = RESERVED_STRATEGY_BASELINE,
    strategy_id: str = RESERVED_STRATEGY_BASELINE,
    prefer_active_slot: bool = True,
) -> dict[str, Any] | None:
    """Latest baseline policy row for ``market_event_id``.

    When ``prefer_active_slot`` is True (default), tries the execution-effective engine first
    (``resolve_baseline_jupiter_policy_for_execution``), then the other ``signal_mode`` so historic rows still resolve
    after a policy switch.

    When ``prefer_active_slot`` is False (historic / strip / reports), tries **v4, then v3, then v2**.
    If multiple rows exist for the same bar (e.g. legacy v2 backfill plus v3 evaluator), the **highest**
    version wins — otherwise v2 would always shadow v3/v4.
    """
    mid = (market_event_id or "").strip()
    if not mid:
        return None
    modes: list[str]
    if prefer_active_slot:
        slot = resolve_baseline_jupiter_policy_for_execution(conn)
        primary = signal_mode_for_baseline_policy_slot(slot)
        others = [
            m
            for m in (
                SIGNAL_MODE_JUPITER_2,
                SIGNAL_MODE_JUPITER_3,
                SIGNAL_MODE_JUPITER_4,
            )
            if m != primary
        ]
        modes = [primary] + others
    else:
        modes = [SIGNAL_MODE_JUPITER_4, SIGNAL_MODE_JUPITER_3, SIGNAL_MODE_JUPITER_2]
    seen: set[str] = set()
    for sm in modes:
        if sm in seen:
            continue
        seen.add(sm)
        row = fetch_policy_evaluation_for_market_event(
            conn, mid, lane=lane, strategy_id=strategy_id, signal_mode=sm
        )
        if row:
            return row
    return None


def fetch_baseline_jupiter_open_state_json(
    conn: sqlite3.Connection,
    *,
    position_key: str,
) -> str | None:
    row = conn.execute(
        "SELECT state_json FROM baseline_jupiter_open_positions WHERE position_key = ?",
        (position_key.strip(),),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def upsert_baseline_jupiter_open_state(
    conn: sqlite3.Connection,
    *,
    position_key: str,
    trade_id: str,
    state_json: str,
) -> None:
    ts = utc_now_iso()
    conn.execute(
        """
        INSERT INTO baseline_jupiter_open_positions (position_key, trade_id, state_json, updated_at_utc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(position_key) DO UPDATE SET
          trade_id = excluded.trade_id,
          state_json = excluded.state_json,
          updated_at_utc = excluded.updated_at_utc
        """,
        (position_key.strip(), str(trade_id).strip(), state_json, ts),
    )


def delete_baseline_jupiter_open_state(conn: sqlite3.Connection, *, position_key: str) -> None:
    conn.execute(
        "DELETE FROM baseline_jupiter_open_positions WHERE position_key = ?",
        (position_key.strip(),),
    )


def next_position_event_sequence(conn: sqlite3.Connection, trade_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM position_events WHERE trade_id = ?",
        (str(trade_id).strip(),),
    ).fetchone()
    return int(row[0]) if row else 0


def append_position_event(
    conn: sqlite3.Connection,
    *,
    trade_id: str,
    market_event_id: str,
    event_type: str,
    payload: dict[str, Any],
    sequence_num: int | None = None,
) -> int:
    """Append one ``position_events`` row. If ``sequence_num`` is None, uses next free index for ``trade_id``."""
    tid = str(trade_id).strip()
    mid = str(market_event_id).strip()
    seq = int(sequence_num) if sequence_num is not None else next_position_event_sequence(conn, tid)
    eid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT OR IGNORE INTO position_events (
          event_id, trade_id, market_event_id, lane, sequence_num, event_type, payload_json, created_at_utc, schema_version
        ) VALUES (?, ?, ?, 'baseline', ?, ?, ?, ?, ?)
        """,
        (
            eid,
            tid,
            mid,
            seq,
            str(event_type),
            json.dumps(payload, default=str, sort_keys=True),
            utc_now_iso(),
            POSITION_EVENT_SCHEMA_VERSION,
        ),
    )
    return seq


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
    _migrate_sequential_learning_schema(conn, root)
    _migrate_policy_evaluation_schema(conn, root)
    _migrate_policy_activation_schema(conn, root)
    _migrate_execution_trades_lineage_columns(conn)
    _migrate_position_events_schema(conn, root)
    _migrate_baseline_jupiter_open_positions(conn)
    _migrate_baseline_operator_kv(conn)
    conn.commit()


POLICY_EVALUATION_SCHEMA_VERSION = "policy_evaluation_v1"
POSITION_EVENT_SCHEMA_VERSION = "position_event_v1"


def insert_baseline_paper_lifecycle_events(
    conn: sqlite3.Connection,
    *,
    trade_id: str,
    market_event_id: str,
    bar: dict[str, Any],
    side: str,
    pnl_usd: float,
    mode: str,
) -> None:
    """
    Record open + close for **legacy** baseline same-bar mechanical trades (bucket 2).

    Jupiter_2 lifecycle uses ``position_open`` / ``position_close`` with SL/TP from
    ``jupiter_2_baseline_lifecycle`` instead.
    """
    o = bar.get("open")
    c = bar.get("close")
    if o is None or c is None:
        raise ValueError("bar_missing_ohlc")
    sd = (side or "long").strip().lower()
    if sd not in ("long", "short"):
        sd = "long"
    sym = str(bar.get("canonical_symbol") or "SOL-PERP")
    ts = utc_now_iso()
    open_payload: dict[str, Any] = {
        "phase": "position_open",
        "entry_price": float(o),
        "same_bar_close_preview": float(c),
        "side": sd,
        "symbol": sym,
        "mode": str(mode or "paper"),
        "virtual_tp": None,
        "virtual_sl": None,
        "note": (
            "Paper baseline: 1-unit open→close on this bar. "
            "TP/SL/trail rows appear when the execution layer records them."
        ),
    }
    close_payload: dict[str, Any] = {
        "phase": "position_close",
        "exit_price": float(c),
        "pnl_usd_1unit": float(pnl_usd),
        "exit_reason": "BAR_CLOSE",
        "note": "Same-candle exit as baseline ledger (economic_basis=jupiter_policy or mechanical long).",
    }
    rows_spec = (
        (0, "position_open", open_payload),
        (1, "position_close", close_payload),
    )
    for seq, etype, payload in rows_spec:
        eid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT OR IGNORE INTO position_events (
              event_id, trade_id, market_event_id, lane, sequence_num, event_type, payload_json, created_at_utc, schema_version
            ) VALUES (?, ?, ?, 'baseline', ?, ?, ?, ?, ?)
            """,
            (
                eid,
                str(trade_id).strip(),
                str(market_event_id).strip(),
                int(seq),
                str(etype),
                json.dumps(payload, default=str, sort_keys=True),
                ts,
                POSITION_EVENT_SCHEMA_VERSION,
            ),
        )


def fetch_policy_evaluation_for_market_event(
    conn: sqlite3.Connection,
    market_event_id: str,
    *,
    lane: str = RESERVED_STRATEGY_BASELINE,
    strategy_id: str = RESERVED_STRATEGY_BASELINE,
    signal_mode: str = "sean_jupiter_v1",
) -> dict[str, Any] | None:
    """Latest policy_evaluations row for baseline policy at ``market_event_id``.

    ``signal_mode`` defaults to ``sean_jupiter_v1`` (historic env name); evaluator is **Jupiter_2**
    (``jupiter_2_sean_policy``).
    """
    mid = (market_event_id or "").strip()
    if not mid:
        return None
    cur = conn.execute(
        """
        SELECT market_event_id, lane, strategy_id, signal_mode, tick_mode, trade, side, reason_code,
               features_json, pnl_usd, evaluated_at_utc
        FROM policy_evaluations
        WHERE market_event_id = ? AND lane = ? AND strategy_id = ? AND signal_mode = ?
        LIMIT 1
        """,
        (mid, lane.strip().lower(), strategy_id.strip(), signal_mode.strip()),
    )
    r = cur.fetchone()
    if not r:
        return None
    feat: Any = {}
    try:
        feat = json.loads(r[8]) if r[8] else {}
    except json.JSONDecodeError:
        feat = {"raw": r[8]}
    return {
        "market_event_id": r[0],
        "lane": r[1],
        "strategy_id": r[2],
        "signal_mode": r[3],
        "tick_mode": r[4],
        "trade": bool(r[5]),
        "side": r[6],
        "reason_code": r[7],
        "features": feat if isinstance(feat, dict) else {},
        "pnl_usd": r[9],
        "evaluated_at_utc": r[10],
    }


def fetch_recent_policy_evaluations(
    conn: sqlite3.Connection,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT market_event_id, lane, strategy_id, signal_mode, tick_mode, trade, side, reason_code,
               features_json, pnl_usd, evaluated_at_utc
        FROM policy_evaluations
        ORDER BY evaluated_at_utc DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        feat: Any = {}
        try:
            feat = json.loads(r[8]) if r[8] else {}
        except json.JSONDecodeError:
            feat = {"raw": r[8]}
        out.append(
            {
                "market_event_id": r[0],
                "lane": r[1],
                "strategy_id": r[2],
                "signal_mode": r[3],
                "tick_mode": r[4],
                "trade": bool(r[5]),
                "side": r[6],
                "reason_code": r[7],
                "features": feat,
                "pnl_usd": r[9],
                "evaluated_at_utc": r[10],
            }
        )
    return out


def fetch_recent_position_events(
    conn: sqlite3.Connection,
    *,
    limit: int = 48,
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT event_id, trade_id, market_event_id, lane, sequence_num, event_type, payload_json, created_at_utc
        FROM position_events
        ORDER BY created_at_utc DESC, trade_id, sequence_num DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    )
    out: list[dict[str, Any]] = []
    for r in cur.fetchall():
        try:
            pl = json.loads(r[6]) if r[6] else {}
        except json.JSONDecodeError:
            pl = {"raw": r[6]}
        out.append(
            {
                "event_id": r[0],
                "trade_id": r[1],
                "market_event_id": r[2],
                "lane": r[3],
                "sequence_num": r[4],
                "event_type": r[5],
                "payload": pl,
                "created_at_utc": r[7],
            }
        )
    return out


def upsert_policy_evaluation(
    *,
    market_event_id: str,
    signal_mode: str,
    tick_mode: str,
    trade: bool,
    reason_code: str,
    features: dict[str, Any],
    lane: str = RESERVED_STRATEGY_BASELINE,
    strategy_id: str = RESERVED_STRATEGY_BASELINE,
    side: str | None = None,
    pnl_usd: float | None = None,
    evaluated_at_utc: str | None = None,
    policy_id: str | None = None,
    policy_version: str | None = None,
    slot: str | None = None,
    db_path: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """
    One row per (market_event_id, lane, strategy_id, signal_mode): policy outcome for backtest joins.

    Call after ``evaluate_sean_jupiter_baseline_v1`` (or equivalent) on every baseline tick,
    including ``trade=false`` outcomes.
    """
    mid = (market_event_id or "").strip()
    if not mid:
        raise ValueError("market_event_id required")
    _validate_lane_strategy(lane, strategy_id)
    tm = (tick_mode or "paper").strip().lower()
    if tm not in ("live", "paper"):
        raise ValueError("tick_mode must be live or paper")
    sm = (signal_mode or "").strip()
    if not sm:
        raise ValueError("signal_mode required")
    ts = evaluated_at_utc or utc_now_iso()
    sd = None
    if side is not None and str(side).strip():
        sd = str(side).strip().lower()
        if sd not in ("long", "short", "flat"):
            raise ValueError("side must be long, short, flat, or empty")

    payload = json.dumps(features, default=str, sort_keys=True)
    close_conn = False
    if conn is None:
        conn = connect_ledger(db_path)
        close_conn = True
    try:
        ensure_execution_ledger_schema(conn)
        pid = (policy_id or "").strip() or None
        pver = (policy_version or "").strip() or None
        slot_v = (slot or "").strip() or None
        conn.execute(
            """
            INSERT INTO policy_evaluations (
              market_event_id, lane, strategy_id, signal_mode, tick_mode,
              trade, side, reason_code, features_json, pnl_usd,
              evaluated_at_utc, schema_version,
              policy_id, policy_version, slot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_event_id, lane, strategy_id, signal_mode) DO UPDATE SET
              tick_mode = excluded.tick_mode,
              trade = excluded.trade,
              side = excluded.side,
              reason_code = excluded.reason_code,
              features_json = excluded.features_json,
              pnl_usd = excluded.pnl_usd,
              evaluated_at_utc = excluded.evaluated_at_utc,
              schema_version = excluded.schema_version,
              policy_id = excluded.policy_id,
              policy_version = excluded.policy_version,
              slot = excluded.slot
            """,
            (
                mid,
                lane,
                strategy_id,
                sm,
                tm,
                1 if trade else 0,
                sd,
                str(reason_code or ""),
                payload,
                (float(pnl_usd) if pnl_usd is not None else 0.0) if trade else None,
                ts,
                POLICY_EVALUATION_SCHEMA_VERSION,
                pid,
                pver,
                slot_v,
            ),
        )
        conn.commit()
    finally:
        if close_conn:
            conn.close()


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
    policy_id: str | None = None,
    policy_version: str | None = None,
    lineage_slot: str | None = None,
    originating_market_event_id: str | None = None,
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
        "policy_id": (policy_id or "").strip() or None,
        "policy_version": (policy_version or "").strip() or None,
        "slot": (lineage_slot or "").strip() or None,
        "originating_market_event_id": (originating_market_event_id or "").strip() or None,
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
              pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc,
              policy_id, policy_version, slot, originating_market_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                row["policy_id"],
                row["policy_version"],
                row["slot"],
                row["originating_market_event_id"],
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


def query_trades_for_symbol_timeframe_in_events(
    symbol: str,
    timeframe: str,
    market_event_ids: list[str],
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Trades whose ``market_event_id`` is in the given set (e.g. chart window bars).
    Used to align ledger rows with OHLC history for time-based overlays.
    """
    mids = [str(x).strip() for x in market_event_ids if str(x).strip()]
    if not mids:
        return []
    sym = (symbol or "").strip()
    tf = (timeframe or "").strip()
    if not sym or not tf:
        return []
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        placeholders = ",".join("?" * len(mids))
        cur = conn.execute(
            f"""
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
            FROM execution_trades
            WHERE symbol = ? AND timeframe = ? AND market_event_id IN ({placeholders})
            ORDER BY entry_time ASC, trade_id ASC
            """,
            (sym, tf, *mids),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def query_trades_for_symbol_timeframe_overlapping_window(
    symbol: str,
    timeframe: str,
    window_start_utc: str,
    window_end_utc: str,
    *,
    limit: int = 800,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Trades that may span multiple bars: overlap [window_start_utc, window_end_utc] lexicographically
    (ISO-8601 strings) using entry/exit times.
    """
    sym = (symbol or "").strip()
    tf = (timeframe or "").strip()
    ws = (window_start_utc or "").strip()
    we = (window_end_utc or "").strip()
    if not sym or not tf or not ws or not we:
        return []
    conn = connect_ledger(db_path)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, trace_id, schema_version, created_at_utc
            FROM execution_trades
            WHERE symbol = ? AND timeframe = ?
              AND entry_time IS NOT NULL AND entry_time <= ?
              AND (exit_time IS NULL OR exit_time >= ?)
            ORDER BY entry_time ASC, trade_id ASC
            LIMIT ?
            """,
            (sym, tf, we, ws, int(limit)),
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
