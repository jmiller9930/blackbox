"""One-shot recorder: Pyth primary + Coinbase comparator → store + gates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _paths import default_market_data_path, repo_root

from market_data.feeds_coinbase import fetch_coinbase_ticker
from market_data.feeds_pyth import fetch_pyth_latest
from market_data.gates import evaluate_gates
from market_data.store import connect_market_db, ensure_market_schema, insert_tick


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def record_market_snapshot(
    *,
    symbol: str = "SOL-USD",
    coinbase_product: str = "SOL-USD",
    db_path: Path | None = None,
    max_age_sec: float = 120.0,
    max_rel_diff: float = 0.005,
    degraded_rel_diff: float = 0.002,
) -> dict[str, Any]:
    """
    Fetch Pyth (primary) + Coinbase (comparator), evaluate gates, persist one row.

    Fail-closed: missing prices or bad gates yield gate_state blocked/degraded; row still stored.
    """
    root = repo_root()
    path = db_path or default_market_data_path()
    conn = connect_market_db(path)
    ensure_market_schema(conn, root)

    pyth = fetch_pyth_latest(logical_symbol=symbol)
    cb = fetch_coinbase_ticker(coinbase_product)

    wall = datetime.now(timezone.utc)
    gr = evaluate_gates(
        primary_observed_at=pyth.observed_at,
        comparator_observed_at=cb.observed_at,
        primary_price=pyth.price,
        comparator_price=cb.price,
        wall_now=wall,
        max_age_sec=max_age_sec,
        max_rel_diff=max_rel_diff,
        degraded_rel_diff=degraded_rel_diff,
    )

    inserted_at = _utc_now_iso()
    row_id = insert_tick(
        conn,
        symbol=symbol,
        inserted_at=inserted_at,
        primary_source=pyth.source,
        primary_price=pyth.price,
        primary_observed_at=pyth.observed_at,
        primary_publish_time=pyth.publish_time,
        primary_raw=pyth.raw if pyth.raw else None,
        comparator_source=cb.source,
        comparator_price=cb.price,
        comparator_observed_at=cb.observed_at,
        comparator_raw=cb.raw if cb.raw else None,
        gate_state=gr.state.value,
        gate_reason=gr.reason,
    )
    conn.close()

    return {
        "kind": "market_snapshot_record_v1",
        "row_id": row_id,
        "db_path": str(path),
        "symbol": symbol,
        "inserted_at": inserted_at,
        "primary": {
            "source": pyth.source,
            "price": pyth.price,
            "observed_at": pyth.observed_at,
            "publish_time": pyth.publish_time,
            "notes": pyth.notes,
        },
        "comparator": {
            "source": cb.source,
            "price": cb.price,
            "observed_at": cb.observed_at,
            "notes": cb.notes,
        },
        "gate": {"state": gr.state.value, "reason": gr.reason, "details": gr.details},
    }


def snapshot_json(**kwargs: Any) -> str:
    return json.dumps(record_market_snapshot(**kwargs), indent=2, ensure_ascii=False)


__all__ = ["record_market_snapshot", "snapshot_json"]
