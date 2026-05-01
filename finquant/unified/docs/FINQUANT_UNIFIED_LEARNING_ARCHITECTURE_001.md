# FinQuant Unified Learning Architecture 001

**Status:** Draft working architecture for the isolated FinQuant learning project  
**Scope:** `finquant/unified/` only  
**Application boundary:** The main application and `renaissance_v4/game_theory/` remain reference-only for this project unless a future integration phase is explicitly approved.

---

## 1. Purpose

This document defines the architecture for the isolated FinQuant learning project.

The purpose of this project is to build and prove an agentic learning system outside the main application so that:

- the **LLM** can function as a governed brain layer,
- the **agent** can provide memory, lifecycle, retrieval, and evaluation,
- the system can improve behavior over time,
- and that improvement can be demonstrated honestly as **learned behavior**.

This project is not a UI task, not a Flask task, and not a direct modification of the production Pattern Machine Learning stack. It is an isolated proving ground for a future unified agent.

---

## 2. Primary Goal

The primary goal is to build a training and evaluation mechanism that gives FinQuant these core attributes:

- **Context**
- **Memory**
- **Judgment**
- **Restraint**
- **Uncertainty awareness**
- **Learned behavior**
- **Governed learning**
- **Explainability**
- **Causal / no-lookahead discipline**
- **Training discipline**
- **Evaluation discipline**
- **Unified agent behavior**

Short mission sentence:

> FinQuant should become a unified learning agent that uses context, memory, judgment, and restraint to make better decisions over time, and prove that improvement through governed training and repeatable evaluation.

### 2.1 Primary operating hypothesis

FinQuant is primarily a pattern-recognition and judgment system.

The core internal hypothesis for the student is:

> Have I seen this before, and if so, should that prior pattern change what I do now?

That question must be answered using only causal pre-reveal context.

The isolated project therefore centers on these decision questions:

- have I seen this pattern before,
- does current context make that memory relevant,
- should I take a position or stay flat,
- which bounded strategy hypothesis is strongest,
- and if I am in a position, when should I exit.

FinQuant is not being trained merely to emit a direction.
It is being trained to:

- recognize recurring market states,
- interpret indicators and mathematical features,
- compare multiple candidate hypotheses at once,
- judge whether similarity is meaningful,
- use context to influence confidence and action,
- choose `NO_TRADE` when conviction is weak,
- and reason about lifecycle exits instead of entry alone.

---

## 3. Isolation Boundary

### 3.1 Working boundary

This architecture applies to:

- `finquant/unified/`
- `finquant/unified/agent_lab/`
- `finquant/training/`
- `finquant/evals/`
- supporting isolated docs and scripts under `finquant/`

### 3.2 Reference-only boundary

The following are authoritative references but not active write targets for this project:

- `renaissance_v4/game_theory/`
- `docs/rm_refactor_architecture_v1.md`
- `docs/architect/finquant_quant_exam_architect_spec_v1.md`
- `renaissance_v4/configs/manifests/baseline_v1_recipe.json`
- `renaissance_v4/configs/manifests/baseline_v1_policy_framework.json`

### 3.3 Operational boundary

- **Local repo:** architecture, code, isolated lab design
- **Remote server:** training runs, adapter materialization, exam execution

The remote host is an execution environment, not the architecture source of truth.

---

## 4. Reference Strategy Surface

FinQuant must not invent a free-form trading philosophy. It should reason against the existing bounded strategy surface defined by the project baseline.

### 4.1 Baseline execution manifest

Reference:

- `renaissance_v4/configs/manifests/baseline_v1_recipe.json`

Current baseline facts:

- Strategy id: `renaissance_baseline_v1_stack`
- Symbol: `SOLUSDT`
- Native baseline timeframe: `5m`
- Signal families:
  - `trend_continuation`
  - `pullback_continuation`
  - `breakout_expansion`
  - `mean_reversion_fade`
- Regime module: `regime_v1_default`
- Risk model: `risk_governor_v1_default`
- Fusion module: `fusion_geometric_v1`
- Execution template: `execution_manager_v1_default`

