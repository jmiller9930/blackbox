"""
Ask DATA — bounded PML self-explainer (run + system facts + **system dictionary**).

When LLM is enabled, an **intent router** (``ask_data_router_v1``) picks the best **read-only**
tier: fast **PML lightweight**, stronger **system_agent** for schema/API-style questions, or
**deepseek_escalation** for explicit ``[debug]`` / ``[escalation]`` prompts. Models never execute
mutations. Disable: ``ASK_DATA_ROUTER=0``; force tier: ``ASK_DATA_ROUTE=lightweight|system_agent|deepseek``.
Operator **signals** (``ask_data_operator_feedback_v1``): append-only JSONL + ``POST /api/ask-data/feedback``;
rollups inject ``operator_feedback_signals`` into the bundle (telemetry, not Referee). Disable:
``ASK_DATA_OPERATOR_FEEDBACK=0``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.ask_data_operator_surface_v1 import (
    ASK_DATA_UI_CONTEXT_ALLOWED as _UI_CONTEXT_ALLOWED,
    build_operator_surface_catalog_for_ask_v1,
)

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
    "replay_decision_windows_sum",
    "replay_bars_processed_sum",
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
        "knowledge_bundle_robustness_v1": (
            "**Design intent:** Ask DATA is anchored on a **wide, honest bundle** — factual sections such as "
            "`data_health_snapshot`, `evaluation_window_resolved`, `wiring_module_board`, run/scorecard slices, "
            "`ui_context`, `operator_strategy_upload_state`, and `system_dictionary` — not any single scripted flow. "
            "Curated walkthroughs (e.g. three submission paths, paste-and-review hints) are **reusable patterns** when "
            "the operator’s question matches; they are **not** an exhaustive product spec. If a walkthrough and a factual "
            "section disagree, **follow the factual section** and say what is still unknown."
        ),
        "ask_data_clarifying_question_v1": (
            "**Leading the operator when intent is unclear:** After you explain what the bundle supports, if the question "
            "could still mean more than one thing (or you need them to pick a scope), end with **exactly one** short, "
            "answerable question — e.g. “Do you mean the **calendar evaluation window** in Controls, **5-minute bar rows** "
            "on the tape, or **DW / decision-window counts** from your last batch?” — not a long questionnaire. "
            "Ask DATA does **not** change Controls; the operator must adjust the UI. Use `operator_surface_catalog` for control names, DOM ids, and limits."
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
        "evaluation_window_vs_bar_cadence_v1": (
            "**Two different “windows”:** (1) **Evaluation window** in the UI — modes `12`, `18`, `24`, or `custom` — "
            "means **approximately that many calendar months** of historical tape counted backward from the **last bar** "
            "in the loaded dataset (see `evaluation_window_resolved` in the bundle when present). "
            "(2) **Bar interval** — each row in SQLite table `market_bars_5m` is one **5-minute** OHLC candle. "
            "So “12” is **not** “12 minutes” or “5 minutes”; it is **~12 calendar months** of 5m bars for replay slicing "
            "unless the bundle’s `data_health_snapshot` shows a shorter tape or clamping in run audit."
        ),
        "operator_time_window_disambiguation_v1": (
            "**“Window” is overloaded** — more than one answer can be correct; separate them for the operator:\n"
            "(1) **Evaluation / calendar window** (Controls) — last **N approximate calendar months** of tape from the **last bar**; "
            "see `evaluation_window_resolved` and `ui_context.evaluation_window_mode`.\n"
            "(2) **5m bar resolution** — each replay row is a **five-minute** OHLC candle in `market_bars_5m`; "
            "see `data_health_snapshot.bar_interval` and row counts.\n"
            "(3) **Decision windows (DW)** — **replay engine step counters** during a batch (scorecard / telemetry “Work” / DW); "
            "not calendar months and not “five minutes of clock time” per count; see `replay_decision_windows_sum` on the scorecard snapshot when present.\n"
            "(4) **Exam / Student “N bars”** — some packs use a **fixed count of five-minute bars** for termination or context; "
            "that is **pack-specific** and only answer numerically if exam/run facts are in the bundle.\n"
            "If the question mixes these (e.g. “5m trade window” + “operating under”), give **each applicable reading** in short labeled bullets; "
            "say explicitly that **multiple readings apply** when they do."
        ),
        "ask_data_upload_paste_conversation_v1": (
            "**Strategy / manifest — conversational help in Ask DATA:** If the bundle does not contain the file body, "
            "reply in a **short, human turn**: invite the operator to **paste** manifest JSON, the failing slice, or the validation error **into this Ask DATA box** on the next message "
            "so you can reformat, list missing keys, and sanity-check — all **read-only**. "
            "Ask **one** concrete question at a time (e.g. “Paste the top-level keys of your manifest” or “Paste the last validator line”). "
            "**Do not** imply you can click Upload for them or persist files; **binding** upload + Run stays in **Controls** with `use_operator_uploaded_strategy` and `operator_strategy_upload_state` in the bundle when present."
        ),
        "ask_data_submit_three_paths_walkthrough_v1": (
            "**Three ways to get scenarios into a batch — walk operators with leading questions (one per reply).** "
            "If intent is unclear, **first** ask: “Which path — **A** built-in pattern/recipe, **B** uploaded strategy manifest, or **C** Custom JSON / policy-heavy scenario?” "
            "**Path A — Pattern / built-in “template” (curated recipe, not Custom):** Required before Run: Pattern **not** set to Custom; pick **operator recipe**; set **evaluation window**; "
            "`context_signature_memory_mode` as intended; **workers**; confirm scenarios resolve from **examples** (see `static_knowledge.scenarios_sources`). "
            "Leading Q examples: “Is Pattern set to a named recipe (not Custom)?” then “Which evaluation window?” then “Ready to hit Run?” "
            "**Path B — Operator-uploaded strategy:** Required: enable **`use_operator_uploaded_strategy`** in UI context; a **validated** manifest via Controls upload (see `operator_strategy_upload_state` in the bundle for errors/labels). "
            "Leading Q: “Are you binding an uploaded manifest for this batch?” then “Does upload state show valid?” then “Paste validator output here if not.” "
            "**Path C — Custom JSON / framework wording:** Pattern **Custom**; paste **scenario array** (or object the UI expects) in the **Custom JSON** path; **policy framework** is governance metadata carried on scenarios/manifests — not a separate mystery upload in this UI. "
            "Leading Q: “Do you need Custom JSON in the textarea?” vs “Are you asking about policy framework labels on scenarios?” "
            "**Cross-cutting honesty:** Ask DATA does **not** Run or Upload; it only explains and asks. **Run** is always the operator button after Controls are satisfied."
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


def _operator_window_question_needs_multisense(qlow: str) -> bool:
    """
    True when the operator probably means more than one “window” (calendar slice vs 5m bars vs DW).

    Used so Ask DATA does not answer **only** evaluation_window_resolved when they also invoked 5m / trade / bar language.
    """
    scope = any(
        x in qlow
        for x in (
            "window",
            "operating",
            "time frame",
            "timeframe",
            "under ",
            "which window",
            "what window",
        )
    )
    bar_or_dw = any(
        x in qlow
        for x in (
            "5m",
            "5 m",
            "five-minute",
            "five minute",
            "trade window",
            "bar interval",
            "ohlc",
            "market_bars",
            "decision window",
            " dw",
            "replay depth",
            "telemetry",
        )
    )
    return scope and bar_or_dw


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
    dh = bundle.get("data_health_snapshot")
    if isinstance(dh, dict) and any(
        x in qlow
        for x in (
            "sql",
            "sqlite",
            "database",
            "how much data",
            "db size",
            "rows in",
            "bar row",
            "market_bars",
        )
    ):
        parts: list[str] = []
        if dh.get("summary_line"):
            parts.append(str(dh["summary_line"]))
        if dh.get("all_bars_count") is not None:
            parts.append(f"All symbols: {dh.get('all_bars_count')} rows in `market_bars_5m`.")
        if dh.get("solusdt_bar_count") is not None:
            parts.append(f"{dh.get('replay_symbol', 'SOLUSDT')}: {dh.get('solusdt_bar_count')} rows.")
        sz = dh.get("database_file_size_bytes")
        if isinstance(sz, int):
            parts.append(f"SQLite file size on disk: {sz} bytes (`database_path` in bundle).")
        elif dh.get("database_path"):
            parts.append(f"SQLite path: {dh.get('database_path')}.")
        if dh.get("bar_interval"):
            parts.append(str(dh["bar_interval"]))
        if parts:
            return (" ".join(parts), "data_health")
    ew = bundle.get("evaluation_window_resolved")
    if _operator_window_question_needs_multisense(qlow) and isinstance(dh, dict):
        parts_ms: list[str] = []
        dis = static.get("operator_time_window_disambiguation_v1")
        if dis:
            parts_ms.append(str(dis))
        if isinstance(ew, dict) and not ew.get("resolve_error") and ew.get("effective_calendar_months") is not None:
            parts_ms.append(
                f"**Controls — evaluation (calendar) window:** mode {ew.get('evaluation_window_mode')!r} → "
                f"**~{ew.get('effective_calendar_months')} calendar months** of tape from the last bar."
            )
        bi = dh.get("bar_interval") or "Replay uses SQLite table `market_bars_5m`: one row per **5-minute** OHLC bar."
        parts_ms.append(f"**Tape — bar resolution:** {bi} Summary: {dh.get('summary_line') or 'see `data_health_snapshot`.'}")
        if isinstance(snap, dict) and snap.get("replay_decision_windows_sum") is not None:
            parts_ms.append(
                "**Replay work — decision windows (DW):** for the selected scorecard job, "
                f"`replay_decision_windows_sum` is **{snap.get('replay_decision_windows_sum')}** "
                "(engine step counts — not “5 minutes” each and not the same as the calendar evaluation window)."
            )
        parts_ms.append(
            "**Follow-up (pick one):** Reply with **1** for the **calendar evaluation window** in Controls, **2** for **5-minute bar rows** "
            "on the SQLite tape, or **3** for **DW / decision-window replay depth** for a batch (include `job_id` in Ask DATA if you mean a specific row)."
        )
        return ("\n\n".join(parts_ms), "static+data_health+evaluation_window")
    if isinstance(ew, dict) and not ew.get("resolve_error") and any(
        x in qlow
        for x in (
            "evaluation window",
            "time window",
            "how many month",
            "operating under",
            "calendar month",
            "window mode",
        )
    ):
        mode = ew.get("evaluation_window_mode", "?")
        em = ew.get("effective_calendar_months")
        cadence = static.get("evaluation_window_vs_bar_cadence_v1") or ""
        if em is not None:
            head = (
                f"From your current Controls: `evaluation_window_mode` is {mode!r}, so replay uses the last "
                f"**~{em} calendar months** of available bars (counted from the last bar), **not** a five-minute wall-clock window. "
            )
            tail = f"\n\n{cadence}" if cadence else ""
            return (head + tail, "evaluation_window")
    wb = bundle.get("wiring_module_board")
    if isinstance(wb, dict) and wb.get("modules") and any(
        x in qlow
        for x in (
            "wired",
            "how is the code",
            "how the code",
            "module board",
            "subsystems",
            " wiring",
            "wiring ",
            "def-001",
            "def001",
        )
    ):
        lines: list[str] = []
        for m in wb["modules"][:14]:
            if not isinstance(m, dict):
                continue
            lab = str(m.get("label") or m.get("id") or "?")
            ok = "OK" if m.get("ok") else "not OK"
            det = str(m.get("detail") or "")[:220]
            lines.append(f"- **{lab}** ({ok}): {det}")
        note = str(wb.get("def001_note") or "").strip()
        body = "\n".join(lines) if lines else "(no module rows)"
        if note:
            body = body + "\n\n" + note
        return (body, "wiring")
    osc = bundle.get("operator_surface_catalog")
    if isinstance(osc, dict) and any(
        x in qlow
        for x in (
            "what controls",
            "which controls",
            "controls in",
            "settings in",
            "dom id",
            "ui_context keys",
            "configurable",
        )
    ):
        keys = osc.get("ask_data_ui_context_keys") or []
        lim = osc.get("parallel_limits") or {}
        plist = osc.get("pattern_select", {}).get("options") or []
        psum = ", ".join(f"{p.get('recipe_id')}" for p in plist[:8] if isinstance(p, dict)) or "(see catalog)"
        return (
            "Primary controls are described in the bundle section **`operator_surface_catalog`** (data-generated from "
            f"code — DOM ids, evaluation-window options, worker limits, pattern list). "
            f"**`ui_context`** echoes only these keys to Ask DATA: {', '.join(keys)}. "
            f"Worker limits on this host: hard_cap={lim.get('hard_cap_workers')}, recommended={lim.get('recommended_max_workers')}. "
            f"Visible pattern recipe_ids include: {psum}. Ask DATA cannot change Controls — adjust the UI, then ask again. "
            "**Which control do you want detail on** (e.g. evaluation window, workers, or upload toggle)?",
            "operator_surface",
        )
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
    walk = static.get("ask_data_submit_three_paths_walkthrough_v1")
    if isinstance(walk, str) and walk.strip():
        walk_hit = (
            ("all three" in qlow)
            or ("walk me" in qlow)
            or (
                any(x in qlow for x in ("submit", "walk", "guide", "through", "require", "required", "leading", "step by step"))
                and any(x in qlow for x in ("template", "strateg", "framework", "pattern", "manifest", "upload", "custom", "recipe"))
            )
        )
        if walk_hit:
            return (str(walk), "app_knowledge")
    sdict = bundle.get("system_dictionary") or {}
    topics = sdict.get("topics") if isinstance(sdict, dict) else {}
    upaste = static.get("ask_data_upload_paste_conversation_v1")
    if isinstance(upaste, str) and upaste.strip():
        if ("strateg" in qlow or "manifest" in qlow) and any(
            x in qlow
            for x in (
                "paste",
                "format",
                "conversation",
                "this box",
                "what should i paste",
                "what do i send",
                "share it back",
            )
        ):
            return (str(upaste), "app_knowledge")
    if isinstance(topics, dict):
        fw_hit = (
            "framework" in qlow
            or ("pattern" in qlow and any(x in qlow for x in ("chang", "switch", "select", "pick", "choose")))
            or ("strateg" in qlow and any(x in qlow for x in ("load", "upload", "manifest")))
            or "uploaded strategy" in qlow
            or ("template" in qlow and "load" in qlow)
            or "custom json" in qlow
            or ("preset" in qlow and "scenario" in qlow)
            or ("how do i load" in qlow and any(x in qlow for x in ("scenario", "template", "strateg")))
        )
        if fw_hit:
            t = topics.get("operator_framework_scenarios_templates")
            if t:
                return (str(t), "system_dictionary")
        stu_learn_hit = ("student" in qlow or "proctor" in qlow) and any(
            x in qlow for x in ("learn", "persist", "learning store", "saved to", "what does the code")
        )
        if stu_learn_hit:
            t = topics.get("student_learning_persistence_code")
            if t:
                return (str(t), "system_dictionary")
        if any(x in qlow for x in ("level 1", "level 2", "level 3", "l1 ", "l2 ", "l3 ", "exam list", "carousel")):
            t = topics.get("student_fold_levels")
            if t:
                return (str(t), "system_dictionary")
        if "ask data" in qlow and "student" in qlow:
            t = topics.get("ask_data_vs_student")
            if t:
                return (str(t), "system_dictionary")
        if "ollama" in qlow and "rout" in qlow:
            t = topics.get("ollama_role_routing")
            if t:
                return (str(t), "system_dictionary")
        if "data_gap" in qlow or "data gap" in qlow:
            t = topics.get("data_gap_honesty")
            if t:
                return (str(t), "system_dictionary")
    return (
        "I do not have a keyword-matched canned answer. "
        "Turn on the local formatter (Ollama / same as Barney) for a fuller reply, "
        "or ask about a specific control, memory mode, or scorecard column named in the legend. "
        "Anything not in the bundled JSON is: not available in current run data or not in this build.",
        "fallback",
    )


def snapshot_data_health_for_ask_v1() -> dict[str, Any]:
    """Live SQLite / bar-table facts for Ask DATA (same source as ``/api/data-health``)."""
    from pathlib import Path

    from renaissance_v4.game_theory.data_health import get_data_health

    h = get_data_health()
    path = Path(str(h.get("database_path") or ""))
    size_b: int | None = None
    if path.is_file():
        try:
            size_b = int(path.stat().st_size)
        except OSError:
            size_b = None
    return {
        "schema": "ask_data_data_health_snapshot_v1",
        "bar_interval": "Each replay bar row is one 5-minute OHLC interval (SQLite table `market_bars_5m`).",
        "database_path": h.get("database_path"),
        "database_file_exists": h.get("database_file_exists"),
        "database_file_size_bytes": size_b,
        "overall_ok": h.get("overall_ok"),
        "database_open_ok": h.get("database_open_ok"),
        "table_market_bars_ok": h.get("table_market_bars_ok"),
        "replay_symbol": h.get("replay_symbol"),
        "all_bars_count": h.get("all_bars_count"),
        "solusdt_bar_count": h.get("solusdt_bar_count"),
        "all_bars_span_days": h.get("all_bars_span_days"),
        "solusdt_span_days": h.get("solusdt_span_days"),
        "replay_min_rows": h.get("replay_min_rows"),
        "replay_rows_ok": h.get("replay_rows_ok"),
        "max_evaluation_window_calendar_months": h.get("max_evaluation_window_calendar_months"),
        "twelve_month_window_ok": h.get("twelve_month_window_ok"),
        "summary_line": h.get("summary_line"),
        "error": h.get("error"),
    }


def evaluation_window_snapshot_for_ask_v1(ui_context: dict[str, Any]) -> dict[str, Any]:
    """Resolve UI evaluation window mode to integer calendar months (same rules as Run prep)."""
    from renaissance_v4.game_theory.evaluation_window_runtime import resolve_ui_evaluation_window

    mode = str((ui_context or {}).get("evaluation_window_mode") or "12").strip().lower()
    custom = (ui_context or {}).get("evaluation_window_custom_months")
    try:
        r = resolve_ui_evaluation_window(mode, custom)
        return {"schema": "ask_data_evaluation_window_resolved_v1", **r}
    except ValueError as e:
        return {
            "schema": "ask_data_evaluation_window_resolved_v1",
            "evaluation_window_mode": mode,
            "resolve_error": str(e),
        }


def wiring_module_board_compact_for_ask_v1() -> dict[str, Any]:
    """DEF-001 module board rows (compact) — how major subsystems are wired, not run outcomes."""
    try:
        from renaissance_v4.game_theory.module_board import compute_pattern_game_module_board

        board = compute_pattern_game_module_board()
        rows = board.get("modules") if isinstance(board, dict) else []
        compact: list[dict[str, Any]] = []
        for m in rows or []:
            if not isinstance(m, dict):
                continue
            compact.append(
                {
                    "id": m.get("id"),
                    "label": m.get("label"),
                    "title": m.get("title"),
                    "ok": bool(m.get("ok")),
                    "detail": str(m.get("detail") or "")[:300],
                }
            )
        return {
            "schema": "ask_data_wiring_module_board_v1",
            "def001_note": (board.get("def001_note") if isinstance(board, dict) else "") or "",
            "modules": compact,
        }
    except Exception as e:
        return {
            "schema": "ask_data_wiring_module_board_v1",
            "error": f"{type(e).__name__}: {e}"[:500],
            "modules": [],
        }


def build_ask_data_bundle_v1(
    *,
    barney_facts: dict[str, Any] | None,
    scorecard_snapshot: dict[str, Any] | None,
    ui_context: dict[str, Any],
    operator_strategy_state: dict[str, Any] | None,
    job_resolution: str,
) -> dict[str, Any]:
    from renaissance_v4.game_theory.ask_data_system_dictionary_v1 import system_dictionary_context_v1

    return {
        "schema": "ask_data_bundle_v1",
        "job_resolution": job_resolution,
        "static_knowledge": pml_static_knowledge_v1(),
        "system_dictionary": system_dictionary_context_v1(),
        "barney_facts": barney_facts,
        "scorecard_snapshot": scorecard_snapshot,
        "ui_context": ui_context,
        "operator_strategy_upload_state": operator_strategy_state,
        "data_health_snapshot": snapshot_data_health_for_ask_v1(),
        "evaluation_window_resolved": evaluation_window_snapshot_for_ask_v1(ui_context),
        "wiring_module_board": wiring_module_board_compact_for_ask_v1(),
        "operator_surface_catalog": build_operator_surface_catalog_for_ask_v1(),
    }


def ask_data_format_with_llm(
    bundle: dict[str, Any],
    question: str,
    *,
    route: str,
    timeout: float | None = None,
) -> tuple[str, str | None]:
    from renaissance_v4.game_theory.ask_data_router_v1 import ask_data_ollama_target_for_route_v1

    ollama_generate = _runtime_imports()
    base, model, default_timeout = ask_data_ollama_target_for_route_v1(route)  # type: ignore[arg-type]
    eff_timeout = default_timeout if timeout is None else timeout
    payload = json.dumps(bundle, indent=2, ensure_ascii=False)
    prompt = (
        "You are **Ask DATA** — a Pattern Machine Learning (PML) **self-explainer** for operators.\n\n"
        f"ROUTING_TIER: **{route}** — you were selected for this tier to balance speed vs depth. "
        "Same honesty rules apply; you still do **not** execute mutations or call live tools.\n\n"
        "RULES (hard):\n"
        "- Answer ONLY using: (1) the JSON bundle sections `static_knowledge`, `system_dictionary`, `barney_facts`, "
        "`scorecard_snapshot`, `ui_context`, `operator_strategy_upload_state`, `job_resolution`, "
        "`data_health_snapshot` (live SQLite / bar counts / DB path / on-disk size when readable), "
        "`evaluation_window_resolved` (UI mode → **calendar months** for replay slice), "
        "`wiring_module_board` (subsystem wiring truth / DEF-001 — not Referee scores), "
        "`operator_surface_catalog` (data-generated list of primary controls, limits, DOM ids, and which fields echo in `ui_context`), "
        "and `operator_feedback_signals` (prior operator ratings for **similar** questions — aggregate telemetry, "
        "not run truth). "
        "Do NOT use outside knowledge, the internet, or guesses.\n"
        "- If the bundle does not contain enough information, say clearly: "
        "**not available in current run data** or **not available in current app state** or "
        "**not implemented in this build** — pick the best fit.\n"
        "- Do NOT invent controls, columns, memory behavior, strategy logic, or file paths.\n"
        "- Plain English first; short by default; add technical detail only if the question asks for it.\n"
        "- **Bundle philosophy:** The entire JSON is the contract. Walkthroughs in `static_knowledge` (submission paths, paste hints) are **examples** "
        "for matching questions — not a stricter truth than `data_health_snapshot`, `wiring_module_board`, run/scorecard facts, or `system_dictionary`. "
        "Prefer the most **specific factual** sections for architecture, data volume, wiring, and run truth; use leading questions only when a checklist truly helps.\n"
        "- **Overloaded “window” / 5m / trade phrasing:** If the question could mean **calendar evaluation months**, **5-minute bar resolution**, "
        "**decision-window (DW) replay counts**, and/or **exam pack bar counts**, do **not** answer with only one. "
        "Follow `static_knowledge.operator_time_window_disambiguation_v1`: give **short labeled bullets** for each meaning the bundle supports; "
        "state explicitly when **multiple correct readings** apply. Use `evaluation_window_resolved`, `data_health_snapshot`, "
        "and `scorecard_snapshot.replay_decision_windows_sum` when present. Then end with **one** clarifying question "
        "(see `static_knowledge.ask_data_clarifying_question_v1`) so the operator’s next message can lock which reading they care about.\n"
        "- For **uploaded strategy / manifest / paste-formatting**: prefer a **conversational** reply. If file contents are **not** in the bundle, "
        "end with **one** clear ask (e.g. paste manifest JSON or the validation error here). Never claim you can perform the Controls upload or start a run; "
        "separate **review in chat** from **binding submit in the operator UI**. Follow `static_knowledge.ask_data_upload_paste_conversation_v1` and "
        "`system_dictionary.topics.operator_framework_scenarios_templates`.\n"
        "- For **submitting** a **pattern/recipe run**, an **uploaded strategy**, or **Custom / framework-heavy** scenarios **when that is what they asked**: "
        "draw on `static_knowledge.ask_data_submit_three_paths_walkthrough_v1` and `system_dictionary.topics.submission_paths_walk_template_strategy_framework` "
        "as **guidance** (see `static_knowledge.knowledge_bundle_robustness_v1`). "
        "Use **leading questions** only where useful; cover only the **A/B/C** paths that apply; **one** checklist question per reply when walking submission, not for every topic.\n"
        "- If the question is general trivia or unrelated to this application, refuse in one short paragraph "
        "(same idea as static_knowledge.refusal_policy).\n"
        "- At the end, add a single line starting with **Sources used:** listing only from: "
        "`run_facts` | `scorecard` | `ui` | `static` | `dictionary` | `upload` | `data_health` | "
        "`evaluation_window` | `wiring` | `operator_surface` | `refused` | `operator_signals` — comma-separated, "
        "reflecting what you actually relied on (`dictionary` = `system_dictionary` topics; "
        "`operator_signals` = `operator_feedback_signals` rollup; `data_health` = `data_health_snapshot`; "
        "`evaluation_window` = `evaluation_window_resolved`; `wiring` = `wiring_module_board`; "
        "`operator_surface` = `operator_surface_catalog`).\n\n"
        f"OPERATOR QUESTION:\n{question.strip()}\n\n"
        "--- BUNDLE JSON ---\n"
        + payload
    )
    res = ollama_generate(prompt, base_url=base, model=model, timeout=eff_timeout)
    if res.error:
        return "", res.error
    return (res.text or "").strip(), None


def ask_data_answer(
    question: str,
    bundle: dict[str, Any],
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    from renaissance_v4.game_theory.ask_data_operator_feedback_v1 import (
        append_ask_data_interaction_telemetry_v1,
        ask_data_operator_feedback_enabled_v1,
        bundle_with_operator_feedback_signals_v1,
        new_interaction_id_v1,
        question_fingerprint_v1,
        rollup_operator_feedback_for_fingerprint_v1,
    )
    from renaissance_v4.game_theory.ask_data_router_v1 import classify_ask_data_route_v1

    q = (question or "").strip()
    if not q:
        return {
            "ok": False,
            "text": "",
            "answer_source": "refused",
            "error": "question is empty",
        }

    fp = question_fingerprint_v1(q)
    signals = rollup_operator_feedback_for_fingerprint_v1(fp)
    eff_bundle = bundle_with_operator_feedback_signals_v1(bundle, signals)
    job_res = str((bundle or {}).get("job_resolution") or "")

    route = classify_ask_data_route_v1(q)

    def _finalize(
        *,
        ok: bool,
        text: str,
        answer_source: str,
        error: Any,
        router_label: str,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": ok,
            "text": text,
            "answer_source": answer_source,
            "error": error,
            "ask_data_route": route,
            "ask_data_router": router_label,
        }
        if ask_data_operator_feedback_enabled_v1():
            iid = new_interaction_id_v1()
            append_ask_data_interaction_telemetry_v1(
                interaction_id=iid,
                question_fingerprint=fp,
                job_id=job_id,
                ask_data_route=route,
                answer_source=answer_source,
                job_resolution=job_res,
                question_len=len(q),
            )
            out["interaction_id"] = iid
            out["question_fingerprint"] = fp
        return out

    if looks_off_topic(q):
        return _finalize(
            ok=True,
            text=refusal_text_general(),
            answer_source="refused",
            error=None,
            router_label="off_topic",
        )

    if not ask_data_use_llm():
        txt, src = _fallback_answer_from_bundle(q, eff_bundle)
        return _finalize(ok=True, text=txt, answer_source=src, error=None, router_label="off_llm")

    txt, err = ask_data_format_with_llm(eff_bundle, q, route=route)
    if err or not txt:
        fb, src = _fallback_answer_from_bundle(q, eff_bundle)
        return _finalize(
            ok=True,
            text=fb + ("\n\n(Formatter unavailable: " + str(err) + ")" if err else ""),
            answer_source=src + "+fallback",
            error=err,
            router_label="fallback_after_llm_error",
        )
    return _finalize(ok=True, text=txt, answer_source="llm", error=None, router_label="llm")
