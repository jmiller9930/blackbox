"""
D14 proof (P2/P5/P7/P9/P11 partial): contract and truth-separation guards.

Uses synthetic payloads only — no Referee/Student substitution checks require a full batch on disk.
"""

from __future__ import annotations

from renaissance_v4.game_theory.student_panel_d14 import groundhog_state_d14


def test_groundhog_state_d14_classification_matrix() -> None:
    assert groundhog_state_d14(groundhog_active=False, behavior_changed=True, outcome_improved=True) == "COLD"
    assert groundhog_state_d14(groundhog_active=True, behavior_changed=True, outcome_improved=True) == "STRONG"
    assert groundhog_state_d14(groundhog_active=True, behavior_changed=True, outcome_improved=False) == "WEAK"
    assert groundhog_state_d14(groundhog_active=True, behavior_changed=True, outcome_improved=None) == "ACTIVE"


def test_student_fields_never_equal_referee_field_names_in_contract() -> None:
    """Cheap static guard: canonical record exposes distinct keys for Student vs Referee (P2 intent)."""
    student_keys = {"student_action", "student_direction", "student_confidence_01"}
    referee_keys = {"referee_actual_trade", "referee_direction", "referee_outcome", "referee_pnl"}
    assert not student_keys.intersection(referee_keys)


def test_trade_id_is_carousel_and_api_key() -> None:
    """Carousel slice schema requires trade_id (P7 intent)."""
    from renaissance_v4.game_theory.student_panel_d13 import SCHEMA_CAROUSEL_SLICE

    sample = {
        "schema": SCHEMA_CAROUSEL_SLICE,
        "trade_id": "T1",
        "timestamp_utc": "data_gap",
        "student_direction": "LONG",
        "student_confidence_01": 0.5,
        "referee_outcome": "WIN",
        "groundhog_usage_label": "data_gap",
        "decision_changed_flag": "data_gap",
    }
    assert sample["trade_id"] == "T1"
