# Student panel dictionary (operator) — v1.2

**Canonical file:** `renaissance_v4/game_theory/docs/STUDENT_PANEL_DICTIONARY_v1.md`  
**Browser:** Pattern Machine learning UI → **Student → learning → outcome** fold → link **“Student panel dictionary”**, or open **`/docs/student-panel-dictionary`** on the same host as Flask (e.g. `http://127.0.0.1:8765/docs/student-panel-dictionary`).  
**Deep architecture:** `docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` (exam frames, grading, directives).

---

## Levels (L1 / L2 / L3)

| Term | Meaning |
|------|--------|
| **Level 1 (L1)** | **Exam list** — one row per parallel batch / scorecard line (`job_id`). Harness + Referee rollups at run grain; not per-trade detail. |
| **Level 2 (L2)** | **One selected exam** — **run summary** band plus **trade carousel**: one card per closed trade opportunity (`trade_id` / `graded_unit_id`). |
| **Level 3 (L3)** | **One trade deep dive** — `student_decision_record_v1` (or successor): field-by-field with `data_gap` / `data_gaps[]` when something is not wired. |

---

## Scorecard & list columns (L1 table)

| Term | Meaning |
|------|--------|
| **Sys BL %** | **System baseline trade win %** — batch trade win % of the **oldest** completed run in the same **fingerprint** chain (anchor for that recipe/window). |
| **Run TW %** | **This exam’s** Referee batch rollup trade win % (`batch_trade_win_pct` / `avg_trade_win_pct`). |
| **>BL** | **Strict beat vs Sys BL** — YES / NO / = / — (not on anchor row; honest when inputs missing). |
| **#Tr** | `batch_trades_count` — trade count for the batch line. |
| **E/tr** | `expectancy_per_trade` — batch economic rollup (not the same as exam-pack timeline **E** unless denorm says so). |
| **HB** (legacy) | **Harness behavior changed** — Groundhog / recall / bias signals on the **replay harness** path (not Student store writes). Prefer treating as **system** lane, not “Anna”. |
| **SH** (legacy) | **Student handoff** — learning rows appended or retrieval matched; UI may show **ExLog / Learn** style labels elsewhere. |
| **Evidence** | Nested object: **Referee** (trades, TW%, expectancy), **Harness** (recall, bias flags), **Student handoff** (rows, retrieval, fingerprint tail). |
| **Groundhog state** | COLD / ACTIVE / STRONG / WEAK / N/A / RUNNING — retrieval + behavior + outcome-improved heuristic vs prior same-fingerprint run (see panel legend). |
| **Fingerprint** | `run_config_fingerprint_sha256_40` in `memory_context_impact_audit_v1`, or a **40-char hash** from `operator_batch_audit` when MCI fingerprint is absent — **chains** runs for Sys BL and road logic. |

---

## Student brain profile (GT_DIRECTIVE_015)

| Term | Meaning |
|------|--------|
| **student_brain_profile_v1** | Canonical **Student brain** mode for the run (persisted on scorecard). |
| **baseline_no_memory_no_llm** | Cold system path: no cross-run Student memory emphasis; **no** Student LLM. |
| **memory_context_student** | Memory + context plumbing; **stub** Student emitter (no Ollama). |
| **memory_context_llm_student** | Memory + context + **LLM** (Ollama when configured). **`llm_model`** (e.g. Qwen, DeepSeek) is **nested metadata**, not a separate top-level “lane”. |
| **exam_run_contract_v1** | Request/UI block declaring profile, optional `student_llm_v1`, `prompt_version`, skip-cold **metadata**, etc. |
| **skip_cold_baseline** | **Metadata only** — whether a prior anchor existed for comparison; **does not** skip physical Referee replay in v1. |

---

## Decision A — directional thesis (exam)

What the Student must **solve for** at commitment time is a **directional thesis**, not indicator trivia. **Indicators** supply signals; **memory** supplies prior cases; **context** supplies regime; **LLM** (when enabled) helps judge **alignment vs conflict** among signals — still bounded by the legal packet and **no** self-grading.

