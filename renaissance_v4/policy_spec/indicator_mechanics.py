"""
Mechanical support classification for canonical indicator kinds (DV-ARCH-INDICATOR-MECHANICS-064).

Source of truth: each ``kind`` in ``INDICATOR_KIND_VOCABULARY`` maps to exactly one class:
  - mechanically_supported — computed in ``indicator_engine.mjs`` and passed into policy evaluation
  - declaration_only — valid in contract; intake fails if declared (not silently ignored)
  - unsupported — reserved / not implemented; intake fails if declared

Extension path: add kind to vocabulary → param validation in indicators_v1.py → class here →
implement in indicator_engine.mjs (if mechanically_supported).
"""

from __future__ import annotations

import json
from typing import Any

from renaissance_v4.policy_spec.indicators_v1 import INDICATOR_KIND_VOCABULARY


class MechanicalClass:
    MECHANICALLY_SUPPORTED = "mechanically_supported"
    DECLARATION_ONLY = "declaration_only"
    UNSUPPORTED = "unsupported"


# Every vocabulary kind must appear exactly once.
MECHANICAL_CLASS_BY_KIND: dict[str, str] = {
    "ema": MechanicalClass.MECHANICALLY_SUPPORTED,
    "sma": MechanicalClass.MECHANICALLY_SUPPORTED,
    "rsi": MechanicalClass.MECHANICALLY_SUPPORTED,
    "atr": MechanicalClass.MECHANICALLY_SUPPORTED,
    "macd": MechanicalClass.MECHANICALLY_SUPPORTED,
    "bollinger_bands": MechanicalClass.MECHANICALLY_SUPPORTED,
    "vwap": MechanicalClass.MECHANICALLY_SUPPORTED,
    "supertrend": MechanicalClass.MECHANICALLY_SUPPORTED,
    "stochastic": MechanicalClass.MECHANICALLY_SUPPORTED,
    "adx": MechanicalClass.MECHANICALLY_SUPPORTED,
    "cci": MechanicalClass.MECHANICALLY_SUPPORTED,
    "williams_r": MechanicalClass.MECHANICALLY_SUPPORTED,
    "mfi": MechanicalClass.MECHANICALLY_SUPPORTED,
    "obv": MechanicalClass.MECHANICALLY_SUPPORTED,
    "parabolic_sar": MechanicalClass.MECHANICALLY_SUPPORTED,
    "ichimoku": MechanicalClass.MECHANICALLY_SUPPORTED,
    "donchian": MechanicalClass.MECHANICALLY_SUPPORTED,
    "volume_filter": MechanicalClass.MECHANICALLY_SUPPORTED,
    "body_measurement": MechanicalClass.MECHANICALLY_SUPPORTED,
    "fixed_threshold": MechanicalClass.MECHANICALLY_SUPPORTED,
    # Meta / multi-series semantics — not computed in harness v1; explicit failure if declared
    "divergence": MechanicalClass.DECLARATION_ONLY,
    "threshold_group": MechanicalClass.DECLARATION_ONLY,
}


def assert_registry_covers_vocabulary() -> None:
    """Call from tests; ensures registry stays aligned with vocabulary."""
    vocab = set(INDICATOR_KIND_VOCABULARY)
    reg = set(MECHANICAL_CLASS_BY_KIND.keys())
    assert vocab == reg, f"vocabulary/registry mismatch: {vocab ^ reg}"


def mechanical_support_json_for_harness() -> str:
    """JSON for RV4_MECHANICAL_REGISTRY_JSON (Node harness parity check)."""
    return json.dumps(
        {"schema_version": "indicator_mechanics_v1", "kinds": MECHANICAL_CLASS_BY_KIND},
        separators=(",", ":"),
        ensure_ascii=True,
    )


def mechanical_support_errors_for_declarations(declarations: list[Any]) -> list[str]:
    """
    If any declaration is not mechanically_supported, return one error per kind:
    ``indicator_declared_but_not_mechanically_supported: <kind>``
    """
    errs: list[str] = []
    if not isinstance(declarations, list):
        return errs
    for d in declarations:
        if not isinstance(d, dict):
            continue
        kind = str(d.get("kind") or "").strip().lower()
        if not kind:
            continue
        cls = MECHANICAL_CLASS_BY_KIND.get(kind)
        if cls == MechanicalClass.MECHANICALLY_SUPPORTED:
            continue
        errs.append(f"indicator_declared_but_not_mechanically_supported: {kind}")
    return errs
