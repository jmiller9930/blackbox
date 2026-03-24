"""Authoritative rule facts for LLM grounding."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "runtime"))

from anna_modules.rule_facts import compute_rule_facts


def test_confidence_gate_facts():
    q = "If a setup scores 61 confidence after adjustments and our threshold is 65, what should happen?"
    hi = {"intent": "QUESTION", "topic": "trading_general"}
    rf = compute_rule_facts(q, hi)
    facts = rf["facts_for_prompt"]
    assert any("61" in f for f in facts)
    assert any("65" in f for f in facts)
    assert rf["structured"].get("forward_to_execution") is False


def test_definition_question_includes_registry_facts():
    q = "What is a spread?"
    hi = {"intent": "QUESTION", "topic": "trading_general"}
    rf = compute_rule_facts(q, hi, concept_ids=["spread"])
    facts = "\n".join(rf["facts_for_prompt"])
    assert "bid" in facts.lower() and "ask" in facts.lower()
    assert "registry" in facts.lower()
    assert "spread" in rf["structured"].get("registry_definition_grounding", [])
