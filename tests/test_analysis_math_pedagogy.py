"""Anna math analysis pedagogy wired into prompts and pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from anna_modules.analysis_math_pedagogy import (  # noqa: E402
    MATH_ANALYSIS_PROCEDURE,
    pedagogy_snippets_for_pipeline,
)
from llm.prompt_builder import build_anna_llm_prompt  # noqa: E402


def test_pedagogy_snippets_non_empty() -> None:
    s = pedagogy_snippets_for_pipeline()
    assert len(s) >= 3
    assert "math engine procedure" in s[0].lower()


def test_prompt_includes_procedure_block() -> None:
    p = build_anna_llm_prompt(
        user_question="What is my win rate?",
        human_intent={"intent": "analysis", "topic": "performance"},
        rule_snippets=["x"],
        authoritative_facts=["FACT (math engine): test"],
        include_math_analysis_pedagogy=True,
    )
    assert "MATH ENGINE & ANALYSIS PROCEDURE" in p
    assert MATH_ANALYSIS_PROCEDURE.split("\n")[0].strip() in p or "MATH ENGINE" in p


def test_prompt_can_disable_procedure() -> None:
    p = build_anna_llm_prompt(
        user_question="Hi",
        human_intent={},
        rule_snippets=[],
        authoritative_facts=[],
        include_math_analysis_pedagogy=False,
    )
    assert "MATH ENGINE & ANALYSIS PROCEDURE" not in p
