> **Source:** `docs/blackbox_master_plan.md` in repository **blackbox**, branch **`main`** (includes Phase **4.x** control stack, Phase **5–8** roadmap, [`development_plan.md`](development_plan.md)).

> **Purpose:** Architect-facing copy of the master plan. **Canonical file remains** [`docs/blackbox_master_plan.md`](../blackbox_master_plan.md) — refresh this share file when roadmap phases change.

---

# BLACK BOX — MASTER PROJECT PLAN

## Overview

This document defines the full Phase 1 bootstrap for Cody (Code Bot) using OpenClaw.

It is the **single source of truth** for project **rehydration** (Architect, Cursor, Operator). **Directives** issued as work packages map to sections here and to companion markdown specs; keep this file aligned with **implemented reality**.

### Roadmap at a glance

| Phase | Name | Status (this document) |
|-------|------|-------------------------|
| **1** | Foundation | Complete |
| **1.5** | Agent hardening | Complete |
| **1.6** | Controlled execution | Complete |
| **2** | Paper system | Complete — runtime pipeline (see [Phase 2 — Paper System](#phase-2--paper-system)) |
| **3** | Intelligence layer | **3.1–3.8** closed (clawbot-verified; see [`agent_verification.md`](architect/agent_verification.md)) |
| **4.0** | Execution context rehydration | **Closed** |
| **4.1** | Trading readiness map | **Blueprint** — [`phase_4_1_trading_readiness.md`](architect/phase_4_1_trading_readiness.md) (planning only; **not** go-live) |
| **4.2** | Wallet / account architecture | **Stub** — [`phase_4_2_wallet_account_architecture.md`](architect/phase_4_2_wallet_account_architecture.md) (technical shape; **no** implementation) |
| **4.1+** | Real trading prerequisites (detail) | Master plan § Phase 4 below; implementation **after** architect alignment |
| **5** | Core trading engine | **Next active build phase** (planning / not implemented) — [Phase 5](#phase-5--core-trading-engine); tasks [`development_plan.md`](development_plan.md) |
| **6** | Intelligence & self-improvement | **FUTURE / STUB ONLY** — **not** current sprint — [Phase 6](#phase-6--intelligence--self-improvement-future) |
| **7** | Bot hub / ecosystem | **FUTURE / STUB ONLY** — **not** current sprint — [Phase 7](#phase-7--bot-hub--ecosystem-future) |
| **8** | Trading operations & governance | Planning — [Phase 8](#phase-8--trading-operations--governance) |

**Do not confuse:** The **[future decision-science stub](#future-decision-science-stub-not-phase-2-runtime)** (expected utility, Bayesian *teaching* framing) is **not** the same as **Phase 2 — Paper System** (implemented scripts). During rehydration, treat them as distinct.

**Execution / proof:** Primary host **`clawbot.a51.corp`**, repo path **`~/blackbox`**. Phase closures use [`docs/architect/global_clawbot_proof_standard.md`](architect/global_clawbot_proof_standard.md).

### Where we are now

- **Completed through:** Phase **4.1** blueprint (and Phase **4.0**, all Phase **3.x**).
- **Current planning artifact:** **Phase 4.2** — [`docs/architect/phase_4_2_wallet_account_architecture.md`](architect/phase_4_2_wallet_account_architecture.md) (wallet/account **architecture stub**; **no** code).
- **Prior blueprint:** **Phase 4.1** — [`phase_4_1_trading_readiness.md`](architect/phase_4_1_trading_readiness.md).
- **Next focus:** Phase **4.1+** prerequisites (§ below) and architect approval before **any** implementation that touches keys or venues.
- **Roadmap beyond Phase 4 control stack:** **Phase 5 — Core trading engine** is the **next** canonical build target. **Phase 6** and **7** are **stub / future only** — **not** in scope for the current sprint. See [Phase 5](#phase-5--core-trading-engine)–[8](#phase-8--trading-operations--governance) and [`development_plan.md`](development_plan.md).
- **Safe resume:** Read this plan → [`docs/runtime/execution_context.md`](runtime/execution_context.md) → `python3 scripts/runtime/context_loader.py` → run mandated verification on **clawbot** before claiming closure.

---

## Core Philosophy

- Pattern recognition over prediction
- Structured learning
- Risk-controlled decisions
- No autonomous unsafe behavior

---

## Phase 1 — Foundation

### Phase 1 Goal

Build Cody as an OpenClaw SKILL-driven engineering agent.

---

### Key Components

#### Cody — Code Bot

**Role:**

- Software engineer agent
- System architect
- Planning and scaffolding

**NOT:**

- Trader
- Analyst
- Execution bot

---

### Directory Structure

```text
blackbox/
├── agents/
│   └── cody/
│       ├── agent.md
│       ├── prompts/
│       ├── skills/
│       │   └── cody-planner/
│       │       └── SKILL.md
│       ├── runtime/
│       └── templates/
├── docs/
├── modules/
├── data/
└── tests/
```

---

### SKILL.md Core

- **name:** `cody_planner`
- **Purpose:** Plan system architecture, recommend build steps, guide development (see `agents/cody/skills/cody-planner/SKILL.md` in-repo).

---

### OpenClaw Integration

OpenClaw loads skills from `<workspace>/skills` (highest precedence), then `~/.openclaw/skills`, then bundled skills. The canonical copy in **git** lives at `agents/cody/skills/`.

**Make skills visible to the gateway** by one of:

- Copying `cody-planner` into `<workspace>/skills/` (symlinks that escape the workspace root may be **rejected** by OpenClaw), or  
- Setting `skills.load.extraDirs` in `~/.openclaw/openclaw.json` to an allowed path (see OpenClaw docs: *Skills*, *Creating Skills*).

**Verify:**

```bash
openclaw skills list
```

---

### Test Prompt

Use the Cody planner skill to recommend next steps for building BLACK BOX.

---

### Success Criteria

- Cody loads in OpenClaw
- Cody responds as engineering agent
- No trading behavior
- Structured outputs

---

## Phase 1.5 — Agent hardening (complete)

**Goal:** Move from “working shell” to **disciplined multi-agent foundation**: explicit boundaries, persistence, reduced drift.

**Canonical spec (architect):** [`docs/architect/phase_1_5_agent_hardening_spec.md`](architect/phase_1_5_agent_hardening_spec.md)

**Delivered in-repo:**

| Item | Location |
|------|----------|
| Cody boundary files | `agents/cody/IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `AGENTS.md`, `USER.md` |
| DATA agent package | `agents/data/` (+ `data_guardian` skill) |
| SQLite schema | `data/sqlite/schema_phase1_5.sql` — init: `./scripts/init_phase1_5_sqlite.sh` |
| Skill sync (Cody + DATA) | `./scripts/sync_openclaw_skills.sh` (replaces single-skill sync for full Phase 1.5) |

**OpenClaw / gateway:** Register **DATA** as an agent in OpenClaw config and run skill sync on the lab host when ready (not automatic in this repo).

**Non-goals (Phase 1.5):** Trading analyst/executor, autonomous team expansion, uncontrolled API consult — per architect spec.

---

## Phase 1.6 — Controlled execution (complete)

**Goal:** Move from “agents on paper” to **agents doing controlled, real work** on clawbot: SQLite + DATA health logging + Cody structured plans — **no expansion** until validation.

**Canonical spec (architect):** [`docs/architect/phase_1_6_agent_activation.md`](architect/phase_1_6_agent_activation.md) — **first workloads / acceptance:** [`docs/architect/phase_1_6_next_steps_spec.md`](architect/phase_1_6_next_steps_spec.md)

**Architect concurrence:** Cody + DATA implementation **approved**; audit [`docs/architect/agent_verification.md`](architect/agent_verification.md). **Workspace sync** is a **hard operational requirement** — [`docs/architect/workspace_sync.md`](architect/workspace_sync.md).

**SQLite:** Apply Phase 1.5 + 1.6 — [`scripts/init_phase1_6_sqlite.sh`](scripts/init_phase1_6_sqlite.sh) (includes `system_health_logs`, `alerts`, `agent_tasks` view). **Bridge schema** (not final DDL) — [`docs/architect/architect_sqlite_deviation_response.md`](architect/architect_sqlite_deviation_response.md).

**Constraints:** No new agents; no vault/secrets integration in this phase; no broad tool expansion; no autonomous execution beyond scope — per spec.

---

## Phase 2 — Paper System

**Purpose:** The **implemented** safe simulation and paper pipeline that sits **before** real venue integration. This is **Phase 2** in the roadmap — not the “Phase 2+” decision-science stub below.

**Runtime (representative):** trade lifecycle aggregation (`trade_episode_aggregator.py`), system insight (`insight_generator.py`), system trend (`insight_trend_tracker.py`), guardrail evaluation (`guardrail_policy_evaluator.py`), policy-gated action (`policy_gated_action_filter.py`) — **paper-only**; outputs feed Phase 3 intelligence and validation loops.

**Learning doctrine (paper path):** The system is expected to learn from **both wins and losses**. **Wins do not automatically prove good logic; losses do not automatically prove bad logic.** Every material outcome should support **root-cause analysis** before patterns or behaviors are promoted. Promotion requires **evidence** (repeatability, documented conditions), not a single lucky or unlucky draw.

**Status:** **Complete** as an implemented baseline for paper/safe simulation; evolution continues under Phase 3 validation and governance.

---

## Future decision-science stub (not Phase 2 runtime)

> **STUB — not implemented.** This section is a **future** decision-theory / teachable-analytics layer. It is **not** the same as **[Phase 2 — Paper System](#phase-2--paper-system)** above (implemented scripts). No Analyst *decision-science* runtime here; **Anna** in Phase 3 is the **intelligence layer** with its own closures. Keywords for search: **decision layer**, **analyst model**, **expected utility**, **bayesian update**, **learning system**.

### Purpose

Introduce structured, **auditable** reasoning for:

- trade decisions (long / short / none as a **recommendation**, not autonomous execution)
- risk evaluation (limits, drawdown, exposure)
- confidence scoring (explicit, not opaque)

**Trade team learning (human-in-the-loop):** the same frameworks should double as **teachable methods**—so operators understand *why* a recommendation carries a given confidence and *how* new evidence updates beliefs—rather than treating the layer as a black box. Teaching uses **explained theory + worked examples + outcome reflection**, not reinforcement-learning training in the initial phase.

### Principle

Combine:

- **Theory** — decision frameworks (see below) stated clearly enough to audit and to teach
- **Historical data** — outcomes and prior cases stored in SQLite (and related stores)
- **Real-time data** — market state and **DATA** outputs (health, signals context)
- **Reflection** — compare predicted vs actual outcomes; update documented rationale (Bayesian belief update as a *process*, not a hidden model)

### Initial frameworks (future stub — not Phase 2 paper runtime)

- **Decision theory / expected utility** — preferences over outcomes under uncertainty; explicit tradeoffs
- **Bayesian belief updates** — principled revision of confidence as evidence arrives (explainable steps)
- **Risk & survival constraints** — drawdown limits, exposure caps, survival-style rules (constraints before optimization)

### Inputs

- signals (from trading logic / existing bots)
- market state (including **DATA** outputs where relevant)
- historical outcomes (SQLite and curated history)

### Outputs

- trade recommendation (long / short / none)
- confidence score (defined scale, documented)
- reasoning metadata (why the decision was made—**no hidden state**)

### Constraints

- no reinforcement learning in the initial phase
- must be auditable and explainable end-to-end
- must be testable against historical and live data (replay / paper scenarios)
- no hidden state or black-box behavior in the core path

### Non-goals (for this phase of the stub)

- no RL training
- no autonomous execution (Billy / execution layer remains separate and gated)
- no complex portfolio optimization as a first deliverable

**Alignment:** Roster “Anna — Analyst” ([`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md)) is a **persona** this *future* layer could complement; **implemented Anna** lives under [Phase 3 — Intelligence Layer](#phase-3--intelligence-layer). This stub does **not** implement either by itself.

---

## Meet the Team

Roster — **software agents** vs **human roles** — aligned with runtime architecture (see [`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md) for the canonical table).

| Name | Type | Role | Status |
|------|------|------|--------|
| **Cody** | Agent | Software engineer — builds the system and agents | Active (Phase 1–2 runtime) |
| **DATA** | Agent | Evidence / health / integrity — monitoring, logging, guardian posture | Active |
| **Mia** | Agent | Market info — real-time market data (**read-only**) | Active |
| **Anna** | Agent | Analyst intelligence layer — **`anna_analysis_v1`**, proposals, registry-aware reasoning (Phase 3); not live execution | Active (CLI + modular runtime) |
| **Billy** | Agent | Execution / TBot — **future** venue execution **only** under policy, governance, and Phase 4+ gates (not autonomous in Phase 3) | Planned |
| **Sean** | Human | CEO — strategy, goals, risk tolerance | Active |
| **John** | Human | CTO — architecture, security, technical direction | Active |

---

## Future phases (stub — architect review)

> **Note:** Not in scope for Phase 1 delivery. Below is a **proposal stub** for roadmap alignment. **Confirm with the architect** before design or implementation.

**Proposed addition (Cursor assistant, 2026-03-22) — should be looked at**

1. **Consult / escalation (API “second opinion”)**  
   After the application is in a working state, support **optional** calls to **web/API models** (e.g. Claude, ChatGPT-class providers) using **server-held API keys**, so agents can **escalate** when an answer is **insufficient** or **confidence is low**—without replacing the default local-first Cody loop.

2. **Router / model picker / scoring**  
   Introduce a **routing or scoring layer** that selects among **multiple** candidate models (order-of-magnitude ~10–15 profiles) by **task type, cost, latency, and policy**, rather than a single fixed model for every turn.

3. **Governance**  
   Escalation should be **explicitly triggered** (rules + signals—not only model self-reported confidence), **metered**, **audited**, and **key-safe** (secrets never in repo or public channels).

This section is intentionally high-level; detailed triggers, providers, and OpenClaw wiring belong in a follow-on spec once Phase 1.5 hardening and product direction are set.

---

## Phase 3 — Intelligence Layer

### Shared explanation of learning (future requirement)

Any agent that **explains** how learning, validation, outcome reflection, or concept promotion works must eventually use a **single shared explanation source** (canonical documentation or controlled text), so **no agent improvises a contradictory story** about the learning engine. This is an **architectural** rule; implementation may evolve.

---

> **Mostly planning in this document.** Phase 3 is where **intelligence** (interpretation, conversation, validation, and **read-only** market context) layers on top of the **Phase 2** paper pipeline. **Exceptions:** [Phase 3.1](#phase-31--market-data-ingestion-read-only) — **`market_data_ingestor.py`** (read-only snapshots); [Phase 3.2](#phase-32--anna-conversational-analyst-layer) — **`anna_analyst_v1.py`** (CLI rule-based **`anna_analysis_v1`**, no Telegram). **No** registry loader, **no** Phase 4 execution paths, **no** venue writes beyond these scoped scripts until implemented per architect.

**What Phase 3 is not:** live trading; wallet integration; exchange execution; unrestricted LLM behavior.

**What Phase 3 is:** market visibility; **Anna** as the analyst intelligence layer; **concept registry** and retrieval; expert interaction with Sean; **validation** and concept promotion; **extensible reasoning modules**.

**No exchange trading, no wallet keys, and no live execution** are implied by this section until [Phase 4](#phase-4--real-trading-integration) gates are met.

**Keywords for search:** Phase 3, Anna, intelligence layer, Telegram, validation loop, market data ingestion, Solana, read-only, trading concept registry, intelligence extensibility, concept retrieval, modular reasoning, concept formation pipeline.

**Upstream (Phase 2) — safe simulation:** The intelligence layer must align with trade episodes (`trade_episode_aggregator.py`), system insight (`insight_generator.py`), system trend (`insight_trend_tracker.py`), guardrail policy (`guardrail_policy_evaluator.py`), policy-gated action (`policy_gated_action_filter.py`) — all **paper-only** today (episodes, insights, trends, policy / guardrails).

**Downstream (Phase 4) — real trading prerequisites:** [Phase 4 — Real Trading Integration](#phase-4--real-trading-integration) — wallet, custody, access, approval, governance — before any real venue execution.

**Placement:** Phase 3 sits between **safe simulation** (Phase 2) and **real-world trading integration** ([Phase 4](#phase-4--real-trading-integration)).

**Roster alignment:** Anna (analyst), Sean (human expert), DATA/Mia — see [`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md).

### Phase 3.1 — Market Data Ingestion (Read-Only)

#### Purpose

Allow the system to **see** the market before it tries to reason about it.

#### Required content

The system must support **read-only** ingestion of market data relevant to the target crypto trading environment (e.g. **Solana** ecosystem; exact feeds and venues are implementation choices).

This must include, as applicable:

- **price**
- **volume**
- **spread**
- **liquidity context**
- **order book / depth context** where available
- **volatility context**
- **timestamped normalized market snapshots**

Data should be **normalized** into a **consistent internal structure** for analysts and downstream logic.

#### Requirements

- **Read-only only** — no orders, no signed transactions, no venue keys in application code paths for this phase’s ingestion scope.
- **No trading** in this step.
- **DATA** monitors **feed health** (staleness, gaps, source failures) alongside existing health duties.

#### Explicit rule

**Phase 3.1 is visibility only.** It does **not** grant permission to execute.

#### Runtime implementation (started)

- **Script:** `scripts/runtime/market_data_ingestor.py` — emits **`market_snapshot_v1`** JSON (`kind`, `schema_version`, `generated_at`, `source`, `market_symbol`, `asset`, `price`, `bid`, `ask`, `spread`, `volume`, `liquidity_depth_summary`, `volatility_placeholder`, `notes`). Optional **`--store`** writes a completed **`[Market Snapshot]`** row in existing `tasks` (no new tables).
- **Sources (read-only, no API keys):** try in order **Coinbase Exchange** product ticker (default `SOL-USD`), **Kraken** `SOLUSD`, **Binance** `SOLUSDT` (may be geo-restricted), then **CoinGecko** price-only (bid/ask **null**). Unavailable fields stay **null** with explanation in **`notes`** — **no fabricated values**.
- **DATA:** failures must be explicit in output; deeper health wiring is **future** (optional `system_health_logs` hook noted in script).

**Closure (verified):** clawbot runtime proof recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.1 — Market data ingestion*.

### Phase 3.2 — Anna: Conversational Analyst Layer

#### Purpose

Define **Anna** as the **primary cognitive intelligence layer** for market reasoning.

#### Definition

Anna is a **domain-aware analyst** that can communicate with **expert humans (especially Sean)**, understand **trader language**, and translate that language into **structured system reasoning**.

#### Anna responsibilities

- Understand trader language: **liquidity**, **spreads**, **slippage**, **order flow**, **volatility**, **market depth**, **market-making / maker concepts** (as vocabulary and reasoning inputs — not as autonomous execution in Phase 3).
- **Translate** trader language into **system-usable concepts** and structured signals compatible with existing pipelines.
- **Align** reasoning with **current decision context**, **trends**, and **guardrail policy**; align with **paper outcomes** from Phase 2.
- **Propose** adjustments, critiques, or candidate improvements — as **recommendations**, not autonomous trades.
- **Push back** when expert input is weak, unsupported, or contradicted by evidence.
- **Request more evidence** when needed.
- **Explain reasoning** clearly in both **human** and **system** terms.

#### Interaction model

- **Sean** communicates with Anna via **Telegram** (primary human channel for this design).
- Anna must be able to: **converse** in trader language; **ask clarifying questions**; **agree**; **disagree**; **request evidence**; **suggest alternatives**.

#### Explicit rule

Anna is **not** a blind translator and **not** a yes-bot. Anna must be able to **challenge weak logic**.

#### Explicit non-goals (Phase 3.2)

Phase 3.2 does **not** mean:

- live execution
- direct code mutation
- direct system reconfiguration from chat
- automatic adoption of expert suggestions

#### Runtime implementation (v1 — started)

- **Script:** `scripts/runtime/anna_analyst_v1.py` — **`anna_analysis_v1`** JSON: interpretation, **`market_context`** (optional latest **`[Market Snapshot]`**), **`risk_assessment`**, **`policy_alignment`** (optional latest **`[Guardrail Policy]`**), paper-only **`suggested_action`**, **`concepts_used`** (registry-backed **`concept_id`**s when matched), **`concept_support`** (concise summaries for matched IDs only — see Phase 3.6). Flags: **`--use-latest-market-snapshot`**, **`--use-latest-decision-context`**, **`--use-latest-trend`**, **`--use-latest-policy`**, **`--store`** → **`[Anna Analysis]`**. Rule-based; **no** Telegram, **no** registry mutation, **no** execution.

**Closure (verified):** clawbot runtime proof recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.2 — Anna analyst v1 (CLI)*. Telegram / gateway Anna remains **out of scope** for this closure.

### Phase 3.3 — Validation & Learning Loop

#### Purpose

Codify the core philosophy: **trust → test → validate → adopt or reject**.

#### Required loop

**human input → analyst interpretation → structured proposal → controlled evaluation (paper system) → outcome → reflection → why did it succeed or fail → retain or reject**

(Equivalent shorthand: **human input → analyst interpretation → system proposal → controlled evaluation (paper system) → outcome → reflection (why) → retain or reject**.)

#### Required rules

- **No idea becomes system behavior** without **validation** on the paper path (or equivalent controlled evaluation).
- **Success must be repeatable** under documented conditions.
- **Failure must be explained** (what broke, what to change).
- **Reasoning must be stored** alongside outcomes where the architecture persists artifacts (e.g. SQLite tasks, episode/insight records).
- **Expert input is valuable** but **not automatically correct**.
- **System evidence** is the **final arbiter** for what becomes trusted behavior.

#### Explicit rule

The system must always ask: **why did this work?** and **why did this fail?**

**Philosophy:** **trust → test → validate → adopt or reject** — not “ship intuition.”

**Learning doctrine:** Treat **wins and losses** symmetrically for analysis — both require **root-cause** understanding. **Patterns and behaviors are promoted only with evidence**; a win does not prove the logic was sound, and a loss does not by itself prove the logic was wrong.

#### Runtime implementation (v1 — started)

- **Script:** `scripts/runtime/anna_proposal_builder.py` — maps **`anna_analysis_v1`** → **`anna_proposal_v1`** (`proposal_type`, `validation_plan`, `supporting_reasoning`, etc.). **`--use-latest-stored-anna-analysis`** or **live** text with the same optional context flags as **`anna_analyst_v1`**. **`--store`** → **`[Anna Proposal]`** completed task. Deterministic; **no** schema migration; prepares records for later comparison to paper outcomes / reflections / insights / trends.

**Closure (verified):** clawbot proof recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.3 — Anna proposal builder*.

### Phase 3.4 — Anna Modular Extensibility Model

#### Purpose

Ensure Anna becomes smarter by **adding modules**, not by turning into a **single giant prompt blob**.

#### Required content

Anna must be built as a **modular reasoning system**. The plan defines the following categories:

#### Input adapters

Examples: **Telegram** expert input; **market data snapshots**; **system state / guardrail state**; **outcomes / insights / trends**.

#### Concept interpreter

Maps **human language** and **system language** into **registry concepts** (Phase 3.5).

#### Reasoning modules

Examples: **liquidity reasoning**; **spread / slippage reasoning**; **execution risk reasoning**; **contradiction / challenge logic**; **confidence / justification logic**.

#### Output adapters

Examples: **human-facing** analyst answer; **structured proposal** for system use; **challenge / pushback** output; **concept-tagged** reasoning output.

#### Explicit rule

Anna intelligence must scale by adding modular “Legos,” **not** by endlessly bloating a single prompt.

#### Runtime implementation (skeleton — started)

- **Package:** `scripts/runtime/anna_modules/` — **`input_adapter`**, **`interpretation`**, **`risk`**, **`policy`**, **`analysis`** (`anna_analysis_v1`), **`proposal`** (`anna_proposal_v1`), **`util`**. CLI entrypoints **`anna_analyst_v1.py`** and **`anna_proposal_builder.py`** compose these layers; see [`scripts/runtime/README.md`](../scripts/runtime/README.md) (Anna modular package — Phase 3.4).

**Closure (verified):** clawbot backward-compat + modular layout recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.4 — Anna modular extensibility*.

### Phase 3.5 — Trading Concept Registry

#### Purpose

Create the **stable knowledge layer** Anna relies on.

#### Canonical location

- JSON-based registry: **[`data/concepts/registry.json`](../../data/concepts/registry.json)** (or equivalent), version-controlled in **Git**.
- **Mutation rule:** No **runtime** mutation without **validation** and human/process approval; changes land via **PR / review**, not ad hoc edits in production.

#### Each concept entry

| Field | Purpose |
|--------|---------|
| `concept_id` | Stable identifier |
| `name` | Short title |
| `definition` | Precise definition |
| `trader_meaning` | How traders use the term |
| `why_it_matters` | Relevance to decisions |
| `data_signals` | What observables relate |
| `decision_impact` | How it affects recommendations |
| `execution_impact` | How it would affect execution (when allowed) |
| `failure_modes` | What goes wrong if misunderstood |
| `examples` | Concrete examples |
| `status` | `draft` \| `validated` \| `deprecated` (see lifecycle in Phase 3.7) |
| `version` | Monotonic or semver per concept |

#### Explicit rule

The **concept registry is canonical memory**. The **LLM is not** canonical memory.

#### Runtime implementation (scaffold v1 — started)

- **File:** [`data/concepts/registry.json`](../../data/concepts/registry.json) — **`kind`: `trading_concept_registry_v1`**, seed **Foundation + Mechanical** concepts (read-only at runtime). **Mutation** only via **PR / review**, not live writes.
- **Reader:** `scripts/runtime/concept_registry_reader.py` — **`--list`**, **`--concept <id>`**, **`--search <keyword>`**; JSON only; **no** DB. **Anna wiring:** read-only retrieval in Phase 3.6 (`anna_modules/concept_retrieval.py`). **Promotion** remains Phase 3.7+.

**Closure (verified):** clawbot + audit **2026-03-23** — [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.5 — Trading concept registry*.

#### Concept categories (registry growth)

The registry should grow in **layers**, for example:

##### Foundation / “for dummies” layer

price, bid, ask, spread, orders, volume, liquidity, candles, timeframes

##### Mechanical layer

slippage, depth, price impact, volatility, maker / taker

##### Behavioral layer

trend, chop, breakout, fakeout, stop hunt

##### Risk layer

drawdown, position sizing, tail risk, regime shift

##### Strategy layer

market making, mean reversion, momentum, arbitrage, trend following

#### Explicit rule

The registry should **begin with foundational and mechanical** concepts **before** advanced strategy concepts.

### Phase 3.6 — Runtime Concept Retrieval Pattern

#### Purpose

Prevent Anna from “forgetting” concepts and prevent **concept drift**.

#### Required pattern

When implemented:

1. **Detect** concepts in user input or task context.
2. **Fetch** matching **registry entries** only (partial load).
3. **Inject** those entries into Anna’s reasoning context.
4. **Do not** load the entire registry every time.

#### Required rules

- **Registry-backed reasoning** — **no** reliance on assumed LLM memory for canonical definitions.
- **Unknown** concept → **flagged** as draft / unresolved — **not** silent invention.
- **Output** should reference **`concepts_used`** where persisted.

#### Structured output requirement

Anna outputs (when persisted) should support:

- **`concepts_used`**
- **Reasoning tied to concept IDs** (and registry fields where applicable)
- **Mapping** from concept → **system effect** (decision vs execution posture)

#### Explicit rule

**Concept memory lives in the system**, not in temporary LLM context.

#### Hybrid intelligence (reference)

| Layer | Role |
|--------|------|
| **Registry** | Stable, reviewed **knowledge** |
| **Anna** | **Reasoning** over registry + live context |
| **LLM** | **Assistive** drafting/expansion only |

An LLM may **propose** definitions; the **registry** (after review) is **final authority**.

#### Runtime implementation (Phase 3.6)

- **Module:** `scripts/runtime/anna_modules/concept_retrieval.py` — pattern-detects registry **`concept_id`**s in trader text; loads **only** matching rows via `concept_registry_reader.load_registry` / `find_concept`; **`concept_support`** on **`anna_analysis_v1`** carries **`concept_ids`** plus concise **`concept_summaries`** (`concept_id`, `name`, `status`, **`why_it_matters`**). Null-safe if the registry file is missing or invalid; **`notes`** explain no-match or load failure. **No** full-registry dump, **no** mutation, **no** DB schema change.

**Closure (verified):** clawbot runtime proof recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.6 — Runtime concept retrieval (Anna)*.

### Phase 3.7 — Intelligence Ingestion & Concept Formation Pipeline

#### Purpose

Define how the system **gains new concepts** and **improves over time**.

#### Intelligence sources

##### 1. Expert input

- Sean’s guidance
- Sean’s code / strategy logic
- Sean’s trader-language observations

##### 2. Public / external knowledge

- definitions, theory, vocabulary, reference knowledge

##### 3. System evidence

- outcomes, insights, trends, policy / guardrail interactions (Phase 2 artifacts)

#### Required pipeline

**source input → concept extraction → external validation / naming → registry encoding as draft → system testing → outcome evaluation → promote to validated or reject**

#### Required rules

- **Sean** input is **high-value**, not automatically correct.
- **Internet / external** knowledge is **reference**, not final authority.
- **System evidence** decides whether a concept becomes **trusted**.
- Concepts must move through lifecycle states: **`draft`** → **`under test`** → **`validated`** → **`deprecated`** (exact encoding is an implementation detail; semantics are fixed here).

#### Explicit rule

**No concept** should become **`validated`** without **system-backed evidence**.

#### Integration with concept lifecycle (Phase 3.3)

**proposal → test → outcome → reflection → validation → registry update** — Sean may propose; Anna challenges or refines; the system confirms through outcomes (paper path first).

#### Runtime implementation (Phase 3.7)

- **Staging file:** [`data/concepts/staging_registry.json`](../../data/concepts/staging_registry.json) — **`kind`: `trading_concept_staging_v1`**. Holds **candidate** concepts only; **not** the canonical registry.
- **CLI:** [`scripts/runtime/concept_ingestor.py`](../../scripts/runtime/concept_ingestor.py) — `--add` (with `--concept-id`, `--source-type`, `--definition`, `--rationale`, `--signals`, `--impact`), `--update <concept_id> --status` (appends **`status_history`**, bumps **`version`**; preserves prior fields), `--list`, `--concept <id>` — **JSON only** to stdout. **No** writes to **`registry.json`**, **no** automatic promotion, **no** Anna auto-wiring, **no** new DB tables.

**Canonical vs staging:** **`registry.json`** is reviewed canonical memory; **staging** is where new ideas land until evidence and PR merge promote them (or they are **rejected**).

**Closure (verified):** clawbot proof recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.7 — Concept staging & ingestion*.

### Phase 3.8 — Advanced Strategy Awareness (Constrained)

#### Purpose

Acknowledge **advanced topics** without prematurely implementing them.

#### Required content

Anna may **reason about** advanced concepts discussed by expert users, such as:

- maker / market making
- spread capture
- bid/ask positioning
- liquidity provision
- microstructure effects
- inventory risk
- adverse selection

#### Explicit constraints

- **Awareness** does **not** equal **implementation**.
- **No** market manipulation behavior.
- **No** assumption of sufficient capital to influence markets.
- **No execution behavior** is created in this phase.
- These concepts are **discussion / reasoning inputs** only.

#### Explicit rule

Advanced concepts may enter the registry as **draft** or **exploratory** concepts, but do **not** imply deployment.

#### Runtime implementation (Phase 3.8)

- **Modules:** [`scripts/runtime/anna_modules/interpretation.py`](../../scripts/runtime/anna_modules/interpretation.py) — pattern detection for awareness-only strategy ids (`market_making`, `spread_capture`, `inventory_risk`, `adverse_selection`, `liquidity_provision`, `order_book_dynamics`); [`analysis.py`](../../scripts/runtime/anna_modules/analysis.py) adds optional **`strategy_awareness`** on **`anna_analysis_v1`** (`detected`, `explanation`, `risks`, `applicability`, `note`). **No** execution, **no** registry mutation, **no** policy bypass.
- **Null-safe:** `strategy_awareness` is **`null`** when no strategy language matches.

**Closure (verified):** clawbot proof recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.8 — Advanced strategy awareness*.

---

## Phase 4 — Real Trading Integration

Phase **4** spans **execution-context rehydration** (4.0, closed) and **readiness for** touching a real venue (**4.1+** — next focus). **Planning-only for 4.1+:** the system may be **prepared** to touch a **real trading venue** only after gates and human approval. **Nothing here implies live trading is enabled by default.**

**Keywords for search:** Phase 4, real trading, venue, wallet, custody, go-live, governance, signing, policy gate.

**Related:** executor / trading architecture discussion — [`docs/architect/architect_update_trading_system.md`](architect/architect_update_trading_system.md); roster — [`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md); runtime guardrail — `scripts/runtime/guardrail_policy_evaluator.py` (paper-only pipeline today).

### Phase 4.0 — Execution context rehydration

**Problem:** Without a shared, loadable context, verification can drift to local-only runs, informal proof, or missed **clawbot** execution—forcing repeated instructions.

**Mitigation:** Canonical file [`docs/runtime/execution_context.md`](runtime/execution_context.md) records **current phase**, **last completed phase**, **primary host** (`clawbot.a51.corp`), **repo path** (`~/blackbox`), and ties to the [**global clawbot proof standard**](architect/global_clawbot_proof_standard.md). [`scripts/runtime/context_loader.py`](../scripts/runtime/context_loader.py) reads the embedded JSON and prints structured JSON (phase, host, `proof_required`, rules).

**Enforcement:** Runtime work that claims phase closure **must** follow that proof standard; **context_loader** is the lightweight preflight. Other scripts should run it or document that context was loaded.

**Closure (verified):** clawbot proof recorded **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 4.0 — Execution context rehydration*.

### Phase 4.1 — Trading readiness map (blueprint)

**Operational map (planning only):** [`docs/architect/phase_4_1_trading_readiness.md`](architect/phase_4_1_trading_readiness.md) — account model, wallet/connection, authority (Anna / human / Billy / revoke), execution modes (read-only / paper / live gated), approval & signing flow, **chat vs secure execution plane** (chat never executes trades), safety/kill switches, audit link to Phase 2/3 learning, **non-goals** (no live trading, no keys in repo). **Does not** implement execution code.

### Phase 4.2 — Wallet / account architecture (stub)

**Technical architecture stub:** [`docs/architect/phase_4_2_wallet_account_architecture.md`](architect/phase_4_2_wallet_account_architecture.md) — entity model (human, trading account, wallet, venue, roles), wallet integration patterns, access modes, identity/authority (Anna recommends, Billy bounded, humans grant/revoke), **signing boundary** (analysis → approval → signing → execution), **chat-to-secure-plane handoff**, vault boundary (no vault product locked), conceptual audit events, failure/safety cases, **non-goals** (no wallet/signing/exchange code, no secrets). **Does not** implement runtime or schema.

### Phase 4.1+ — Real trading integration readiness (master plan detail)

The following subsections (**1–7**) are **prerequisites** consistent with the Phase **4.1** blueprint: governance, custody, venue, signing, secrets, gates, and non-goals — **not** automatic deployment.

#### 1. Ownership and Governance

Real trading integration requires **clear human ownership** and **explicit approval** before any live capability is enabled.

| Concern | Expectation |
|--------|-------------|
| **Business / risk owner** | **Sean** is the default business and risk owner unless revised in writing. |
| **Technical authority** | CTO / architecture (e.g. **John**) retains technical direction and security oversight for how integration is built. |
| **Account ownership** | Venue and funding accounts must be owned by identified humans or legal entities; **no anonymous or shared “system” accounts** without documented owners. |
| **Who approves access** | Human approvers (risk + technical) must sign off before credentials, API keys, or signing paths are provisioned. |
| **Who approves go-live** | **Explicit human go-live approval** (not model self-approval) before real execution is allowed. |
| **Who can revoke** | Same governance chain must define **revocation**: disable keys, freeze integration, or pull execution access without redeploying the whole app. |

**Human approval policy:** No live trading capability is “on” until a documented approval record exists (who, when, scope).

#### 2. Wallet / Custody Prerequisites

Real trading requires a **wallet architecture** (chain- and venue-specific details are chosen later).

- **Wallet selection:** Example class — **Phantom** or a comparable **Solana** wallet for human-initiated operations; other chains require an explicit decision.  
- **Custody model:** Define whether keys are **hot**, **warm**, or **hardware-backed** for production; default assumption is **no hot-wallet free-for-all** for system funds.  
- **Recovery / secrets:** Rules for **recovery phrase** and **secret material** handling (offline backup, split custody, no single-person copy in chat).  
- **Hardening path:** **Hardware wallet** or stronger custody is a **future hardening** step, not a shortcut around governance.

**Non-negotiables (secrets):**

- **No private keys or seed phrases in Git.**  
- **No private keys or seed phrases in chat** (including Cursor, Slack, email).  
- **No direct unsafe embedding** of raw secrets into runtime scripts or env files committed to the repo.

The system must **never casually “hold” raw secrets**; integration must use **approved secret storage** (see below) when execution is real.

#### 3. Platform / Venue Prerequisites

Before real execution:

- **Target platform / venue** must be **selected** explicitly (generic examples: CEX vs DEX, Drift-class venue — **not locked** here unless architect says so).  
- **Account creation / onboarding** must be completed under the **owner** identity.  
- **Policy on venue type** must be written (what is allowed vs forbidden).

**Explicit distinction:**

| Mode | Meaning |
|------|--------|
| **Read-only market access** | Quotes, charts, public data — **no signing, no orders**. |
| **Paper / simulated** | Current BLACK BOX paper pipeline — **no venue keys required**. |
| **Real execution** | Orders, deposits, or signed transactions — **only after Phase 4 gates + approval**. |

#### 4. Signing / Execution Control Model

A **controlled execution model** is required:

- **Authorization:** Orders or transactions must be **authorized** by a defined path (human approval first).  
- **Initial assumption:** **Human approval** before every real execution **until** a stricter automated policy is validated and approved.  
- **Later:** **Controlled automated approval** only after **validation**, audits, and rollback drills — not a default.  
- **Auditable path:** Every real execution must be **traceable** (who/what approved, what was signed, when).

**Explicit statements:**

- **No silent execution** — no background signing without policy visibility.  
- **No uncontrolled signing** — no ad hoc scripts with keys.  
- **No direct production execution** without passing the **policy gate** (e.g. guardrail / governance layer — see Phase 2.11–2.12 runtime and future enforcement).

#### 5. Environment / Secrets / Access Controls

- **Secret storage policy:** Secrets live in **approved vaults** or host-managed secret stores — **not** in the repo.  
- **Direction:** Integrate with a **vault / secret-manager** pattern approved by technical leadership.  
- **Access classes by role:** Separate **data** access, **planning** access, and **execution** access; least privilege.  
- **No secrets in repo**; **no secrets in chat**; **no ad hoc copying** of credentials into scripts.

#### 6. Safety Gates Before Live Integration

Phase 4 **must not** begin real execution until **all** of the following are true:

1. **Phase 2** paper-only pipeline is **complete and stable** (lifecycle → insight → trend → guardrail as implemented).  
2. **Phase 3** intelligence / data phase is **complete enough** per architect (not defined here in detail).  
3. **Guardrail policy** exists and is **enforceable** in downstream workflows (see `policy_gated_action_filter.py` and policy storage).  
4. **Wallet / access governance** is **documented** (this section + approvals).  
5. **Approval model** is **documented** and followed.  
6. **Test capital policy** is **documented** (how much, which account, kill switch).  
7. **Rollback / disable path** is **documented** (how to turn off venue access without code panic).

#### 7. Explicit Non-Goals

Phase 4 **does not** automatically mean:

- **Immediate autonomous trading**  
- **Unrestricted exchange access**  
- **Direct hot-wallet free-for-all**  
- **Bypassing policy** because the system “looks ready”

---

## Phase 5 — Core Trading Engine

> **Next active build phase (not implemented in tree at roadmap insert).** Enables the first real **Anna + Billy** trading path to execute trades **end-to-end** using **live market data** and **controlled execution** (Layers **1–4** unchanged in canonical master plan), while establishing the canonical **multi-participant** architecture for additional humans and constrained bot participants. Detailed tasks: [`development_plan.md`](development_plan.md).

> **Core Principle — Perpetual, Risk-Tiered Winning (Anna):** Anna is a perpetual, self-improving competitor whose “win” is **repeatable, risk-controlled PnL within an authorized risk tier**. Risk tier is set by operators (CEO/human), never by Anna; Anna adapts inside that tier, but cannot bypass hard limits (stale/divergence blocks, size/drawdown caps, approvals, kill switch). Strategies are promoted/demoted by rolling, risk-adjusted performance; execution remains separated (Billy) and policy-gated.
> **Self-development & Emergent Behavior:** Anna is expected to self-improve without human prompts: she can schedule backtests, parameter sweeps, and paper drills, and generate/retire strategies autonomously. Exploration is **bounded**: no raising risk limits, no bypassing approvals/guardrails, and no execution without policy gates. Emergent behaviors are acceptable only when they increase safe, repeatable wins.
> **Advanced methods (bleeding-edge, bounded by guardrails):** Fast EV gate with capped Kelly sizing; conformal prediction for calibrated uncertainty/abstain; distributional RL with CVaR objective (tail-aware); realistic LOB simulator for offline training; adversarial/hostile guard (fail closed on divergence/staleness/hostile book). “Skip” is a rewarded action when uncertainty or EV is poor.

### Purpose

Deliver the **data → strategy → approval → execution** spine in production shape: ingest, store, signal, bind to Layer **3** approval, execute via Layer **4** intent and **Billy** (edge execution), with risk controls and observability.

### 5.0 Multi-participant + risk tier interaction model

- **Participants:** BLACK BOX must support multiple human participants (Sean plus future operators/users) and future bot participants. Anna is **not** a single-user analyst surface.
- **Identity model:** every interaction and every trade artifact must resolve **participant identity**, **participant type** (human / bot), **account / wallet context**, **selected risk tier**, and **interaction path**.
- **Wallet / account association:** each participant operates inside their own documented account / wallet context, aligned with the Phase **4.2** entity model. Shared or pooled accounts require explicit human governance and role mapping.
- **Risk tier ownership:** Anna does **not** assign or escalate risk tiers. A human selects the risk tier, and that choice defines the strategy space, behavioral boundaries, and allowable exposure.
- **Canonical tiers:** Tier **1** = low risk (conservative exposure, slower cadence, tighter constraints, capital preservation + consistent gain). Tier **2** = medium risk (moderate exposure, balanced cadence, controlled expansion, disciplined growth). Tier **3** = high risk (higher exposure, faster cadence, wider exploration inside bounds, aggressive but controlled edge extraction).
- **Shared psychology across tiers:** Anna remains relentless, learning, and competitive in every tier; only the amount of room she is allowed to operate in changes.
- **Interaction scoping:** before Anna responds or emits a signal, the system must identify the participant, wallet/account context, and chosen risk tier. Output is scoped to that participant and logged for audit.
- **Bot participants:** future bots may request a strategy, signal stream, or tier-scoped output, but they are treated as constrained participants. Bots cannot override tiers, escalate risk, or bypass approvals.
- **Implementation note:** the first working slice may start with one human participant in practice, but the contracts, storage, and approvals must be multi-participant and tier-aware from day one.

### 5.1 Market data ingestion

- **Primary feed** (e.g. Pyth).
- **Fallback** (e.g. Coinbase REST).
- **Normalization** → canonical snapshot schema.
- **Health checks** + **gap detection**.

### 5.2 Market data store

- **Production database** (non-sandbox).
- **Queryable** time-series / snapshots.
- **Participant-aware consumers:** strategy readers and audit views must resolve which participant/account/tier is consuming a signal even if market data itself is shared.

### 5.3 Strategy engine

- **Initial deterministic strategy** (single symbol / universe).
- **Signal generation** + **confidence**.
- **Backtest / simulation loop** using **stored** data.
- **Adaptive loop:** maintain a portfolio of strategies; score by risk-adjusted PnL, rule adherence, and consistency; promote/demote based on rolling windows.
- **Self-directed learning:** allow Anna to launch sanctioned experiments (paper/backtest/parameter sweeps) on her own schedule, auto-retire underperformers, and propose new configs—without raising risk or changing guardrails.
- **Pre-trade fast gate (live path):** closed-form EV after fees/slippage + risk penalty; conformal interval check; capped Kelly/half-Kelly sizing; “skip” rewarded; hard fail on stale/divergence/guardrails.
- **Split-second “brain” sim:** before any live intent, run the fast EV/uncertainty/sizing check as a micro pre-trade simulation; reject or downgrade trades whose probable outcome is negative or too uncertain.
- **Offline training (paper/sim path):** distributional RL with CVaR objective trained against recorded ticks and a realistic LOB simulator; only promoted to paper/live if risk-adjusted performance and guardrail adherence meet thresholds.
- **Tier alignment:** strategies adapt **within** the selected risk tier; Anna must not mix behaviors across tiers or expand beyond the participant’s authorized envelope.

### 5.4 Signal → approval binding

- **Candidate trade artifact**.
- **Size / risk / expiry**.
- **Routed through Layer 3 approval** (no execution without approval).
- **Scope fields required:** participant id, participant type, account/wallet context, selected risk tier, and strategy profile must be present on the signal/candidate artifact before approval.

### 5.5 Execution adapter

- **Single venue** first.
- **Paper / sandbox mode** → **small-size live**.
- **Consumes Layer 4 execution intent** (per [`layer_4_execution_interface_design.md`](layer_4_execution_interface_design.md)).
- **Integrates with Billy** (edge execution).
- **Context enforcement:** execution resolves the approved participant account/wallet context and risk tier; Billy cannot substitute wallets, merge participant scopes, or expand tier limits.

### 5.6 Risk & controls

- **Per-trade** and **per-account** limits.
- **Per-participant** and **per-tier** limits.
- **Approval expiry** enforcement.
- **Global kill switch**.
- **Position / PnL** tracking.

### 5.7 Observability & operations

- **Metrics** (data feed, signals, approvals, executions).
- **Logs** and **failure** tracking.
- **Runbooks** (halt / rollback / revoke).
- **Auditability:** all outputs and executions must remain attributable to participant, wallet/account context, and selected risk tier.

### First approved slice (paper-first, narrow scope)

> **Status:** Build path **approved** for first end-to-end loop (paper-first). **Scope is narrow:** one **SOL** strategy, **Pyth** feed, **Coinbase** adapter, single approved trade loop with stored outcome. No multi-asset, no ML, no scale-out in this slice.

- **Separation:** **Anna = strategy only** (signals; **no** execution). **Billy = execution only** (approved intents; **no** signal invention). **No** fused signal+execution in this path.
- **Perpetual winner discipline:** Anna’s objective combines PnL with strict penalties for stale/divergent data, guardrail breaches, hallucination/unsupported claims, and drawdown/size violations. Success is measured over rolling windows; advancement (size/frequency) is conditional on repeatable wins inside the selected tier; any breach forces demotion/pause.
- **Multi-participant contract rule:** the first paper loop may be operated by one human in practice, but signal, approval, execution intent, and outcome contracts must still carry participant/account/tier fields from day one. Human selects the tier; Anna never does.
- **Contracts to lock before coding:** strategy (signal) contract for SOL; execution intent (`approval_id`, `intent_id`, `context_hash`, order params, idempotency, participant scope, risk tier) **only** after L3; outcome record (`intent_id`, `execution_id`, outcome, fills, fees, timestamps, `failure_class`, participant scope) **durable**.
- **Data guards:** Pyth **freshness**; **divergence** vs Coinbase before signal (**fail closed**).
- **Layer 4:** Section **13** safety (grant, audit-before-effect, entry point, context hash, kill/abort); **hard fail** when guards fail.
- **Build order:** (1) Pyth ingestion SOL → (2) normalized store → (3) deterministic strategy → signal contract → (4) L3 approval binding → (5) execution intent contract → (6) Billy + Coinbase sandbox → (7) outcome storage. **Goal:** one approved signal → one paper trade → verified outcome → stored.

### Relationship to Phase 4

- Phase **4** = **control framework** (visibility, approval, execution **design** / mock paths). Phase **5** = **first real trading engine** that **uses** that framework for **live** path — **no** bypass of Layers **2–4**.

**Status:** Roadmap structural insert; implementation only per future directives.

---

## Phase 6 — Intelligence & Self-Improvement (Future)

> **NOT IN SCOPE for current sprint. FUTURE / STUB ONLY.** No implementation required at this stage.

### Purpose

Enhance Anna’s **decision quality** using **evidence-based learning** (post–Phase 5 engine).

### Stub sections (not scheduled)

- **Confidence scoring** refinement.
- **Expected utility** / decision theory.
- **Bayesian updating**.
- **Outcome-based** pattern promotion / rejection.
- **Explainability** (“why this trade”).

**Status:** Placeholder; elaboration when Phase **5** is underway.

---

## Phase 7 — Bot Hub / Ecosystem (Future)

> **NOT IN SCOPE for current sprint. FUTURE / STUB ONLY.** External-facing; **not** part of the **core control stack** (Phase **4** Layers **1–4**).

### Purpose

Expose BLACKBOX as a **platform** for external bots and **distributed** execution.

### Stub sections (not scheduled)

- **Bot onboarding** / portal.
- **Wallet / token identity** model.
- **Billy bot distribution**.
- **Strategy request API**.
- **Telemetry** + outcome collection.
- **Network data flywheel**.
- **Lightweight public metrics**.

**Status:** Placeholder; protocol and security hardening require future directives.

---

## Phase 8 — Trading Operations & Governance

> **Planning.** Defines how the organization **operates** trading-capable systems after **Phase 4+** integration groundwork and the **Phase 5** engine exist — not a promise that every item is implemented on day one.

### Purpose

Establish **operations**, **interaction models**, and **governance** so that any execution path remains **human-accountable**, **auditable**, and **consistent** with policy.

### Required themes (architectural)

| Theme | Expectation |
|--------|----------------|
| **Individual accounts** | Clear workflows and ownership for single-account operation. |
| **Shared / pooled / hedge-style** | Explicit rules when exposure is shared across strategies or entities; **no** implicit commingling without documentation and approval. |
| **Chat-first interaction** | Conversational interfaces may be primary for awareness and routine prompts; **must not** replace required **approval planes** for high-risk actions. |
| **Secure portal / approval plane** | Sensitive approvals use a **dedicated, reviewable surface** (not only informal chat). |
| **Mobile-first principle** | Operational and approval flows should assume **mobile** use where the architect requires real-time human decisions. |
| **Approval / signing model** | Defined roles, limits, separation of duties, revocation. |
| **Audit & traceability** | Records of who approved what, when, and under which policy revision. |
| **Safety controls** | Kill switches, limits, and rollback consistent with Phase 4 gates. |

### Explicit non-goals

- **Not** a substitute for **human risk ownership** (Sean / delegated officers).
- **Not** “autonomous operations” without governance visibility.
- **Not** mixing **paper** and **live** runbooks without explicit labeling.
- Detailed UI specs may land in separate architect-approved documents.

### Relationship

- **Phase 4** = **readiness** and **control stack** (custody, venue policy, gates, Layers **1–4**).
- **Phase 5** = **core trading engine** (data, strategy, execution adapter).
- **Phase 8** = **how we run** organizationally once the engine exists — day-two **operations** and **governance**.

**Status:** Framing for rehydration; elaboration tracks architectural decisions already discussed in chat.

---

## Final Rule

If unclear: **STOP → LOOK UP DOCS → THEN IMPLEMENT**
