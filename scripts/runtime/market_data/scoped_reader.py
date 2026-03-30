"""Participant-scoped market data read surface (Phase 5.2a).

Provides a stable read API that wraps the shared canonical ``market_ticks`` store
with participant scope.  Raw market data remains shared — this layer adds
participant context for downstream strategy, approval, and audit consumption.

No execution behavior.  No writes.  No signal invention.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_data.participant_scope import ParticipantScope, validate_participant_scope
from market_data.store import latest_tick


@dataclass(frozen=True)
class ScopedMarketDataSnapshot:
    """Participant-scoped view of the latest market data tick.

    Combines raw shared tick data with the consuming participant's scope.
    This is the canonical return type for scoped market data reads.
    """

    scope: ParticipantScope
    tick: dict[str, Any] | None
    symbol: str
    read_at: str
    gate_state: str | None
    error: str | None = None
    schema_version: str = "scoped_market_data_snapshot_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_latest_scoped_tick(
    scope: ParticipantScope,
    symbol: str = "SOL-USD",
    *,
    db_path: Path | None = None,
) -> ScopedMarketDataSnapshot:
    """Read the latest market tick scoped to a validated participant.

    1. Validates the participant scope deterministically.
    2. Opens a read-only connection to the shared market_data store.
    3. Returns a ScopedMarketDataSnapshot with both raw data and scope context.

    Never writes.  Never modifies the store.  Fails safely on any error.
    """
    read_at = datetime.now(timezone.utc).isoformat()

    try:
        validate_participant_scope(scope)
    except ValueError as exc:
        return ScopedMarketDataSnapshot(
            scope=scope,
            tick=None,
            symbol=symbol,
            read_at=read_at,
            gate_state=None,
            error=f"scope_validation_failed:{exc}",
        )

    if db_path is None:
        try:
            from _paths import default_market_data_path

            db_path = default_market_data_path()
        except Exception as exc:  # noqa: BLE001
            return ScopedMarketDataSnapshot(
                scope=scope,
                tick=None,
                symbol=symbol,
                read_at=read_at,
                gate_state=None,
                error=f"db_path_resolution_failed:{exc}",
            )

    if not db_path.is_file():
        return ScopedMarketDataSnapshot(
            scope=scope,
            tick=None,
            symbol=symbol,
            read_at=read_at,
            gate_state=None,
            error=f"market_data_db_missing:{db_path}",
        )

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tick = latest_tick(conn, symbol)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return ScopedMarketDataSnapshot(
            scope=scope,
            tick=None,
            symbol=symbol,
            read_at=read_at,
            gate_state=None,
            error=f"market_data_read_error:{exc}",
        )

    if tick is None:
        return ScopedMarketDataSnapshot(
            scope=scope,
            tick=None,
            symbol=symbol,
            read_at=read_at,
            gate_state=None,
            error=f"market_data_no_rows:{symbol}",
        )

    return ScopedMarketDataSnapshot(
        scope=scope,
        tick=tick,
        symbol=symbol,
        read_at=read_at,
        gate_state=tick.get("gate_state"),
        error=None,
    )
