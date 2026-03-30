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
| **4.3** | Execution plane skeleton (mock) | **Implemented** — [`scripts/runtime/execution_plane/`](../scripts/runtime/execution_plane/) + [`execution_cli.py`](../scripts/runtime/execution_cli.py) (approval gate, kill switch, audit to `system_events`; **no** wallets/venues/secrets) |
| **4.4** | Execution feedback & learning loop | **Implemented** — [`scripts/runtime/learning_loop/`](../scripts/runtime/learning_loop/) (outcome + `insight_kind` in `system_events` `execution_feedback_v1`; **no** ML, tasks, or schema) |
| **4.5** | Learning visibility & reporting | **Implemented** — [`scripts/runtime/learning_visibility/`](../scripts/runtime/learning_visibility/) + [`learning_cli.py`](../scripts/runtime/learning_cli.py) (query/summarize/report over `execution_feedback_v1`; **no** ML, registry writes, or schema) |
| **4.6** | Telegram interaction layer | **Implemented** — [`scripts/runtime/telegram_interface/`](../scripts/runtime/telegram_interface/) (Bot API; Anna + learning visibility; **no** execution from chat; token via env) |
| **4.6.2** | Multi-agent persona (single bot) | **Implemented** — [`@anna` / `@data` / `@cody`](../scripts/runtime/telegram_interface/) routing + `[Anna]`/`[DATA]`/`[Cody]` labels (no extra bots or processes) |
| **4.6.3** | Identity, routing, persona enforcement | **Implemented** — mandatory tags, silo defaults, SQLite `agents` + registry alignment (see Phase 4.6.3 below) |
| **4.6.3.1** | Telegram Anna product surface & validation | **Directive (code/CI) met** — proof package [`agent_verification.md`](architect/agent_verification.md) § Phase 4.6.3.1; **operational acceptance** = live Telegram sign-off in that section |
| **4.6.3.3** | Messaging interface abstraction | **Closed** — [`directives/directive_4_6_3_3_messaging_interface.md`](architect/directives/directive_4_6_3_3_messaging_interface.md); proof [`directives/directive_4_6_3_3_closure_evidence.md`](architect/directives/directive_4_6_3_3_closure_evidence.md) |
| **4.6.3.4** | Messenger config + Slack adapter | **Directive (active)** — [`directives/directive_4_6_3_4_slack_adapter_and_config.md`](architect/directives/directive_4_6_3_4_slack_adapter_and_config.md); one active backend; Slack operator surface; **no** OpenClaw gateway / **no** multi-fan-out |
| **4.6.3.5** | **Anna Data Grounding Layer** | **Closed (4.6.3.5.A)** — live-data detector + market-data client integration with explicit no-data fallback, plus system-path containment against ungrounded market-like output; verified on live `#blackbox_lab` prompt set |
| **4.6.3.2** | **Learning Core Extraction** (`agent_learning_core`) | **Part A complete (containment only)** — lifecycle baseline + validated-only reuse gate committed/accepted (`ea9c215`); Part B planning only, no new runtime expansion yet |
| **4.1+** | Real trading prerequisites (detail) | Master plan § Phase 4 below; implementation **after** architect alignment |
| **5** | Core trading engine | **Next active build phase** (planning / not implemented) — [Phase 5](#phase-5--core-trading-engine); tasks [`development_plan.md`](architect/development_plan.md) |
| **6** | Intelligence & self-improvement | **FUTURE / STUB ONLY** — **not** current sprint — [Phase 6](#phase-6--intelligence--self-improvement-future) |
| **7** | Bot hub / ecosystem | **FUTURE / STUB ONLY** — **not** current sprint — [Phase 7](#phase-7--bot-hub--ecosystem-future) |
| **8** | Trading operations & governance | Planning — [Phase 8](#phase-8--trading-operations--governance) |

**Do not confuse:** The **[future decision-science stub](#future-decision-science-stub-not-phase-2-runtime)** (expected utility, Bayesian *teaching* framing) is **not** the same as **Phase 2 — Paper System** (implemented scripts). During rehydration, treat them as distinct.

**Execution / proof:** Primary host **`clawbot.a51.corp`**, repo path **`~/blackbox`**. Phase closures use [`docs/architect/global_clawbot_proof_standard.md`](architect/global_clawbot_proof_standard.md).

**Architect directives (registry):** [`docs/architect/directives/README.md`](architect/directives/README.md) — e.g. **4.6.3.3** (closed), **4.6.3.4** (Slack + config).

**Status Synchronization Rule (mandatory):**
- The master plan and directive execution log must remain synchronized.
- If a twig/sub-step is recorded as active, complete, closed, implemented, or corrected in the execution log, the master plan must reflect the same status granularity in the same change set (broader umbrella wording is not sufficient for a more specific log entry).
- No directive/twig is canonically advanced or closed unless both documents agree.
- Closeout summaries must include: `Plan/log status sync: PASS`.
- **Canonical scaffolds:** [`docs/architect/directives/DIRECTIVE_TEMPLATE.md`](architect/directives/DIRECTIVE_TEMPLATE.md), [`docs/architect/directives/CLOSEOUT_PACKET_TEMPLATE.md`](architect/directives/CLOSEOUT_PACKET_TEMPLATE.md).

### Where we are now

- **Completed through:** Phase **4.6.3** (persona enforcement + DB/registry alignment), **4.6.2** Telegram multi-persona, **4.6** bot layer, **4.5** learning visibility, **4.4** feedback loop, **4.3** execution plane (mock), **4.2** stub, **4.1** blueprint (and **4.0**, all Phase **3.x**).
- **Current planning artifact:** **Phase 4.6.3** — **Anna** default front door; **DATA** / **Cody** silos; mandatory `[Anna]`/`[DATA]`/`[Cody]` in message text; Telegram bot name ≠ persona — [`telegram_interface/`](../scripts/runtime/telegram_interface/), [`agents/agent_registry.json`](../agents/agent_registry.json).
- **Prior blueprint:** **Phase 4.1** — [`phase_4_1_trading_readiness.md`](architect/phase_4_1_trading_readiness.md); **4.2** architecture — [`phase_4_2_wallet_account_architecture.md`](architect/phase_4_2_wallet_account_architecture.md).
- **Next infrastructure focus:** Phase **4.6.3.4** — messenger config + Slack adapter (one active backend); see [`directives/directive_4_6_3_4_slack_adapter_and_config.md`](architect/directives/directive_4_6_3_4_slack_adapter_and_config.md). **4.6.3.3** closed — [`directives/directive_4_6_3_3_closure_evidence.md`](architect/directives/directive_4_6_3_3_closure_evidence.md).
- **Next focus (trading):** Phase **4.1+** prerequisites (§ below) and architect approval before **any** implementation that touches keys or venues.
- **Roadmap beyond Phase 4 control stack:** **Phase 5 — Core trading engine** is the **next** canonical build target (live data → strategy → Layer 3/4-gated execution). **Phase 6** (intelligence) and **Phase 7** (bot ecosystem) are **stub / future only** — **not** in scope for the current sprint. See [Phase 5](#phase-5--core-trading-engine)–[8](#phase-8--trading-operations--governance) and [`development_plan.md`](architect/development_plan.md).
- **Safe resume:** Read this plan → [`docs/runtime/execution_context.md`](runtime/execution_context.md) → `python3 scripts/runtime/context_loader.py` → run mandated verification on **clawbot** before claiming closure.

---

## Core Philosophy

- Pattern recognition over prediction
- Structured learning
- Risk-controlled decisions
- No autonomous unsafe behavior
- **Governed agent development:** The project **explicitly authorizes** training and development of agents—**especially Anna**—as **analyst** and **strategist**, within the same governance and safety boundaries as all other work (directives, proof, human-owned risk tiers, Layer 3/4 gates for execution). Canonical statement: [`docs/architect/development_governance.md`](architect/development_governance.md) — *Project declaration — agent training (analyst and strategist)*.

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

## Phase 4.x — System Visibility & Interface Architecture

### Core Principle

**BLACKBOX is not a single interface and not a single UI.** It is a **layered interaction stack**: multiple surfaces, each with a distinct role, composed together without collapsing into one pane or one mental model.

At a high level the stack follows:

observe → validate → simulate → approve → execute

Each layer is isolated and must not bypass another.

---

### Layer 1 — Playground (Developer / Architect Surface)

Type: CLI + TUI  
Purpose: Debugging and inspection  

Responsibilities:
- run full DATA pipeline end-to-end  
- run and inspect each stage of the pipeline end-to-end (full staged visibility, not only endpoints)  
- display all stages: **detect → suggest → ingest → validate → analyze → pattern → simulate**  
- support step, replay, and seed modes  

Constraints:
- sandbox-only  
- no production DB access  
- no execution capability  
- no integration with DATA runtime or messaging systems  

Rule:
Playground is a debug surface only, never an operational interface.

**Operator Playground — Visibility Layer 1 (Complete):** [`scripts/runtime/playground/run_data_pipeline.py`](../scripts/runtime/playground/run_data_pipeline.py) — sandbox-only CLI (`--sandbox-db` required; rejects production runtime SQLite); full staged run (**detect → suggest → ingest → validate → analyze → pattern → simulate**); `--json`, `--step`, `--replay`, `--seed-demo`. Optional TUI wrapper: [`scripts/runtime/playground/playground_ui.py`](../scripts/runtime/playground/playground_ui.py). **Not** a runtime entrypoint; **not** wired into DATA or messaging responses.

**Playground output contract (canonical):** [`directives/directive_4_6_3_3_playground_output_contract.md`](architect/directives/directive_4_6_3_3_playground_output_contract.md) — stage-specific operator fields per stage (DETECT…SIMULATE); JSON envelope stable; `stages[].contract` aligned to that structure (presentation-only; unavailable fields shown as `N/A`). **Playground Output Contract Alignment — Complete.** **Plan/log status sync: PASS**

---

### Layer 2 — Operator Dashboard (Read-Only)

Type: Web UI  
Purpose: Visibility and monitoring  

Displays:
- system health  
- detected issues  
- validation results  
- remediation patterns  
- simulation outcomes  

Constraints:
- strictly read-only  
- no execution  
- no approval  
- no system mutation  

Rule:
Dashboard is a glass window, not a control surface.

**Layer 2 Dashboard — Implemented (read-only):** [`scripts/runtime/operator_dashboard/`](../scripts/runtime/operator_dashboard/) — WSGI app + `static/index.html`; `GET` only; reads sandbox SQLite with **`file:…?mode=ro`** and **`PRAGMA query_only`** (no writes). Surfaces: pipeline runs (seven stages synthesized per `remediation_id`), validation runs, outcome analyses, patterns, simulations, approvals (**status display only**). Run: `cd scripts/runtime && python3 -m operator_dashboard --sandbox-db /path/to/sandbox.db` (bind defaults `127.0.0.1:8765`). **Not** an approval interface; **not** execution; **not** messaging; **not** pipeline control; **no** background jobs. Tests: [`tests/test_operator_dashboard_readonly.py`](../tests/test_operator_dashboard_readonly.py). **Plan/log status sync: PASS**

---

### Layer 3 — Approval Interface (Implemented — decision surface)

Type: Controlled UI  

Purpose:
Introduce explicit permission to act  

Responsibilities:
- approve / reject / defer actions  
- enforce policy constraints  

Constraints:
- separate from Slack  
- fully audited  
- not tied to pattern or simulation output  

Rule:
Approval is a distinct system boundary, not an extension of analysis.

**Canonical design:** [`docs/architect/layer_3_approval_interface_design.md`](architect/layer_3_approval_interface_design.md). **Implemented UI/API:** [`scripts/runtime/approval_interface/`](../scripts/runtime/approval_interface/) — WSGI + `static/index.html`; `GET` list/detail/context; `POST` `/api/approvals/<id>/decision` with **`--decision-token`** (Bearer / `X-Approval-Token`) for **approve / reject / defer** only; **no** execution_plane, messaging, pipeline rerun, or mutation of non-`approvals` tables. Run: `cd scripts/runtime && python3 -m approval_interface --sandbox-db /path/to/sandbox.db --decision-token <secret>` (default bind `127.0.0.1:8766`). **Twig 6 data model:** `DEFERRED` status + `decision_note` on sandbox `approvals` (migration in `remediation_validation`); [`learning_core/approval_model.py`](../scripts/runtime/learning_core/approval_model.py) (`defer_pending`, `list_approvals`, …); [`approval_cli.py`](../scripts/runtime/approval_cli.py) includes `--defer`. Tests: [`tests/test_approval_interface.py`](../tests/test_approval_interface.py). **Live** controlled remediation **execution** remains **not built**. **Plan/log status sync: PASS**

---

### Layer 4 — Execution Interface (Design Complete)

Type: Restricted system layer  

Purpose:
Execute approved actions safely  

Constraints:
- requires approval artifact  
- policy gated  
- rollback capable  
- fully auditable  

Rule:
Execution is never triggered directly from UI.

**Status:** **Design complete** — canonical specification: [`docs/architect/layer_4_execution_interface_design.md`](architect/layer_4_execution_interface_design.md). Layer 4 is **action only**: **explicit** execution requests with **valid** **approval_id**, **re-validation**, **idempotency**, **audit**, **kill/abort** boundaries; **no** bypass of Layer 3; **no** Slack/Telegram/pattern/simulation-triggered execution; **no** upstream artifact mutation as part of core execution; **no** messaging as control plane. **Safety mitigation contract (section 13):** default **one successful execution per `approval_id`** (bounded repeat opt-in only on approval); **audit-before-effect** (durable intent before irreversible effects); **Layer 4 sole remediation entry point** (`execution_plane` remains mock/lab — not Layer 4); **context hash match** (no drift; fail closed); **kill switch / abort / observability** minimum contract. **Implementation** of this interface (workers, connectors, production execution store) is **not** claimed here — **live** controlled remediation execution remains **not built** until a future implementation directive. **Plan/log status sync: PASS**

---

### Slack / Messenger Role (Clarification)

Slack and Telegram remain the PRIMARY operator interface.

They are responsible for:
- querying system state  
- receiving summaries  
- conversational interaction  

They are NOT:
- a playground  
- a pipeline runner  
- an approval interface  
- an execution interface  

---

### System Relationship

The primary architectural picture for operator-facing control and decision surfaces is a **linear layer stack**:

**Playground → Dashboard → Approval → Execution**

Slack and Telegram sit **in parallel** to that stack: they are the primary **communication** surfaces for querying state, receiving summaries, and conversation. They are **not** inline between Dashboard and Approval, or between Approval and Execution—i.e. they do not substitute for the approval or execution layers, and they are not the playground or pipeline runner.

---

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

### Phase 4.3 — Execution plane skeleton (mock)

**Implemented control layer (safe, no real trading):** [`scripts/runtime/execution_plane/`](../scripts/runtime/execution_plane/) + [`scripts/runtime/execution_cli.py`](../scripts/runtime/execution_cli.py) — `anna_proposal_v1` → `execution_request_v1` (file-backed), **human approval** before any mock execution, **kill switch** (`data/runtime/execution_plane/kill_switch.json`) that blocks all runs when active, **audit** to existing SQLite `system_events` (`source='execution_plane'`; no schema change). **Non-goals:** no wallets, exchanges, API keys, or signing.

**Closure (verified):** clawbot proof — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 4.3 — Execution plane skeleton (mock)*.

### Phase 4.4 — Execution feedback & learning loop (mock)

**Problem:** Execution results need **structured, append-only feedback** so downstream learning can consume **deterministic signals** without new ML, task queues, or schema migrations.

**Mitigation:** [`scripts/runtime/learning_loop/`](../scripts/runtime/learning_loop/) — after each `run_execution` attempt, **one** `system_events` row (`event_type`=`execution_feedback_v1`, `source`=`execution_plane`) stores **outcome** (request_id, status, reason, timestamp) and **insight** (`insight_kind`, `type`, `reasoning`, `linked_request_id`). **Amendment 4.4.1:** canonical store only in `system_events`; append-only (repeat runs append rows); failure taxonomy preserved (`blocked_not_approved`, `blocked_kill_switch`, `blocked_unknown_request`, `execution_succeeded`). **No** tasks, **no** Phase 3 triggers from this layer.

**Closure (verified):** clawbot proof — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 4.4 — Execution feedback & learning loop*.

### Phase 4.5 — Learning visibility & reporting

**Problem:** Feedback rows exist in `system_events`, but operators need **queryable lists**, **aggregates**, and **human-readable** summaries without ad-hoc SQL.

**Mitigation:** [`scripts/runtime/learning_visibility/`](../scripts/runtime/learning_visibility/) — read-only **query** (`insight_query.py`), **aggregation** (`insight_summary.py`), and **report text** from summary data only (`report_generator.py`). CLI: [`scripts/runtime/learning_cli.py`](../scripts/runtime/learning_cli.py) — `list_insights`, `summarize_insights`, `generate_report`. Filters: `insight_kind`, success/failure (`insight.type`), `request_id`. **Non-goals:** no ML, no registry mutation, no learning triggers, no schema change.

**Closure (verified):** clawbot proof — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 4.5 — Learning visibility & reporting*.

### Phase 4.6 — Telegram interaction layer (agents interface)

**Problem:** Operators need a **primary human-facing channel** without bypassing governance.

**Mitigation:** [`scripts/runtime/telegram_interface/`](../scripts/runtime/telegram_interface/) — Bot API via **`TELEGRAM_BOT_TOKEN`** (env only). **Message router** → **agent dispatcher** (Anna via `anna_analyst_v1.analyze_to_dict`; `report` / `insights` via read-only `learning_visibility`). **Response formatter** → concise Telegram text. **Non-goals:** no `run_execution`, approval, or kill switch from Telegram; no secrets in repo; no schema change.

**Phase 4.6.1 (UX):** Identity intents (`help`, `who are you`, `what can you do`, `how do I use this`), `agent_identity` copy for Anna, and responses shaped as **Answer → Expand → Guide → Offer** with rotating closing lines — **behavior/UX only** (no backend or DB changes).

**Phase 4.6.2 (multi-persona, single bot):** `@anna` / `@data` / `@cody` explicit routing; default Anna; `report` / `insights` / `status` → DATA; `cody …` or engineering-style openers → Cody stub; all replies prefixed `[Anna]`, `[DATA]`, or `[Cody]` — **no** extra Telegram bots, tokens, or processes.

**Phase 4.6.2a (routing correction):** Removed broad “engineering keyword” routing to Cody so general trading/market text **defaults to Anna**; Cody only via `@cody`, leading `cody …`, or exact `cody`. Identity/help phrases checked first (including `@anna help` → identity).

**Ownership (UX):** Trading / market / risk / concepts / education → **Anna** by default. Reporting / system-state / insights / status → **DATA** (including conservative natural-language cues). Engineering / repo / code / architecture → **Cody**. Replies are `[Anna]` / `[DATA]` / `[Cody]` with content matching role; optional Telegram **first name** in copy.

**Phase 4.6.3 — Agent identity, routing, persona enforcement (system integrity):** **Default:** no `@` → trading/market/risk/concept → **Anna**; DB/system/status/connectivity/report/insights/infra cues → **DATA**; engineering cues → **Cody**; **ambiguous → Anna** (spokesperson). **Telegram:** every user-visible reply passes through **`response_formatter`**; first line **`[Anna]`**, **`[DATA]`**, or **`[Cody]`** (and **`[Mia]`** only for reserved `@mia`); invalid/missing tag → **Anna** fallback (`re-evaluate…`). Telegram **sender name** (BotFather) is **not** the persona — identity is in the message body. **SQLite:** `agents` rows `main`→Cody, `data`→DATA, `anna`→Anna, `mia`→Mia (inactive); new Anna tasks use `agent_id = "anna"`. **Project:** [`agents/agent_registry.json`](../agents/agent_registry.json) `runtimeAlignment` on Anna; **not** a separate OpenClaw runtime for Telegram. **Tone:** Anna conversational analyst; DATA factual/state-based; Cody structured engineering.

**Phase 4.6.3.1 — Telegram interface correction & validation (product surface):** Treat Telegram as the **primary Anna interface**, not transport-only. Anna’s bubble must reflect **`interpretation.summary`** (real reasoning path) **without** generic tails (e.g. default **WATCH** / **Risk read** / **paper-only** boilerplate) unless **`ANNA_TELEGRAM_VERBOSE=1`** for debug. First-line Anna tag: **`[Anna — Trading Analyst]`**. Missing context → clarification only (see **`context_requirements`**). Model/rules failure → **explicit limitation** text, not silent template filler. **Acceptance** requires live operator validation on Telegram (e.g. Sean loop); code in [`telegram_interface/response_formatter.py`](../scripts/runtime/telegram_interface/response_formatter.py).

**Phase 4.6.3.3 — Messaging interface abstraction (infrastructure leaf):** Decouple Anna from Telegram; introduce **`messaging_interface/`** (`base_interface`, `cli_adapter`, `telegram_adapter`). Anna is **not** aware of transport. **Normalized output** (non-negotiable): compare `interpretation.summary`, `answer_source`, intent, topic, `limitation_flag` (if present); adapters **format only**. **CLI** is the **primary validation surface**; phase **cannot close** without CLI validation (`echo "…" | python -m messaging_interface.cli_adapter`). **Slack** and **OpenClaw gateway** integration are **out of scope** for this directive. **Depends on** 4.6.3.1 (code closure). Canonical spec: [`docs/architect/directives/directive_4_6_3_3_messaging_interface.md`](architect/directives/directive_4_6_3_3_messaging_interface.md). **Status: closed** — evidence [`directives/directive_4_6_3_3_closure_evidence.md`](directives/directive_4_6_3_3_closure_evidence.md).

**Phase 4.6.3.4 — Messenger configuration + Slack adapter (directive):** Single-runtime **`config/messaging_config.json`** (shape in directive); **`backend`** selects exactly one of `slack` | `telegram` | `cli` at startup — **no** multi-fan-out. Implement **`messaging_interface/slack_adapter.py`** calling shared **`run_dispatch_pipeline`**; Slack **mrkdwn** / transport only after normalized output. **OpenClaw gateway** and **Discord** **out of scope**. CLI remains proof surface; Slack is operator surface. Example config (no secrets): [`config/messaging_config.example.json`](../config/messaging_config.example.json). Spec: [`directives/directive_4_6_3_4_slack_adapter_and_config.md`](directives/directive_4_6_3_4_slack_adapter_and_config.md).

**Phase 4.6.3.5 — Anna Data Grounding Layer (Directive 4.6.3.5.A, closed):** Added deterministic live-data question detection (`messaging_interface/live_data.py`), read-only market lookups (`data_clients/market_data.py`), and Anna-path integration in dispatch (`telegram_interface/agent_dispatcher.py`) with strict fallback text when verified live data is unavailable: **`I don’t have access to live market data for that request right now.`** Added containment on the Slack system path (`scripts/openclaw/slack_anna_ingress.py`, `slack_persona_enforcement.py`) so `hello` stays system-consistent and does not emit ungrounded market-like values. **Live proof (clawbot/OpenClaw/Slack #blackbox_lab):** price → fallback, spread → fallback, concept question → explanation, hello → `[BlackBox — System Agent] Hello — how can I help?`; no post-hello cascade.

**Phase 4.6.3.2 — Learning Core Extraction (`agent_learning_core`) — Part A accepted (containment scope only):** Part A is now canonically complete for containment: lifecycle baseline + enforced reuse gate (`candidate -> under_test -> validated|rejected`) with validated-only memory reuse and transition audit trail (`ea9c215`). **Completion meaning is limited:** this does **not** include full cross-agent runtime rollout or autonomous learning influence. **Other-agent expansion rule remains:** DATA expands first under tightly scoped twigs, Cody follows DATA, Mia and Billy remain planning stubs unless explicitly authorized.

**4.6.3.2 Part B — DATA infrastructure-intelligence sequencing (twigs):**

**Status alignment (mandatory):** A Part B twig or directive is not treated as closed or advanced unless **`docs/blackbox_master_plan.md`** and **`docs/architect/directives/directive_execution_log.md`** are updated in the **same change set** with **matching status granularity** (scope, completion level, safety boundaries).

- **DATA Twig 1 — Visibility (Complete):** DATA has read-only visibility into learning lifecycle state via inspection helpers; helpers are not in output-generation paths.
- **DATA Twig 2 — Execution-Aware Diagnostics (Complete):** DATA has execution-sensitive state awareness, infrastructure-action risk classification (`safe` / `controlled` / `blocked`), and defer/report decisions; diagnostics-only and non-remediating.
- **DATA Twig 3 — Structured Issue Detection + Suggestion Layer (Complete):** deterministic issue detection + structured issue objects + non-executable fix suggestions are available for diagnostic contexts only; recent-event window uses **`system_events.created_at`** ordering (not `id`); no remediation, no execution, and no DATA output-generation integration.
- **DATA Twig 4 — Remediation Validation Pipeline (Design Complete):** lifecycle and safety design for sandbox remediation validation; see `docs/architect/directives/directive_4_6_3_2_part_b_twig4_design.md`.
- **DATA Twig 4.1 — Sandbox Validation Engine (Complete):** isolated SQLite sandbox (`remediation_candidates`, `validation_runs`); deterministic `run_validation` with simulated before/after; no production DB path.
- **DATA Twig 4.2 — Remediation Candidate Ingestion + Registry Boundary (Complete):** controlled `ingest_remediation_candidate(...)`; lifecycle `candidate` only at ingest; duplicate guard; no auto-promotion.
- **DATA Twig 4.3 — Detection → Ingestion → Validation Integration (Complete):** manual `run_remediation_validation_pipeline` (sandbox only); traceability; stop on ingestion failure; no runtime/DATA wiring.
- **DATA Twig 4.4 — Validation Outcome Analysis Layer (Complete):** deterministic analysis of sandbox `validation_runs` into structured artifacts (`validation_outcome_analysis.py`); outcome categories (`validated_success`, `rejected_functional`, `rejected_regression`, `rejected_stability`, `insufficient_evidence`); evidence summaries derived from sandbox snapshots only (no LLM); persisted analyses are diagnostic retention only — **not** live approval, **not** execution triggers; optional trend listing per remediation; no DATA output integration; no production mutation.
- **DATA Twig 4.5 — Validated Remediation Pattern Registry Boundary (Complete):** sandbox tables `remediation_patterns` + `remediation_pattern_history`; `remediation_pattern_registry.py` registers patterns from Twig 4.4 analyses with traceability (`validation_run_id`, `remediation_id`, `outcome_analysis_id`); lifecycle `candidate_pattern` → `validated_pattern` (explicit promote only) or `rejected_pattern`; `validated_pattern` → `deprecated_pattern`; rejected outcomes terminal and never reusable; **`validated_pattern` means sandbox-validated knowledge only — not live approval, not executable instruction, not permission to act**; diagnostics/listing only; no DATA output; no execution; no production mutation.
- **DATA Twig 5 — Simulation-First Remediation Execution Layer (Complete):** `remediation_execution_simulator.py` simulates application of a pattern on synthetic inputs only; sandbox table `remediation_execution_simulations`; policy gate simulation (`approval_required`, `maintenance_window_required`, `execution_blocked_reason`, `would_allow_real_execution` always false in this phase); deterministic rollback flags; **simulation results are not permission to execute**; no production mutation; no DATA output integration; no imports from runtime execution or DATA response paths.
- **Operator Playground — Visibility Layer 1 (Complete):** [`scripts/runtime/playground/run_data_pipeline.py`](../scripts/runtime/playground/run_data_pipeline.py) orchestrates the seven DATA remediation stages against a user-supplied sandbox SQLite only; optional [`playground_ui.py`](../scripts/runtime/playground/playground_ui.py); **not** a runtime entrypoint; **not** execution permission; **not** DATA/messaging integration.
- **DATA Twig 6 — Approval model (Implementation complete; live execution not started):** Sandbox **`approvals`** persistence + lifecycle + [`approval_cli.py`](../scripts/runtime/approval_cli.py) per [`twig6_approval_model.md`](architect/design/twig6_approval_model.md); artifact field **`source_remediation_id`**; **no** execution hooks; **no** production mutation; **no** messaging integration. **Live** controlled remediation **execution** remains **stub** / not built.
- **DATA Twig 7 — Learning-Backed Ops Optimization (Stub):** future optimization from validated remediation outcomes; must remain infrastructure-scoped (not market strategy reasoning).

**Roadmap safety note:** DATA is an infrastructure intelligence / telemetry / diagnostic agent, not a market analyst or trading decision-maker. DATA is not permitted to perform disruptive infrastructure actions during active execution/trading state unless a future explicitly approved control framework authorizes it.

**Twig 4.x–5 safety boundary:** no live remediation execution; no DATA output-generation integration; no production system mutation; validation, ingestion, pipeline, outcome analysis, pattern registry, and execution **simulation** are sandbox-only unless explicitly scoped otherwise; analysis artifacts and patterns do not bypass lifecycle controls or imply operational approval; patterns are **not** executable instructions; **simulation artifacts are not permission to execute**.

**Closure (verified):** clawbot proof — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 4.6 — Telegram interaction layer* / *4.6.2* / *4.6.3*. **Note:** **4.6.3.1** is **code-tracked**; **operational closure** is when Telegram validation passes per directive.

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

> **Next active build phase (not implemented in tree at roadmap insert).** Enables the first real **Anna + Billy** trading path to execute trades **end-to-end** using **live market data** and **controlled execution** (Layers **1–4** unchanged above), while establishing the canonical **multi-participant** architecture that later supports additional humans and constrained bot participants. Detailed tasks: [`docs/architect/development_plan.md`](architect/development_plan.md).

> **Core Principle — Perpetual, Risk-Tiered Winning (Anna):** Anna is a perpetual, self-improving competitor whose “win” is **repeatable, risk-controlled PnL within an authorized risk tier**. Risk tier is set by operators (CEO/human), never by Anna; Anna adapts inside that tier, but cannot bypass hard limits (stale/divergence blocks, size/drawdown caps, approvals, kill switch). Strategies are promoted/demoted by rolling, risk-adjusted performance; execution remains separated (Billy) and policy-gated.

> **Review Flag — 2026-03-28:** Persona carry-forward rule requires explicit architect review. Anna’s core student persona must retain **capital preservation**, **RCS (Reflection Cycle Summary)**, and **RCA (Root Cause Analysis)** discipline across **Bachelor**, **Master**, and **PhD**. These behaviors are not tier-specific add-ons; they persist through the full college ladder and must remain part of her canonical operating psychology.
> **Self-development & Emergent Behavior:** Anna is expected to self-improve without human prompts: she can schedule backtests, parameter sweeps, and paper drills, and generate/retire strategies autonomously. Exploration is **bounded**: no raising risk limits, no bypassing approvals/guardrails, and no execution without policy gates. Emergent behaviors are acceptable only when they increase safe, repeatable wins.
> **Advanced methods (bleeding-edge, bounded by guardrails):** Fast EV gate with capped Kelly sizing; conformal prediction for calibrated uncertainty/abstain; distributional RL with CVaR objective (tail-aware); realistic LOB simulator for offline training; adversarial/hostile guard (fail closed on divergence/staleness/hostile book). “Skip” is a rewarded action when uncertainty or EV is poor.

### Purpose

Deliver the **data → strategy → approval → execution** spine in production shape: ingest, store, signal, bind to Layer **3** approval, execute via Layer **4** intent and **Billy** (edge execution), with risk controls and observability.

### Canonical plan layers (aligned with `development_plan.md`)

Normative three-layer model for Phase **5** (full table: [`docs/architect/development_plan.md`](architect/development_plan.md) — **Phase 5 — Canonical structure**):

- **Layer A — Engine spine (5.0–5.7 + first approved slice):** Data through **venue adapter** and observability; **exchange** connection. Advances on directives **without** requiring full **5.8** University implementation.
- **Layer B — Engine-native context (5.9):** Ledger, bundles, registry **`contextProfile`**; Anna as first consumer when directed.
- **Layer C — University platform (5.8):** Global training governance — Dean, **colleges** as domain silos (many colleges; one primary enrollment per student by default), Professor, Exam board, curriculum injection, **binary/scored** evidence of learning. **Same University-wide training methods** across colleges; college varies **domain** and **benchmarks**. Sequenced after **Pillars 2 and 3** per roadmap rule.

### Shared context service (engine-native; interim ledger; Gnosis future)

- **Engine-native:** **Context** is **core platform infrastructure**, not an Anna-only feature or a late add-on. Online agents should receive **agent-scoped views** of **engine-global** context **automatically**, per registry **`contextProfile`**, instead of one-off integrations.
- **Module home:** [`modules/context_ledger/`](../modules/context_ledger/) — interim append-only ledger and bundle contracts (`ContextRecord`, `ContextBundle`). See [`modules/context_ledger/README.md`](../modules/context_ledger/README.md).
- **Gnosis (external):** Possible future **context-as-a-service** provider — **not** a dependency for delivery until integrated. Implement **baked, contracted** context in BLACK BOX first; add a **Gnosis adapter** later that maps to the same contracts.
- **Consumers:** Core infra → **Anna** (first) → future agents → **University** → optional **Gnosis**. Gap analysis and open items: [`docs/architect/hydration_context_governance.md`](architect/hydration_context_governance.md) §10; tasks: [`development_plan.md`](architect/development_plan.md) §5.9.

### 5.0 Multi-participant + risk tier interaction model

- **Participants:** BLACK BOX must support multiple human participants (Sean plus future operators/users) and future bot participants. Anna is **not** a single-user analyst surface.
- **Identity model:** every interaction and every trade artifact must resolve **participant identity**, **participant type** (human / bot), **account / wallet context**, **selected risk tier**, and **interaction path**.
- **Wallet / account association:** each participant operates inside their own documented account / wallet context, aligned with the Phase **4.2** entity model. Shared or pooled accounts require explicit human governance and role mapping.
- **Risk tier ownership:** Anna does **not** assign or escalate risk tiers. A human selects the risk tier, and that choice defines the strategy space, behavioral boundaries, and allowable exposure.
- **Canonical tiers:** Tier **1** = low risk (conservative exposure, slower cadence, tighter constraints, capital preservation + consistent gain). Tier **2** = medium risk (moderate exposure, balanced cadence, controlled expansion, disciplined growth). Tier **3** = high risk (higher exposure, faster cadence, wider exploration inside bounds, aggressive but controlled edge extraction).
- **Shared psychology across tiers:** Anna remains relentless, learning, and competitive in every tier; only the amount of room she is allowed to operate in changes.
- **Shared discipline across tiers:** Anna also retains the same preservation and self-correction backbone in every tier: protect capital, perform lightweight reflection continuously, perform RCA on qualifying failures, and never drop those mechanisms as authority expands.
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
- **Current implementation status (2026-03-30):** Phases **5.3a** through **5.3e** are in-repo and architect-closed (strategy path + guardrailed experiment). **5.4 (first slice)** — **`CandidateTradeV1`** in `market_data/candidate_trade.py`: typed candidate with size/risk envelope/expiry and embedded **participant scope** for future Layer 3; **no** approval router or execution in this slice. **Next 5.4 work:** route candidates through **Layer 3** approval; **no** execution without **APPROVED** artifact.
- **Adaptive loop:** maintain a portfolio of strategies; score by risk-adjusted PnL, rule adherence, and consistency; promote/demote based on rolling windows. Exploration allowed within safety constraints; no strategy may bypass guardrails.
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
- **Consumes Layer 4 execution intent** (per [`layer_4_execution_interface_design.md`](architect/layer_4_execution_interface_design.md)).
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

### 5.8 University / learning system

- **Core engine rule:** University is part of the core engine, not a detached side project.
- **Ordering rule:** University work must **not** begin before **Pillars 2 and 3** are complete; it is a later engine workstream that comes after the higher-priority core-engine build steps.
- **Foundational context rule:** The interim structured memory/context ledger needed by University should be treated as foundational core-engine work for BLACK BOX, because student reasoning, Dean governance, and exam-board supervision all depend on reliable recall before a future external context service exists.
- **Interim module placement:** The first implementation home for that foundational memory surface should be `modules/context_ledger/` inside BLACK BOX, with a reusable contract that later University services and future external context providers can consume or replace.
- **Canonical platform standard:** [`docs/architect/blackbox_university.md`](architect/blackbox_university.md) defines the bot-agnostic University model for enrollment, curriculum, scored evaluation, promotion / rejection, and reward governance.
- **Anna-specific supplement:** [`docs/architect/anna_university_methodology.md`](architect/anna_university_methodology.md) defines Anna’s role as the first reference student, including context-bundle requirements, teacher-student methodology, curriculum discipline, and grounded evaluation design.
- **Persona carry-forward rule (review required, 2026-03-28):** University tier progression must preserve Anna’s core student discipline rather than replacing it. Capital preservation, RCS, and RCA remain mandatory through Bachelor, Master, and PhD; later tiers add latitude but do not delete those mechanisms.
- **University subtree:** the in-repo staging area for the future standalone multi-project University project lives under [`university/`](../university/README.md).
- **Dean model:** the Dean is the university-wide intake and governance agent. Humans submit curriculum to the Dean using a strict repeatable template, primarily via Slack in BLACK BOX. The Dean validates, routes to the correct college, hydrates the professor path, and coordinates sponsor-facing graduation and export decisions.
- **College model:** colleges are narrow-discipline boundaries. Each college has its own professor and exam board. Single-college enrollment is the default; dual enrollment is an explicit Dean-approved exception, not normal behavior.
- **Context rule:** University must implement a shared context-engineering layer across colleges. Basic chunk-only RAG is insufficient as the full strategy; University should combine structured retrieval, metadata filters, memory, typed context bundles, and benchmark/policy context.
- **Measurement rule:** “student got smarter” must remain binary and sponsor-aligned. Curriculum is only retained when exam-board evaluation shows measurable improvement against the college contract.
- **Core-engine work items:** Dean intake contract, curriculum schema, enrollment records, college/professor/exam-board contracts, context-bundle contracts, evaluation harnesses, binary promotion / rejection state machine, reward and graduation system, and Anna-on-University rollout.
- **Boundary:** University extends the engine’s intelligence loop, but it must not bypass approvals, execution controls, selected risk tiers, or human governance.
- **Canonical rule:** conversation and episodic context may inform learning, but structured curriculum / promoted knowledge artifacts remain the canonical semantic layer.

### First approved slice (paper-first, narrow scope)

> **Status:** Build path **approved** for first end-to-end loop (paper-first). **Scope is narrow:** one **SOL** strategy, **Pyth** feed, **Coinbase** adapter, single approved trade loop with stored outcome. No multi-asset, no ML, no scale-out in this slice.

- **Separation:** **Anna = strategy only** (signals; **no** execution). **Billy = execution only** (approved intents; **no** signal invention). **No** fused signal+execution in this path.
- **Perpetual winner discipline:** Anna’s objective combines PnL with strict penalties for stale/divergent data, guardrail breaches, hallucination/unsupported claims, and drawdown/size violations. Success is measured over rolling windows; advancement (size/frequency) is conditional on safe, repeatable wins; any breach forces demotion/pause.
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

> **FUTURE EXPANSION.** No implementation required at this stage. Core University work has been moved into the engine roadmap under **Phase 5.8**.

### Purpose

Enhance Anna’s **decision quality** using **evidence-based learning** (post–Phase 5 engine).

### Stub sections (not scheduled)

- **Confidence scoring** refinement.
- **Expected utility** / decision theory.
- **Bayesian updating**.
- **Outcome-based** pattern promotion / rejection.
- **Explainability** (“why this trade”).
- **Long-horizon intelligence extensions** beyond the core University engine work already listed in Phase 5.8.

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
