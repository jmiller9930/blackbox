"""
FinQuant — Pattern Signature

Generates a deterministic identity for a market state. Two similar setups must
map to the same signature so evidence can accumulate over time.

Signature components:
  - regime bucket (volatility class + RSI state + price-vs-EMA)
  - bucketed RSI (5-pt bins)
  - bucketed ATR (0.5 bins)
  - volume regime
  - position state (flat / long / short)

Same signature = same pattern. Different signatures = different pattern.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


# Regime bucket helpers -------------------------------------------------

def rsi_bucket(rsi: float | None) -> str:
    if rsi is None:
        return "rsi_unknown"
    if rsi >= 70:
        return "rsi_70plus"
    if rsi >= 65:
        return "rsi_65_70"
    if rsi >= 60:
        return "rsi_60_65"
    if rsi >= 55:
        return "rsi_55_60"
    if rsi >= 50:
        return "rsi_50_55"
    if rsi >= 45:
        return "rsi_45_50"
    if rsi >= 40:
        return "rsi_40_45"
    if rsi >= 35:
        return "rsi_35_40"
    return "rsi_under35"


def atr_bucket(atr: float | None) -> str:
    if atr is None:
        return "atr_unknown"
    if atr >= 3.0:
        return "atr_3plus"
    if atr >= 2.0:
        return "atr_2_3"
    if atr >= 1.5:
        return "atr_1_5_2"
    if atr >= 1.0:
        return "atr_1_1_5"
    if atr >= 0.5:
        return "atr_05_1"
    return "atr_under05"


def volatility_class(atr: float | None) -> str:
    if atr is None:
        return "vol_unknown"
    if atr >= 2.0:
        return "vol_high"
    if atr >= 1.0:
        return "vol_normal"
    return "vol_low"


def trend_class(price_above_ema: bool, price_up: bool) -> str:
    if price_above_ema and price_up:
        return "trend_up"
    if not price_above_ema and not price_up:
        return "trend_down"
    return "trend_mixed"


def volume_class(volume_expand: bool) -> str:
    return "vol_expand" if volume_expand else "vol_contract"


# Position state -------------------------------------------------------

def position_class(position_open: bool) -> str:
    return "pos_open" if position_open else "pos_flat"


# Signature generation -------------------------------------------------

def build_signature(
    *,
    rsi: float | None,
    atr: float | None,
    price_above_ema: bool,
    price_up: bool,
    volume_expand: bool,
    position_open: bool,
    symbol: str = "",
    timeframe_minutes: int = 0,
) -> dict[str, Any]:
    """
    Build a structured signature dict and a deterministic ID hash.

    Returns:
      {
        "pattern_id_v1": "<sha256[:16]>",
        "components_v1": {...},
        "human_label_v1": "trend_up | rsi_55_60 | vol_high | pos_flat"
      }
    """
    components = {
        "symbol_v1": symbol,
        "timeframe_minutes_v1": int(timeframe_minutes or 0),
        "trend_v1": trend_class(price_above_ema, price_up),
        "rsi_bucket_v1": rsi_bucket(rsi),
        "atr_bucket_v1": atr_bucket(atr),
        "volatility_v1": volatility_class(atr),
        "volume_v1": volume_class(volume_expand),
        "position_v1": position_class(position_open),
    }

    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"))
    pattern_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    human_label = " | ".join([
        components["trend_v1"],
        components["rsi_bucket_v1"],
        components["volatility_v1"],
        components["position_v1"],
    ])

    return {
        "pattern_id_v1": pattern_id,
        "components_v1": components,
        "human_label_v1": human_label,
        "canonical_v1": canonical,
    }


def build_signature_from_packet(
    input_packet: dict[str, Any],
    position_open: bool,
) -> dict[str, Any]:
    """Convenience: build signature directly from an input_packet_v1."""
    math = input_packet.get("market_math_v1", {}) or {}
    ctx = input_packet.get("market_context_v1", {}) or {}
    return build_signature(
        rsi=math.get("rsi_14_v1"),
        atr=math.get("atr_14_v1"),
        price_above_ema=bool(ctx.get("price_above_ema_v1", False)),
        price_up=bool(ctx.get("price_up_v1", False)),
        volume_expand=bool(ctx.get("volume_expand_v1", False)),
        position_open=position_open,
        symbol=str(input_packet.get("symbol", "")),
        timeframe_minutes=int(input_packet.get("timeframe_minutes") or 0),
    )