| Term | Meaning |
|------|--------|
| **Directional thesis** | **Direction** (long / short / sideways or neutral edge) + **confidence** + **which indicators support vs conflict** + **context fit** + **action** (ENTER with side vs NO_TRADE) + **invalidation**. Full product definition: **`STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §1.0**. |
| **Learning loop (concept)** | Indicators → direction estimate → confidence → action → outcome → memory update; reliability is proven over runs via **Referee** **E**/**P**, not narrative length. |

**`student_output_v1` (parallel seam) — optional thesis keys** (validated when present; see **`STUDENT_PATH` §1.0.1**):

| Field | Meaning |
|-------|--------|
| **`confidence_band`** | `low` \| `medium` \| `high` — complements numeric **`confidence_01`**. |
| **`supporting_indicators`** | `string[]` — names of signals/cues that agree with **`direction`**. |
| **`conflicting_indicators`** | `string[]` — names that disagree or weaken the thesis. |
| **`context_fit`** | Short regime/structure label (e.g. trend, chop, reversal). |
| **`invalidation_text`** | What would prove the thesis wrong (pre-reveal legal only). |
| **`student_action_v1`** | `enter_long` \| `enter_short` \| `no_trade` — must agree with **`act`** and **`direction`**. |

---

## L1 road API (GT_DIRECTIVE_016)

**Route:** `GET /api/student-panel/l1-road`  
**Schema:** `student_panel_l1_road_v1`

| Term | Meaning |
|------|--------|
| **Group** | Aggregates for one key: **same fingerprint** + **brain profile** + **`llm_model`** (null for non-LLM profiles). Built in a **single** scorecard file read — no per-row Student JSONL scan. |
| **band A** | **Improved** vs the fingerprint’s **baseline anchor**: group mean **E** (`expectancy_per_trade`) **>** anchor **E**, and when **P** exists on both sides, group mean **P** ≥ anchor **P** (within tolerance). |
| **band B** | **Not improved or degraded** — does not meet the A rule (includes ties on E when P unavailable). |
| **baseline_ruler** | The group whose profile is **baseline_no_memory_no_llm** — the **ruler** row for that fingerprint; not A/B-scored against itself. |
| **band data_gap** | Honest gap: e.g. **no baseline** in that fingerprint, or missing expectancy on anchor/group — see `data_gaps[]` on the group. |
| **pass_rate_percent** | Mean of **`referee_win_pct`** on lines in the group (session Referee win rate as recorded — not invented pass bits). |
| **avg_e_expectancy_per_trade** | Mean **`expectancy_per_trade`** on lines in the group (batch **economic** rollup on scorecard). |
| **avg_p_process_score** | Mean **`student_l1_process_score_v1`** when that optional field is present on lines; else **null** (reserved for future batch denorm). |
| **process_leg** | `compared` when P was used for A/B; **`data_gap`** when P was missing and A/B used **E-only**. |
| **legend** (JSON) | API-delivered strings describing profiles, bands, and metrics — **source of truth** for UI copy (avoid duplicating conflicting definitions only in JS). |
| **`road_by_job_id_v1`** | Map **`job_id` →** `{ band, process_leg, anchor_job_id, row_anchor_role_v1, group_data_gaps, student_brain_profile_v1, llm_model, fingerprint_sha256_40 }` for L1 row join. |
| **`l1_road_v1` (on `/runs`)** | Overlay: **`legend`**, **`road_by_job_id_v1`**, **`data_gaps`** — same aggregation as full road endpoint; embedded in run list response. |
| **row_anchor_role_v1** | **`ruler`** = baseline profile group; **`baseline_anchor`** = this `job_id` is the fingerprint’s baseline anchor row; **`compare`** = other profiles / models compared to that anchor. |

---

## L2 carousel & Referee coupling

| Term | Meaning |
|------|--------|
| **Trade set** | One **evaluated opportunity**: decision-time context + Student commitment (when in store) + path to close + Referee outcome. Default: one **`trade_id`** = one set. |
| **student_referee_direction_align** | **True / False / data_gap** — Student store **direction** vs Referee **outcome direction** (GT_DIRECTIVE_009a); not a baseline delta. |
| **referee_direction** | Direction from Referee / replay outcome for that trade. |
| **dir_align** (run summary) | Rollup: `student_referee_direction_align_*` — how often Student direction matched Referee over evaluable trades. |

---

## Memory, context, LLM (product)

| Term | Meaning |
|------|--------|
| **Memory** | Durable **store** of past graded / learning rows; **retrieved** into the next run through legal paths. |
| **Context** | What the Student **may** condition on at decision time (bars, indicators, **retrieved memory slices**). |
| **LLM** | **Governed component** inside the Student brain — refines/expresses reasoning from the context bundle; does **not** self-grade and does **not** replace memory. |

---

## Learning loop (short)

| Term | Meaning |
|------|--------|
| **Good learning loop** | Past **graded** outcomes feed **memory** → next run **context** → Student **decision** → Referee **E + P**; improvement is **measurable** behavior, not “the LLM got smarter” alone. See **§1.2** in `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`. |
| **GT_DIRECTIVE_018** | **Learning-loop governance** — retrieval caps, newest-first slices, seam audit fields (not the same as 015 contract). |

---

## APIs (quick index)

| Route | Role |
|--------|------|
| `GET /api/student-panel/runs` | L1 rows + `l1_columns_v1` + **`l1_road_v1`** overlay (`legend`, **`road_by_job_id_v1`** per `job_id`) so the embedded table can show Profile / LLM / Road / Anchor / gaps without a second fetch. |
| `GET /api/student-panel/l1-road` | Full L1 **road** payload (`groups`, **`road_by_job_id_v1`**, `legend`, `data_gaps`). |
| `GET /api/student-panel/run/<job_id>/decisions` | L2 payload (run summary + carousel). |
| `GET /api/student-panel/decision?job_id=&trade_id=` | L3 `student_decision_record_v1`. |

---

## data_gap

| Term | Meaning |
|------|--------|
| **data_gap** | Explicit **unknown or not wired** — we do not invent values. L3 lists stable **`data_gaps[]`** reason codes. |

---

*Revision: v1 — aligned with GT_DIRECTIVE_015 / 016 / 009a and STUDENT_PATH v1.20+.*