### 4.2 Baseline policy framework

Reference:

- `renaissance_v4/configs/manifests/baseline_v1_policy_framework.json`

This framework defines the bounded adaptation space. It explicitly prioritizes:

- `expectancy_per_trade`
- `avg_win_size`
- `avg_loss_size`
- `win_loss_size_ratio`
- `exit_efficiency`

It explicitly does **not** optimize for:

- raw PnL maximization
- raw win-count maximization

### 4.3 Architectural implication

FinQuant should learn to reason **around** this framework, not replace it silently.

The isolated project must therefore answer:

- when the baseline conditions are strong enough to justify action,
- when the correct action is `NO_TRADE`,
- when memory or prior experience should modify confidence,
- and when a bounded adaptation within the policy framework is justified.

---

## 5. Data Topology

The isolated FinQuant project must be wired to the real upstream market-data sources used by the broader BlackBox environment, even while remaining outside the main application runtime.

### 5.1 Remote execution host

Current reference host for live and historical market data:

- `jmiller@clawbot.a51.corp`

This host is the operational reference for:

- market-data SQLite storage,
- Pyth SSE ingest,
- canonical 5m bar materialization,
- and baseline bridge parity paths.

### 5.2 Canonical market-data database

On clawbot, the current canonical market-data SQLite is:

- `/home/jmiller/blackbox/data/sqlite/market_data.db`

This path is also the default market-data location resolved by:

- `scripts/runtime/_paths.py` via `default_market_data_path()`

Override environment:

- `BLACKBOX_MARKET_DATA_PATH`

### 5.3 Canonical upstream tables

The isolated project should treat these as the primary upstream market-data tables:

- `market_ticks`
- `market_bars_5m`

#### `market_ticks`

Defined in:

- `data/sqlite/schema_phase5_market_data.sql`

Purpose:

- append-only tick tape,
- primary oracle leg,
- optional comparator and tertiary legs,
- ingest gate state and gate reason,
- publish-time aware event history.

Key fields include:

- `symbol`
- `inserted_at`
- `primary_source`
- `primary_price`
- `primary_observed_at`
- `primary_publish_time`
- `gate_state`
- `gate_reason`

#### `market_bars_5m`

Defined in:

- `data/sqlite/schema_phase5_canonical_bars.sql`

Purpose:

- canonical closed 5m bars derived from the tick tape,
- market-event identity per bar,
- tick count and optional quote volume enrichment.

Key fields include:

- `canonical_symbol`
- `tick_symbol`
- `timeframe`
- `candle_open_utc`
- `candle_close_utc`
- `market_event_id`
- `open`
- `high`
- `low`
- `close`
- `tick_count`
- `volume_base`

### 5.4 Live Pyth path

Current live Pyth ingest path:

- `scripts/trading/pyth_sse_ingest.py`

This ingest subscribes to Hermes SSE and writes into `market_ticks`, then refreshes canonical bars into `market_bars_5m`.

Important facts from the live ingest:

- Source: Hermes Pyth SSE
- Default policy: one SQLite row per valid SSE message
- Default logical symbol: `SOL-USD`
- Canonical bar refresh is triggered from ingest
- Canonical bars are 5m identity bars

Related operational/readiness surfaces:

- `scripts/trading/pyth_stream_probe.py`
- `scripts/operator/preflight_pyth_tui.py`
- `tests/test_pyth_sqlite_quote.py`
- `tests/test_pyth_sse_readiness.py`

### 5.5 Baseline bridge relationship

The isolated project should also understand the baseline bridge contract:

- canonical 5m bars in `market_bars_5m` are the source for baseline policy evaluation,
- the baseline bridge writes policy decisions into the execution ledger,
- operator truth is the posted baseline decision for a closed `market_event_id`,
- the Python parity harness under `basetrade/` is a reference validation path, not a replacement truth source.

Reference:

- `basetrade/README.md`

### 5.6 Architectural implication for FinQuant

For the isolated project, the real upstream data contract should be:

