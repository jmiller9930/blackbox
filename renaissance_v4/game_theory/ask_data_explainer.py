"""
Ask DATA — bounded PML self-explainer (run + system facts only).

Uses the same local Ollama stack as Barney when enabled; otherwise deterministic fallback.
Not a general chatbot: off-topic questions are refused before LLM when possible.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Whitelist keys from scorecard JSONL / batch-detail scorecard (no raw scenario bodies).
_SCORECARD_SNAPSHOT_KEYS: tuple[str, ...] = (
    "job_id",
    "started_at_utc",
    "ended_at_utc",
    "duration_sec",
    "status",
    "learning_status",
    "total_scenarios",
    "total_processed",
    "ok_count",
    "failed_count",
    "workers_used",
    "candidate_count",
    "selected_candidate_id",
    "winner_vs_control_delta",
    "memory_used",
    "memory_records_loaded",
    "groundhog_status",
    "recall_attempts",
    "recall_matches",
    "recall_bias_applied",
    "referee_win_pct",
    "batch_sessions_judged",
    "run_ok_pct",
    "session_log_batch_dir",
    "operator_recipe_id",
    "operator_recipe_label",
    "memory_context_impact_audit_v1",
)

_UI_CONTEXT_ALLOWED: frozenset[str] = frozenset(
    {
        "operator_recipe_id",
        "evaluation_window_mode",
        "evaluation_window_custom_months",
        "context_signature_memory_mode",
        "use_operator_uploaded_strategy",
        "scenarios_source",
        "recipe_label",
        "pattern_game_web_ui_version",
    }
)

_OFF_TOPIC_REGEX = re.compile(
    r"(?i)\b("
    r"weather|forecast|\btemperature\b|"
    r"capital of\b|who won the superbowl|super bowl|"
    r"tell me a joke|\bcook me\b|"
    r"what is the meaning of life|horoscope|"
    r"translate\b.*\bto\b (?:french|spanish|german|japanese)|"
    r"write a poem|song lyrics"
    r")\b"
)


def _runtime_imports() -> Any:
    rt = str(_REPO_ROOT / "scripts" / "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    from llm.local_llm_client import ollama_generate

    return ollama_generate


def ask_data_use_llm() -> bool:
    v = os.environ.get("ASK_DATA_USE_LLM")
    if v is not None and str(v).strip() != "":
        return str(v).strip().lower() not in ("0", "false", "no", "off")
    from renaissance_v4.game_theory.barney_summary import barney_use_llm

    return barney_use_llm()


def pml_static_knowledge_v1() -> dict[str, Any]:
    """Structured glossary and workflow — no live run numbers."""
    return {
        "schema": "pml_static_knowledge_v1",
        "what_is_pml": (
            "Pattern Machine Learning (PML) is this web UI plus a replay engine: you pick an operator "
            "pattern (recipe), an evaluation window, optional contextual memory mode, and scenarios. "
            "The Referee replays historical bars and scores outcomes. Nothing here places live trades."
        ),
        "pattern_vs_framework_vs_manifest": (
            "**Pattern** (operator recipe) chooses which curated playbook or Custom JSON drives the batch. "
            "**Policy framework** (when used by a scenario) attaches governance/audit metadata for replay. "
            "**Manifest** is the JSON file path the engine loads for policy/stack — shown in batch audit when present. "
            "Exact fields for your run appear only in run facts / scorecard — do not invent paths."
        ),
        "reference_comparison": (
            "When learning recipes run multiple candidates against a control, **Reference Comparison** "
            "means the batch compares candidates to a baseline/control per harness rules. "
            "Winner columns (e.g. selected candidate, WΔ) come from audit counters — if null, say not in data."
        ),
        "memory_modes": (
            "**context_signature_memory_mode**: `off` — memory disabled. `read` — may load prior signatures for recall. "
            "`read_write` — may read and append new memory records when the scenario allows. "
            "Whether memory actually influenced a scenario is per-scenario in results — use run facts / scorecard."
        ),
        "scenarios_sources": (
            "Scenarios come from: (1) built-in recipe files under game_theory/examples when Pattern is not Custom, "
            "(2) the Custom JSON textarea when Pattern is Custom, (3) operator-uploaded strategy when the upload "
            "checkbox is on and a valid manifest was processed. The UI state you receive states which applies."
        ),
        "scorecard_columns_hint": (
            "Abbreviations on the scorecard table are documented in the legend above the table (Run OK %, "
            "Session WIN %, Learn, DW, Bars, Cand, Sel, WΔ, Mem, …). If the operator asks about one column, "
            "explain using that legend wording; do not invent new meanings."
        ),
        "clear_vs_reset": (
            "**Clear Card** truncates `batch_scorecard.jsonl` only (audit table input). "
            "**Reset Learning State** is destructive for engine memory files — separate flow with typed confirm."
        ),
        "operator_controlled": (
            "Operator controls: pattern, evaluation window, workers slider, memory mode, custom JSON, "
            "uploaded strategy toggle, run/reset actions. Engineering controls build/version and host paths."
        ),
        "refusal_policy": (
            "If the question is general trivia, unrelated life advice, or open internet facts, refuse in one short "
            "paragraph and say you only explain this Pattern Game UI, its runs, and controls."
        ),
    }


def scorecard_snapshot_for_ask(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    out = {"schema": "pml_scorecard_snapshot_v1"}
    for k in _SCORECARD_SNAPSHOT_KEYS:
        if k in entry:
            out[k] = entry.get(k)
    return out if len(out) > 1 else None


def sanitize_ui_context(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in _UI_CONTEXT_ALLOWED:
            continue
        if k == "evaluation_window_custom_months":
            try:
                out[k] = int(v) if v is not None else None
            except (TypeError, ValueError):
                continue
        elif k in ("use_operator_uploaded_strategy",):
            out[k] = bool(v)
        elif k == "recipe_label":
            s = str(v).strip()[:160]
            if s:
                out[k] = s
        else:
            s = str(v).strip()[:500] if v is not None else ""
            if s:
                out[k] = s
    return out


def looks_off_topic(question: str) -> bool:
    q = (question or "").strip()
    if len(q) < 2:
        return False
    if _OFF_TOPIC_REGEX.search(q):
        return True
    return False


def refusal_text_general() -> str:
    return (
        "Ask DATA only explains this Pattern Machine Learning UI, your current run facts, scorecard row, "
        "and the bundled operator glossary. I cannot answer general trivia or unrelated topics. "
        "Try rephrasing in terms of this screen (for example: memory mode, scorecard columns, or what failed in the run)."
    )


def _fallback_answer_from_bundle(question: str, bundle: dict[str, Any]) -> tuple[str, str]:
    """Short non-LLM answer; answer_source tag."""
    qlow = (question or "").lower()
    static = bundle.get("static_knowledge") or {}
    facts = bundle.get("barney_facts")
    snap = bundle.get("scorecard_snapshot")
    if "what does pml" in qlow or "what is pml" in qlow or "what does pattern machine" in qlow:
        return (str(static.get("what_is_pml") or ""), "app_knowledge")
    if "pattern" in qlow and "manifest" in qlow:
        return (str(static.get("pattern_vs_framework_vs_manifest") or ""), "app_knowledge")
    if "memory" in qlow and ("mode" in qlow or "using" in qlow):
        return (str(static.get("memory_modes") or ""), "app_knowledge")
    if snap and isinstance(snap, dict):
        mca = snap.get("memory_context_impact_audit_v1")
        if isinstance(mca, dict) and mca.get("barney_operator_truth_line_v1"):
            if "memory" in qlow and (
                "impact" in qlow
                or "deterministic" in qlow
                or "recall" in qlow
                or "bias" in qlow
                or "context" in qlow
            ):
                return (str(mca["barney_operator_truth_line_v1"]), "run_facts")
    if facts and isinstance(facts, dict) and facts.get("memory_operator_truth_line_v1"):
        if "memory" in qlow and (
            "impact" in qlow
            or "deterministic" in qlow
            or "recall" in qlow
            or "bias" in qlow
        ):
            return (str(facts["memory_operator_truth_line_v1"]), "run_facts")
    if "scenario" in qlow and ("where" in qlow or "come from" in qlow or "hidden" in qlow or "custom" in qlow):
        return (str(static.get("scenarios_sources") or ""), "app_knowledge")
    if facts and isinstance(facts, dict):
        st = facts.get("run_status")
        if "fail" in qlow and st == "error":
            em = facts.get("error_message") or "not available in current run data"
            return (
                f"This run failed (status error). Error message in run data: {em}. "
                "No extra causes are inferred here.",
                "run_facts",
            )
        if "baseline" in qlow or "beat" in qlow or "improve" in qlow:
            nw = facts.get("no_winner")
            wd = facts.get("winner_vs_control_delta")
            if nw is True:
                return (
                    "Run facts say **no_winner**: no candidate beat the baseline in this batch (per harness audit).",
                    "run_facts",
                )
            return (
                f"Winner vs control delta in run facts: {wd!r}. "
                "If null, that comparison was not present in run data.",
                "run_facts",
            )
    if snap and "column" in qlow:
        return (
            (static.get("scorecard_columns_hint") or "Use the legend above the scorecard table for column meanings.")
            + " If you need one cell, click the row and read batch detail.",
            "app_knowledge",
        )
    return (
        "I do not have a keyword-matched canned answer. "
        "Turn on the local formatter (Ollama / same as Barney) for a fuller reply, "
        "or ask about a specific control, memory mode, or scorecard column named in the legend. "
        "Anything not in the bundled JSON is: not available in current run data or not in this build.",
        "fallback",
    )


def build_ask_data_bundle_v1(
    *,
    barney_facts: dict[str, Any] | None,
    scorecard_snapshot: dict[str, Any] | None,
    ui_context: dict[str, Any],
    operator_strategy_state: dict[str, Any] | None,
    job_resolution: str,
) -> dict[str, Any]:
    return {
        "schema": "ask_data_bundle_v1",
        "job_resolution": job_resolution,
        "static_knowledge": pml_static_knowledge_v1(),
        "barney_facts": barney_facts,
        "scorecard_snapshot": scorecard_snapshot,
        "ui_context": ui_context,
        "operator_strategy_upload_state": operator_strategy_state,
    }


def ask_data_format_with_llm(bundle: dict[str, Any], question: str, *, timeout: float = 120.0) -> tuple[str, str | None]:
    from renaissance_v4.game_theory.ollama_role_routing_v1 import (
        pml_lightweight_ollama_base_url,
        pml_lightweight_ollama_model,
    )

    ollama_generate = _runtime_imports()
    base = pml_lightweight_ollama_base_url()
    model = pml_lightweight_ollama_model()
    payload = json.dumps(bundle, indent=2, ensure_ascii=False)
    prompt = (
        "You are **Ask DATA** — a Pattern Machine Learning (PML) **self-explainer** for operators.\n\n"
        "RULES (hard):\n"
        "- Answer ONLY using: (1) the JSON bundle sections `static_knowledge`, `barney_facts`, "
        "`scorecard_snapshot`, `ui_context`, `operator_strategy_upload_state`, and `job_resolution`. "
        "Do NOT use outside knowledge, the internet, or guesses.\n"
        "- If the bundle does not contain enough information, say clearly: "
        "**not available in current run data** or **not available in current app state** or "
        "**not implemented in this build** — pick the best fit.\n"
        "- Do NOT invent controls, columns, memory behavior, strategy logic, or file paths.\n"
        "- Plain English first; short by default; add technical detail only if the question asks for it.\n"
        "- If the question is general trivia or unrelated to this application, refuse in one short paragraph "
        "(same idea as static_knowledge.refusal_policy).\n"
        "- At the end, add a single line starting with **Sources used:** listing only from: "
        "`run_facts` | `scorecard` | `ui` | `static` | `upload` | `refused` — comma-separated, "
        "reflecting what you actually relied on.\n\n"
        f"OPERATOR QUESTION:\n{question.strip()}\n\n"
        "--- BUNDLE JSON ---\n"
        + payload
    )
    res = ollama_generate(prompt, base_url=base, model=model, timeout=timeout)
    if res.error:
        return "", res.error
    return (res.text or "").strip(), None


def ask_data_answer(
    question: str,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    q = (question or "").strip()
    if not q:
        return {
            "ok": False,
            "text": "",
            "answer_source": "refused",
            "error": "question is empty",
        }
    if looks_off_topic(q):
        return {
            "ok": True,
            "text": refusal_text_general(),
            "answer_source": "refused",
            "error": None,
        }
    if not ask_data_use_llm():
        txt, src = _fallback_answer_from_bundle(q, bundle)
        return {"ok": True, "text": txt, "answer_source": src, "error": None}
    txt, err = ask_data_format_with_llm(bundle, q)
    if err or not txt:
        fb, src = _fallback_answer_from_bundle(q, bundle)
        return {
            "ok": True,
            "text": fb + ("\n\n(Formatter unavailable: " + str(err) + ")" if err else ""),
            "answer_source": src + "+fallback",
            "error": err,
        }
    return {"ok": True, "text": txt, "answer_source": "llm", "error": None}
