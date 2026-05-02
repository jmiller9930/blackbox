"""Tests for learning/learning_unit.py"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.learning_unit import (
    new_learning_unit,
    record_observation,
    update_status,
    compute_confidence,
    hit_rate,
    total_observations,
    summarize_unit,
)


def _u():
    return new_learning_unit(
        pattern_id="abc123",
        signature_components={"trend_v1": "trend_up"},
        human_label="trend_up | rsi_55_60",
        proposed_action="ENTER_LONG",
        hypothesis="trend continuation",
        expected_outcome="price up",
        invalidation_condition="rsi < 45",
    )


def test_new_unit_starts_as_candidate():
    u = _u()
    assert u["status_v1"] == "candidate"
    assert u["hit_count_v1"] == 0
    assert u["miss_count_v1"] == 0
    assert u["confidence_score_v1"] == 0.0


def test_record_confirmed_updates_hit():
    u = _u()
    record_observation(u, verdict="confirmed", evidence_record_id="lr_1")
    assert u["hit_count_v1"] == 1
    assert "lr_1" in u["evidence_record_ids_v1"]
    assert u["confidence_score_v1"] > 0.0
    assert u["recent_verdict_chain_v1"][-1] == "confirmed"


def test_record_rejected_updates_miss():
    u = _u()
    record_observation(u, verdict="rejected", evidence_record_id="lr_2")
    assert u["miss_count_v1"] == 1
    # Confidence should be < 0.5 after a single rejection
    assert u["confidence_score_v1"] < 0.5


def test_record_inconclusive_does_not_change_hit_or_miss():
    u = _u()
    record_observation(u, verdict="inconclusive", evidence_record_id="lr_3")
    assert u["hit_count_v1"] == 0
    assert u["miss_count_v1"] == 0
    assert u["inconclusive_count_v1"] == 1


def test_record_invalid_verdict_raises():
    u = _u()
    with pytest.raises(ValueError):
        record_observation(u, verdict="bogus", evidence_record_id="lr_4")


def test_compute_confidence_with_strong_history():
    u = _u()
    for _ in range(20):
        record_observation(u, verdict="confirmed", evidence_record_id="x")
    for _ in range(2):
        record_observation(u, verdict="rejected", evidence_record_id="x")
    conf = compute_confidence(u)
    assert conf > 0.8


def test_hit_rate_computed_correctly():
    u = _u()
    for _ in range(7):
        record_observation(u, verdict="confirmed", evidence_record_id="x")
    for _ in range(3):
        record_observation(u, verdict="rejected", evidence_record_id="x")
    assert abs(hit_rate(u) - 0.7) < 0.001


def test_total_observations_includes_inconclusive():
    u = _u()
    record_observation(u, verdict="confirmed", evidence_record_id="x")
    record_observation(u, verdict="rejected", evidence_record_id="x")
    record_observation(u, verdict="inconclusive", evidence_record_id="x")
    assert total_observations(u) == 3


def test_update_status_logs_history():
    u = _u()
    update_status(u, new_status="provisional", reason="enough observations")
    assert u["status_v1"] == "provisional"
    assert len(u["status_history_v1"]) == 2
    assert u["status_history_v1"][-1]["from"] == "candidate"
    assert u["status_history_v1"][-1]["to"] == "provisional"


def test_update_status_to_retired_records_reason():
    u = _u()
    update_status(u, new_status="retired", reason="hit rate too low")
    assert u["status_v1"] == "retired"
    assert u["retired_reason_v1"] == "hit rate too low"
    assert u["retired_at_v1"] is not None


def test_summarize_unit_compact():
    u = _u()
    record_observation(u, verdict="confirmed", evidence_record_id="x")
    s = summarize_unit(u)
    assert s["pattern_id_v1"] == "abc123"
    assert s["status_v1"] == "candidate"
    assert s["hit_count_v1"] == 1
