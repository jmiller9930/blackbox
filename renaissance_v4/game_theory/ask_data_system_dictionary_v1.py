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
            "exam_ep_student_panel_gt020": (
                "**GT_DIRECTIVE_020 — Exam E/P visibility:** `exam_e_score_v1` and `exam_p_score_v1` come only from "
                "`compute_exam_grade_v1` (denormalized on the scorecard). L1 road bands and the Student panel table use **the same** "
                "scalars (not a shadow metric). `l1_e_value_source_v1` / `l1_p_value_source_v1` label **exam_pack_grading_v1** vs "
                "batch proxies so operators are never confused. `exam_pass_v1` is the pack pass bit. When grading is missing but "
                "expected, L3 emits a **critical** `exam_grading_missing_for_scored_run_v1` gap."
            ),
            "operator_framework_scenarios_templates": (
                "**Framework / pattern:** use the **Pattern** (operator recipe) control — it selects which curated playbook runs, "
                "or **Custom** for JSON from the textarea. **Policy framework** is scenario metadata for governance/audit when the manifest provides it — "
                "not a separate “load framework file” button in this UI. **Templates / presets:** built-in scenarios come from `game_theory/examples` "
                "when not Custom; the **Custom JSON** textarea is the batch body when Pattern is Custom; **Scenario presets** in Advanced lists raw example files. "
                "**Uploaded strategy:** turn on **use_operator_uploaded_strategy** in UI context, pass manifest validation in Controls, then run — scenarios resolve from that manifest when enabled. "
                "**Paste in Ask DATA (conversation):** paste manifest JSON, scenario snippets, or validator errors **into this same question box** for read-only checks and suggested wording. "
                "Ask DATA should **ask for one missing artifact at a time** when the bundle has no file body. "
                "**Honesty:** Ask DATA does **not** perform the Controls file upload, attach binaries, or start runs — **binding submit** stays in the operator UI + Run."
            ),
            "student_learning_persistence_code": (
                "**Student learning (what the stack persists):** the **Student / Proctor** path grades exam-style replays and writes **versioned** rows "
                "(e.g. `student_output_v1`, learning-store JSONL) for retrieval on later units — contracts live under `student_proctor/` and GT directives. "
                "The **Referee** batch does not “learn” online; improvement comes from **comparing runs** and promoted bundles per governance. "
                "Ask DATA does not mutate stores; use the Student panel + scorecard + architecture doc for the full seam."
            ),
            "submission_paths_walk_template_strategy_framework": (
                "**Submitting a batch — three paths:** **A)** built-in **pattern/recipe** (not Custom) from examples; **B)** **uploaded strategy** manifest with "
                "`use_operator_uploaded_strategy` + validated `operator_strategy_upload_state`; **C)** **Custom JSON** scenarios (and policy/framework metadata on scenarios/manifests). "
                "Ask DATA should **only** walk the paths the operator needs, using **leading questions** one at a time. Full checklist: "
                "`static_knowledge.ask_data_submit_three_paths_walkthrough_v1`."
            ),
        },
        "how_to_use": (
            "Ask in plain English about controls, columns, memory, runs, or how L1/L2/L3 relate. "
            "To **submit** a recipe run, uploaded strategy, or Custom/framework-heavy batch, Ask DATA can walk you via **leading questions** (see "
            "`static_knowledge.ask_data_submit_three_paths_walkthrough_v1`) — it still cannot Run or Upload for you. "
            "For **uploads / manifests**, paste text in this box — Ask DATA can review and say what is still required; it does not replace the Controls upload button. "
            "For **deep diagnostic reasoning**, prefix with `[debug]` or `[escalation]`. "
            "For **structured / API / schema** style questions, ask explicitly (e.g. JSON validation, routes) — the router may select a stronger model. "
            "After each reply, use **Helpful / Not helpful** (``POST /api/ask-data/feedback``) so repeat questions can surface prior operator signals in "
            "``operator_feedback_signals`` — telemetry for better explanations, not Referee truth."
        ),
    }


__all__ = ["system_dictionary_context_v1"]
