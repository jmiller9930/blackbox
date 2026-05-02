"""Tests for learning/promotion_engine.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.learning_unit import new_learning_unit, record_observation
from learning.promotion_engine import evaluate_promotion


def _u():
    return new_learning_unit(
        pattern_id="p", signature_components={}, human_label="x",
        proposed_action="ENTER_LONG", hypothesis="", expected_outcome="", invalidation_condition="")


def test_candidate_stays_with_few_observations():
    u = _u()
    record_observation(u, verdict="confirmed", evidence_record_id="x", pnl=1.0, outcome_kind="win")
    decision = evaluate_promotion(u)
    assert decision["transition"] is False


def test_candidate_promotes_to_provisional_after_five_observations():
    u = _u()
    for _ in range(5):
        record_observation(u, verdict="confirmed", evidence_record_id="x", pnl=1.0, outcome_kind="win")
    decision = evaluate_promotion(u)
    assert decision["transition"] is True
    assert decision["to_status"] == "provisional"


def test_provisional_promotes_to_validated_with_strong_history():
    u = _u()
    u["status_v1"] = "provisional"
    for _ in range(20):
        record_observation(u, verdict="confirmed", evidence_record_id="x", pnl=1.5, outcome_kind="win")
    for _ in range(12):
        record_observation(u, verdict="rejected", evidence_record_id="x", pnl=-0.5, outcome_kind="loss")
    # 32 total, win_rate ~0.625, expectancy positive
    decision = evaluate_promotion(u)
    assert decision["transition"] is True
    assert decision["to_status"] == "validated"


def test_validated_promotes_to_active_with_recent_streak():
    u = _u()
    u["status_v1"] = "validated"
    decision = evaluate_promotion(
        u, recent_verdicts=["confirmed", "confirmed", "confirmed"])
    assert decision["transition"] is True
    assert decision["to_status"] == "active"


def test_validated_does_not_promote_without_streak():
    u = _u()
    u["status_v1"] = "validated"
    decision = evaluate_promotion(
        u, recent_verdicts=["confirmed", "rejected", "confirmed"])
    assert decision["transition"] is False


def test_unit_retires_when_win_rate_collapses():
    u = _u()
    u["status_v1"] = "provisional"
    for _ in range(2):
        record_observation(u, verdict="confirmed", evidence_record_id="x", pnl=1.0, outcome_kind="win")
    for _ in range(8):
        record_observation(u, verdict="rejected", evidence_record_id="x", pnl=-1.0, outcome_kind="loss")
    # 2/10 = 0.2 win_rate, 10 total -> retire
    decision = evaluate_promotion(u)
    assert decision["transition"] is True
    assert decision["to_status"] == "retired"


def test_active_does_not_re_promote():
    u = _u()
    u["status_v1"] = "active"
    decision = evaluate_promotion(u, recent_verdicts=["confirmed"])
    assert decision["transition"] is False


def test_retired_stays_retired():
    u = _u()
    u["status_v1"] = "retired"
    for _ in range(20):
        record_observation(u, verdict="confirmed", evidence_record_id="x", pnl=1.0, outcome_kind="win")
    decision = evaluate_promotion(u)
    assert decision["transition"] is False
