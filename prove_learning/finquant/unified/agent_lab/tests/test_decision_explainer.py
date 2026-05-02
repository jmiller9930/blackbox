"""Tests for learning/decision_explainer.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.learning_unit import new_learning_unit
from learning.decision_explainer import build_decision_explanation


def _unit(pid, action, status, confidence, hits=0, misses=0):
    u = new_learning_unit(
        pattern_id=pid, signature_components={}, human_label=f"label_{pid}",
        proposed_action=action, hypothesis="", expected_outcome="", invalidation_condition="")
    u["status_v1"] = status
    u["confidence_score_v1"] = confidence
    u["hit_count_v1"] = hits
    u["miss_count_v1"] = misses
    return u


def test_no_primary_says_no_active_match():
    competition = {
        "primary_unit_v1": None,
        "challengers_v1": [],
        "observers_v1": [],
        "suppressors_v1": [],
        "reason_v1": "no eligible active unit",
    }
    expl = build_decision_explanation(
        pattern_id="abc",
        human_label="trend_up",
        competition=competition,
        final_action="NO_TRADE",
        final_decision_source="llm",
    )
    assert expl["primary_unit_v1"] is None
    assert "No ACTIVE learning unit matched" in expl["narrative_v1"]


def test_primary_attributable_when_actions_match():
    primary = _unit("x", "ENTER_LONG", "active", 0.8, hits=10, misses=2)
    competition = {
        "primary_unit_v1": primary,
        "challengers_v1": [],
        "observers_v1": [],
        "suppressors_v1": [],
        "reason_v1": "test",
    }
    expl = build_decision_explanation(
        pattern_id="x",
        human_label="trend_up",
        competition=competition,
        final_action="ENTER_LONG",
        final_decision_source="llm",
    )
    assert expl["primary_attributable_v1"] is True
    assert "followed the unit's proposal" in expl["narrative_v1"]


def test_primary_not_attributable_when_actions_differ():
    primary = _unit("x", "ENTER_LONG", "active", 0.8, hits=10, misses=2)
    competition = {
        "primary_unit_v1": primary,
        "challengers_v1": [],
        "observers_v1": [],
        "suppressors_v1": [],
        "reason_v1": "test",
    }
    expl = build_decision_explanation(
        pattern_id="x",
        human_label="trend_up",
        competition=competition,
        final_action="NO_TRADE",
        final_decision_source="llm",
    )
    assert expl["primary_attributable_v1"] is False
    assert "but the student chose NO_TRADE" in expl["narrative_v1"]


def test_observer_count_surfaced():
    observers = [_unit("o1", "NO_TRADE", "candidate", 0.0), _unit("o2", "NO_TRADE", "provisional", 0.3)]
    competition = {
        "primary_unit_v1": None,
        "challengers_v1": [],
        "observers_v1": observers,
        "suppressors_v1": [],
        "reason_v1": "no active",
    }
    expl = build_decision_explanation(
        pattern_id="abc", human_label="lab",
        competition=competition,
        final_action="NO_TRADE", final_decision_source="rule",
    )
    assert expl["observer_unit_count_v1"] == 2
    assert "2 candidate/provisional" in expl["narrative_v1"]


def test_suppressors_surface_negative_knowledge():
    sup = [_unit("s1", "ENTER_LONG", "retired", 0.1)]
    competition = {
        "primary_unit_v1": None,
        "challengers_v1": [],
        "observers_v1": [],
        "suppressors_v1": sup,
        "reason_v1": "no active",
    }
    expl = build_decision_explanation(
        pattern_id="abc", human_label="lab",
        competition=competition,
        final_action="NO_TRADE", final_decision_source="rule",
    )
    assert len(expl["suppressor_units_v1"]) == 1
    assert "negative knowledge" in expl["narrative_v1"]
