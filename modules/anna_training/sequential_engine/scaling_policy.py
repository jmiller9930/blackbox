"""
Protocol-driven execution tier (bounded, conservative). No adaptive learning.

Tiers are read from protocol JSON only; this module does not invent thresholds.
"""

from __future__ import annotations

from typing import Any, Literal

Tier = Literal["no_execution", "baseline_only", "scaled_conservative"]


def execution_tier(
    *,
    sprt_decision: str,
    baseline_comparison: Literal["below", "match", "above"],
    protocol: dict[str, Any],
) -> Tier:
    """
    Map statistical state + baseline comparison to execution tier.

    baseline_comparison:
      - below: candidate performance below baseline (not necessarily SPRT — operator signal)
      - match: not statistically above baseline / continue state
      - above: SPRT PROMOTE (or protocol-defined equivalent)

    protocol keys (example — all optional with safe defaults):
      - max_scale: float, default 1.25 (hard cap on notional multiplier vs baseline)
      - require_promote_for_scale: bool, default True
    """
    _ = protocol  # reserved for explicit caps (max_scale, min_eligible_n_for_scale, etc.)
    req_promote = bool(protocol.get("require_promote_for_scale", True))
    d = (sprt_decision or "").strip().upper()
    bc = baseline_comparison

    if bc == "below":
        return "no_execution"
    if req_promote and d != "PROMOTE":
        return "baseline_only"
    if d == "PROMOTE" and bc == "above":
        return "scaled_conservative"
    return "baseline_only"


def max_scale_bound(protocol: dict[str, Any]) -> float:
    """Upper bound on scaling multiplier (protocol-only)."""
    raw = protocol.get("max_scale")
    if raw is None:
        return 1.25
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 1.25
    return min(max(v, 1.0), 1.25)
