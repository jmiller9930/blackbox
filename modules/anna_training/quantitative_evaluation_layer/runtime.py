"""
QEL runtime — survival evaluation on the operating path (not manual-only).

Default: run after parallel Anna + baseline ledger each Karpathy loop tick.
Disable: ANNA_QEL_SURVIVAL_EACH_TICK=0
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema

from .survival_engine import run_survival_checkpoints_for_test


def run_qel_survival_tick(
    *,
    db_path: Path | None = None,
    market_db_path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate every **active** survival test once.

    Trigger point: called from ``anna_karpathy_loop_daemon.run_one_tick`` after
    ``run_parallel_anna_strategies_tick`` and ``run_baseline_ledger_bridge_tick`` so new
    ledger rows exist before checkpoint evaluation.
    """
    raw = (os.environ.get("ANNA_QEL_SURVIVAL_EACH_TICK") or "1").strip().lower()
    if raw in ("0", "false", "no", "off", ""):
        return {"ok": True, "enabled": False, "reason": "ANNA_QEL_SURVIVAL_EACH_TICK off"}

    conn = connect_ledger(db_path or default_execution_ledger_path())
    ensure_execution_ledger_schema(conn)
    try:
        cur = conn.execute(
            "SELECT test_id FROM anna_survival_tests WHERE status = 'active' ORDER BY created_at_utc ASC"
        )
        tids = [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    for tid in tids:
        results.append(
            run_survival_checkpoints_for_test(
                tid,
                db_path=db_path,
                market_db_path=market_db_path,
                config=config,
            )
        )

    return {
        "ok": True,
        "enabled": True,
        "tests_evaluated": len(results),
        "results": results,
    }
