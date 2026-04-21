# Student panel — high-level development overview

Audience: engineers and anyone planning work on the Pattern Machine **Student** operator surface (web UI + APIs + supporting exports).

This document is **strategic**. For **D14** contract, proof register, and `student_decision_record_v1` columns, see **`D14_student_panel_architecture_spec_v1.md`** and **`D14_student_panel_gap_closure_proof.md`**. For D13 file artifacts, see **`D13_student_panel_curriculum_v1.md`**. For field-level honesty and gaps, see **`student_data_capability_audit_v1.md`**.

---

## 1. Product intent (curriculum)

**Training mode is forced trade.** The smallest unit of “did learning happen on this interaction?” is **one trade opportunity**, not one parallel scenario row, unless the scenario happens to contain exactly one closed trade.

**Flashcard metaphor:** Each closed trade (`trade_id` / `graded_unit_id`) is one **flashcard** — one chance to show what the Student did, what she saw, what influenced her, and what the Referee says happened. A run with **939** closed trades is **939** flashcards for demonstration of learning, **not** “939 scenarios” unless each scenario closes one trade.

**Non-negotiable:** Do not use `scenario_id` as the slice identity for the carousel or deep dive when multiple trades exist under one scenario.

---

## 2. UI levels (mental model)

| Level | What the user sees | Grain |
|--------|-------------------|--------|
| **L1** | Run table | One row per batch / `job_id` (Referee + harness rollups) |
| **L2** | Single selected-run panel: **run summary band** + **trade carousel** | Run aggregates + **per trade** cards |
| **L3** | Deep dive | **One** `trade_id` |

No mixing grain: run stats stay in the summary band; carousel cards are trade-only; L3 explains **one** trade.

---

## 3. Architecture (where logic lives)

| Area | Primary modules |
|------|------------------|
| Parallel worker rows + `replay_outcomes_json` | `renaissance_v4/game_theory/parallel_runner.py` |
| Persist full batch results for trade enumeration | `batch_parallel_results_v1.json` next to session batch logs |
| Load batch artifact | `renaissance_v4/game_theory/scorecard_drill.py` — `load_batch_parallel_results_v1` |
| Scorecard / batch folder resolution | `scorecard_drill.py`, `batch_scorecard` |
| D13 payloads + `student_decision_record_v1` | `renaissance_v4/game_theory/student_panel_d13.py` |
| Run table rows (shared rollups / Groundhog tier inputs) | `renaissance_v4/game_theory/student_panel_d11.py` — `build_d11_run_rows_v1` |
| Student store (per graded unit) | `renaissance_v4/game_theory/student_proctor/student_learning_store_v1.py` |
| HTTP API + embedded UI | `renaissance_v4/game_theory/web_app.py` |

---

## 4. Data contract philosophy

- **Student** fields must come from Student / Proctor truth (e.g. learning store `student_output` when present).
- **Referee** fields must come from Referee truth (e.g. `OutcomeRecord` / `replay_outcomes_json`).
- **Baseline** and **rich context** are **not** invented: if the engine does not export them per trade, the API and UI surface **`data_gap`** (or equivalent explicit label).

**Do not** “help” with heuristics that relabel scenario-level numbers as trade-level truth, or synthesize baseline/context/Groundhog attribution when the directive says export is missing.

---

## 5. Accepted gaps (planned follow-on, not workarounds)

These require **focused directives** and **new exports**, not UI patches:

1. **Per-trade baseline** (direction / confidence / decision vs control path).
2. **Groundhog per-trade attribution** when one scenario contains **multiple** trades.
3. **Decision-time context export** (OHLC, indicators, regime, structure, etc.) joined causally to the decision.

Until then, missing fields remain **`data_gap`**.

---

## 6. Verification checklist (new batch)

After changing Student panel or export paths, validate with a **new** parallel batch (session logs on so `batch_parallel_results_v1.json` exists):

1. Run summary band appears **above** the carousel.
2. Carousel cards are **trade_id** cards (one card per closed trade, not one per scenario unless one trade).
3. Clicking a card opens L3 for the **same** `trade_id`.
4. Missing exports show as **`data_gap`**, not guessed values.
5. No scenario-level values are presented as **trade-level** truth.

---

## 7. Versioning

Bump **`PATTERN_GAME_WEB_UI_VERSION`** in `web_app.py` when changing operator-visible HTML/JS/CSS for the Student panel so caches and deployments stay consistent.

---

## 8. Changelog

| Version | Note |
|---------|------|
| v1 | Initial high-level overview aligned with D13 trade-grain implementation and accepted gaps. |
