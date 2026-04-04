# Context engine & memory — as-built (Engineering)

**Audience:** Training Architect / Agentic Training Advisor  
**Type:** System explanation (not a design proposal).  
**Code anchors:** `scripts/runtime/anna_modules/analysis.py` (`build_analysis`), `anna_modules/pipeline.py`, `anna_modules/context_memory.py`, `modules/anna_training/cumulative.py`, `modules/anna_training/store.py`, optional `anna_modules/context_ledger_consumer.py`, `modules/context_engine/*`.

**Contract (target vs gap):** For **memory-driven** behavior (similarity retrieval, structured lessons), see **[W8 — Context & Memory Contract](context_memory_contract_w8.md)**. As-built is **not** fully compliant with W8 — see W8 §8.

---

## 1. Context system — what feeds a single analysis cycle

**Entry points:** `build_analysis` (used by `anna_analyst_v1.analyze_to_dict`, Karpathy paper harness, proposal builder, Telegram path when wired).

**Per-cycle inputs (assembled in order, then merged into “authoritative” FACT lines for the LLM path):**

| Layer | Source | Notes |
|-------|--------|--------|
| **Human text** | Caller (`input_text`) | Normalized; drives intent classification. |
| **Market snapshot** | SQLite `load_latest_market_snapshot` if `use_snapshot` | Price/spread-style context. |
| **Decision context** | SQLite `try_load_decision_context` if `use_ctx` | Operational/task context when present. |
| **Trend** | SQLite `try_load_trend` if `use_trend` | Windowed trend metadata. |
| **Guardrail policy** | SQLite `load_latest_guardrail_policy` if `use_policy` | Risk/guardrail resolution. |
| **Market tick** | `load_latest_market_data_tick` | Phase-5-style tick + optional regime inference. |
| **Concepts / registry** | `retrieve_concept_support` | Concepts tied to input. |
| **Rule + math FACTs** | `compute_rule_facts`, `compute_math_engine_facts` | Merged via `merge_authoritative_fact_layers`. |
| **Training state — carryforward** | `load_state()` → `carryforward_fact_lines` | Up to **12** `carryforward_bullets` as `FACT (cumulative learning): …` plus **school mandate** lines from gates/mandate. |
| **Strategy / regime FACTs** | `regime_signal`, `strategy_catalog`, `strategy_stats` | Extra `facts_for_prompt` lines when imports succeed. |
| **SQLite episodic reuse** | `find_reusable_answer` | **Only** if `conn` provided: match **intent + topic + normalized question**; reuse gated by `learning_core` validation (`is_reusable_by_source`). |
| **Strategy playbook** | `apply_strategy_playbook` | Keyword/playbook narrative into LLM **snippets** (context, not authoritative FACT). |
| **Optional ContextBundle** | `resolve_context_bundle_attachment` | Phase 5.9: validated bundle from context engine; can attach summary or reject with reason. |

**Injection into the agent:** For LLM-on path, authoritative FACT lines + pedagogy/playbook/memory snippets go through `build_anna_llm_prompt` (`pipeline.resolve_answer_layers`). Without LLM, template/playbook/memory fallback paths apply.

**Not in default prompt:** The full **`paper_trades.jsonl`** history is **not** loaded line-by-line into each analysis. The **ledger** is used for **gates/metrics** and optional **human-facing** report paths, not as a complete episodic context window for every tick.

---

## 2. Memory persistence

