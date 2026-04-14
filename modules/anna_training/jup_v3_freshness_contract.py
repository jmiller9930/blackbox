"""
Jupiter_3 (Binance strategy bars) — **freshness tolerance contract** and timeline invariant proof.

Single definition of “expected last closed 5m candle” lives in ``market_data.canonical_time``
(``last_closed_candle_open_utc`` / ``format_candle_open_iso_z``). JUPv3 authoritative table is
``binance_strategy_bars_5m`` only — never ``market_bars_5m`` for this contract.

Environment:
  BLACKBOX_JUPV3_MAX_ACCEPTABLE_CLOSED_BUCKET_LAG — non-negative integer (default **1**).
  Lag 0 = in lock. Lags 1..max = **warning** (within contract). Lag > max = **fault**.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import BASELINE_POLICY_SLOT_JUP_V3

JUP_V3_FRESHNESS_CONTRACT_ID = "jup_v3_five_m_binance_v1"
JUP_V3_FRESHNESS_CONTRACT_VERSION = "1.0"


def allowed_closed_bucket_lag_max() -> int:
    """Closed buckets behind wall-clock ``last_closed_candle_open_utc`` still treated as warning (not fault)."""
    raw = (os.environ.get("BLACKBOX_JUPV3_MAX_ACCEPTABLE_CLOSED_BUCKET_LAG") or "").strip()
    if not raw:
        return 1
    try:
        n = int(raw)
    except ValueError:
        return 1
    return max(0, min(24, n))


def freshness_severity(closed_bucket_lag: int | None, *, allowed_max: int) -> str:
    if closed_bucket_lag is None:
        return "unknown"
    if closed_bucket_lag <= 0:
        return "ok"
    if closed_bucket_lag <= allowed_max:
        return "warning"
    return "fault"


def within_freshness_contract(closed_bucket_lag: int | None, *, allowed_max: int) -> bool:
    if closed_bucket_lag is None:
        return False
    return closed_bucket_lag <= allowed_max


def enrich_jup_v3_five_m_freshness(out: dict[str, Any]) -> dict[str, Any]:
    """
    Mutate **JUPv3** ``five_m_ingest_freshness`` dict with contract fields (same dict returned).
    No-op if not Binance path / missing lag.
    """
    if (out.get("freshness_source") or "") != "binance_strategy_bars_5m":
        out["freshness_contract_applies"] = False
        return out
    mx = allowed_closed_bucket_lag_max()
    lag = out.get("closed_bucket_lag")
    try:
        lag_i = int(lag) if lag is not None else None
    except (TypeError, ValueError):
        lag_i = None
    sev = freshness_severity(lag_i, allowed_max=mx)
    out["freshness_contract_applies"] = True
    out["freshness_contract_id"] = JUP_V3_FRESHNESS_CONTRACT_ID
    out["freshness_contract_version"] = JUP_V3_FRESHNESS_CONTRACT_VERSION
    out["allowed_closed_bucket_lag_max"] = mx
    out["freshness_severity"] = sev
    out["within_freshness_contract"] = within_freshness_contract(lag_i, allowed_max=mx)
    return out


def build_jup_v3_timeline_proof(
    *,
    trade_chain: dict[str, Any] | None,
    jupiter_policy_snapshot: dict[str, Any] | None,
    market_db_path: Path | None,
) -> dict[str, Any] | None:
    """
    Operator/engineering proof: one object per bundle when active slot is JUPv3.

    Invariant (deterministic):
    - ``expected_last_closed`` from ``canonical_time`` (via ``five_m_ingest_freshness``).
    - ``db_max`` and ``selected_tile`` from ``binance_strategy_bars_5m`` / tile selection proof.
    - **PASS** iff tile candle == DB max AND closed_bucket_lag <= allowed max AND selection_matches_db_max.
    """
    tc = trade_chain if isinstance(trade_chain, dict) else {}
    jp = jupiter_policy_snapshot if isinstance(jupiter_policy_snapshot, dict) else {}
    slot = (tc.get("baseline_jupiter_policy") or {}).get("active_id")
    if slot != BASELINE_POLICY_SLOT_JUP_V3:
        return None
    ff = tc.get("five_m_ingest_freshness") if isinstance(tc.get("five_m_ingest_freshness"), dict) else {}
    tbp = jp.get("tile_bar_selection_proof") if isinstance(jp.get("tile_bar_selection_proof"), dict) else {}
    mx = allowed_closed_bucket_lag_max()
    lag = ff.get("closed_bucket_lag")
    try:
        lag_i = int(lag) if lag is not None else None
    except (TypeError, ValueError):
        lag_i = None

    exp = str(ff.get("expected_last_closed_candle_open_utc") or "").strip() or None
    dbm = str(ff.get("db_newest_closed_candle_open_utc") or "").strip() or None
    sel = str(tbp.get("selected_candle_open_utc") or "").strip() or None
    sel_match = tbp.get("selection_matches_db_max")
    tile_ok = bool(sel_match) if sel_match is not None else False
    db_tile = str(tbp.get("db_max_candle_open_utc") or "").strip() or None
    db_consistent = not (dbm and db_tile and dbm != db_tile)

    within = within_freshness_contract(lag_i, allowed_max=mx)
    invariant_pass = bool(
        tile_ok
        and within
        and db_consistent
        and dbm
        and sel
        and dbm == sel
    )
    sev = freshness_severity(lag_i, allowed_max=mx)
    diagnostic: str | None = None
    if not invariant_pass:
        parts = []
        if not tile_ok:
            parts.append("tile_selected_candle_open_neq_db_max")
        if not within:
            parts.append(f"closed_bucket_lag({lag_i})_exceeds_allowed_max({mx})")
        if not db_consistent:
            parts.append(f"freshness_db_max({dbm})_neq_tile_proof_db_max({db_tile})")
        if sel and dbm and sel != dbm:
            parts.append(f"selected({sel})_neq_db_newest_from_freshness({dbm})")
        if not exp:
            parts.append("missing_expected_last_closed")
        diagnostic = "; ".join(parts) if parts else "invariant_failed"

    return {
        "schema": "jup_v3_timeline_proof_v1",
        "contract_id": JUP_V3_FRESHNESS_CONTRACT_ID,
        "contract_version": JUP_V3_FRESHNESS_CONTRACT_VERSION,
        "policy_slot": BASELINE_POLICY_SLOT_JUP_V3,
        "market_db_path": str(market_db_path.resolve()) if market_db_path else None,
        "freshness_source": ff.get("freshness_source"),
        "canonical_clock_expected_last_closed_candle_open_utc": exp,
        "db_max_candle_open_utc": dbm,
        "db_max_from_tile_proof": tbp.get("db_max_candle_open_utc"),
        "selected_tile_candle_open_utc": sel,
        "closed_bucket_lag": lag_i,
        "allowed_closed_bucket_lag_max": mx,
        "tile_selection_matches_db_max": bool(sel_match) if sel_match is not None else None,
        "within_freshness_contract": within,
        "freshness_severity": sev,
        "timeline_invariant_pass": invariant_pass,
        "diagnostic": diagnostic,
    }
