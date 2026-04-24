# GT_DIRECTIVE_015 — Run exam: baseline vs repeat-sit engine contract

**Date:** 2026-04-24  
**Status:** **ACTIVE** — engineering implementation in progress (v1 persistence + API validation landed; full two-phase cold skip of Referee replay is **not** claimed until explicitly shipped).  
**From:** Architect (via operator product lock)  
**To:** Engineer  
**CC:** Operator, Product, Referee, UI  
**Scope:** `renaissance_v4/game_theory` — parallel batch entrypoint (`web_app.py` `POST /api/run-parallel/start`, blocking `/api/run-parallel`), `parallel_runner.py`, `batch_scorecard.py`, operator batch audit / fingerprinting, **Student seam / reasoning emitters** (stub vs Ollama-backed paths), and **persisted exam-run metadata** so grading can attribute outcomes to mode.

### Active engineering brief (canonical mode names)

At minimum, **`student_reasoning_mode`** must be one of:

- `cold_baseline`
- `repeat_anna_memory_context` (legacy API alias: `memory_context_only`)
- `llm_assisted_anna_qwen` (legacy: `llm_qwen2_5_7b`)
- `llm_assisted_anna_deepseek_r1_14b` (legacy: `llm_deepseek_r1_14b`)

**Persisted** (scorecard line, merged at batch finish): `student_reasoning_mode`, `llm_used`, `llm_model`, `ollama_base_url`, `prompt_version`, `memory_context_used`, `retrieved_context_ids`, `skip_cold_baseline`, `skip_reason`, plus `cold_baseline_anchor_job_id_v1`, `run_config_fingerprint_sha256_40_echo_v1`, `system_baseline_captured_v1` where applicable.

**Operator proof artifact:** `docs/proof/exam_v1/GT_DIRECTIVE_015_operator_proof_run_lanes_v1.md`  
**Fixture:** `tests/fixtures/gt_directive_015_scorecard_fixture_lines.json`  
**Code:** `exam_run_contract_v1.py`, `batch_scorecard.record_parallel_batch_finished(..., exam_run_line_meta_v1=...)`, `web_app._exam_run_line_meta_for_parallel_job_v1`.

## Canonical workflow record

This file is the canonical record for this directive.

Workflow:

1. Architect issues directive here.
2. Engineer reads and performs work.
3. Engineer appends response below.
4. Operator notifies Architect to review this folder.
5. Architect appends acceptance or rework below.

## Fault

**Today:** One **Run exam** always runs **one** full parallel replay with the UI’s memory mode, then the Student seam post-pass. There is **no** first-class separation between **(A) cold system baseline** and **(B) Anna repeat sit**; operators pay full replay cost every time and cannot rely on the product rule: *baseline anchor exists → do not rerun cold system*.

**Also today:** **DeepSeek** (or any Ollama model) is **not** wired as a **declared Student reasoning mode** on the exam path. There is **no** persisted **`student_reasoning_mode`** / **`llm_model`** on the exam unit or scorecard line, so **E/P (or pack PASS)** cannot be **attributed** to “Qwen vs DeepSeek vs stub” — and changing `OLLAMA_MODEL` would risk a **silent global** swap, which is **forbidden** by this directive.

## Directive

Implement and document the **run contract** below. Exact mechanics (single job with two internal phases vs two scorecard lines) are for engineering, but **semantics** are fixed.

### 15.1 Exam identity (anchor key)

Treat **one exam identity** as unchanged when **all** of the following are unchanged:

- **Baseline framework** (policy framework / fusion contract identity as recorded on the batch line).
- **Baseline policy** (operator recipe + evaluation window effective months + primary manifest fingerprint as already used for `run_config_fingerprint` / operator batch audit).
- **Pattern** (graded template / scenario pack identity — **not** cosmetic labels alone).

When **any** of the three changes, the prior **system baseline anchor** is **invalid** for comparisons until a **new** cold system sit completes.

### 15.2 When the cold **system** replay must run

The engine **must** run the **cold system** path (context-signature memory **off** for that path unless architect explicitly documents an exception) when:

1. **No** completed scorecard row exists for this exam identity with `status: done` and a valid **system baseline captured** flag (engineer to define the exact field name on `pattern_game_batch_scorecard_v1`); **or**
2. The operator or system invalidates the anchor (policy/framework/pattern change per §15.1; optional: architect-approved **data refresh** invalidation).

