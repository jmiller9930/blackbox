"""
Downstream frame generator — **GT_DIRECTIVE_006** / architecture **§11.4**, **§7**.

After Decision A = **ENTER**, append frames **1..n** using only each bar's own OHLCV (no lookahead).
**NO_TRADE** → zero downstream frames (caller omits this module).

Termination modes (exactly one per unit via policy):

* ``fixed_bars`` — ``D`` downstream bars (default **5** per architecture if unset).
* ``until_invalidation`` — emit frames until ``invalidation_triggers_on_close`` on a bar dict.
* ``volatility_regime_cap`` — stop when ``(high-low)/close >= range_threshold`` **or** ``max_bars`` reached.
"""

from __future__ import annotations

import threading
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import (
    DecisionFramePayloadV1,
    DecisionFrameV1,
    OhlcvV1,
    decision_frame_id_v1,
)

TerminationModeV1 = Literal["fixed_bars", "until_invalidation", "volatility_regime_cap"]


class DownstreamTerminationPolicyV1(BaseModel):
    """Pack-facing termination (dev: POSTed with OHLC strip until pack registry exists)."""

    model_config = ConfigDict(extra="forbid")

    mode: TerminationModeV1 = "fixed_bars"
    D: int = Field(default=5, ge=1, le=10_000, description="Fixed downstream bar count (default 5).")
    max_bars: int = Field(default=50, ge=1, le=10_000, description="Cap for volatility mode.")
    range_threshold: float = Field(
        default=0.5,
        ge=0.0,
        description="(high-low)/close threshold for volatility stop (deterministic test strips tune this).",
    )


class OhlcBarDictV1(BaseModel):
    """One bar row in the replay strip (index 0 = opening / frame 0 bar)."""

    model_config = ConfigDict(extra="allow")

    bar_close: str = Field(min_length=8, max_length=64)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    invalidation_triggers_on_close: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


def _bar_to_ohlcv(b: OhlcBarDictV1) -> OhlcvV1:
    return OhlcvV1(open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)


def _downstream_payload_no_lookahead_v1(b: OhlcBarDictV1) -> DecisionFramePayloadV1:
    """Single-bar snapshot only — no future fields."""
    ctx = dict(b.context) if isinstance(b.context, dict) else {}
    return DecisionFramePayloadV1(
        opening_snapshot=None,
        deliberation=None,
        decision_a=None,
        downstream_reserved=None,
        price_snapshot=_bar_to_ohlcv(b),
        downstream_context=ctx,
    )


def _bar_at_v1(strip: list[dict[str, Any]], i: int) -> OhlcBarDictV1:
    """Parse exactly ``strip[i]`` (no other indices read)."""
    return OhlcBarDictV1.model_validate(dict(strip[i]))


