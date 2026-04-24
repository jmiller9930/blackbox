"""
Structured **system dictionary** for Ask DATA — bounded context for natural-language Q&A.

Content is operator-safe summaries only (no live secrets, no file paths beyond public docs).
Expand by appending topics; keep each value short so the bundle stays prompt-friendly.
"""

from __future__ import annotations

from typing import Any


def system_dictionary_context_v1() -> dict[str, Any]:
    return {
        "schema": "ask_data_system_dictionary_v1",
        "topics": {
            "student_fold_levels": (
                "**Level 1 — Exam list:** rows from the scorecard; each row is one exam (`job_id`). "
                "**Level 2 — One run:** run summary band + trade carousel (one tile per closed trade / trade set). "
                "**Level 3 — Trade deep dive:** `student_decision_record_v1` — every field for that `trade_id`, "
                "with explicit `data_gap` where exporters are not wired. Student LLM path is separate from Ask DATA."
            ),
            "ask_data_vs_student": (
                "**Ask DATA** (this channel) explains the Pattern UI, glossary topics, and run/scorecard facts from the bundle — "
                "it does **not** grade exams or emit `student_output_v1`. **Student** (Proctor / parallel replay) produces graded "
                "decisions and learning-store rows. Do not conflate the two."
            ),
            "ollama_role_routing": (
                "Ollama is **role-routed**: Barney + Ask DATA default to **PML lightweight** (fast UI). "
                "The **System Agent** tier uses a stronger coder model for structured explanations only — still **no direct execution**. "
                "**DeepSeek escalation** is for explicit debug/deep-reasoning prompts. Proof: `GET /api/operator/ollama-role-routing` on this Flask host."
            ),
            "scorecard_vs_referee": (
                "The **scorecard** is the operator audit table (JSONL). **Referee** truth for a trade lives in `replay_outcomes_json` inside batch results. "
                "Win rate on L1 is Referee trade outcomes for that run, not Ask DATA opinion."
            ),
            "memory_modes": (
                "`context_signature_memory_mode`: **off** — no retrieval/write; **read** — may load prior signatures; **read_write** — may append. "
                "Whether a scenario actually used memory is in per-scenario results and scorecard audit fields — not inferred here."
            ),
            "clear_vs_reset_learning": (
                "**Clear scorecard** removes lines from `batch_scorecard.jsonl` only. **Reset learning** is a separate destructive flow "
                "for engine / pattern memory with typed confirmation — never implied by Ask DATA answers."
            ),
            "exam_artifacts": (
                "Exam units, decision frames, deliberation, and grading are **versioned contracts** (see architecture doc §11 / GT directives). "
                "Ask DATA may summarize what exists in the bundle; it does **not** create or mutate exam packs."
            ),
            "data_gap_honesty": (
                "`data_gap` means the field is **not available** from wired sources — not a bug in the operator question. "
                "Prefer naming the gap (`data_gaps[]` on L3) over guessing."
            ),
        },
        "how_to_use": (
            "Ask in plain English about controls, columns, memory, runs, or how L1/L2/L3 relate. "
            "For **deep diagnostic reasoning**, prefix with `[debug]` or `[escalation]`. "
            "For **structured / API / schema** style questions, ask explicitly (e.g. JSON validation, routes) — the router may select a stronger model."
        ),
    }


__all__ = ["system_dictionary_context_v1"]
