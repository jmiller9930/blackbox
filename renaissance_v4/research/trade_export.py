"""
Normalized closed-trade export for robustness / Monte Carlo (read-only on replay outcomes).

Does not modify baseline behavior; serializes OutcomeRecord fields required by the robustness spec.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord


def outcome_from_dict(t: dict[str, Any]) -> OutcomeRecord:
    """Rehydrate minimal OutcomeRecord for deterministic metrics (robustness compare)."""
    return OutcomeRecord(
        trade_id=str(t.get("trade_id", "")),
        symbol=str(t.get("symbol", "")),
        direction=str(t.get("direction", "")),
        entry_time=int(t.get("entry_time", 0)),
        exit_time=int(t.get("exit_time", 0)),
        entry_price=float(t.get("entry_price", 0.0)),
        exit_price=float(t.get("exit_price", 0.0)),
        pnl=float(t.get("pnl", 0.0)),
        mae=float(t.get("mae", 0.0)),
        mfe=float(t.get("mfe", 0.0)),
        exit_reason=str(t.get("exit_reason", "")),
        contributing_signals=list(t.get("contributing_signals") or []),
        regime=str(t.get("regime", "")),
        size_tier=str(t.get("size_tier", "")),
        notional_fraction=float(t.get("notional_fraction", 0.0)),
        metadata=dict(t.get("metadata") or {}),
    )


def outcome_to_dict(o: OutcomeRecord) -> dict[str, Any]:
    return {
        "trade_id": o.trade_id,
        "symbol": o.symbol,
        "direction": o.direction,
        "entry_time": o.entry_time,
        "exit_time": o.exit_time,
        "entry_price": o.entry_price,
        "exit_price": o.exit_price,
        "pnl": o.pnl,
        "mae": o.mae,
        "mfe": o.mfe,
        "exit_reason": o.exit_reason,
        "contributing_signals": list(o.contributing_signals),
        "regime": o.regime,
        "size_tier": o.size_tier,
        "notional_fraction": o.notional_fraction,
        "metadata": dict(o.metadata),
    }


def outcomes_to_dicts(outcomes: list[OutcomeRecord]) -> list[dict[str, Any]]:
    return [outcome_to_dict(o) for o in outcomes]


def export_trades_json(outcomes: list[OutcomeRecord], path: Path, *, dataset_bars: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "renaissance_v4_closed_trades_v1",
        "dataset_bars": dataset_bars,
        "trade_count": len(outcomes),
        "trades": outcomes_to_dicts(outcomes),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_trades_json(path: Path) -> tuple[list[dict[str, Any]], int | None]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw, None
    trades = raw.get("trades") or []
    bars = raw.get("dataset_bars")
    return trades, bars if isinstance(bars, int) else None


def pnl_series_from_trade_dicts(trades: list[dict[str, Any]]) -> list[float]:
    return [float(t["pnl"]) for t in trades]


def outcomes_from_trade_dicts(trades: list[dict[str, Any]]) -> list[OutcomeRecord]:
    ordered = sorted(trades, key=lambda x: int(x.get("exit_time", 0)))
    return [outcome_from_dict(t) for t in ordered]
