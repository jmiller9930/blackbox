"""
Strategy lifecycle transitions — auditable, explicit, no silent promotion.

experiment → test requires: stable strategy_id, survival test row with hypothesis,
allowed_inputs, lane/mode — see validate_experiment_to_test_prerequisites.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema
from modules.anna_training.store import utc_now_iso

from .constants import (
    HUMAN_ONLY_TRANSITIONS,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_EXPERIMENT,
    LIFECYCLE_STATES,
    LIFECYCLE_TEST,
    promotion_requires_human_actor,
    transition_allowed,
)
from .hypothesis_hash import normalized_hypothesis_hash


def _conn(db_path: Path | None) -> sqlite3.Connection:
    c = connect_ledger(db_path or default_execution_ledger_path())
    ensure_execution_ledger_schema(c)
    return c


def get_strategy_lifecycle_state(strategy_id: str, *, db_path: Path | None = None) -> str | None:
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "SELECT lifecycle_state FROM strategy_registry WHERE strategy_id = ?",
            (strategy_id.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return str(row[0]) if row[0] else LIFECYCLE_EXPERIMENT
    finally:
        conn.close()


def validate_experiment_to_test_prerequisites(strategy_id: str, *, db_path: Path | None = None) -> tuple[bool, list[str]]:
    """
    A strategy may not enter ``test`` until all are satisfied:

    - Registered in strategy_registry with stable strategy_id
    - Active survival test in authoritative store with hypothesis, allowed_inputs, lane/mode
    """
    errors: list[str] = []
    sid = strategy_id.strip()
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "SELECT strategy_id, lifecycle_state FROM strategy_registry WHERE strategy_id = ?",
            (sid,),
        )
        row = cur.fetchone()
        if not row:
            errors.append("strategy_not_in_registry")
            return False, errors
        st = str(row[1] or LIFECYCLE_EXPERIMENT)
        if st != LIFECYCLE_EXPERIMENT:
            errors.append(f"lifecycle_not_experiment:{st}")

        cur = conn.execute(
            """
            SELECT test_id, hypothesis_json, allowed_inputs_json, lane_allowed_json, mode_allowed_json, status
            FROM anna_survival_tests
            WHERE strategy_id = ? AND status = 'active'
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (sid,),
        )
        t = cur.fetchone()
        if not t:
            errors.append("no_active_survival_test")
            return False, errors
        _tid, hyp, allowed, lanes, modes, status = t
        if not (hyp or "").strip():
            errors.append("empty_hypothesis_json")
        try:
            hj = json.loads(hyp) if hyp else {}
        except json.JSONDecodeError:
            errors.append("invalid_hypothesis_json")
            hj = {}
        if not hj:
            errors.append("hypothesis_required")
        try:
            json.loads(allowed) if allowed else {}
        except json.JSONDecodeError:
            errors.append("invalid_allowed_inputs_json")
        try:
            lj = json.loads(lanes) if lanes else []
            mj = json.loads(modes) if modes else []
        except json.JSONDecodeError:
            errors.append("invalid_lane_or_mode_json")
            lj, mj = [], []
        if not isinstance(lj, list) or not lj:
            errors.append("lane_allowed_required")
        if not isinstance(mj, list) or not mj:
            errors.append("mode_allowed_required")

        return len(errors) == 0, errors
    finally:
        conn.close()


def create_survival_test(
    *,
    strategy_id: str,
    hypothesis: dict[str, Any],
    allowed_inputs: dict[str, Any],
    lanes: list[str],
    modes: list[str],
    created_by: str = "operator",
    supersedes_test_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Insert authoritative survival test row; returns test_id and hypothesis_hash."""
    hjson = json.dumps(hypothesis, sort_keys=True, ensure_ascii=False)
    allowed_json = json.dumps(allowed_inputs, sort_keys=True, ensure_ascii=False)
    lane_json = json.dumps([str(x).strip().lower() for x in lanes], sort_keys=True)
    mode_json = json.dumps([str(x).strip().lower() for x in modes], sort_keys=True)
    hhash = normalized_hypothesis_hash(hypothesis)
    tid = str(uuid.uuid4())
    now = utc_now_iso()
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO anna_survival_tests (
              test_id, strategy_id, hypothesis_json, hypothesis_hash,
              allowed_inputs_json, lane_allowed_json, mode_allowed_json,
              status, supersedes_test_id, created_at_utc, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                tid,
                strategy_id.strip(),
                hjson,
                hhash,
                allowed_json,
                lane_json,
                mode_json,
                supersedes_test_id,
                now,
                created_by,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "test_id": tid,
        "hypothesis_hash": hhash,
        "created_at_utc": now,
    }


def apply_strategy_transition(
    *,
    strategy_id: str,
    to_state: str,
    reason_code: str,
    actor: str,
    payload: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Enforce allowed edges; promotion to ``promoted`` requires actor human_promotion.
    Appends strategy_lifecycle_transitions audit row and updates strategy_registry.
    """
    sid = strategy_id.strip()
    ts = to_state.strip()
    if ts not in LIFECYCLE_STATES:
        raise ValueError(f"invalid lifecycle state: {ts}")
    if promotion_requires_human_actor(ts) and actor != "human_promotion":
        raise ValueError("promoted requires actor=human_promotion")

    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "SELECT lifecycle_state FROM strategy_registry WHERE strategy_id = ?",
            (sid,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("strategy_not_in_registry")
        from_st = str(row[0] or LIFECYCLE_EXPERIMENT)
        if from_st not in LIFECYCLE_STATES:
            from_st = LIFECYCLE_EXPERIMENT

        if (from_st, ts) in HUMAN_ONLY_TRANSITIONS and actor != "human_promotion":
            raise ValueError("transition_requires_human_promotion")

        if not transition_allowed(from_st, ts):
            raise ValueError(f"transition_not_allowed:{from_st}->{ts}")

        if from_st == LIFECYCLE_EXPERIMENT and ts == LIFECYCLE_TEST:
            ok, errs = validate_experiment_to_test_prerequisites(sid, db_path=db_path)
            if not ok:
                raise ValueError(f"experiment_to_test_blocked:{','.join(errs)}")

        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO strategy_lifecycle_transitions (
              strategy_id, from_state, to_state, reason_code, actor, payload_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                from_st,
                ts,
                reason_code,
                actor,
                json.dumps(payload or {}, ensure_ascii=False),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE strategy_registry
            SET lifecycle_state = ?, qel_updated_at_utc = ?
            WHERE strategy_id = ?
            """,
            (ts, now, sid),
        )
        conn.commit()
        return {"ok": True, "from_state": from_st, "to_state": ts, "created_at_utc": now}
    finally:
        conn.close()


def ensure_strategy_registered_for_qel(
    strategy_id: str,
    *,
    title: str = "",
    description: str = "",
    source: str = "qel",
    db_path: Path | None = None,
) -> None:
    """Upsert registry row with lifecycle experiment if new."""
    sid = strategy_id.strip()
    now = utc_now_iso()
    conn = _conn(db_path)
    try:
        cur = conn.execute("PRAGMA table_info(strategy_registry)")
        has_lifecycle = any(str(r[1]) == "lifecycle_state" for r in cur.fetchall())
        if not has_lifecycle:
            return
        conn.execute(
            """
            INSERT INTO strategy_registry (
              strategy_id, title, description, registered_at_utc, source,
              lifecycle_state, parent_strategy_id, qel_updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(strategy_id) DO NOTHING
            """,
            (sid, title[:500], description[:2000], now, source, LIFECYCLE_EXPERIMENT, now),
        )
        conn.commit()
    finally:
        conn.close()
