"""
GT058 — Label-based trade filtering (activation / test mode).

Entry blocking and ``student_output`` overlays are implemented by **GT059 precision tuning**
(see :mod:`renaissance_v4.game_theory.gt059_precision_gate_v1`) when activation is enabled.

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


def gt058_should_block_entry_from_prior_labels_v1(
    priors: list[int],
    *,
    ev_best_value_v1: float | None = None,
) -> bool:
    """Delegates to GT059 precision replay gate (threshold + EV override)."""
    from renaissance_v4.game_theory.gt059_precision_gate_v1 import gt059_should_block_replay_entry_v1

    return gt059_should_block_replay_entry_v1(priors, ev_best_value_v1=ev_best_value_v1)


def apply_gt058_student_output_override_v1(lr: dict[str, Any]) -> None:
    """Delegates to GT059 seam overlay (negative-label + EV nuance)."""
    from renaissance_v4.game_theory.gt059_precision_gate_v1 import apply_gt059_student_output_override_v1

    apply_gt059_student_output_override_v1(lr)


__all__ = [
    "apply_gt058_student_output_override_v1",
    "gt058_label_gate_activation_enabled_v1",
    "gt058_should_block_entry_from_prior_labels_v1",
    "gt058_signature_key_v1",
]
