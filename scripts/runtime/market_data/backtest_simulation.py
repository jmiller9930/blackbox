"""Phase 5.3b — Stored-data backtest / simulation loop.

Reads historical rows from the shared ``market_ticks`` store (read-only) and
reuses Phase 5.3a :func:`strategy_eval._evaluate_from_snapshot` for each tick
in chronological order.  Emits a single aggregated :class:`SimulationRunV1`
artifact.  No execution, no writes, no tier changes.

Deterministic given the same DB slice and participant scope.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_data.participant_scope import ParticipantScope, validate_participant_scope
from market_data.read_contracts import MarketDataReadContractV1, validate_market_data_read_contract
from market_data.scoped_reader import ScopedMarketDataSnapshot
from market_data.store import ticks_chronological
from market_data.strategy_eval import STRATEGY_VERSION, _evaluate_from_snapshot

SIMULATION_VERSION = "stored_simulation_v1"

DEFAULT_MAX_TICKS = 500


@dataclass(frozen=True)
class SimulationRunV1:
    """Aggregated simulation artifact over a chronological tick window."""

    participant_scope: ParticipantScope
    symbol: str
    strategy_version: str
    simulation_version: str
    sample_count: int
    window_first_inserted_at: str | None
    window_last_inserted_at: str | None
    outcome_counts: dict[str, int]
    abstain_count: int
    skip_count: int
    mean_confidence_non_abstain: float | None
    run_at: str
    error: str | None = None
    schema_version: str = "simulation_run_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_db_path(db_path: Path | None) -> Path:
    if db_path is not None:
        return db_path
    from _paths import default_market_data_path

    return default_market_data_path()


def run_stored_simulation(
    scope: ParticipantScope,
    symbol: str,
    *,
    db_path: Path | None = None,
    max_ticks: int = DEFAULT_MAX_TICKS,
) -> SimulationRunV1:
    """Run a deterministic stored-data simulation for one symbol.

    Loads up to ``max_ticks`` rows oldest-first, evaluates each with the 5.3a
    strategy logic, and aggregates counts.  Read-only.
    """
    run_at = datetime.now(timezone.utc).isoformat()
    try:
        validate_participant_scope(scope)
    except ValueError as exc:
        return SimulationRunV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            simulation_version=SIMULATION_VERSION,
            sample_count=0,
            window_first_inserted_at=None,
            window_last_inserted_at=None,
            outcome_counts={},
            abstain_count=0,
            skip_count=0,
            mean_confidence_non_abstain=None,
            run_at=run_at,
            error=f"scope_validation_failed:{exc}",
        )

    path = _resolve_db_path(db_path)
    if not path.is_file():
        return SimulationRunV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            simulation_version=SIMULATION_VERSION,
            sample_count=0,
            window_first_inserted_at=None,
            window_last_inserted_at=None,
            outcome_counts={},
            abstain_count=0,
            skip_count=0,
            mean_confidence_non_abstain=None,
            run_at=run_at,
            error=f"market_data_db_missing:{path}",
        )

    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only = ON;")
            rows = ticks_chronological(conn, symbol, limit=max_ticks)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return SimulationRunV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            simulation_version=SIMULATION_VERSION,
            sample_count=0,
            window_first_inserted_at=None,
            window_last_inserted_at=None,
            outcome_counts={},
            abstain_count=0,
            skip_count=0,
            mean_confidence_non_abstain=None,
            run_at=run_at,
            error=f"market_data_read_error:{exc}",
        )

    if not rows:
        return SimulationRunV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            simulation_version=SIMULATION_VERSION,
            sample_count=0,
            window_first_inserted_at=None,
            window_last_inserted_at=None,
            outcome_counts={},
            abstain_count=0,
            skip_count=0,
            mean_confidence_non_abstain=None,
            run_at=run_at,
            error="market_data_no_rows",
        )

    outcome_counts: dict[str, int] = {
        "long_bias": 0,
        "short_bias": 0,
        "neutral": 0,
        "abstain": 0,
    }
    abstain_count = 0
    skip_count = 0
    conf_sum = 0.0
    conf_n = 0

    first_at = rows[0].get("inserted_at")
    last_at = rows[-1].get("inserted_at")

    for tick in rows:
        read_at = str(tick.get("inserted_at") or run_at)
        snapshot = ScopedMarketDataSnapshot(
            scope=scope,
            tick=tick,
            symbol=symbol,
            read_at=read_at,
            gate_state=tick.get("gate_state"),
            error=None,
        )
        ev = _evaluate_from_snapshot(snapshot, scope, symbol, evaluated_at=read_at)
        o = ev.evaluation_outcome
        if o in outcome_counts:
            outcome_counts[o] += 1
        else:
            skip_count += 1
            continue
        if o == "abstain":
            abstain_count += 1
        else:
            conf_sum += float(ev.confidence)
            conf_n += 1

    mean_conf: float | None = None
    if conf_n > 0:
        mean_conf = round(conf_sum / conf_n, 6)

    return SimulationRunV1(
        participant_scope=scope,
        symbol=symbol,
        strategy_version=STRATEGY_VERSION,
        simulation_version=SIMULATION_VERSION,
        sample_count=len(rows),
        window_first_inserted_at=str(first_at) if first_at else None,
        window_last_inserted_at=str(last_at) if last_at else None,
        outcome_counts=outcome_counts,
        abstain_count=abstain_count,
        skip_count=skip_count,
        mean_confidence_non_abstain=mean_conf,
        run_at=run_at,
        error=None,
    )


def run_stored_simulation_from_read_contract(
    contract: MarketDataReadContractV1,
    *,
    db_path: Path | None = None,
    max_ticks: int = DEFAULT_MAX_TICKS,
) -> SimulationRunV1:
    """Phase 5.3b entry point using Phase 5.2a read contract (symbol + scope)."""

    run_at = datetime.now(timezone.utc).isoformat()
    try:
        validate_market_data_read_contract(contract)
    except ValueError as exc:
        scope = contract.to_participant_scope()
        return SimulationRunV1(
            participant_scope=scope,
            symbol=str(contract.market_symbol or "").strip() or "?",
            strategy_version=STRATEGY_VERSION,
            simulation_version=SIMULATION_VERSION,
            sample_count=0,
            window_first_inserted_at=None,
            window_last_inserted_at=None,
            outcome_counts={},
            abstain_count=0,
            skip_count=0,
            mean_confidence_non_abstain=None,
            run_at=run_at,
            error=f"market_data_read_contract_invalid:{exc}",
        )
    scope = contract.to_participant_scope()
    return run_stored_simulation(
        scope,
        contract.market_symbol.strip(),
        db_path=db_path,
        max_ticks=max_ticks,
    )
