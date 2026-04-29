"""GT_DIRECTIVE_041 — registry shape + acceptance summarizer (no heavy DB dependency)."""

from __future__ import annotations

from renaissance_v4.game_theory.exam.student_reasoning_exam_gt041_v1 import (
    summarize_gt041_acceptance_v1,
)
from renaissance_v4.game_theory.exam.student_reasoning_exam_scenarios_v1 import (
    scenario_templates_gt041_memory_ev_v1,
)


def test_gt041_scenario_registry_has_ten_lanes() -> None:
    t = scenario_templates_gt041_memory_ev_v1()
    assert len(t) == 10
    lanes = [str(x.get("gt041_lane_v1") or "") for x in t]
    assert lanes.count("memory_positive") == 3
    assert lanes.count("memory_negative") == 3
    assert lanes.count("ev_positive") == 2
    assert lanes.count("ev_negative") == 2


def test_summarize_gt041_acceptance_all_yes() -> None:
    rows = []
    for i in range(6):
        rows.append(
            {
                "gt041_proof_v1": {
                    "gt041_lane_v1": "memory_positive",
                    "matched_count_v1": 3,
                    "pattern_effect_to_score_v1": 0.05,
                    "expected_value_available_v1": True,
                    "ev_score_adjustment_v1": 0.01,
                }
            }
        )
    for i in range(4):
        rows.append(
            {
                "gt041_proof_v1": {
                    "gt041_lane_v1": "ev_positive" if i < 2 else "ev_negative",
                    "matched_count_v1": 3,
                    "pattern_effect_to_score_v1": 0.02,
                    "expected_value_available_v1": True,
                    "ev_score_adjustment_v1": -0.06,
                }
            }
        )
    acc = summarize_gt041_acceptance_v1(rows)
    assert acc["memory_matches_observed_v1"] == "YES"
    assert acc["fingerprint_shows_memory_and_ev_v1"] == "YES"
