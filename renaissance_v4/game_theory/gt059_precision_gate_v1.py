"""
GT059 — Precision tuning for GT058 label gate (pre-exam readiness).

Replay:
* ``len(priors) < GT059_LABEL_MIN_SAMPLES`` (default 5) → do not block on labels.
* ``label_avg < GT059_LABEL_BLOCK_THRESHOLD`` (default -0.2) → block unless EV override applies.
* EV override: ``label_avg < 0`` path uses ``ev_best_value_v1 > 0`` → allow (block=false).

Seam:
* Negative triple-barrier label: force ``no_trade`` only when EV override does not apply
  (no positive ``ev_best_value_v1`` on ``student_output`` when present).

Does not modify execution engines, GT056 formulas, or ledger mechanics.
"""

from __future__ import annotations

import os
from typing import Any


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, min(int(raw), 512))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def gt059_label_min_samples_v1() -> int:
    return max(1, _env_int("GT059_LABEL_MIN_SAMPLES", 5))


def gt059_label_block_threshold_v1() -> float:
    return _env_float("GT059_LABEL_BLOCK_THRESHOLD", -0.2)


def gt059_ev_best_proxy_from_signal_results_v1(signal_results: list[Any], *, entry_direction: str) -> float:
    """
    Replay-only proxy for ``ev_best_value_v1``: max ``expected_edge`` among active signals
    aligned with ``entry_direction`` (long/short).
    """
    ed = str(entry_direction or "").strip().lower()
    best = 0.0
    for r in signal_results:
        if not getattr(r, "active", False):
            continue
        d = str(getattr(r, "direction", "") or "").strip().lower()
        if ed == "long" and d != "long":
            continue
        if ed == "short" and d != "short":
            continue
        try:
            ee = float(getattr(r, "expected_edge", 0.0) or 0.0)
        except (TypeError, ValueError):
            ee = 0.0
        if ee > best:
            best = ee
    return float(best)


def gt059_should_block_replay_entry_v1(
    priors: list[int],
    *,
    ev_best_value_v1: float | None,
) -> bool:
    """
    GT059 replay gate — block only strong historical losers; allow EV-positive bars to pass.
    """
    from renaissance_v4.game_theory.gt058_label_gate_v1 import gt058_label_gate_activation_enabled_v1

    if not gt058_label_gate_activation_enabled_v1():
        return False
    min_n = gt059_label_min_samples_v1()
    if len(priors) < min_n:
        return False
    avg = sum(priors) / len(priors)
    thr = gt059_label_block_threshold_v1()
    if avg >= thr:
        return False
    # Strong negative historical label mean (e.g. < -0.2).
    try:
        ev = float(ev_best_value_v1) if ev_best_value_v1 is not None else None
    except (TypeError, ValueError):
        ev = None
    # Directive: if label_avg < 0 AND ev_best > 0 → allow (even inside strong bucket by avg alone).
    if avg < 0 and ev is not None and ev > 0:
        return False
    return True


def _ev_best_from_student_output_v1(so: dict[str, Any]) -> float | None:
    ev = so.get("expected_value_risk_cost_v1")
    if not isinstance(ev, dict):
        return None
    if not ev.get("available_v1"):
        return None
    try:
        return float(ev.get("ev_best_value_v1"))
    except (TypeError, ValueError):
        return None


def apply_gt059_student_output_override_v1(lr: dict[str, Any]) -> None:
    """
    GT059 seam overlay: do not blanket no_trade on -1 label when EV says positive best value.
    Neutral label: still reduce confidence (GT058 behavior).
    """
    from renaissance_v4.game_theory.gt058_label_gate_v1 import gt058_label_gate_activation_enabled_v1

    if not gt058_label_gate_activation_enabled_v1():
        return
    ref = lr.get("referee_outcome_subset")
    if not isinstance(ref, dict):
        return
    lab_raw = ref.get("triple_barrier_label_v1")
    try:
        li = int(lab_raw) if lab_raw is not None else None
    except (TypeError, ValueError):
        li = None
    if li is None:
        return
    so = lr.get("student_output")
    if not isinstance(so, dict):
        return

    ev_best = _ev_best_from_student_output_v1(so)

    if li < 0:
        if ev_best is not None and ev_best > 0:
            so["gt059_precision_gate_v1"] = {
                "schema": "gt059_precision_gate_v1",
                "reason": "ev_override_negative_label_allow_v1",
                "ev_best_value_v1": ev_best,
            }
            return
        so["student_action_v1"] = "no_trade"
        so["act"] = False
        so["direction"] = "flat"
        so["gt059_precision_gate_v1"] = {
            "schema": "gt059_precision_gate_v1",
            "reason": "triple_barrier_label_negative_no_ev_override_v1",
        }
        return

    if li == 0:
        try:
            c = float(so.get("confidence_01") if so.get("confidence_01") is not None else 0.5)
        except (TypeError, ValueError):
            c = 0.5
        so["confidence_01"] = max(0.0, min(1.0, round(c * 0.5, 6)))
        so["gt059_precision_gate_v1"] = {
            "schema": "gt059_precision_gate_v1",
            "reason": "triple_barrier_label_neutral_reduce_confidence_v1",
        }


__all__ = [
    "apply_gt059_student_output_override_v1",
    "gt059_ev_best_proxy_from_signal_results_v1",
    "gt059_label_block_threshold_v1",
    "gt059_label_min_samples_v1",
    "gt059_should_block_replay_entry_v1",
]