### 15.3 When the cold system replay **must not** run

If a **valid system baseline anchor** already exists for this exam identity, **Run exam** for a **repeat Anna sit** **must not** rerun the full cold parallel batch **unless** the operator explicitly chooses **“Re-baseline”** (separate control or confirm dialog — product decision in implementation).

Repeat sits run the **Anna / memory-context** configuration only (per operator settings), then Student seam and scorecard updates as today — **and** the operator-selected **`student_reasoning_mode`** (§15.5) must be applied **for that run only**.

### 15.4 Scorecard / API honesty

- Persist enough on the scorecard line to answer: **was cold system run for this line?** (boolean + optional link to cold `job_id` if split IDs).
- **Never** imply `Run TW %` is “Anna” when it is system rollup; reserve Anna metrics for **GT_DIRECTIVE_016**.

### 15.5 Student reasoning mode (LLM) contract — **non-negotiable**

**Principle:** **DeepSeek must not silently replace Qwen** (or any default) **globally**. Each exam run **declares** its mode; defaults in env/docs are **only** fallbacks when the UI/API does not send a mode.

#### 15.5.1 Declared modes (canonical string IDs)

Implement at least these **distinct** modes (exact spelling for persistence and APIs):

| `student_reasoning_mode` | When the Student uses **no** LLM | When it uses **Qwen** | When it uses **DeepSeek** |
|---------------------------|------------------------------------|-------------------------|-----------------------------|
| `cold_baseline` | Always (system path). No Student LLM. | N/A | N/A |
| `repeat_anna_memory_context` (alias `memory_context_only`) | Student path: **stub / deterministic** emitters only (Directive 03 style). **No** Ollama call for Student output in v1. | N/A | N/A |
| `llm_assisted_anna_qwen` (alias `llm_qwen2_5_7b`) | N/A | Declared **`qwen2.5:7b`** on run-scoped Ollama base URL (**stub note** until seam calls Ollama). | N/A |
| `llm_assisted_anna_deepseek_r1_14b` (alias `llm_deepseek_r1_14b`) | N/A | N/A | Declared **`deepseek-r1:14b`** (**stub note** until seam wired). |

**Adding `llm_deepseek_r1_32b` (or others)** is allowed later as **new enum values**, never as an undeclared override.

#### 15.5.2 When each mode applies

- **`cold_baseline`:** only the **system** replay arm (§15.2); **no** Student LLM.
- **`repeat_anna_memory_context`** (alias **`memory_context_only`**): repeat Anna sit **with** memory/context plumbing **on**, **no** LLM in the Student emitter (v1 stub).
- **`llm_assisted_anna_qwen` / `llm_assisted_anna_deepseek_r1_14b`** (legacy ids still accepted): repeat sits where the operator **explicitly** selects that **Student** LLM mode; **same** exam identity + tape comparison rules as §15.1 for cross-mode scoring.

#### 15.5.3 Persistence on the exam unit / scorecard (every run)

Each completed run **must** persist (scorecard line, `operator_batch_audit`, or a dedicated `student_exam_run_meta_v1` blob — **one** canonical place, documented in the PR):

| Field | Purpose |
|--------|---------|
| `student_reasoning_mode` | One of the declared IDs above. |
| `llm_used` | Boolean: **any** Ollama call made for **Student** reasoning this run. |
| `llm_model` | Ollama model tag actually used for Student (e.g. `qwen2.5:7b`, `deepseek-r1:14b`), or `null` if none. |
| `ollama_base_url` | Resolved base URL for that run (e.g. `http://172.20.2.230:11434`). |
| `prompt_version` | Version string / hash of the **bounded** Student prompt template (so grading comparisons are apples-to-apples). |
| `memory_context_used` | Honest summary flag(s) for whether memory/context paths were active (align with **GT_DIRECTIVE_016** `Mem`/`Ctx` semantics when merged). |

**DeepSeek installed** on the lab host is **not sufficient** — **`llm_model` + `student_reasoning_mode`** must match what ran.

#### 15.5.4 Repeating the **same** exam across modes

- **Same exam identity** = §15.1 fingerprint unchanged.
- **Different** `student_reasoning_mode` = **different** scorecard row / `job_id`, same anchor `Sys BL` reference for comparison.
- **Ordering:** document whether operators must run **baseline first** once per identity; repeat sits may cycle `repeat_anna_memory_context` → `llm_assisted_anna_qwen` → `llm_assisted_anna_deepseek_r1_14b` for **value tests**.

