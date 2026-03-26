"""Phase 5.2a — participant-scoped market-data read contracts (read-only).

Goal: Provide a stable, participant/tier-scoped read API for downstream strategy/approval/audit
without implying execution.

This module does NOT write to market_data.db.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_ALLOWED_RISK_TIERS = {"tier_1", "tier_2", "tier_3"}


@dataclass(frozen=True)
class MarketDataReadContractV1:
    """Required participant scope + read request parameters (Phase 5.2a)."""

    participant_id: str
    participant_type: str
    account_id: str
    wallet_context: str
    risk_tier: str
    interaction_path: str
    market_symbol: str
    schema_version: str = "market_data_read_contract_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_market_data_read_contract(obj: MarketDataReadContractV1) -> None:
    missing = [
        name
        for name in (
            "participant_id",
            "participant_type",
            "account_id",
            "wallet_context",
            "risk_tier",
            "interaction_path",
            "market_symbol",
        )
        if not str(getattr(obj, name, "") or "").strip()
    ]
    if missing:
        raise ValueError(f"market_data_read_contract_missing_fields:{','.join(missing)}")
    if obj.risk_tier not in _ALLOWED_RISK_TIERS:
        raise ValueError(f"market_data_read_contract_invalid_risk_tier:{obj.risk_tier}")


def _resolve_market_data_path() -> Path:
    from _paths import default_market_data_path

    return default_market_data_path()


def connect_market_db_readonly(db_path: Path) -> sqlite3.Connection:
    """Read-only connection with query_only enforced."""

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON;")
    return conn


def load_latest_tick_scoped(
    contract: MarketDataReadContractV1,
    *,
    db_path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (tick_dict, None) on success, else (None, error_string).

    Fail-closed behavior:
    - invalid/missing contract fields => error
    - missing DB => error
    - query errors/no rows => error

    Optional gate: if BLACKBOX_MARKET_DATA_REQUIRE_OK=1, reject non-ok gate_state.
    """

    try:
        validate_market_data_read_contract(contract)
    except ValueError as exc:
        return None, str(exc)

    path = db_path or _resolve_market_data_path()
    if not path.is_file():
        return None, f"market_data_db_missing:{path}"

    try:
        conn = connect_market_db_readonly(path)
        try:
            row = conn.execute(
                """
                SELECT id, symbol, inserted_at,
                       primary_source, primary_price, primary_observed_at,
                       comparator_source, comparator_price, comparator_observed_at,
                       gate_state, gate_reason
                FROM market_ticks
                WHERE symbol = ?
                ORDER BY inserted_at DESC, id DESC
                LIMIT 1
                """,
                (contract.market_symbol,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            return None, f"market_data_query_error:{exc}"
        finally:
            conn.close()

        if row is None:
            return None, f"market_data_no_rows:{contract.market_symbol}"

        cols = [
            "id",
            "symbol",
            "inserted_at",
            "primary_source",
            "primary_price",
            "primary_observed_at",
            "comparator_source",
            "comparator_price",
            "comparator_observed_at",
            "gate_state",
            "gate_reason",
        ]
        tick = dict(zip(cols, row))

        require_ok = os.environ.get("BLACKBOX_MARKET_DATA_REQUIRE_OK", "").strip() in (
            "1",
            "true",
            "yes",
        )
        if require_ok and tick.get("gate_state") != "ok":
            return None, f"market_data_gate_blocked:{tick.get('gate_state')}:{tick.get('gate_reason')}"

        # Echo scope into the response for auditability (no mutation, just return payload).
        tick["participant_scope"] = {
            "participant_id": contract.participant_id,
            "participant_type": contract.participant_type,
            "account_id": contract.account_id,
            "wallet_context": contract.wallet_context,
            "risk_tier": contract.risk_tier,
            "interaction_path": contract.interaction_path,
            "schema_version": contract.schema_version,
        }
        return tick, None
    except Exception as exc:  # noqa: BLE001
        return None, f"market_data_unexpected:{exc}"

