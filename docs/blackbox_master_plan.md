# BLACK BOX — MASTER PROJECT PLAN

## Overview

This document defines the full Phase 1 bootstrap for Cody (Code Bot) using OpenClaw.

---

## Core Philosophy

- Pattern recognition over prediction
- Structured learning
- Risk-controlled decisions
- No autonomous unsafe behavior

---

## Phase 1 Goal

Build Cody as an OpenClaw SKILL-driven engineering agent.

---

## Key Components

### Cody — Code Bot

**Role:**

- Software engineer agent
- System architect
- Planning and scaffolding

**NOT:**

- Trader
- Analyst
- Execution bot

---

## Directory Structure

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

## SKILL.md Core

- **name:** `cody_planner`
- **Purpose:** Plan system architecture, recommend build steps, guide development (see `agents/cody/skills/cody-planner/SKILL.md` in-repo).

---

## OpenClaw Integration

OpenClaw loads skills from `<workspace>/skills` (highest precedence), then `~/.openclaw/skills`, then bundled skills. The canonical copy in **git** lives at `agents/cody/skills/`.

**Make skills visible to the gateway** by one of:

- Copying `cody-planner` into `<workspace>/skills/` (symlinks that escape the workspace root may be **rejected** by OpenClaw), or  
- Setting `skills.load.extraDirs` in `~/.openclaw/openclaw.json` to an allowed path (see OpenClaw docs: *Skills*, *Creating Skills*).

**Verify:**

```bash
openclaw skills list
```

---

## Test Prompt

Use the Cody planner skill to recommend next steps for building BLACK BOX.

---

## Success Criteria

- Cody loads in OpenClaw
- Cody responds as engineering agent
- No trading behavior
- Structured outputs

---

## Phase 1.5 — Agent hardening (in progress)

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

## Phase 1.6 — Controlled execution (active)

**Goal:** Move from “agents on paper” to **agents doing controlled, real work** on clawbot: SQLite + DATA health logging + Cody structured plans — **no expansion** until validation.

**Canonical spec (architect):** [`docs/architect/phase_1_6_agent_activation.md`](architect/phase_1_6_agent_activation.md) — **first workloads / acceptance:** [`docs/architect/phase_1_6_next_steps_spec.md`](architect/phase_1_6_next_steps_spec.md)

**Architect concurrence:** Cody + DATA implementation **approved**; audit [`docs/architect/agent_verification.md`](architect/agent_verification.md). **Workspace sync** is a **hard operational requirement** — [`docs/architect/workspace_sync.md`](architect/workspace_sync.md).

**SQLite:** Apply Phase 1.5 + 1.6 — [`scripts/init_phase1_6_sqlite.sh`](scripts/init_phase1_6_sqlite.sh) (includes `system_health_logs`, `alerts`, `agent_tasks` view). **Bridge schema** (not final DDL) — [`docs/architect/architect_sqlite_deviation_response.md`](architect/architect_sqlite_deviation_response.md).

**Constraints:** No new agents; no vault/secrets integration in this phase; no broad tool expansion; no autonomous execution beyond scope — per spec.

---

## Phase 2+ — Decision Layer (Analyst Model) [STUB]

> **STUB — not implemented.** No Analyst agent code, no runtime wiring, no new tools in this phase. Recorded for roadmap and context rehydration. Keywords for search: **decision layer**, **analyst model**, **expected utility**, **bayesian update**, **learning system**.

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

### Initial frameworks (Phase 2 targets)

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

**Alignment:** Roster “Anna — Analyst” ([`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md)) is the **persona** this layer eventually supports; this stub does **not** implement Anna.

**Superseded in roadmap detail by:** [Phase 3 — Intelligence Layer](#phase-3--intelligence-layer) below (Anna, ingestion, validation loop, concept registry, optional strategy awareness).

---

## Meet the Team

Roster — **software agents** vs **human roles** — status as of planning docs (see [`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md) for the canonical table).

| Name | Type | Role | Status |
|------|------|------|--------|
| **Cody** | Agent | Software engineer — builds the system and agents | In progress |
| **DATA** | Agent | System & data guardian — health, integrity, monitoring | In progress |
| **Mia** | Agent | Market info — real-time market data (**read-only**) | Active |
| **Anna** | Agent | Analyst — trade signals and confidence | In progress |
| **Billy** | Agent | TBot executor — executes trades and manages positions | In development |
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

