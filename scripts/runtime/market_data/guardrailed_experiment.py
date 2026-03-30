"""Phase 5.3e — Guardrailed self-directed paper/backtest experiments.

Orchestrates existing Phase 5.3a–d surfaces in one deterministic, auditable path:

1. Stored-data simulation (5.3b) over a bounded tick window.
2. Strategy evaluation on the **last tick in that same window** (aligned with simulation).
3. Pre-trade fast gate (5.3c) with simulation aggregate.
4. Tier-aligned strategy selection (5.3d).

``ParticipantScope`` is **immutable**; ``risk_tier`` is never assigned or escalated here.
No execution, no tier mutation, no Billy/L3/L4.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market_data.backtest_simulation import SimulationRunV1, run_stored_simulation
from market_data.participant_scope import ParticipantScope, validate_participant_scope
from market_data.pre_trade_fast_gate import PreTradeGateV1, run_pre_trade_fast_gate
from market_data.scoped_reader import ScopedMarketDataSnapshot
from market_data.store import ticks_chronological
from market_data.strategy_eval import STRATEGY_VERSION, StrategyEvaluationV1, _evaluate_from_snapshot
from market_data.strategy_selection import StrategySelectionV1, select_tier_aligned_strategy

GUARDRAILED_EXPERIMENT_VERSION = "guardrailed_experiment_v1"


def _resolve_db_path(db_path: Path | None) -> Path:
    if db_path is not None:
        return db_path
    from _paths import default_market_data_path

    return default_market_data_path()


def _evaluation_on_last_window_tick(
    scope: ParticipantScope,
    symbol: str,
    *,
    db_path: Path,
    max_ticks: int,
) -> StrategyEvaluationV1:
    """Evaluate strategy on the last tick of the same oldest-first window as simulation."""
    run_at = datetime.now(timezone.utc).isoformat()
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only = ON;")
            rows = ticks_chronological(conn, symbol, limit=max_ticks)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="db_read_failed",
            gate_state=None,
            primary_price=None,
            comparator_price=None,
            spread_pct=None,
            tier_thresholds_used=None,
            evaluated_at=run_at,
            error=f"evaluation_window_read:{exc}",
        )

    if not rows:
        return StrategyEvaluationV1(
            participant_scope=scope,
            symbol=symbol,
            strategy_version=STRATEGY_VERSION,
            evaluation_outcome="abstain",
            confidence=0.0,
            abstain_reason="no_ticks_in_window",
            gate_state=None,
            primary_price=None,
            comparator_price=None,
            spread_pct=None,
            tier_thresholds_used=None,
            evaluated_at=run_at,
        )

    last = rows[-1]
    read_at = str(last.get("inserted_at") or run_at)
    snapshot = ScopedMarketDataSnapshot(
        scope=scope,
        tick=last,
        symbol=symbol,
        read_at=read_at,
        gate_state=last.get("gate_state"),
        error=None,
    )
    return _evaluate_from_snapshot(snapshot, scope, symbol, evaluated_at=read_at)


@dataclass(frozen=True)
class GuardrailedExperimentRunV1:
    """Single end-to-end paper experiment artifact (5.3e)."""

    experiment_id: str
    guardrailed_experiment_version: str
    participant_scope: ParticipantScope
    symbol: str
    original_risk_tier: str
    max_ticks: int
    simulation: SimulationRunV1
    evaluation: StrategyEvaluationV1 | None
    gate: PreTradeGateV1 | None
    selection: StrategySelectionV1 | None
    tier_unchanged_assertion: bool
    guardrail_notes: tuple[str, ...]
    run_at: str
    error: str | None = None
    schema_version: str = "guardrailed_experiment_run_v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["participant_scope"] = self.participant_scope.to_dict()
        d["simulation"] = self.simulation.to_dict()
        d["evaluation"] = self.evaluation.to_dict() if self.evaluation else None
        d["gate"] = self.gate.to_dict() if self.gate else None
        d["selection"] = self.selection.to_dict() if self.selection else None
        return d


def run_guardrailed_paper_experiment(
    scope: ParticipantScope,
    symbol: str,
    *,
    experiment_id: str = "default",
    max_ticks: int = 500,
    db_path: Path | None = None,
) -> GuardrailedExperimentRunV1:
    """Run one guardrailed paper/backtest experiment (read-only).

    ``scope.risk_tier`` is fixed for the whole run; selection stays within that tier.
    """
    run_at = datetime.now(timezone.utc).isoformat()
    original_tier = scope.risk_tier
    notes: list[str] = [
        "participant_scope_immutable",
        "no_tier_assignment_in_experiment_layer",
        "uses_5_3b_simulation_5_3c_gate_5_3d_selection",
    ]

    try:
        validate_participant_scope(scope)
    except ValueError as exc:
        return GuardrailedExperimentRunV1(
            experiment_id=experiment_id,
            guardrailed_experiment_version=GUARDRAILED_EXPERIMENT_VERSION,
            participant_scope=scope,
            symbol=symbol,
            original_risk_tier=original_tier,
            max_ticks=max_ticks,
            simulation=SimulationRunV1(
                participant_scope=scope,
                symbol=symbol,
                strategy_version=STRATEGY_VERSION,
                simulation_version="stored_simulation_v1",
                sample_count=0,
                window_first_inserted_at=None,
                window_last_inserted_at=None,
                outcome_counts={},
                abstain_count=0,
                skip_count=0,
                mean_confidence_non_abstain=None,
                run_at=run_at,
                error=f"scope_invalid:{exc}",
            ),
            evaluation=None,
            gate=None,
            selection=None,
            tier_unchanged_assertion=True,
            guardrail_notes=tuple(notes),
            run_at=run_at,
            error=f"scope_invalid:{exc}",
        )

    path = _resolve_db_path(db_path)
    sim = run_stored_simulation(scope, symbol, db_path=path, max_ticks=max_ticks)

    if sim.error is not None or sim.sample_count == 0:
        return GuardrailedExperimentRunV1(
            experiment_id=experiment_id,
            guardrailed_experiment_version=GUARDRAILED_EXPERIMENT_VERSION,
            participant_scope=scope,
            symbol=symbol,
            original_risk_tier=original_tier,
            max_ticks=max_ticks,
            simulation=sim,
            evaluation=None,
            gate=None,
            selection=None,
            tier_unchanged_assertion=scope.risk_tier == original_tier,
            guardrail_notes=tuple(notes + ["simulation_empty_or_error_skip_downstream"]),
            run_at=run_at,
            error=sim.error,
        )

    ev = _evaluation_on_last_window_tick(scope, symbol, db_path=path, max_ticks=max_ticks)
    gate = run_pre_trade_fast_gate(ev, simulation=sim)
    sel = select_tier_aligned_strategy(ev, gate=gate)

    tier_ok = (
        scope.risk_tier == original_tier
        and sel.selected_risk_tier == original_tier
        and ev.participant_scope.risk_tier == original_tier
    )
    if not tier_ok:
        notes.append("TIER_INVARIANT_VIOLATION_RECORDED")
    return GuardrailedExperimentRunV1(
        experiment_id=experiment_id,
        guardrailed_experiment_version=GUARDRAILED_EXPERIMENT_VERSION,
        participant_scope=scope,
        symbol=symbol,
        original_risk_tier=original_tier,
        max_ticks=max_ticks,
        simulation=sim,
        evaluation=ev,
        gate=gate,
        selection=sel,
        tier_unchanged_assertion=tier_ok,
        guardrail_notes=tuple(notes),
        run_at=run_at,
        error=None if tier_ok else "tier_invariant_failed",
    )
