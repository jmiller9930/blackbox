"""
Directive 02 — Student **legal decision packet** builder (pre-reveal only).

Assembles ``student_decision_packet_v1``: causal market state at decision time ``t``
(``open_time <= decision_open_time_ms``), **no** Referee flashcards, **no** future bars.

Causal state is obtained from SQLite ``market_bars_5m`` (same table as replay), read-only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    validate_pre_reveal_bundle_v1,
)

SCHEMA_STUDENT_DECISION_PACKET_V1 = "student_decision_packet_v1"

# Same allowlist as Anna visible window (5m SOL path).
_DEFAULT_TABLE = "market_bars_5m"


def _rows_chronological(rows_desc: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows_desc, key=lambda r: int(r.get("open_time") or 0))


def fetch_bars_causal_up_to(
    *,
    db_path: Path | str,
    symbol: str,
    decision_open_time_ms: int,
    table: str = _DEFAULT_TABLE,
    max_bars_in_packet: int = 10_000,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Return bars with ``open_time <= decision_open_time_ms``, oldest→newest.

    Caps by taking the **most recent** ``max_bars_in_packet`` bars still satisfying the cutoff
    (so very long history does not blow memory). All returned rows are causal at ``t``.
    """
    p = Path(db_path)
    if not p.is_file():
        return [], f"database file missing: {p}"
    if table != _DEFAULT_TABLE:
        table = _DEFAULT_TABLE
    try:
        with sqlite3.connect(str(p)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                f"""
                SELECT open_time, symbol, open, high, low, close, volume
                FROM {table}
                WHERE symbol = ? AND open_time <= ?
                ORDER BY open_time DESC
                LIMIT ?
                """,
                (symbol, int(decision_open_time_ms), int(max_bars_in_packet)),
            )
            rows_desc = [dict(r) for r in cur.fetchall()]
    except (OSError, sqlite3.Error) as e:
        return [], f"{type(e).__name__}: {e}"
    return _rows_chronological(rows_desc), None


def build_student_decision_packet_v1(
    *,
    db_path: Path | str,
    symbol: str,
    decision_open_time_ms: int,
    table: str = _DEFAULT_TABLE,
    max_bars_in_packet: int = 10_000,
    notes: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Build ``student_decision_packet_v1`` — **only** causal OHLCV rows + envelope metadata.

    Does **not** load replay outcomes, trades, PnL, or post-hoc batch summaries. Optional
    ``notes`` is for operator debugging strings only (must not contain outcome key names).

    Returns ``(packet, None)`` or ``(None, error)``.
    """
    bars, err = fetch_bars_causal_up_to(
        db_path=db_path,
        symbol=symbol,
        decision_open_time_ms=decision_open_time_ms,
        table=table,
        max_bars_in_packet=max_bars_in_packet,
    )
    if err:
        return None, err
    packet: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_DECISION_PACKET_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "symbol": symbol,
        "table": table,
        "decision_open_time_ms": int(decision_open_time_ms),
        "graded_unit_type_hint": "closed_trade",
        "bars_inclusive_up_to_t": bars,
        "bar_count": len(bars),
    }
    if notes:
        packet["builder_notes"] = notes[:4000]
    vpre = validate_pre_reveal_bundle_v1(packet)
    if vpre:
        return None, "internal error: packet failed pre_reveal validation: " + "; ".join(vpre)
    return packet, None


def validate_student_decision_packet_v1(packet: Any) -> list[str]:
    """Structural + pre-reveal validation for ``student_decision_packet_v1``."""
    errs: list[str] = []
    if not isinstance(packet, dict):
        return ["student_decision_packet_v1 must be a dict"]
    if packet.get("schema") != SCHEMA_STUDENT_DECISION_PACKET_V1:
        errs.append(f"schema must be {SCHEMA_STUDENT_DECISION_PACKET_V1!r}")
    if packet.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append(f"contract_version must be {CONTRACT_VERSION_STUDENT_PROCTOR_V1}")
    if not isinstance(packet.get("symbol"), str) or not packet.get("symbol"):
        errs.append("symbol must be non-empty string")
    t_cut = packet.get("decision_open_time_ms")
    if not isinstance(t_cut, int):
        errs.append("decision_open_time_ms must be int (ms)")
    bars = packet.get("bars_inclusive_up_to_t")
    if not isinstance(bars, list):
        errs.append("bars_inclusive_up_to_t must be a list")
    else:
        for i, row in enumerate(bars):
            if not isinstance(row, dict):
                errs.append(f"bars[{i}] must be dict")
                continue
            ot = row.get("open_time")
            if t_cut is not None and isinstance(ot, int) and ot > t_cut:
                errs.append(f"causal violation: bars[{i}].open_time > decision_open_time_ms")
    errs.extend(validate_pre_reveal_bundle_v1(packet))
    return errs
