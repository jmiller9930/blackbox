# Learning overview — code-grounded path (incomplete)

**What this document is:** The **operator / architect overview** of how Anna moves from **rule-following analyst** to **governed, evidence-backed independence** — **tied to modules and contracts that exist in the repo**, not aspirational prose alone.

**What this document is not:** A claim that every layer is **finished**. **Gaps** are named; the WebUI **`intelligence_visibility`** block on **`/dashboard.html`** (from **`GET /api/v1/dashboard/bundle`**) surfaces **implemented / partial / missing** honestly.

**Canonical school contract (detail):** [`ANNA_GOES_TO_SCHOOL.md`](ANNA_GOES_TO_SCHOOL.md). **Trade / PnL / MAE definitions:** [`trade_math_operator_reference.md`](trade_math_operator_reference.md). **Memory contract (largely not implemented):** [`context_memory_contract_w8.md`](context_memory_contract_w8.md) §8.

---

## 1. End-to-end story (step-by-step, code-anchored)

Read this as **stages**. Later stages depend on earlier ones; **skipping** a stage shows up as **Partial** or **Offline** in **`intelligence_visibility`**, not as “Anna is fully agentic.”

### Stage A — Market spine and preflight (she is not “blind”)

| Step | What must be true | Code / artifact |
|------|-------------------|-----------------|
| A1 | Canonical **market events** and **bars** exist for analysis and ledger rows. | `market_data.db` → `market_bars_5m`; `market_event_id` in [`scripts/runtime/market_data/market_event_id.py`](../../scripts/runtime/market_data/market_event_id.py). |
| A2 | Anna’s **training / analyst** paths that require data **fail closed** when unhealthy. | `modules/anna_training/readiness.py` — `ensure_anna_data_preflight`; env `ANNA_SKIP_PREFLIGHT` tests-only. |

**If A fails:** downstream “learning” numbers are **not trustworthy** — fix ingestion before interpreting gates or SPRT.

### Stage B — Analyst layer (structured reasoning, not execution)

| Step | What must be true | Code / artifact |
|------|-------------------|-----------------|
| B1 | Trader text → **`anna_analysis_v1`** with intent, risk, policy alignment. | [`scripts/runtime/anna_analyst_v1.py`](../../scripts/runtime/anna_analyst_v1.py) → [`anna_modules/analysis.py`](../../scripts/runtime/anna_modules/analysis.py) **`build_analysis`**. |
| B2 | **Optional** local **LLM** (Ollama) when enabled — **not** canonical memory. | `ANNA_USE_LLM`; [`scripts/runtime/anna_modules/pipeline.py`](../../scripts/runtime/anna_modules/pipeline.py); preflight in **`state.json`** → `karpathy_last_llm_preflight`. |
| B3 | **Lesson memory** / carryforward ( **partial** vs full W8 lesson DB). | [`lesson_memory.py`](../../scripts/runtime/anna_modules/lesson_memory.py), [`internalized_knowledge.py`](../../modules/anna_training/internalized_knowledge.py); W8 **gap**: similarity lesson store — see §4. |

This stage is **“thinking”** in the product sense: **structured output**. It does **not** place live venue trades.

### Stage C — School: curriculum + Karpathy loop (habits and gates)

| Step | What must be true | Code / artifact |
|------|-------------------|-----------------|
| C1 | **Curriculum** and **method** ids are assigned in **state**. | [`modules/anna_training/catalog.py`](../../modules/anna_training/catalog.py) — `grade_12_paper_only`, `karpathy_loop_v1`; [`store.py`](../../modules/anna_training/store.py) **`state.json`**. |
| C2 | **Four Grade-12 tools** (binary checklist) before headline numeric cohort is admissible for **PASS**. | [`curriculum_tools.py`](../../modules/anna_training/curriculum_tools.py); [`gates.py`](../../modules/anna_training/gates.py) **`evaluate_grade12_gates`**. |
| C3 | **Paper judgment** cohort on **`paper_trades.jsonl`** (win-rate floor + min decisive — **defaults in env**). | [`gates.py`](../../modules/anna_training/gates.py); `ANNA_GRADE12_MIN_WIN_RATE`, `ANNA_GRADE12_MIN_DECISIVE_TRADES`. |
| C4 | **Long-running loop**: Karpathy **daemon** advances iterations, heartbeats, optional **paper harness** ticks. | [`scripts/runtime/anna_karpathy_loop_daemon.py`](../../scripts/runtime/anna_karpathy_loop_daemon.py); [`karpathy_paper_harness.py`](../../modules/anna_training/karpathy_paper_harness.py). |

This stage is **“school”**: **process**, **tool mastery**, **paper outcomes** on the **judgment** ledger — **not** the same as sequential SPRT (see Stage E).

### Stage D — Execution identity: baseline vs Anna (measurement instrument)

| Step | What must be true | Code / artifact |
|------|-------------------|-----------------|
| D1 | **Baseline** lane = reference book line on the same **market_event_id** spine. | [`baseline_ledger_bridge.py`](../../modules/anna_training/baseline_ledger_bridge.py); ledger schema + [`execution_ledger.py`](../../modules/anna_training/execution_ledger.py). |
| D2 | **Anna** strategies produce **lane=strategy** rows; **parallel** runner can append **paper** harness rows. | [`parallel_strategy_runner.py`](../../modules/anna_training/parallel_strategy_runner.py); `ANNA_PARALLEL_STRATEGY_MODE`. |
| D3 | **PnL** for economic modes is **derived** in ledger — not free-typed. | **`compute_pnl_usd`** in [`execution_ledger.py`](../../modules/anna_training/execution_ledger.py). |

