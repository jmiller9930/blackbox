"""
Automatic QEL lifecycle advancement after a full survival pass (no drop, all enabled checkpoints survived).

Rules (config/survival_engine.json lifecycle_auto):
  - 1st completed_survived while lifecycle=test → candidate, spawn follow-up active test
  - 2nd completed_survived while lifecycle=candidate → validated_strategy, spawn follow-up
  - 3rd completed_survived while lifecycle=validated_strategy → promotion_ready (no follow-up test)

Promotion to promoted remains human-only.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema

from .checkpoint_config import load_survival_config
from .constants import (
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_PROMOTION_READY,
    LIFECYCLE_TEST,
    LIFECYCLE_VALIDATED_STRATEGY,
)
from .lifecycle import apply_strategy_transition, create_survival_test

CHECKPOINT_ORDER = [
    "min_economic_trades",
    "min_distinct_market_events",
    "min_calendar_span_days",
    "distinctiveness_hash",
    "min_regime_vol_buckets",
    "min_performance",
]


def enabled_checkpoint_keys(cfg: dict[str, Any]) -> list[str]:
    cp = cfg.get("checkpoints") or {}
    out: list[str] = []
    for k in CHECKPOINT_ORDER:
        spec = cp.get(k)
        if spec is None:
            continue
        if spec.get("enabled", True):
            out.append(k)
    return out


def all_enabled_checkpoints_survived(
    conn: sqlite3.Connection,
    test_id: str,
    cfg: dict[str, Any],
) -> bool:
    """Each enabled checkpoint has a latest evaluation row with decision survive."""
    keys = enabled_checkpoint_keys(cfg)
    if not keys:
        return False
    tid = test_id.strip()
    for name in keys:
        cur = conn.execute(
            """
            SELECT decision FROM anna_survival_evaluation_runs
            WHERE test_id = ? AND checkpoint_name = ?
            ORDER BY evaluated_at_utc DESC
            LIMIT 1
            """,
            (tid, name),
        )
        row = cur.fetchone()
        if not row or str(row[0]) != "survive":
            return False
    return True


def count_completed_survived_tests(conn: sqlite3.Connection, strategy_id: str) -> int:
    cur = conn.execute(
        """
        SELECT COUNT(*) FROM anna_survival_tests
        WHERE strategy_id = ? AND status = 'completed_survived'
        """,
        (strategy_id.strip(),),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _load_test_row(conn: sqlite3.Connection, test_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT test_id, strategy_id, hypothesis_json, allowed_inputs_json, lane_allowed_json, mode_allowed_json
        FROM anna_survival_tests
        WHERE test_id = ?
        """,
        (test_id.strip(),),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "test_id": row[0],
        "strategy_id": row[1],
        "hypothesis_json": row[2],
        "allowed_inputs_json": row[3],
        "lane_allowed_json": row[4],
        "mode_allowed_json": row[5],
    }


def spawn_followup_survival_test(
    *,
    strategy_id: str,
    previous_test_id: str,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Clone hypothesis from previous test into a new active survival test."""
    conn = connect_ledger(db_path or default_execution_ledger_path())
    ensure_execution_ledger_schema(conn)
    try:
        prev = _load_test_row(conn, previous_test_id)
    finally:
        conn.close()
    if not prev:
        return None
    try:
        hyp = json.loads(prev["hypothesis_json"] or "{}")
        allowed = json.loads(prev["allowed_inputs_json"] or "{}")
        lanes = json.loads(prev["lane_allowed_json"] or "[]")
        modes = json.loads(prev["mode_allowed_json"] or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(lanes, list) or not lanes:
        lanes = ["anna"]
    if not isinstance(modes, list) or not modes:
        modes = ["paper"]
    return create_survival_test(
        strategy_id=strategy_id,
        hypothesis=hyp if isinstance(hyp, dict) else {},
        allowed_inputs=allowed if isinstance(allowed, dict) else {},
        lanes=[str(x) for x in lanes],
        modes=[str(x) for x in modes],
        created_by="qel_auto_advance",
        supersedes_test_id=previous_test_id,
        db_path=db_path,
    )


def apply_lifecycle_after_full_survival(
    *,
    completed_test_id: str,
    strategy_id: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Apply automatic transitions after the caller has set the test row to completed_survived.

    Idempotent per completion: one transition per survival completion event.
    """
    cfg = load_survival_config()
    la = cfg.get("lifecycle_auto") or {}
    if not la.get("enabled", True):
        return {"ok": True, "advanced": False, "reason": "lifecycle_auto_disabled"}

    conn = connect_ledger(db_path or default_execution_ledger_path())
    ensure_execution_ledger_schema(conn)
    try:
        cur = conn.execute(
            "SELECT lifecycle_state FROM strategy_registry WHERE strategy_id = ?",
            (strategy_id.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "reason": "strategy_not_in_registry"}
        lifecycle = str(row[0] or LIFECYCLE_TEST)

        if lifecycle not in (LIFECYCLE_TEST, LIFECYCLE_CANDIDATE, LIFECYCLE_VALIDATED_STRATEGY):
            return {
                "ok": True,
                "advanced": False,
                "reason": "lifecycle_not_in_survival_auto_track",
                "lifecycle_state": lifecycle,
            }

        n = count_completed_survived_tests(conn, strategy_id)
        min_pr = int(la.get("min_completed_survived_for_promotion_ready", 3))

        target: str | None = None
        if lifecycle == LIFECYCLE_TEST and n >= 1:
            target = LIFECYCLE_CANDIDATE
        elif lifecycle == LIFECYCLE_CANDIDATE and n >= 2:
            target = LIFECYCLE_VALIDATED_STRATEGY
        elif lifecycle == LIFECYCLE_VALIDATED_STRATEGY and n >= min_pr:
            target = LIFECYCLE_PROMOTION_READY

        transitions: list[dict[str, Any]] = []
        if target:
            apply_strategy_transition(
                strategy_id=strategy_id,
                to_state=target,
                reason_code=f"qel_auto_survival_completed_survived_n={n}",
                actor="system",
                payload={
                    "qel": True,
                    "completed_test_id": completed_test_id,
                    "completed_survived_count": n,
                },
                db_path=db_path,
            )
            transitions.append({"to_state": target})

        followup: dict[str, Any] | None = None
        if target and target != LIFECYCLE_PROMOTION_READY:
            followup = spawn_followup_survival_test(
                strategy_id=strategy_id,
                previous_test_id=completed_test_id,
                db_path=db_path,
            )

        return {
            "ok": True,
            "advanced": bool(target),
            "transitions": transitions,
            "completed_survived_count": n,
            "followup_test": followup,
        }
    finally:
        conn.close()
