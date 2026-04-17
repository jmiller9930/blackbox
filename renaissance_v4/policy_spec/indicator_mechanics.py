"""
Mechanical support classification for canonical indicator kinds (DV-ARCH-INDICATOR-MECHANICS-064).

What "mechanically supported" means in practice
-----------------------------------------------
The **Kitchen intake harness** (Node: ``renaissance_v4/policy_intake/run_ts_intake_eval.mjs``) builds
OHLCV series, then ``indicator_engine.mjs`` **computes** each **mechanically_supported** indicator for
those bars. At each evaluation step, current-bar values are placed in ``ctx.indicators`` keyed by the
declaration ``id``. Your policy's ``generateSignalFromOhlc`` can therefore **read real numbers**
(e.g. ``ctx.indicators.rsi_main``) on the **same** synthetic bars intake uses for pass/fail.

If a kind is **not** mechanically supported (here: **declaration_only** such as ``divergence``,
``threshold_group``), the contract may still allow the **word** in ``indicators_v1``, but **declaring**
that kind in an embedded indicators block **fails intake** (see ``mechanical_support_errors_for_declarations``)
so we never silently run a policy that assumes machinery we did not compute.

Relationship to ``indicators_v1.py``
------------------------------------
``INDICATOR_KIND_VOCABULARY`` lists every **legal** ``kind`` string. This module classifies each kind
for **harness** behavior. ``MECHANICAL_CLASS_BY_KIND`` must contain **every** vocabulary kind exactly
once (tests call ``assert_registry_covers_vocabulary``).

Extension path: add kind to vocabulary → param validation in ``indicators_v1.py`` → row here →
implement in ``indicator_engine.mjs`` if the kind becomes mechanically_supported.
"""

from __future__ import annotations

import json
from typing import Any

from renaissance_v4.policy_spec.indicators_v1 import INDICATOR_KIND_VOCABULARY


class MechanicalClass:
    """Harness classification for a single indicator ``kind`` string."""

    MECHANICALLY_SUPPORTED = "mechanically_supported"
    DECLARATION_ONLY = "declaration_only"
    UNSUPPORTED = "unsupported"


# Maps each ``kind`` in INDICATOR_KIND_VOCABULARY to exactly one MechanicalClass value.
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
    Used during intake static validation (see ``indicators_v1``).

    For each declaration whose ``kind`` is **not** ``MECHANICALLY_SUPPORTED`` (including
    **declaration_only** kinds like ``divergence``), append an error so intake does not pass while
    implying those series exist in ``ctx.indicators``.

    Returns:
        A list like ``["indicator_declared_but_not_mechanically_supported: divergence", ...]``.
        Empty list means every declared kind is computed by the harness.
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
