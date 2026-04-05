"""Build outcome records from paired ledger rows (single MAE v1 path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.sequential_engine.canonical_json import sha256_hex
from modules.anna_training.sequential_engine.mae_v1 import MAE_PROTOCOL_ID, compute_mae_usd_v1
from modules.anna_training.sequential_engine.paired_outcomes import OutcomeClass, classify_paired_outcome, pnl_from_row
from modules.anna_training.sequential_engine.outcome_manifest import trade_row_hash


def build_outcome_record(
    *,
    test_id: str,
    market_event_id: str,
    baseline_row: dict[str, Any] | None,
    candidate_row: dict[str, Any] | None,
    epsilon: float,
    mae_protocol_id: str,
    baseline_trade_id: str | None = None,
    candidate_trade_id: str | None = None,
    market_db_path: Path | None = None,
    ledger_db_path: Path | None = None,
) -> dict[str, Any]:
    """
    One observation per market_event_id. Pairing must be validated by caller.

    mae_protocol_id must equal MAE_PROTOCOL_ID (single runtime path).
    """
    if mae_protocol_id != MAE_PROTOCOL_ID:
        raise ValueError(f"mae_protocol_id must be {MAE_PROTOCOL_ID!r}, got {mae_protocol_id!r}")

    exclusion_reason: str | None = None
    pairing_valid = False

    if not baseline_row or not candidate_row:
        exclusion_reason = exclusion_reason or "missing_leg"
    else:
        b_mid = (baseline_row.get("market_event_id") or "").strip()
        c_mid = (candidate_row.get("market_event_id") or "").strip()
        if b_mid != market_event_id or c_mid != market_event_id:
            exclusion_reason = "market_event_id_mismatch"
        elif (baseline_row.get("lane") or "").strip().lower() != "baseline":
            exclusion_reason = "baseline_lane_invalid"
        elif (candidate_row.get("lane") or "").strip().lower() != "anna":
            exclusion_reason = "candidate_lane_invalid"
        else:
            pairing_valid = True

    pnl_baseline = pnl_from_row(baseline_row) if baseline_row else None
    pnl_candidate = pnl_from_row(candidate_row) if candidate_row else None

    mae_baseline: float | None = None
    mae_candidate: float | None = None
    mae_excl: str | None = None

    if pairing_valid and baseline_row and candidate_row:
        sym = (baseline_row.get("symbol") or "").strip()
        mae_baseline, r1 = compute_mae_usd_v1(
            canonical_symbol=sym,
            side=baseline_row.get("side"),
            entry_price=baseline_row.get("entry_price"),
            size=baseline_row.get("size"),
            entry_time=baseline_row.get("entry_time"),
            exit_time=baseline_row.get("exit_time"),
            market_db_path=market_db_path,
        )
        mae_candidate, r2 = compute_mae_usd_v1(
            canonical_symbol=sym,
            side=candidate_row.get("side"),
            entry_price=candidate_row.get("entry_price"),
            size=candidate_row.get("size"),
            entry_time=candidate_row.get("entry_time"),
            exit_time=candidate_row.get("exit_time"),
            market_db_path=market_db_path,
        )
        if r1:
            exclusion_reason = exclusion_reason or f"mae_baseline:{r1}"
        if r2:
            exclusion_reason = exclusion_reason or f"mae_candidate:{r2}"

    candidate_passes_risk = False
    if (
        pairing_valid
        and mae_baseline is not None
        and mae_candidate is not None
        and mae_baseline >= 0
        and exclusion_reason is None
    ):
        cap = (1.0 + float(epsilon)) * float(mae_baseline)
        candidate_passes_risk = float(mae_candidate) <= cap + 1e-12

    outcome: OutcomeClass
    ex2: str | None
    outcome, ex2 = classify_paired_outcome(
        pnl_candidate=pnl_candidate,
        pnl_baseline=pnl_baseline,
        candidate_passes_risk=candidate_passes_risk,
        exclusion_reason=exclusion_reason,
    )
    if ex2:
        exclusion_reason = ex2

    fp = {
        "market_event_id": market_event_id,
        "test_id": test_id,
        "outcome": outcome,
        "pairing_valid": pairing_valid,
        "exclusion_reason": exclusion_reason,
        "pnl_candidate": pnl_candidate,
        "pnl_baseline": pnl_baseline,
        "mae_candidate": mae_candidate,
        "mae_baseline": mae_baseline,
        "mae_protocol_id": mae_protocol_id,
        "candidate_passes_risk": candidate_passes_risk,
    }
    payload_fingerprint = sha256_hex(fp)

    rec: dict[str, Any] = {
        **fp,
        "payload_fingerprint": payload_fingerprint,
        "baseline_trade_id": baseline_trade_id or (baseline_row or {}).get("trade_id"),
        "candidate_trade_id": candidate_trade_id or (candidate_row or {}).get("trade_id"),
        "baseline_trade_hash": trade_row_hash(
            str((baseline_row or {}).get("trade_id") or ""), db_path=ledger_db_path
        ),
        "candidate_trade_hash": trade_row_hash(
            str((candidate_row or {}).get("trade_id") or ""), db_path=ledger_db_path
        ),
    }
    return rec


def eligible_for_sprt(outcome: str) -> bool:
    return outcome in ("WIN", "NOT_WIN")
