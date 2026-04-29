"""
GT058 — Label-based trade filtering (activation / test mode).

* Replay: optional entry block when rolling triple-barrier label mean for a coarse signature is bad.
* Seam: optional ``student_output`` overlay from GT055 ``triple_barrier_label_v1`` (decision only).

Does not change execution engines, EV math, ledger rules, or GT056 aggregation formulas.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any


_ENV_ACTIVATION = "GT058_LABEL_GATE_ACTIVATION_V1"


def gt058_label_gate_activation_enabled_v1() -> bool:
    return (os.environ.get(_ENV_ACTIVATION) or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def gt058_signature_key_v1(regime: str, fusion_direction: str, active_signal_names: list[str]) -> str:
    """Coarse bucket for rolling label memory (regime × fusion direction × active signals)."""
    parts = [str(regime), str(fusion_direction)] + sorted(str(x) for x in active_signal_names)
    canon = "|".join(parts)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:28]


def gt058_should_block_entry_from_prior_labels_v1(priors: list[int]) -> bool:
    """
    GT058 replay gate — block entry when prior label mean for this signature is negative,
    or (optionally) near zero per ``GT058_NEAR_ZERO_BAND``.
    """
    if not gt058_label_gate_activation_enabled_v1():
        return False
    try:
        min_n = int(os.environ.get("GT058_MIN_PRIOR_LABELS", "3"))
    except (TypeError, ValueError):
        min_n = 3
    min_n = max(1, min_n)
    if len(priors) < min_n:
        return False
    avg = sum(priors) / len(priors)
    if avg < 0:
        return True
    try:
        nz_band = float(os.environ.get("GT058_NEAR_ZERO_BAND", "0") or "0")
    except (TypeError, ValueError):
        nz_band = 0.0
    if nz_band > 0 and abs(avg) <= nz_band:
        return True
    return False


def apply_gt058_student_output_override_v1(lr: dict[str, Any]) -> None:
    """
    Mutates ``student_output`` only when GT058 + GT055 labels are present (learning-record overlay).

    * label < 0 → force ``no_trade`` (contract-aligned flat).
    * label == 0 → halve ``confidence_01`` (bounded).
    * label > 0 → allow (no change).
    """
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
    if li < 0:
        so["student_action_v1"] = "no_trade"
        so["act"] = False
        so["direction"] = "flat"
        so["gt058_label_gate_override_v1"] = {
            "schema": "gt058_label_gate_override_v1",
            "reason": "triple_barrier_label_negative_v1",
        }
        return
    if li == 0:
        try:
            c = float(so.get("confidence_01") if so.get("confidence_01") is not None else 0.5)
        except (TypeError, ValueError):
            c = 0.5
        so["confidence_01"] = max(0.0, min(1.0, round(c * 0.5, 6)))
        so["gt058_label_gate_override_v1"] = {
            "schema": "gt058_label_gate_override_v1",
            "reason": "triple_barrier_label_neutral_reduce_confidence_v1",
        }


__all__ = [
    "apply_gt058_student_output_override_v1",
    "gt058_label_gate_activation_enabled_v1",
    "gt058_should_block_entry_from_prior_labels_v1",
    "gt058_signature_key_v1",
]