> **Mostly planning in this document.** Phase 3 is where **intelligence** (interpretation, conversation, validation, and **read-only** market context) layers on top of the **Phase 2** paper pipeline. **Exceptions:** [Phase 3.1](#phase-31--market-data-ingestion-read-only) — **`market_data_ingestor.py`** (read-only snapshots); [Phase 3.2](#phase-32--anna-conversational-analyst-layer) — **`anna_analyst_v1.py`** (CLI rule-based **`anna_analysis_v1`**, no Telegram). **No** registry loader, **no** Phase 4 execution paths, **no** venue writes beyond these scoped scripts until implemented per architect.

**What Phase 3 is not:** live trading; wallet integration; exchange execution; unrestricted LLM behavior.

**What Phase 3 is:** market visibility; **Anna** as the analyst intelligence layer; **concept registry** and retrieval; expert interaction with Sean; **validation** and concept promotion; **extensible reasoning modules**.

**No exchange trading, no wallet keys, and no live execution** are implied by this section until [Phase 4](#phase-4--real-trading-integration-prerequisites) gates are met.

**Keywords for search:** Phase 3, Anna, intelligence layer, Telegram, validation loop, market data ingestion, Solana, read-only, trading concept registry, intelligence extensibility, concept retrieval, modular reasoning, concept formation pipeline.

**Upstream (Phase 2) — safe simulation:** The intelligence layer must align with trade episodes (`trade_episode_aggregator.py`), system insight (`insight_generator.py`), system trend (`insight_trend_tracker.py`), guardrail policy (`guardrail_policy_evaluator.py`), policy-gated action (`policy_gated_action_filter.py`) — all **paper-only** today (episodes, insights, trends, policy / guardrails).

**Downstream (Phase 4) — real trading prerequisites:** [Phase 4 — Real Trading Integration Prerequisites](#phase-4--real-trading-integration-prerequisites) — wallet, custody, access, approval, governance — before any real venue execution.

**Placement:** Phase 3 sits between **safe simulation** (Phase 2) and **real-world trading integration** (Phase 4).

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

- **Script:** `scripts/runtime/anna_analyst_v1.py` — **`anna_analysis_v1`** JSON: interpretation, **`market_context`** (optional latest **`[Market Snapshot]`**), **`risk_assessment`**, **`policy_alignment`** (optional latest **`[Guardrail Policy]`**), paper-only **`suggested_action`**, **`concepts_used`** (keyword tags; not registry-backed yet). Flags: **`--use-latest-market-snapshot`**, **`--use-latest-decision-context`**, **`--use-latest-trend`**, **`--use-latest-policy`**, **`--store`** → **`[Anna Analysis]`**. Rule-based; **no** Telegram, **no** registry loader, **no** execution.

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

- **Package:** `scripts/runtime/anna_modules/` — layered **input_adapter**, **interpretation**, **risk**, **policy**, **analysis** (compose `anna_analysis_v1`), **proposal** (`anna_proposal_v1`). CLI remains **`anna_analyst_v1.py`** / **`anna_proposal_builder.py`**. See [`scripts/runtime/README.md`](../scripts/runtime/README.md) — *Anna modular runtime — Phase 3.4*.

**Closure (verified):** refactor + clawbot compatibility **2026-03-23** — see [`docs/architect/agent_verification.md`](architect/agent_verification.md) → *Phase 3.4 — Anna modular extensibility (skeleton)*.

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

---

## Phase 4 — Real Trading Integration Prerequisites

> **Planning-only.** Phase 4 is the first phase where the system may be **prepared** to touch a **real trading venue**. This section codifies prerequisites so future context rehydration does not lose governance, custody, or safety boundaries. **Nothing in this section implies live trading is enabled by default.**

**Keywords for search:** Phase 4, real trading, venue, wallet, custody, go-live, governance, signing, policy gate.

**Related:** executor / trading architecture discussion — [`docs/architect/architect_update_trading_system.md`](architect/architect_update_trading_system.md); roster — [`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md); runtime guardrail — `scripts/runtime/guardrail_policy_evaluator.py` (paper-only pipeline today).

### 1. Ownership and Governance

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

### 2. Wallet / Custody Prerequisites

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

### 3. Platform / Venue Prerequisites

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

### 4. Signing / Execution Control Model

A **controlled execution model** is required:

- **Authorization:** Orders or transactions must be **authorized** by a defined path (human approval first).  
- **Initial assumption:** **Human approval** before every real execution **until** a stricter automated policy is validated and approved.  
- **Later:** **Controlled automated approval** only after **validation**, audits, and rollback drills — not a default.  
- **Auditable path:** Every real execution must be **traceable** (who/what approved, what was signed, when).

**Explicit statements:**

- **No silent execution** — no background signing without policy visibility.  
- **No uncontrolled signing** — no ad hoc scripts with keys.  
- **No direct production execution** without passing the **policy gate** (e.g. guardrail / governance layer — see Phase 2.11–2.12 runtime and future enforcement).

### 5. Environment / Secrets / Access Controls

- **Secret storage policy:** Secrets live in **approved vaults** or host-managed secret stores — **not** in the repo.  
- **Direction:** Integrate with a **vault / secret-manager** pattern approved by technical leadership.  
- **Access classes by role:** Separate **data** access, **planning** access, and **execution** access; least privilege.  
- **No secrets in repo**; **no secrets in chat**; **no ad hoc copying** of credentials into scripts.

### 6. Safety Gates Before Live Integration

Phase 4 **must not** begin real execution until **all** of the following are true:

1. **Phase 2** paper-only pipeline is **complete and stable** (lifecycle → insight → trend → guardrail as implemented).  
2. **Phase 3** intelligence / data phase is **complete enough** per architect (not defined here in detail).  
3. **Guardrail policy** exists and is **enforceable** in downstream workflows (see `policy_gated_action_filter.py` and policy storage).  
4. **Wallet / access governance** is **documented** (this section + approvals).  
5. **Approval model** is **documented** and followed.  
6. **Test capital policy** is **documented** (how much, which account, kill switch).  
7. **Rollback / disable path** is **documented** (how to turn off venue access without code panic).

### 7. Explicit Non-Goals

Phase 4 **does not** automatically mean:

- **Immediate autonomous trading**  
- **Unrestricted exchange access**  
- **Direct hot-wallet free-for-all**  
- **Bypassing policy** because the system “looks ready”

---

## Final Rule

If unclear: **STOP → LOOK UP DOCS → THEN IMPLEMENT**
