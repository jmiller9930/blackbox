# GT_DIRECTIVE_015 — Run exam: Student **brain profile** contract + baseline audit

**Date:** 2026-04-24 (amended 2026-04-24 — brain profile v2)  
**Status:** **ACTIVE — OPEN** — brain profile + nested LLM metadata **shipped** in `exam_run_contract_v1` / scorecard / UI; **refine-then-seal** LLM stages and **physical** cold Referee skip remain future slices. E/P comparison surface still outstanding unless deferred in writing.  
**From:** Architect (via operator product lock)  
**To:** Engineer  
**CC:** Operator, Product, Referee, UI  
**Scope:** `renaissance_v4/game_theory` — parallel batch (`web_app.py` `POST /api/run-parallel/start`, blocking `/api/run-parallel`), `batch_scorecard.py`, **Student seam** (memory → context packet → optional governed LLM → sealed `student_output_v1`), **persisted exam truth** for Referee attribution.

**Cross-ref:** **GT_DIRECTIVE_018** owns **learning-loop governance** (retrieval caps, attachment order, future memory-quality / H1–H4 / P metrics) — not duplicated in 015.

---

## Product frame (non-negotiable semantics)

| Layer | Role |
|--------|------|
| **Memory** | What the Student **learned before** — retrieved into the decision packet through legal paths. |
| **Context** | What the Student **sees now** — bars, indicators, annex, **retrieved memory slices**. |
| **LLM** | A **governed reasoning component** inside the Student brain: refine hypotheses, critique interpretation, surface contradictions, improve deliberation — **not** “another Student” competing with the Student. **v1** still uses a bounded **single-shot** completion to `student_output_v1` (`llm_role` = `single_shot_student_output_v1`); multi-stage refine-then-seal is explicitly **future work**. |
| **Referee** | **Proof layer** — grades outcomes; LLM never self-grades. |
| **Learning writeback** | After reveal, outcomes feed memory-capable stores. |

**Primary question:** Does the Student improve under the Referee with **memory + context +** (when enabled) **LLM-assisted reasoning**?  
**Secondary question:** Which **model tag** under `student_llm_v1` works better — **metadata**, not a separate top-level “lane.”

---

## Active engineering brief

### 15.0 Student brain profile (`student_brain_profile_v1`)

Canonical values (persisted on scorecard + echoed in `student_reasoning_mode` for one-key compatibility):

| Profile | Meaning |
|---------|---------|
| `baseline_no_memory_no_llm` | System cold path; no cross-run memory emphasis; **no** Student LLM. (Legacy input: `cold_baseline`.) |
| `memory_context_student` | Memory + context plumbing; **stub** Student emitter (no Ollama). (Legacy: `repeat_anna_memory_context`, `memory_context_only`.) |
| `memory_context_llm_student` | Memory + context + **LLM component**; Ollama when configured. (Legacy lane strings `llm_assisted_anna_qwen`, `llm_qwen2_5_7b`, `llm_assisted_anna_deepseek_r1_14b`, `llm_deepseek_r1_14b` **normalize** to this profile; **model** comes from `student_llm_v1` or legacy inference.) |

### 15.0.1 Nested LLM metadata (`student_llm_v1`)

When profile is `memory_context_llm_student`, request (and scorecard echo) **must** carry:

| Field | v1 |
|--------|-----|
| `llm_provider` | `ollama` only in v1. |
| `llm_model` | Ollama tag, e.g. `qwen2.5:7b`, `deepseek-r1:14b`. |
| `llm_role` | Default `single_shot_student_output_v1` (future: `hypothesis_reasoner`, `critic`, etc.). |

**No silent global swap:** run-scoped `llm_model` + `OLLAMA_BASE_URL` for this request; never assume env default implies Student traffic.

### 15.0.2 Persisted scorecard / operator truth

Merge at batch finish (plus `student_llm_execution_v1` from seam when present):

- `student_brain_profile_v1`, `student_reasoning_mode` (mirror of profile for legacy readers)  
- `student_llm_v1` (when LLM profile)  
- `llm_used`, `llm_model`, `ollama_base_url`, `prompt_version`, `memory_context_used`, `retrieved_context_ids`  
- `skip_cold_baseline`, `skip_reason`, `cold_baseline_anchor_job_id_v1`, `run_config_fingerprint_sha256_40_echo_v1`, `system_baseline_captured_v1`  

