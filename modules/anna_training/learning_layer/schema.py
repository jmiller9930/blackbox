"""Frozen Phase 1 dataset schema (versioned)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# Bump when columns or semantics change (training/shadow must match).
LEARNING_DATASET_SCHEMA_VERSION = "learning_dataset_baseline_v1"

FieldKind = Literal["raw", "derived", "label"]


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: str
    kind: FieldKind
    source: str


# Phase 1 authoritative lineage: execution_trades (baseline) + policy_evaluations (entry) + market_bars_5m.
PHASE1_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("schema_version", "str", "derived", "constant LEARNING_DATASET_SCHEMA_VERSION"),
    ColumnSpec("created_at_utc", "str|null", "raw", "execution_trades.created_at_utc"),
    ColumnSpec("trade_id", "str", "raw", "execution_trades.trade_id"),
    ColumnSpec("market_event_id_exit", "str", "raw", "execution_trades.market_event_id (exit bar)"),
    ColumnSpec("market_event_id_entry", "str|null", "raw", "context_snapshot.entry_market_event_id"),
    ColumnSpec("symbol", "str", "raw", "execution_trades.symbol"),
    ColumnSpec("timeframe", "str", "raw", "execution_trades.timeframe"),
    ColumnSpec("mode", "str", "raw", "execution_trades.mode"),
    ColumnSpec("side", "str|null", "raw", "execution_trades.side"),
    ColumnSpec("entry_price", "float|null", "raw", "execution_trades.entry_price"),
    ColumnSpec("exit_price", "float|null", "raw", "execution_trades.exit_price"),
    ColumnSpec("size", "float|null", "raw", "execution_trades.size"),
    ColumnSpec("pnl_usd", "float|null", "raw", "execution_trades.pnl_usd"),
    ColumnSpec("exit_reason", "str|null", "raw", "execution_trades.exit_reason"),
    ColumnSpec("entry_open", "float|null", "raw", "market_bars_5m.open @ entry"),
    ColumnSpec("entry_high", "float|null", "raw", "market_bars_5m.high @ entry"),
    ColumnSpec("entry_low", "float|null", "raw", "market_bars_5m.low @ entry"),
    ColumnSpec("entry_close", "float|null", "raw", "market_bars_5m.close @ entry"),
    ColumnSpec("entry_volume_base", "float|null", "raw", "market_bars_5m.volume_base @ entry (nullable if unused)"),
    ColumnSpec("exit_open", "float|null", "raw", "market_bars_5m.open @ exit"),
    ColumnSpec("exit_high", "float|null", "raw", "market_bars_5m.high @ exit"),
    ColumnSpec("exit_low", "float|null", "raw", "market_bars_5m.low @ exit"),
    ColumnSpec("exit_close", "float|null", "raw", "market_bars_5m.close @ exit"),
    ColumnSpec("policy_features_json", "str|null", "raw", "policy_evaluations.features_json @ entry mid"),
    ColumnSpec("trade_success", "bool", "label", "label_specs.trade_success_label(exit_reason)"),
    ColumnSpec("stopped_early", "bool", "label", "label_specs.stopped_early_label(exit_reason)"),
    ColumnSpec("beats_baseline", "bool", "label", "label_specs.beats_baseline_label(pnl_usd) Phase1=flat benchmark"),
    ColumnSpec("whipsaw_flag", "bool", "label", "label_specs.compute_whipsaw_flag(...)"),
    ColumnSpec("row_quality", "str", "derived", "ok | missing_entry_mid | missing_policy | missing_bars | ..."),
)


def schema_dict() -> dict[str, Any]:
    return {
        "learning_dataset_schema_version": LEARNING_DATASET_SCHEMA_VERSION,
        "columns": [
            {
                "name": c.name,
                "dtype": c.dtype,
                "kind": c.kind,
                "source": c.source,
            }
            for c in PHASE1_COLUMNS
        ],
    }
