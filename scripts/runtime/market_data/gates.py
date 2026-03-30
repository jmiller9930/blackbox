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
) -> GateResult:
    """Combine primary/comparator freshness and divergence. No silent OK when inputs missing."""
    f1 = evaluate_freshness(observed_at=primary_observed_at, wall_now=wall_now, max_age_sec=max_age_sec)
    f2 = evaluate_freshness(observed_at=comparator_observed_at, wall_now=wall_now, max_age_sec=max_age_sec)
    div = evaluate_divergence(
        primary=primary_price,
        comparator=comparator_price,
        max_rel_diff=max_rel_diff,
        degraded_rel_diff=degraded_rel_diff,
    )
    state = _worst(_worst(f1.state, f2.state), div.state)
    parts = [f1.reason, f2.reason, div.reason]
    reason = ";".join(parts)
    return GateResult(
        state=state,
        reason=reason,
        details={"freshness_primary": f1.details, "freshness_comparator": f2.details, "divergence": div.details},
    )