**Physical** skip of Referee cold replay is **not** v1 — parallel replay always runs. Skip-cold fields are **metadata** (prior anchor existed for comparison validity).

**Code:** `exam_run_contract_v1.py`, `batch_scorecard.record_parallel_batch_finished(..., exam_run_line_meta_v1=...)`, `web_app._exam_run_line_meta_for_parallel_job_v1`, `student_proctor_operator_runtime_v1.py`.  
**Fixture:** `tests/fixtures/gt_directive_015_scorecard_fixture_lines.json`  
**Proof:** `docs/proof/exam_v1/GT_DIRECTIVE_015_operator_proof_run_lanes_v1.md` (filename historical; content describes **profiles**).

---

## Exam identity, cold baseline, scorecard honesty

### 15.1 Exam identity (anchor key)

Unchanged: framework + policy (recipe, window, manifest fingerprint) + pattern identity. Fingerprint recipe matches `memory_context_impact_audit_v1`.

### 15.2–15.3 Cold system replay (engine intent)

Product rules for **when** cold must / must not run remain as before; **implementation** of physical skip is **future**. v1 records audit metadata only.

### 15.4 Scorecard / API honesty

- Do not imply Anna rollup where the line is system baseline.  
- Reserve richer Anna vs system **road** presentation for **GT_DIRECTIVE_016** when shipped.

### 15.5 E/P comparison (primary vs secondary)

- Referee remains sole authority for E/P.  
- **Primary** comparison: same exam identity, different **brain profile** (e.g. `memory_context_student` vs `memory_context_llm_student`) with fixed `prompt_version` where possible.  
- **Secondary**: different `llm_model` under the **same** LLM profile — attribute via `student_llm_v1` + `llm_model` on the line.

### 15.6 Global defaults vs run override

Non-Student callers may use repo defaults; **Student** Ollama calls use run contract + `student_llm_v1`.

---

## Proof required

1. **Tests** — Normalize legacy inputs → profiles; parse validates LLM profile + Ollama URL; scorecard merge includes `student_brain_profile_v1` + `student_llm_v1`.  
2. **HTTP** — `POST /api/run-parallel` and `/api/run-parallel/start` with `exam_run_contract_v1`; scorecard readback shows profile + `llm_model`.  
3. **Doc** — `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §1.1 + §18.4 aligned.  
4. **Closeout** — `PATTERN_GAME_WEB_UI_VERSION` bump when embedded UI changes; push + gsync per operator stack.

---

## Deficiencies log update

Track: **“GT_DIRECTIVE_015 — Student brain profile + exam contract”** until **Accepted** or deferred in writing.

---

## Engineer update

**2026-04-24 — Brain profile v2 (rework of prior lane-centric wording):**

- `exam_run_contract_v1.py` — three **canonical brain profiles**; legacy `student_reasoning_mode` **inputs** still accepted; `student_brain_profile_v1` + `student_llm_v1` on parse output; `build_exam_run_line_meta_v1` persists profile + LLM block; `resolved_llm_for_exam_contract_v1` for seam.  
- `student_proctor_operator_runtime_v1.py` — gates Ollama on `memory_context_llm_student`; seam audit adds `student_brain_profile_echo_v1`, `student_llm_v1_echo`.  
- `web_app.py` — Controls: profile picker + Ollama model sub-picker; `buildExamRunContractV1ForStart()` sends full contract; **PATTERN_GAME_WEB_UI_VERSION** bumped.  
- Tests + fixture + operator proof text updated.  
- **Not done here:** multi-artifact refine-then-seal pipeline; additional `llm_role` behaviors beyond default.

---

## Architect review

**Status:** **OPEN** — accept **brain profile** semantics as the direction of travel; close when E/P comparison surface + any mandated cold-skip **physical** behavior are shipped or explicitly deferred by amendment.

**Do not start GT_DIRECTIVE_016** until this directive is closed or amended regarding 016 start gate.