**Baseline is the law** for **headline** paper book in [`paper_capital.py`](../../modules/anna_training/paper_capital.py) (baseline vs Anna lane rollup).

### Stage E — Sequential experiment layer (MAE + SPRT — **only part** of the full story)

This is **strategy hypothesis testing** with **audit**, not a replacement for Stage C or B.

| Piece | Role | Code |
|-------|------|------|
| **MAE v1** | Worst adverse path on bars — **path risk**. | [`sequential_engine/mae_v1.py`](../../modules/anna_training/sequential_engine/mae_v1.py) |
| **SPRT** | **PROMOTE / KILL / CONTINUE** from accumulated eligible outcomes. | [`sprt.py`](../../modules/anna_training/sequential_engine/sprt.py), [`decision_state.py`](../../modules/anna_training/sequential_engine/decision_state.py) |
| **Manifests** | Append-only outcome records + hashes. | [`outcome_manifest.py`](../../modules/anna_training/sequential_engine/outcome_manifest.py) |
| **Operator UI** | Start / pause / tick / validation. | [`sequential_engine/ui_control.py`](../../modules/anna_training/sequential_engine/ui_control.py) |

**Important:** SPRT is **not** “pattern recognition” in the ML sense — it is **statistical evidence accumulation** on **declared** outcome streams. **Pattern-from-memory** retrieval is **W8** (still **gap** — §4).

### Stage F — Operator visibility and “independent” agency (governed)

| Step | What must be true | Code / artifact |
|------|-------------------|-----------------|
| F1 | **Dashboard** shows **trade chain**, **vs baseline**, **scorecard**, **capital**, **intelligence strip**. | [`dashboard_bundle.py`](../../modules/anna_training/dashboard_bundle.py); [`intelligence_visibility.py`](../../modules/anna_training/intelligence_visibility.py); **`UIUX.Web/dashboard.html`**. |
| F2 | **Designated trading strategy** (registry + operator API). | [`operator_trading_strategy.py`](../../modules/anna_training/operator_trading_strategy.py). |
| F3 | **Independent decisions** = **structured analysis + paper / trial ledger outcomes** — **not** autonomous live venue promotion unless policy and wallet gates say so. | Master plan + [`live_execution`](../../modules/anna_training/dashboard_bundle.py) hints in bundle. |

**Agentic** in this repo means: **traceable proposals**, **measured outcomes**, **governance boundaries** — **not** unconstrained autonomy.

---

## 2. Primer — MAE, SPRT, manifest, promotion (sequential layer only)

*(Same technical definitions as before; kept short.)*

- **MAE:** Adverse excursion from **5m bars** per **`mae_protocol_id`** — see **`mae_v1.py`**.  
- **SPRT:** Likelihood-ratio **stopping** — **`sprt.py`**, decisions persisted.  
- **Manifest:** Auditable outcome rows — **`outcome_manifest.py`**.  
- **Promotion:** **SPRT PROMOTE** is a **statistical** signal; **human / registry promotion** is separate — see **operator trading** and governance.

---

## 3. What “fully learned” would require (contract + honest gaps)

| Requirement | In code today? | Notes |
|-------------|----------------|-------|
| Situation → **similar lesson** retrieval (W8) | **No** (§8 **non-compliant**) | [`context_memory_contract_w8.md`](context_memory_contract_w8.md) |
| **failure_pattern_key** archive / differential | **Partial / TBD** | [`ANNA_GOES_TO_SCHOOL.md`](ANNA_GOES_TO_SCHOOL.md) loop §3 |
| **Grade-12 gate** vs **sequential SPRT** as **single** “primary” headline | **Two mechanisms** — align in **`gates.py` + docs** if policy demotes win-rate | [`gates.py`](../../modules/anna_training/gates.py) |
| **Intelligence strip** shows **Online/Partial/Offline** with **signals** | **Yes** | **`intelligence_visibility`** in dashboard bundle |

Closing gaps = **implement or narrow** each row — **not** more prose.

---

## 4. Appendix A — Metric migration process (when governance changes the headline bar)

Use when changing **`ANNA_GRADE12_*`**, primary proof story, or dashboard semantics:

1. **`gates.py`** / env / tests — one coherent default.  
2. **`report_card_text.py`**, **`api_server.py`**, **`dashboard.html`** — operator copy matches.  
3. **`ANNA_GOES_TO_SCHOOL.md`** / CEO summary — same story.  
4. **Primary host** proof — [`local_remote_development_workflow.md`](local_remote_development_workflow.md).

Rollback: revert env + git; redeploy **api** + **web**.

---

## 5. Appendix B — Dashboard correctness (operator)

1. Bundle **numbers** match DB definitions — restart **api** after deploy.  
2. Do not mix **harness** PnL with **venue** settlement in copy.  
3. **`intelligence_visibility.subsystem_gaps`** must stay **honest** — do not mark W8 “complete” until implemented.

---

**Related:** [`trade_math_operator_reference.md`](trade_math_operator_reference.md), [`ANNA_GOES_TO_SCHOOL.md`](ANNA_GOES_TO_SCHOOL.md), [`runtime/execution_context.md`](../runtime/execution_context.md).