def generate_downstream_frames_after_seal_v1(
    *,
    exam_unit_id: str,
    strip: list[dict[str, Any]],
    policy: DownstreamTerminationPolicyV1,
    decision_a_sealed: bool,
    enter: bool,
) -> list[DecisionFrameV1]:
    """
    Build ``DecisionFrameV1`` rows for indices **1..n** (each uses **only** ``strip[i]`` for payload).

    ``strip[0]`` is the opening-window bar (frame 0 responsibility elsewhere). Downstream starts at **strip[1]**.
    """
    if not decision_a_sealed:
        raise ValueError("downstream_requires_decision_a_sealed")
    if not enter:
        return []
    if len(strip) < 2:
        return []
    n_strip = len(strip)
    uid = exam_unit_id.strip()
    out: list[DecisionFrameV1] = []

    def append_frame(bar_index: int, b: OhlcBarDictV1) -> None:
        fi = len(out) + 1
        if fi != bar_index:
            raise ValueError("internal_frame_index_mismatch")
        pl = _downstream_payload_no_lookahead_v1(b)
        out.append(
            DecisionFrameV1(
                decision_frame_id=decision_frame_id_v1(uid, fi),
                exam_unit_id=uid,
                frame_index=fi,
                timestamp=b.bar_close,
                frame_type="downstream",
                payload=pl,
            )
        )

    if policy.mode == "fixed_bars":
        want = policy.D
        emitted = 0
        i = 1
        while emitted < want and i < n_strip:
            append_frame(i, _bar_at_v1(strip, i))
            emitted += 1
            i += 1
        return out

    if policy.mode == "until_invalidation":
        i = 1
        while i < n_strip:
            b = _bar_at_v1(strip, i)
            append_frame(i, b)
            if b.invalidation_triggers_on_close:
                break
            i += 1
        return out

    if policy.mode == "volatility_regime_cap":
        emitted = 0
        i = 1
        while i < n_strip and emitted < policy.max_bars:
            b = _bar_at_v1(strip, i)
            append_frame(i, b)
            emitted += 1
            c = b.close if b.close not in (0.0, -0.0) else 1e-9
            rng = (b.high - b.low) / c
            if rng >= policy.range_threshold:
                break
            i += 1
        return out

    raise ValueError(f"unknown_termination_mode:{policy.mode}")


_OHLC_STRIPS: dict[str, list[dict[str, Any]]] = {}
_TERMINATION: dict[str, DownstreamTerminationPolicyV1] = {}
_LOCK = threading.Lock()


def set_exam_ohlc_strip_v1(exam_unit_id: str, bars: list[dict[str, Any]]) -> None:
    """Dev: attach OHLCV strip (index 0 = opening bar) before Decision A seal for ENTER downstream."""
    if len(bars) < 1:
        raise ValueError("strip_requires_at_least_one_bar")
    with _LOCK:
        _OHLC_STRIPS[exam_unit_id.strip()] = [dict(x) for x in bars]


def set_exam_downstream_termination_v1(exam_unit_id: str, policy: DownstreamTerminationPolicyV1) -> None:
    with _LOCK:
        _TERMINATION[exam_unit_id.strip()] = policy


def get_exam_ohlc_strip_v1(exam_unit_id: str) -> list[dict[str, Any]] | None:
    with _LOCK:
        v = _OHLC_STRIPS.get(exam_unit_id.strip())
        return [dict(x) for x in v] if v else None


def get_exam_downstream_termination_v1(exam_unit_id: str) -> DownstreamTerminationPolicyV1:
    with _LOCK:
        return _TERMINATION.get(exam_unit_id.strip(), DownstreamTerminationPolicyV1())


def default_synthetic_ohlc_strip_v1(*, n_bars: int = 16) -> list[dict[str, Any]]:
    """Deterministic strip for ENTER when none POSTed (enough for D=5 downstream)."""
    out: list[dict[str, Any]] = []
    base = 100.0
    for i in range(n_bars):
        o = base + i * 0.1
        h = o + 0.5
        l = o - 0.3
        c = o + 0.2
        out.append(
            {
                "bar_close": f"2026-04-21T{(12 + i):02d}:00:00Z",
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000.0 + i,
                "invalidation_triggers_on_close": False,
                "context": {"synthetic_index": i},
            }
        )
    out[4]["invalidation_triggers_on_close"] = True
    return out


def reset_exam_downstream_dev_stores_for_tests_v1() -> None:
    with _LOCK:
        _OHLC_STRIPS.clear()
        _TERMINATION.clear()


__all__ = [
    "DownstreamTerminationPolicyV1",
    "OhlcBarDictV1",
    "TerminationModeV1",
    "default_synthetic_ohlc_strip_v1",
    "generate_downstream_frames_after_seal_v1",
    "get_exam_downstream_termination_v1",
    "get_exam_ohlc_strip_v1",
    "reset_exam_downstream_dev_stores_for_tests_v1",
    "set_exam_downstream_termination_v1",
    "set_exam_ohlc_strip_v1",
]