| Artifact | Survives | What it is |
|----------|----------|------------|
| **`state.json`** (`anna_training_dir`) | Restarts, phases | Curriculum, iterations, `carryforward_bullets`, `grade_12_tool_mastery`, skills deck snapshots, internalization stamps, `cumulative_learning_log` (**last 500** entries), harness snapshots, etc. |
| **`paper_trades.jsonl`** | Until flush/delete | Append-only **history** for training judgment; **not** the same as LLM “memory.” Rows are **`anna_paper_trade_v1`** outcome summaries (`pnl_usd`, `result`, optional `strategy_label`) — **not** a full fill-by-fill lifecycle journal; total P&amp;L on the scorecard is **Σ `pnl_usd`** from those rows (`modules/anna_training/paper_trades.py` — `summarize_trades`). Optional **`market_event_id`** when strict env off; **`ANNA_STRICT_MARKET_EVENT_ID=1`** requires it. |
| **`market_bars_5m` (SQLite)** | With `market_data.db` | **Canonical 5m OHLC** — **identity** for **`market_event_id`**; built from **`market_ticks`** (Pyth primary); **`SOL-USD`** ticks map to canonical **`SOL-PERP`** (`scripts/runtime/market_data/`). |
| **SQLite** (`anna_context_memory`, tasks, learning records) | DB lifetime | Validated reusable Q&A rows; strict match + enforcement. |
| **Per `analyze_to_dict` call** | Single request | Connection opened/closed; no in-process infinite buffer. |

**Tier 1 vs later:** Promotion to bachelor **merges** default carryforward bullets and sets `curriculum_id`; it does **not** wipe `state.json` by default.

**Durable vs transient:** **Durable:** state file, ledger file, SQLite rows subject to schema. **Transient:** anything not saved; LLM context window is **per request**.

---

## 3. Context selection and filtering

- **Carryforward:** **First 12** bullets (no semantic ranking over full history).
- **Episodic reuse:** **Exact** intent + topic + normalized question match; **validation** gate for reuse.
- **Playbook:** Pattern/keyword application (see `strategy_playbook`).
- **No** general **RAG** over all trades, **no** volatility-based pruning of ledger rows in the analyst path, **no** automatic “top-K relevant trades” into the prompt in `build_analysis` as described here.

---

## 4. Behavioral impact

- **FACT layers** are treated as **authoritative** for the LLM prompt builder (model instructed not to contradict them).
- **Execution** (Jack / paper) is **downstream** of analysis + proposal + policy; Anna does **not** “execute” from context memory alone.
- **Prior trades** in bulk do **not** directly change method selection in code; **indirectly**, training state and mandate lines reflect **gate** status.

So: context is **binding** for **stated FACT** and **strongly steers** the LLM; it is **not** a free-form “remember every trade” system.

---

## 5. History vs memory vs operational context

| Concept | In this codebase |
|---------|------------------|
| **History** | Ledger rows, logs, cumulative log (truncated). |
| **Operational “now”** | Market snapshot, tick, policy, trend when enabled. |
| **“Memory” for prompts** | Short carryforward bullets + mandate + optional playbook + rare SQLite reuse + optional bundle. |

They are **partially merged** into one prompt stack; there is **no** separate subsystem that labels “this line is history only, ignore for decisions.”

---

## 6. RCA and pattern retention

- **Grade 12** includes an **RCS/RCA** tool with a **minimal bar**: at least one paper row with **non-empty `notes`** (reflection habit).
- **No** structured RCA schema is **required** for promotion by default.
- **No** dedicated **pattern store** (conditions → lesson) feeding `facts_for_prompt` beyond **carryforward bullets** and **internalization** text when gates pass.

---

## 7. Context during “trading” (school harness)

Karpathy paper harness calls the same **`build_analysis`** stack with harness **input text** and the same **flags** for market/data (per daemon env). The agent “sees” whatever that call loads: **not** a special full-ledger trading view unless something else injects it.

---

## 8. Post–Tier 1

- **State** persists: curriculum can move to bachelor track; **carryforward_bullets** extended on promotion.
- **Ledger** remains historical unless flushed.
- **Nothing** in this path automatically **drops** “Tier 1 memory” except explicit **reset** or **new** state keys.

---

## Bottom line (Advisor question)

The system is **history-aware** (files, gates, logs) and **partially context-driven** (short FACT carryforward + mandates + SQLite reuse + playbook). It is **not** a **full context-driven learning system** in the sense of **automatic** retrieval of **all** trade history, **structured RCA replay**, or **continuous** pattern memory into every decision.

---

*Engineering — reference for formal “Context & Memory Contract” drafting.*
