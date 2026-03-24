"""
Tests for Directive 4.6.3.X — context requirements checker.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "runtime"))

from anna_modules.context_requirements import assess_context_completeness


def test_ambiguous_live_question_triggers_clarification():
    result = assess_context_completeness("Should we take it?")
    assert result["requires_clarification"] is True
    assert "question_mode" in result["missing_fields"]
    assert "Are you asking generally" in result["clarifying_question"]


def test_specific_live_trade_does_not_ask():
    result = assess_context_completeness("For a live SOL-PERP long on the 5m, what would make you exit early?")
    assert result["is_complete"] is True
    assert result["requires_clarification"] is False
    assert result["clarifying_question"] is None


def test_general_strategy_question_is_complete():
    result = assess_context_completeness("How do you know when to get out of a winning trade that is topping?")
    assert result["is_complete"] is True
    assert result["requires_clarification"] is False


def test_context_completeness_structure():
    result = assess_context_completeness("What should I do?")
    assert isinstance(result["missing_fields"], list)
    assert isinstance(result["requires_clarification"], bool)
    assert "clarifying_question" in result


def test_should_i_take_with_symbol_and_timeframe_is_complete():
    """Do not ask for context when the trade is already specified."""
    result = assess_context_completeness("Should I take this SOL-PERP long on the 5m here?")
    assert result["is_complete"] is True
    assert result["requires_clarification"] is False
