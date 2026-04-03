"""One-shot recorder: Pyth + Coinbase + optional Jupiter; when Jupiter is present it is the gate anchor (king)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _paths import default_market_data_path, repo_root

from market_data.feeds_coinbase import fetch_coinbase_ticker
from market_data.feeds_jupiter import fetch_jupiter_implied_sol_usd
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
    include_jupiter: bool | None = None,
    king_pyth_max_rel_diff: float = 0.007,
    king_pyth_degraded_rel_diff: float = 0.004,
    king_coinbase_max_rel_diff: float = 0.025,
    king_coinbase_degraded_rel_diff: float = 0.012,
) -> dict[str, Any]:
    """
    Fetch Pyth + Coinbase + optional Jupiter (SOL→USDC implied USD/SOL), evaluate gates, persist one row.

    When **Jupiter returns a price**, gates use **Jupiter-as-king**: Pyth and Coinbase are each
    checked against Jupiter (Coinbase uses a wider “support” band). When Jupiter is skipped or
    fails, gates fall back to **Pyth vs Coinbase** only.

    Fail-closed: missing prices or bad gates yield gate_state blocked/degraded; row still stored.

    ``include_jupiter``: when True (default unless ``MARKET_DATA_SKIP_JUPITER=1``), fetches a
    fixed-route Jupiter quote.
    """
    root = repo_root()
    if include_jupiter is None:
        include_jupiter = os.environ.get("MARKET_DATA_SKIP_JUPITER", "").strip() not in (
            "1",
            "true",
            "yes",
        )

    path = db_path or default_market_data_path()
    conn = connect_market_db(path)
    ensure_market_schema(conn, root)

    pyth = fetch_pyth_latest(logical_symbol=symbol)
    cb = fetch_coinbase_ticker(coinbase_product)
    jup = fetch_jupiter_implied_sol_usd() if include_jupiter else None

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
        tertiary_observed_at=jup.observed_at if jup else None,
        tertiary_price=jup.price if jup else None,
        king_pyth_max_rel_diff=king_pyth_max_rel_diff,
        king_pyth_degraded_rel_diff=king_pyth_degraded_rel_diff,
        king_coinbase_max_rel_diff=king_coinbase_max_rel_diff,
        king_coinbase_degraded_rel_diff=king_coinbase_degraded_rel_diff,
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
        tertiary_source=jup.source if jup else None,
        tertiary_price=jup.price if jup else None,
        tertiary_observed_at=jup.observed_at if jup else None,
        tertiary_raw=jup.raw if jup else None,
        gate_state=gr.state.value,
        gate_reason=gr.reason,
    )
    conn.close()

    out: dict[str, Any] = {
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
    if include_jupiter and jup is not None:
        out["tertiary"] = {
            "source": jup.source,
            "price": jup.price,
            "observed_at": jup.observed_at,
            "notes": jup.notes,
            "included": True,
        }
    else:
        out["tertiary"] = {"included": bool(include_jupiter), "price": None, "notes": []}
    return out


def snapshot_json(**kwargs: Any) -> str:
    return json.dumps(record_market_snapshot(**kwargs), indent=2, ensure_ascii=False)


__all__ = ["record_market_snapshot", "snapshot_json"]
