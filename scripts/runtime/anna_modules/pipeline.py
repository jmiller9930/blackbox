"""
Anna answer resolution.

Correct flow (when ANNA_USE_LLM=1):
  classify → context ok → load memory/playbook as CONTEXT → compute AUTHORITATIVE rule facts
  → Qwen explains the question using those facts (facts = truth; LLM = meaning for this question).

Without LLM (tests / offline): memory → playbook text → template.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from anna_modules.analysis_math_pedagogy import pedagogy_snippets_for_pipeline
from anna_modules.context_memory import find_reusable_answer, store_interaction
from anna_modules.llm_output_validation import validate_llm_output
from anna_modules.strategy_playbook import apply_strategy_playbook
from llm.local_llm_client import ollama_generate
from llm.prompt_builder import build_anna_llm_prompt


def _ollama_base() -> str:
    from _ollama import ollama_base_url

    return ollama_base_url()


def resolve_answer_layers(
    conn: sqlite3.Connection | None,
    input_text: str,
    human_intent: dict[str, Any],
    *,
    use_llm: bool,
    rule_facts: dict[str, Any] | None = None,
) -> tuple[str | None, str | None, list[str], str | None, dict[str, Any]]:
    """
    When use_llm is True: always call Qwen with authoritative rule facts + playbook/memory context.
    Do not skip the LLM after rules are computed — rules state truth; the model states what it means here.

    When use_llm is False: memory → playbook prose → None (CI / no Ollama).

    Returns (summary, headline, extra_signals, answer_source, meta).
    """
    meta: dict[str, Any] = {
        "memory_hit": False,
        "llm_called": False,
        "llm_error": None,
        "playbook_hit": False,
    }
    extra_signals: list[str] = []
    rf = rule_facts or {}
    auth_lines: list[str] = list(rf.get("facts_for_prompt") or [])
    meta["rule_facts_structured"] = rf.get("structured") or {}

    memory_row: dict[str, Any] | None = None
    if conn:
        hit = find_reusable_answer(conn, question_text=input_text, human_intent=human_intent)
        if hit and hit.get("answer_text"):
            memory_row = hit
            meta["memory_hit"] = True

    pb = apply_strategy_playbook(input_text, human_intent)
    if pb:
        meta["playbook_hit"] = True
        extra_signals.extend(pb.get("extra_signals") or [])

    if use_llm:
        meta["llm_called"] = True
        snippets: list[str] = [
            "Paper-only / advisory; no live execution from Anna.",
            "Prefer concrete risk framing over generic filler.",
        ]
        snippets.extend(pedagogy_snippets_for_pipeline())
        if memory_row:
            snippets.append(
                "Prior stored answer (context only; re-explain for this turn if needed): "
                + (memory_row["answer_text"] or "")[:2000]
            )
        if pb:
            snippets.append(
                "Strategy baseline narrative (context; do not contradict AUTHORITATIVE FACTS above): "
                + (pb.get("summary") or "")[:2000]
            )
            if pb.get("headline"):
                snippets.append(f"Headline theme: {pb['headline']}")

        prompt = build_anna_llm_prompt(
            user_question=input_text,
            human_intent=human_intent,
            authoritative_facts=auth_lines,
            rule_snippets=snippets,
        )
        res = ollama_generate(prompt, base_url=_ollama_base())
        if res.error:
            meta["llm_error"] = res.error
            return _fallback_no_llm(memory_row, pb, meta, extra_signals)

        ok, _why = validate_llm_output(res.text)
        if ok:
            src = _answer_source_with_llm(memory_row is not None, pb is not None)
            return (
                res.text,
                pb.get("headline") if pb else None,
                extra_signals + ["llm:qwen", "pedagogy:math_engine_analysis"],
                src,
                meta,
            )
        meta["llm_error"] = "validation_failed"
        return _fallback_no_llm(memory_row, pb, meta, extra_signals)

    # LLM off: legacy path — first hit wins
    if memory_row:
        return (
            memory_row["answer_text"],
            None,
            ["memory:reused"],
            "memory_only",
            meta,
        )
    if pb:
        return (
            pb["summary"],
            pb.get("headline"),
            extra_signals,
            "rules_only",
            meta,
        )

    return None, None, [], None, meta


def _answer_source_with_llm(has_memory: bool, has_playbook: bool) -> str:
    if has_memory:
        return "memory_plus_qwen"
    if has_playbook:
        return "playbook_plus_qwen"
    return "rules_plus_qwen"


def _fallback_no_llm(
    memory_row: dict[str, Any] | None,
    pb: dict[str, Any] | None,
    meta: dict[str, Any],
    extra_signals: list[str],
) -> tuple[str | None, str | None, list[str], str | None, dict[str, Any]]:
    if memory_row:
        return (
            memory_row["answer_text"],
            None,
            ["memory:reused", "llm:fallback"],
            "memory_only",
            meta,
        )
    if pb:
        return (
            pb["summary"],
            pb.get("headline"),
            extra_signals + ["llm:fallback"],
            "rules_only",
            meta,
        )
    return None, None, [], None, meta


def maybe_store_interaction(
    conn: sqlite3.Connection | None,
    *,
    input_text: str,
    human_intent: dict[str, Any],
    final_summary: str,
    answer_source: str | None,
    pipeline_meta: dict[str, Any],
) -> str | None:
    """Store new answers as candidate (not clarification paths)."""
    if not conn or not answer_source:
        return None
    if answer_source == "clarification_requested":
        return None
    if answer_source == "memory_only":
        return None
    if answer_source == "template_fallback":
        return None
    rid = store_interaction(
        conn,
        question_text=input_text,
        answer_text=final_summary,
        answer_source=answer_source,
        human_intent=human_intent,
        pipeline_meta=pipeline_meta,
        validation_status="candidate",
    )
    return rid
