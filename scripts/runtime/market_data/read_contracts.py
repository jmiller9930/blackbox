"""Phase 5.2a — participant-scoped market-data read contracts (read-only).

Provides a stable, participant/tier-scoped read API for downstream strategy,
approval, and audit consumers.  Raw shared market_ticks storage is the canonical
source; this module adds participant scope without modifying the store.

This module does NOT write to market_data.db.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from market_data.participant_scope import (
    VALID_PARTICIPANT_TYPES,
    VALID_RISK_TIERS,
    ParticipantScope,
    validate_participant_scope,
)


@dataclass(frozen=True)
class MarketDataReadContractV1:
    """Required participant scope + read request parameters (Phase 5.2a).

    Combines a full ParticipantScope identity with a market_symbol request field.
    Validation delegates participant identity checks to validate_participant_scope
    and additionally requires market_symbol.
    """

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

    def to_participant_scope(self) -> ParticipantScope:
        return ParticipantScope(
            participant_id=self.participant_id,
            participant_type=self.participant_type,
            account_id=self.account_id,
            wallet_context=self.wallet_context,
            risk_tier=self.risk_tier,
            interaction_path=self.interaction_path,
        )


def validate_market_data_read_contract(obj: MarketDataReadContractV1) -> None:
    """Validate participant identity fields and market_symbol.

    Delegates identity validation to validate_participant_scope (which checks
    participant_type and risk_tier against canonical allowed values).  Errors
    are re-raised under the ``market_data_read_contract_`` namespace so callers
    see a consistent prefix.
    """
    scope = obj.to_participant_scope()
    try:
        validate_participant_scope(scope)
    except ValueError as exc:
        msg = str(exc).replace("participant_scope_", "market_data_read_contract_")
        raise ValueError(msg) from exc

    if not str(getattr(obj, "market_symbol", "") or "").strip():
        raise ValueError("market_data_read_contract_missing_fields:market_symbol")


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
                       tertiary_source, tertiary_price, tertiary_observed_at,
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
            "tertiary_source",
            "tertiary_price",
            "tertiary_observed_at",
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