1. Historical and live upstream facts come from the market-data SQLite and live Pyth ingest path.
2. FinQuant consumes those facts as context inputs.
3. FinQuant may roll or transform context for its own internal decision windows, but it must preserve causal discipline.
4. FinQuant must not invent a parallel hidden market world when canonical ticks and bars already exist upstream.

This means FinQuant should eventually be able to reason over:

- canonical historical 5m bars,
- rolled-up bars derived from those canonical bars,
- live tick/quote context from the Pyth path,
- and baseline reference decisions tied to the same market-event chain.

---

## 6. System Layers

The isolated FinQuant system is composed of four layers.

### 5.1 Brain layer

The model is the reasoning organ inside FinQuant.

It is responsible for:

- interpreting visible market context,
- generating a structured judgment,
- expressing uncertainty,
- explaining a decision or abstention,
- and consuming retrieved memory summaries when provided.

It is not responsible for:

- writing directly to memory stores,
- changing policy on its own,
- bypassing lifecycle or no-lookahead rules,
- or inventing strategy surfaces outside the bounded baseline.

### 5.2 Agent layer

The agent layer owns:

- lifecycle stepping,
- no-lookahead enforcement,
- retrieval orchestration,
- memory persistence,
- governance decisions,
- training export,
- exam execution,
- and proof artifacts.

This layer turns the model from a callable LLM into an agentic system.

### 5.3 Reference strategy layer

The baseline recipe and policy framework provide the external strategy anchor.

This layer defines:

- valid signal families,
- valid adaptation surfaces,
- context families,
- bounded execution geometry,
- and the difference between allowed tuning and forbidden strategy invention.

### 5.4 Proof layer

The proof layer owns:

- exam packs,
- run artifacts,
- learning records,
- before/after comparisons,
- behavior-delta evidence,
- and pass/fail judgments about learned behavior.

This layer exists to prevent fuzzy claims of “smartness” or “learning.”

---

## 7. Learning Model

The isolated project must distinguish between four different concepts.

### 6.1 Context

Context is what is visible and causally available now.

Examples:

- visible candles
- rolled-up timeframe state
- baseline regime/fusion context
- bounded structured facts from the current step

### 6.2 Memory

Memory is validated prior experience that can be retrieved later.

Examples:

- prior similar setups
- prior outcomes
- prior abstention cases
- prior failure patterns
- prior exit-quality lessons

### 6.3 Judgment

Judgment is how the system weighs:

- what supports action,
- what argues against action,
- how strong the evidence is,
- and whether abstention is the correct choice.

### 6.4 Restraint

Restraint is the ability to choose `NO_TRADE` when:

- context is weak,
- evidence conflicts,
- too little data is visible,
- a memory match is weak,
- or confidence is too low.

This project treats restraint as a first-class success, not a fallback embarrassment.

---

## 8. Learning Mechanism

The system should learn through governed episode capture, not through blind accumulation.

### 7.1 Episode flow

The target learning loop is:

1. Observe current context.
2. Retrieve eligible prior memory when appropriate.
3. Produce a structured decision.
4. Evaluate the lifecycle outcome.
5. Govern the resulting episode.
6. Persist only eligible learning artifacts.
7. Reuse validated prior experience in future runs.

### 7.2 Governed outcomes

Not every run should become memory.

The isolated project should adopt the same high-level learning idea found in the reference stack:

- **reject**: invalid or low-trust episode, do not reuse
- **hold**: potentially useful but not strong enough to promote
- **promote**: validated enough for future retrieval and possible training export

### 7.3 Learned behavior definition

FinQuant may claim learned behavior only when:

- a prior validated episode exists,
- it becomes eligible for retrieval,
- it is surfaced into a later decision,
- behavior changes because of that prior experience,
- and the changed behavior is better, safer, or more correct.

One good run is not learned behavior.

---

## 9. Training Model

Training is not just “more examples.” Training must produce better judgment.

### 8.1 What goes into weights

The model weights should learn:

- how to interpret baseline context,
- how to express trade reasoning,
- how to express abstention reasoning,
- how to weigh evidence for and against action,
- and how to produce disciplined structured outputs.

