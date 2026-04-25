"""
Directive 02 — Student **legal decision packet** builder (pre-reveal only).

Assembles ``student_decision_packet_v1``: causal market state at decision time ``t``
(``open_time <= decision_open_time_ms``), **no** Referee flashcards, **no** future bars.

Causal state is obtained from SQLite ``market_bars_5m`` (same table as replay), read-only.
For TF > 5, the same ``rollup_5m_rows_to_candle_timeframe`` as ``run_manifest_replay`` is applied to
**all** 5m rows for the symbol (same global chunking as replay), then rolled bars with
``open_time <= decision_open_time_ms`` are kept — no boundary skew vs replay (GT_DIRECTIVE_026TF).
For TF = 5, the full 5m series is loaded (replay alignment), then filtered to ``open_time <= t`` and
capped.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.candle_timeframe_runtime import (
    is_allowed_candle_timeframe_minutes_v1,
    rollup_5m_rows_to_candle_timeframe,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1,
    FIELD_STUDENT_CONTEXT_ANNEX_V1,
    SCHEMA_STUDENT_RETRIEVAL_SLICE_V1,
    validate_pre_reveal_bundle_v1,
    validate_student_context_annex_v1,
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


def fetch_all_5m_for_symbol_asc(
    *,
    db_path: Path | str,
    symbol: str,
    table: str = _DEFAULT_TABLE,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Load **all** ``market_bars_5m`` rows for ``symbol``, oldest→newest — same superset as
    ``run_manifest_replay`` uses before rollup (so chunk boundaries match).
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
                WHERE symbol = ?
                ORDER BY open_time ASC
                """,
                (symbol,),
            )
            return [dict(r) for r in cur.fetchall()], None
    except (OSError, sqlite3.Error) as e:
        return [], f"{type(e).__name__}: {e}"


def build_student_decision_packet_v1(
    *,
    db_path: Path | str,
    symbol: str,
    decision_open_time_ms: int,
    candle_timeframe_minutes: int,
    table: str = _DEFAULT_TABLE,
    max_bars_in_packet: int = 10_000,
    notes: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Build ``student_decision_packet_v1`` — **only** causal OHLCV rows + envelope metadata.

    Does **not** load replay outcomes, trades, PnL, or post-hoc batch summaries. Optional
    ``notes`` is for operator debugging strings only (must not contain outcome key names).

    ``candle_timeframe_minutes`` must be one of 5, 15, 60, 240 — same as the run's replay bar width.
    Coarser TFs are built from 5m base rows (rollup), never raw 5m in the student-visible series.

    Returns ``(packet, None)`` or ``(None, error)``.
    """
    if not is_allowed_candle_timeframe_minutes_v1(candle_timeframe_minutes):
        return None, f"invalid candle_timeframe_minutes: {candle_timeframe_minutes!r} (expected 5, 15, 60, or 240)"
    tf = int(candle_timeframe_minutes)
    cut = int(decision_open_time_ms)
    all_5m, err = fetch_all_5m_for_symbol_asc(
        db_path=db_path,
        symbol=symbol,
        table=table,
    )
    if err:
        return None, err
    rollup_audit: dict[str, Any] | None = None
    if tf == 5:
        causal_5m = [r for r in all_5m if int(r.get("open_time") or 0) <= cut]
        if len(causal_5m) > int(max_bars_in_packet):
            bars = causal_5m[-int(max_bars_in_packet) :]
        else:
            bars = causal_5m
    else:
        rolled, rollup_audit = rollup_5m_rows_to_candle_timeframe(
            list(all_5m),
            target_minutes=tf,
        )
        causal = [r for r in rolled if int(r.get("open_time") or 0) <= cut]
        if len(causal) > int(max_bars_in_packet):
            bars = causal[-int(max_bars_in_packet) :]
        else:
            bars = causal
    packet: dict[str, Any] = {
        "schema": SCHEMA_STUDENT_DECISION_PACKET_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "symbol": symbol,
        "table": table,
        "candle_timeframe_minutes": tf,
        "candle_timeframe_base_source_table": _DEFAULT_TABLE,
        "decision_open_time_ms": int(decision_open_time_ms),
        "graded_unit_type_hint": "closed_trade",
        "bars_inclusive_up_to_t": bars,
        "bar_count": len(bars),
    }
    if rollup_audit is not None:
        packet["candle_timeframe_rollup_audit_v1"] = rollup_audit
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
    ctf = packet.get("candle_timeframe_minutes")
    if not isinstance(ctf, int) or not is_allowed_candle_timeframe_minutes_v1(ctf):
        errs.append("candle_timeframe_minutes must be int in {5, 15, 60, 240}")
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

    raws = packet.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
    if raws is not None:
        if not isinstance(raws, list):
            errs.append(f"{FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1} must be a list or absent")
        else:
            for i, sl in enumerate(raws):
                if not isinstance(sl, dict):
                    errs.append(f"{FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1}[{i}] must be dict")
                    continue
                if sl.get("schema") != SCHEMA_STUDENT_RETRIEVAL_SLICE_V1:
                    errs.append(
                        f"{FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1}[{i}].schema must be {SCHEMA_STUDENT_RETRIEVAL_SLICE_V1!r}"
                    )
                if sl.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
                    errs.append(
                        f"{FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1}[{i}].contract_version invalid"
                    )

    annex = packet.get(FIELD_STUDENT_CONTEXT_ANNEX_V1)
    if annex is not None:
        errs.extend(validate_student_context_annex_v1(annex))

    errs.extend(validate_pre_reveal_bundle_v1(packet))
    return errs


def attach_student_context_annex_v1(
    packet: dict[str, Any],
    annex: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Attach a **versioned** context annex to a legal decision packet and re-validate.

    Rich-indicator builders may produce ``student_context_annex_v1`` offline; production paths
    attach only what passes ``validate_student_context_annex_v1`` and full packet validation.
    """
    aerr = validate_student_context_annex_v1(annex)
    if aerr:
        return None, "student_context_annex_v1 invalid: " + "; ".join(aerr)
    out = {**packet, FIELD_STUDENT_CONTEXT_ANNEX_V1: annex}
    perr = validate_student_decision_packet_v1(out)
    if perr:
        return None, "packet with annex invalid: " + "; ".join(perr)
    return out, None