#### 15.5.5 How scores are compared (E + P / pack grading)

- **Referee / pack grading** remains the **only** authority for **E/P** (or PASS/E); the LLM **never** self-grades.
- Comparisons are **only** valid when **`prompt_version`** and **exam identity** are documented as comparable, or comparison is explicitly labeled **“prompt drift allowed.”**
- **Hypothesis:** `llm_assisted_anna_deepseek_r1_14b` improves **E/P** vs `repeat_anna_memory_context` and vs `llm_assisted_anna_qwen` — **prove** with persisted fields + aggregate reports; **no** claim without data.

### 15.6 Global defaults vs run override

- Repo defaults (`OLLAMA_MODEL`, `OLLAMA_BASE_URL`) may remain **qwen** for **Ask DATA / Barney** and other non-Student callers.
- **Student** path **must** pass **run-scoped** model selection into the Ollama client for that request — **never** assume “install DeepSeek ⇒ all Student traffic is DeepSeek.”

## Proof required

1. **Tests** — Unit/integration proving: first sit for fingerprint runs cold path; second sit skips cold when anchor present; invalidation on fingerprint change runs cold again.
2. **Tests — LLM mode** — At least three fixtures: `memory_context_only` (no Ollama mock called), `llm_qwen2_5_7b`, `llm_deepseek_r1_14b` assert **mocked** Ollama receives the **correct** `model` in the JSON body; assert scorecard line persists §15.5.3 fields.
3. **HTTP** — `POST /api/run-parallel/start` + poll until `done`; scorecard row shows correct flags for A/B scenarios **and** `student_reasoning_mode` / `llm_model`.
4. **Doc** — Same PR updates **§18.4** in `docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` with **GT_DIRECTIVE_015** row + status; add operator legend for modes.
5. **Closeout** — Satisfy **§18.3 GT_DIRECTIVE_009** sequence when Student panel / `web_app.py` UI strings change (`PATTERN_GAME_WEB_UI_VERSION`, push, gsync, verify).

## Deficiencies log update

Append to any project deficiencies log: **“GT_DIRECTIVE_015 — baseline skip contract”** with status until **Accepted**.

---

## Engineer update

**Status:** in progress (2026-04-24)

**Work performed (v1 slice):**

- Added `renaissance_v4/game_theory/exam_run_contract_v1.py` — mode normalization/validation, fingerprint **preview** (matches `memory_context_impact_audit_v1` recipe), prior-anchor lookup, `build_exam_run_line_meta_v1` for scorecard fields including **`skip_cold_baseline` / `skip_reason`** (auditable “anchor existed” semantics; **full Referee cold-phase skip** remains future work).
- `batch_scorecard.record_parallel_batch_finished` accepts **`exam_run_line_meta_v1`** and merges onto the scorecard line.
- `web_app` — `_prepare_parallel_payload` parses **`exam_run_contract_v1`** (or flat keys); **400** on unknown mode or invalid Ollama URL for LLM modes; merges request into `operator_batch_audit`; async `/api/run-parallel/start` and blocking `/api/run-parallel` attach metadata on success and error paths. **`PATTERN_GAME_WEB_UI_VERSION` → 2.19.49**.
- Tests: `renaissance_v4/game_theory/tests/test_gt_directive_015_exam_run_contract_v1.py`.
- Fixture + operator proof: `tests/fixtures/gt_directive_015_scorecard_fixture_lines.json`, `docs/proof/exam_v1/GT_DIRECTIVE_015_operator_proof_run_lanes_v1.md`.

**Remaining gaps:** UI control to send `exam_run_contract_v1` per run; wire Student seam to Ollama with **run-scoped** `llm_model` (no env global); automated HTTP integration test against Flask app; E/P comparison report endpoint; full **two-phase** “do not rerun Referee cold parallel” engine behavior when anchor exists.

**Shipped this slice:** `git push origin main` completed; `python3 scripts/gsync.py --no-commit --force-restart` completed (pattern-game Flask + UIUX per operator stack).

**Request:** Architect acceptance when the above gaps are closed or explicitly deferred with directive amendment.

---

## Architect review

**Status:** pending architect review
