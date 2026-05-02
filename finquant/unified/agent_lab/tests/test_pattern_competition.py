"""Tests for learning/pattern_competition.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from learning.learning_unit import new_learning_unit
from learning.pattern_competition import resolve_competition, rank_units, select_primary


def _unit(pid: str, status: str, action: str, confidence: float):
    u = new_learning_unit(
        pattern_id=pid, signature_components={}, human_label=pid,
        proposed_action=action, hypothesis="", expected_outcome="", invalidation_condition="")
    u["status_v1"] = status
    u["confidence_score_v1"] = confidence
    return u


def test_no_units_returns_no_primary():
    result = resolve_competition([])
    assert result["primary_unit_v1"] is None


def test_only_active_unit_wins():
    units = [
        _unit("a", "active", "ENTER_LONG", 0.8),
        _unit("b", "candidate", "ENTER_SHORT", 0.95),
        _unit("c", "validated", "NO_TRADE", 0.99),
    ]
    result = resolve_competition(units)
    assert result["primary_unit_v1"]["pattern_id_v1"] == "a"
    assert len(result["challengers_v1"]) == 1
    assert len(result["observers_v1"]) == 1


def test_highest_confidence_active_wins():
    units = [
        _unit("a", "active", "ENTER_LONG", 0.5),
        _unit("b", "active", "NO_TRADE", 0.85),
    ]
    result = resolve_competition(units)
    assert result["primary_unit_v1"]["pattern_id_v1"] == "b"


def test_retired_unit_logged_as_suppressor():
    units = [
        _unit("a", "active", "ENTER_LONG", 0.7),
        _unit("b", "retired", "ENTER_LONG", 0.0),
    ]
    result = resolve_competition(units)
    assert result["primary_unit_v1"]["pattern_id_v1"] == "a"
    assert len(result["suppressors_v1"]) == 1
    assert "negative knowledge present" in result["reason_v1"]


def test_no_active_returns_none_but_lists_others():
    units = [
        _unit("a", "validated", "ENTER_LONG", 0.9),
        _unit("b", "provisional", "NO_TRADE", 0.4),
    ]
    result = resolve_competition(units)
    assert result["primary_unit_v1"] is None
    assert len(result["challengers_v1"]) == 1
    assert len(result["observers_v1"]) == 1


def test_select_primary_returns_active_only():
    units = [
        _unit("a", "active", "ENTER_LONG", 0.6),
        _unit("b", "validated", "ENTER_LONG", 0.99),
    ]
    primary = select_primary(units)
    assert primary["pattern_id_v1"] == "a"