Examples that especially matter:

- one-candle insufficient-context cases,
- flat or chop conditions,
- weak trend alignment,
- low-conviction setups,
- conflicting evidence,
- correct `NO_TRADE` cases,
- correct hold / exit cases,
- correct rejection of weak analogies.

### 8.2 What stays external

The following should remain external or governed by the agent layer:

- episodic memory
- retrieval eligibility
- promotion / rejection governance
- proof artifacts
- baseline recipe / framework references
- exam definitions

The model should not be treated as the only place where memory lives.

### 8.3 Training discipline

Training datasets should be built from:

- curated FinQuant examples,
- synthetic but bounded cases aligned to the baseline framework,
- governed promoted episodes,
- and explicit abstention / weak-context examples.

The training objective is not “make more trades.”  
The training objective is “make better decisions inside a bounded strategy surface.”

---

## 10. Retrieval and Memory Design

Retrieval must help judgment, not create a prompt stuffing problem.

### 9.1 Retrieval role

Retrieval should provide:

- prior similar cases,
- prior outcomes,
- prior failure patterns,
- and concise memory summaries that affect confidence or abstention.

### 9.2 Retrieval rules

Retrieval should be:

- bounded,
- auditable,
- causal,
- and filtered for quality.

Weak or invalid memories must not contaminate future decisions.

### 9.3 Retrieval success criterion

Retrieval is only useful if it can change future behavior in a measurable way.

If memory is loaded but has no effect, then memory exists operationally but not behaviorally.

---

## 11. Decision Contract

The isolated FinQuant system must produce structured decision artifacts.

At minimum, a decision should include:

- action
- thesis
- invalidation
- risk state
- confidence or confidence band
- memory usage markers
- raw model output capture
- decision source (`rule`, `llm`, or `hybrid`)

The raw LLM output is never authoritative by itself.  
Only the governed decision artifact is authoritative.

---

## 12. Evaluation and Proof

Evaluation must prove behavior quality, not just execution completion.

### 11.1 Exam goals

The exam layer should answer:

- Did the model run?
- Did the model obey the contract?
- Did it choose the correct action?
- Did it abstain when appropriate?
- Did memory affect judgment?
- Did behavior improve relative to prior validated experience?

### 11.2 Learned behavior proof

The isolated project should eventually produce proof bundles that show:

1. baseline behavior,
2. post-learning behavior,
3. memory retrieved,
4. behavior changed,
5. the changed behavior was better.

### 11.3 Anti-bullshit rule

The project must never claim learning from:

- a single lucky run,
- raw PnL alone,
- execution completion alone,
- or vague “seems smarter” language.

Learning claims require artifact-backed evidence.

---

## 13. Current Gaps

As of this draft, the isolated FinQuant project still has these known gaps:

- strong local architecture exists only in fragments, not one canonical isolated learning spec
- retrieval and memory semantics in the isolated lab are simpler than the reference learning stack
- durable learned behavior proof is not yet established
- training and exam loops exist, but the bridge from governed learning to training remains incomplete
- the system can show model participation without yet proving cumulative judgment improvement

---

## 14. Non-goals

This isolated architecture does not aim to:

- modify the main application directly,
- silently replace the baseline recipe,
- enable live autonomous trading,
- optimize for raw PnL without governance,
- or duplicate the entire reference architecture inside FinQuant without adaptation.

---

## 15. Immediate Deliverables

The next concrete deliverables for the isolated project are:

1. A stable local architecture reference for FinQuant unified learning.
2. A governed memory contract for the isolated lab.
3. A training-export contract that can ingest curated promoted episodes.
4. A learned-behavior proof contract.
5. A repeatable exam loop that distinguishes wiring success from judgment success.

---

## 16. Summary

The isolated FinQuant project exists to prove that an LLM can function as part of a real learning agent.

That requires more than training a model.

It requires:

- a brain layer,
- an agent layer,
- a bounded baseline strategy reference,
- governed memory,
- disciplined training,
- and proof of learned behavior.

FinQuant succeeds only when those parts function as one system.
