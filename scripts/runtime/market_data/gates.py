"""Deterministic freshness + divergence fail-closed gates (Phase 5.1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class GateState(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class GateResult:
    state: GateState
    reason: str
    details: dict[str, Any]


def _parse_observed_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def evaluate_freshness(
    *,
    observed_at: str | None,
    wall_now: datetime | None = None,
    max_age_sec: float = 120.0,
) -> GateResult:
    """Fail closed if quote is older than max_age_sec relative to wall clock."""
    now = wall_now or datetime.now(timezone.utc)
    obs = _parse_observed_at(observed_at)
    if obs is None:
        return GateResult(
            state=GateState.BLOCKED,
            reason="freshness_missing_timestamp",
            details={"observed_at": observed_at},
        )
    age = (now - obs).total_seconds()
    if age < 0:
        return GateResult(
            state=GateState.BLOCKED,
            reason="freshness_clock_skew",
            details={"age_sec": age, "observed_at": observed_at},
        )
    if age > max_age_sec:
        return GateResult(
            state=GateState.BLOCKED,
            reason="freshness_stale",
            details={"age_sec": age, "max_age_sec": max_age_sec, "observed_at": observed_at},
        )
    if age > max_age_sec * 0.75:
        return GateResult(
            state=GateState.DEGRADED,
            reason="freshness_near_limit",
            details={"age_sec": age, "max_age_sec": max_age_sec, "observed_at": observed_at},
        )
    return GateResult(
        state=GateState.OK,
        reason="freshness_ok",
        details={"age_sec": age, "max_age_sec": max_age_sec},
    )


def evaluate_divergence(
    *,
    primary: float | None,
    comparator: float | None,
    max_rel_diff: float = 0.005,
    degraded_rel_diff: float = 0.002,
) -> GateResult:
    """Relative mid-price divergence between primary and comparator."""
    if primary is None or comparator is None:
        return GateResult(
            state=GateState.BLOCKED,
            reason="divergence_missing_price",
            details={"primary": primary, "comparator": comparator},
        )
    if primary <= 0 or comparator <= 0:
        return GateResult(
            state=GateState.BLOCKED,
            reason="divergence_nonpositive_price",
            details={"primary": primary, "comparator": comparator},
        )
    mid = (primary + comparator) / 2.0
    rel = abs(primary - comparator) / mid
    if rel > max_rel_diff:
        return GateResult(
            state=GateState.BLOCKED,
            reason="divergence_exceeded",
            details={
                "primary": primary,
                "comparator": comparator,
                "rel_diff": rel,
                "max_rel_diff": max_rel_diff,
            },
        )
    if rel > degraded_rel_diff:
        return GateResult(
            state=GateState.DEGRADED,
            reason="divergence_elevated",
            details={
                "primary": primary,
                "comparator": comparator,
                "rel_diff": rel,
                "degraded_rel_diff": degraded_rel_diff,
            },
        )
    return GateResult(
        state=GateState.OK,
        reason="divergence_ok",
        details={"primary": primary, "comparator": comparator, "rel_diff": rel},
    )


def _worst(a: GateState, b: GateState) -> GateState:
    order = {GateState.OK: 0, GateState.DEGRADED: 1, GateState.BLOCKED: 2}
    return a if order[a] >= order[b] else b


def evaluate_gates(
    *,
    primary_observed_at: str | None,
    comparator_observed_at: str | None,
    primary_price: float | None,
    comparator_price: float | None,
    wall_now: datetime | None = None,
    max_age_sec: float = 120.0,
    max_rel_diff: float = 0.005,
    degraded_rel_diff: float = 0.002,
    tertiary_observed_at: str | None = None,
    tertiary_price: float | None = None,
    king_pyth_max_rel_diff: float = 0.007,
    king_pyth_degraded_rel_diff: float = 0.004,
    king_coinbase_max_rel_diff: float = 0.025,
    king_coinbase_degraded_rel_diff: float = 0.012,
) -> GateResult:
    """Combine freshness + divergence.

    **Jupiter-as-king** (when ``tertiary_price`` is set — Jupiter implied SOL/USD):

    - **Pyth** is checked **against Jupiter** (oracle should track the on-chain anchor).
    - **Coinbase** **supports** Jupiter: checked **against Jupiter** with a **wider** band
      (CEX vs routed DEX basis).
    - Direct Pyth↔Coinbase divergence is **not** used in this mode — Coinbase’s job is to
      align with the king, not to substitute for it.

    **Fallback** (no Jupiter price): classic **Pyth ↔ Coinbase** pair only (``max_rel_diff``).
    """
    f1 = evaluate_freshness(observed_at=primary_observed_at, wall_now=wall_now, max_age_sec=max_age_sec)
    f2 = evaluate_freshness(observed_at=comparator_observed_at, wall_now=wall_now, max_age_sec=max_age_sec)
    details: dict[str, Any] = {
        "freshness_primary": f1.details,
        "freshness_comparator": f2.details,
    }

    if tertiary_price is None:
        div = evaluate_divergence(
            primary=primary_price,
            comparator=comparator_price,
            max_rel_diff=max_rel_diff,
            degraded_rel_diff=degraded_rel_diff,
        )
        state = _worst(_worst(f1.state, f2.state), div.state)
        parts = [f1.reason, f2.reason, div.reason]
        details["divergence"] = div.details
        details["gate_mode"] = "pyth_vs_coinbase"
        details["tertiary"] = {"skipped": True}
        return GateResult(state=state, reason=";".join(parts), details=details)

    f3 = evaluate_freshness(observed_at=tertiary_observed_at, wall_now=wall_now, max_age_sec=max_age_sec)
    # King = Jupiter (first operand) for both divergences — symmetric math, explicit role in details.
    div_pj = evaluate_divergence(
        primary=tertiary_price,
        comparator=primary_price,
        max_rel_diff=king_pyth_max_rel_diff,
        degraded_rel_diff=king_pyth_degraded_rel_diff,
    )
    div_cj = evaluate_divergence(
        primary=tertiary_price,
        comparator=comparator_price,
        max_rel_diff=king_coinbase_max_rel_diff,
        degraded_rel_diff=king_coinbase_degraded_rel_diff,
    )
    state = f1.state
    state = _worst(state, f2.state)
    state = _worst(state, f3.state)
    state = _worst(state, div_pj.state)
    state = _worst(state, div_cj.state)
    parts = [f1.reason, f2.reason, f3.reason, div_pj.reason, div_cj.reason]
    details["freshness_tertiary"] = f3.details
    details["gate_mode"] = "jupiter_king"
    details["divergence_pyth_vs_jupiter_king"] = div_pj.details
    details["divergence_coinbase_supports_jupiter_king"] = div_cj.details

    return GateResult(state=state, reason=";".join(parts), details=details)
