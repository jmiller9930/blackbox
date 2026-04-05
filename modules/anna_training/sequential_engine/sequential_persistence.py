"""Persist SPRT evaluation rows + strategy_registry snapshot (authoritative audit)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema
from modules.anna_training.store import utc_now_iso

from .constants import SEQUENTIAL_ENGINE_VERSION


def persist_sequential_decision_run(
    *,
    test_id: str,
    strategy_id: str,
    sprt_decision: str,
    eligible_n: int,
    win_n: int,
    wilson: dict[str, Any] | None,
    sprt_snapshot: dict[str, Any],
    shadow_tier: dict[str, Any] | None,
    hypothesis_hash: str | None,
    pattern_spec_hash: str | None,
    manifest_content_hash: str | None,
    db_path: Path | None = None,
) -> str:
    """
    Insert one row into ``anna_sequential_decision_runs`` and update
    ``strategy_registry.sequential_learning_snapshot_json`` for ``strategy_id``.
    """
    if sprt_decision not in ("CONTINUE", "PROMOTE", "KILL"):
        raise ValueError(f"invalid sprt_decision {sprt_decision!r}")

    run_id = str(uuid.uuid4())
    now = utc_now_iso()
    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        conn.execute(
            """
            INSERT INTO anna_sequential_decision_runs (
              run_id, test_id, strategy_id, evaluated_at_utc, sprt_decision,
              eligible_n, win_n, wilson_json, sprt_snapshot_json, shadow_tier_json,
              hypothesis_hash, pattern_spec_hash, engine_version, manifest_content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                test_id,
                strategy_id.strip(),
                now,
                sprt_decision,
                int(eligible_n),
                int(win_n),
                json.dumps(wilson, ensure_ascii=False) if wilson else None,
                json.dumps(sprt_snapshot, ensure_ascii=False, sort_keys=True),
                json.dumps(shadow_tier, ensure_ascii=False, sort_keys=True) if shadow_tier else None,
                hypothesis_hash,
                pattern_spec_hash,
                SEQUENTIAL_ENGINE_VERSION,
                manifest_content_hash,
            ),
        )
        snap = {
            "test_id": test_id,
            "last_evaluated_at_utc": now,
            "sprt_decision": sprt_decision,
            "eligible_n": eligible_n,
            "win_n": win_n,
            "engine_version": SEQUENTIAL_ENGINE_VERSION,
            "shadow_tier": shadow_tier or {},
        }
        conn.execute(
            """
            UPDATE strategy_registry
            SET sequential_learning_snapshot_json = ?
            WHERE strategy_id = ?
            """,
            (json.dumps(snap, ensure_ascii=False, sort_keys=True), strategy_id.strip()),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def ensure_strategy_registered(strategy_id: str, *, db_path: Path | None = None) -> None:
    """Insert minimal strategy_registry row if missing (driver prerequisite)."""
    sid = strategy_id.strip()
    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute("SELECT 1 FROM strategy_registry WHERE strategy_id = ?", (sid,))
        if cur.fetchone():
            return
        conn.execute(
            """
            INSERT INTO strategy_registry (strategy_id, title, description, registered_at_utc, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sid,
                sid,
                "auto-registered for sequential learning driver",
                utc_now_iso(),
                "sequential_engine",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_last_sequential_decision(
    strategy_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT sprt_decision, evaluated_at_utc, eligible_n, win_n, wilson_json, sprt_snapshot_json,
                   shadow_tier_json, test_id
            FROM anna_sequential_decision_runs
            WHERE strategy_id = ?
            ORDER BY evaluated_at_utc DESC, run_id DESC
            LIMIT 1
            """,
            (strategy_id.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "sprt_decision": row[0],
            "evaluated_at_utc": row[1],
            "eligible_n": row[2],
            "win_n": row[3],
            "wilson_json": json.loads(row[4]) if row[4] else None,
            "sprt_snapshot_json": json.loads(row[5]) if row[5] else None,
            "shadow_tier_json": json.loads(row[6]) if row[6] else None,
            "test_id": row[7],
        }
    finally:
        conn.close()


def list_sequential_runs_for_test(
    test_id: str,
    *,
    db_path: Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT run_id, strategy_id, evaluated_at_utc, sprt_decision, eligible_n, win_n, shadow_tier_json
            FROM anna_sequential_decision_runs
            WHERE test_id = ?
            ORDER BY evaluated_at_utc DESC
            LIMIT ?
            """,
            (test_id.strip(), int(limit)),
        )
        out: list[dict[str, Any]] = []
        for r in cur.fetchall():
            out.append(
                {
                    "run_id": r[0],
                    "strategy_id": r[1],
                    "evaluated_at_utc": r[2],
                    "sprt_decision": r[3],
                    "eligible_n": r[4],
                    "win_n": r[5],
                    "shadow_tier_json": json.loads(r[6]) if r[6] else None,
                }
            )
        return out
    finally:
        conn.close()
