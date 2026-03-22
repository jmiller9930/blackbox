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

**Superseded in roadmap detail by:** [Phase 3 — Intelligence Layer (Codified)](#phase-3--intelligence-layer-codified) below (Anna, ingestion, validation loop, optional strategy awareness).

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

## Phase 3 — Intelligence Layer (Codified)

> **Planning-only for this document.** Phase 3 is where **intelligence** (interpretation, conversation, validation, and—when built—**read-only** market context) layers on top of the **Phase 2** paper pipeline. **No exchange trading, no wallet keys, and no live execution** are implied by this section until [Phase 4](#phase-4--real-trading-integration-prerequisites) gates are met.

**Keywords for search:** Phase 3, Anna, intelligence layer, Telegram, validation loop, market data ingestion, Solana, read-only, trading concept registry, intelligence extensibility.

**Upstream (Phase 2) evidence the intelligence layer must align with:** trade episodes (`trade_episode_aggregator.py`), system insight (`insight_generator.py`), system trend (`insight_trend_tracker.py`), guardrail policy (`guardrail_policy_evaluator.py`), policy-gated action (`policy_gated_action_filter.py`) — all **paper-only** today.

**Downstream:** [Phase 4 — Real Trading Integration Prerequisites](#phase-4--real-trading-integration-prerequisites) (wallet, custody, signing, governance) applies before any real venue execution.

**Roster alignment:** Anna (analyst), Sean (human expert), DATA/Mia — see [`docs/architect/TEAM_ROSTER.md`](architect/TEAM_ROSTER.md).

### Phase 3A — Market Data Ingestion (READ ONLY)

- The system **ingests live market data** relevant to the **Solana ecosystem** (exact feeds and venues are implementation choices; not locked here).
- Ingestion includes, as applicable: **price**, **volume**, **spreads**, **liquidity context**, normalized into a **structured internal format** for analysts and downstream logic.
- **DATA** monitors **feed health** (staleness, gaps, source failures) alongside existing health duties.

**Explicit:**

- **No trading** from ingestion alone.  
- **Read-only ingestion** — no orders, no signed transactions, no venue keys in application code paths for this phase’s ingestion scope.

### Phase 3B — Conversational Analyst (Anna)

Anna is defined as:

> A **domain-aware analyst** that can communicate with **human traders (Sean)** and **translate trading concepts into system logic** — without becoming an execution path by itself.

**Responsibilities:**

- Understand trader language (**liquidity**, **spreads**, **slippage**, **order flow**, etc.).
- **Translate** into **structured system signals** compatible with existing pipelines.
- **Align** with **system state** (e.g. trends, **guardrail policy**, paper outcomes).
- **Propose** adjustments or strategies as **recommendations**, not autonomous trades.
- **Push back** when input is weak, ambiguous, or unsupported by evidence.

**Interaction model:**

- **Sean** communicates via **Telegram** (primary human channel for this design).
- Anna responds in **trader-accessible language**.
- Anna produces **structured outputs for the system** — **not** direct execution (execution remains gated by policy and Phase 4).

**Required conversational capabilities:**

- Agree / disagree / question  
- Request evidence  
- Suggest alternatives  
- Explain reasoning clearly  

### Phase 3C — Validation & Learning Loop

Codified loop:

**human input → analyst interpretation → system proposal → controlled evaluation (paper system) → outcome → reflection (why) → retain or reject**

**Rules:**

- **No idea becomes system behavior** without **validation** on the paper path (or equivalent controlled evaluation).
- **Success must be repeatable** under documented conditions.
- **Failure must be explained** (what broke, what to change).
- **Reasoning must be stored** alongside outcomes where the architecture persists artifacts (SQLite tasks, episode/insight records).

**Philosophy:** **trust → test → validate → adopt or reject** — not “ship intuition.”

### Phase 3D — Strategy Interaction Layer (Optional / Advanced)

The system may **support discussion** of advanced strategy concepts with expert users **without implementing execution** for those concepts in Phase 3.

#### Market making / maker concepts (awareness only)

Anna may **acknowledge** concepts such as:

- Providing liquidity  
- Spread capture  
- Bid/ask positioning  
- Influencing microstructure **when size permits** (theoretically — not assumed)

**Important constraints:**

- **Not implemented** as trading behavior in Phase 3.  
- **No manipulation** or artificial market movement as a goal.  
- **No assumption** of sufficient capital or market dominance.  
- Treated as **theoretical or exploratory** input unless promoted through validation.

**Purpose:** Let Anna **understand and reason** about these topics and support **structured discussion** — **not** to implement execution behavior here.

### Phase 3E — Trading Concept Registry & Intelligence Extensibility

> **Planning-only in this document.** The **registry file** in-repo is the **canonical shape** for concepts; **no registry loader** or Anna runtime wiring is implied until implemented in a later phase.

#### 1. Trading Concept Registry (source of truth)

- **Location:** [`data/concepts/registry.json`](../../data/concepts/registry.json) (JSON; version-controlled in **Git**).
- **Mutation rule:** No **runtime** mutation without **validation** and human/process approval; changes land via **PR / review**, not ad hoc edits in production.

Each concept entry **should** include:

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
| `status` | `draft` \| `validated` \| `deprecated` |
| `version` | Monotonic or semver per concept |

**Explicit rule:** The **registry is canonical memory** — **not** the LLM. Models may assist drafting; **registry + review** is authoritative.

#### 2. Anna extensibility model

Anna is a **modular reasoning system**, not a single growing prompt:

| Component | Role |
|-----------|------|
| **Input adapters** | Telegram, system context, market/health data |
| **Concept interpreter** | Maps natural language → **registry** concepts |
| **Reasoning modules** | Risk, liquidity, execution *logic* (policy-aligned, paper-first) |
| **Output adapters** | Human-readable + **structured** system payloads |

**Explicit rule:** Intelligence **grows by adding modules**, **not** by enlarging one monolithic prompt.

#### 3. Runtime concept retrieval (pattern)

When implemented:

1. **Detect** concepts in user/system input (IDs or language matches).  
2. **Fetch** matching **registry entries** only (partial load).  
3. **Inject** those entries into Anna context at runtime.  
4. **Do not** load the entire registry into every turn.

**Explicit rules:**

- Prefer **registry-backed** reasoning over assumed model memory.  
- **Unknown** term → treat as **draft** / flag for registry update, not silent invention.

#### 4. Structured concept usage

Anna outputs (when persisted) should support:

- `concepts_used`: `[concept_id, …]`  
- **Reasoning** tied to **registry fields** (which signals, which failure modes considered).  
- Clear **concept → system impact** mapping (decision vs execution posture).

**Purpose:** **Auditability**, **traceability**, **learning-loop** compatibility (Phase 3C).

#### 5. Validation loop integration

Concept lifecycle:

**proposal → test → outcome → reflection → validation → registry update**

**Explicit rules:**

- Concepts are **not trusted** for production semantics until **`validated`**.  
- **Sean** may **propose** concepts; **Anna** must **challenge or refine**.  
- **System** confirms through **outcomes** (paper path first).

#### 6. Hybrid intelligence model

| Layer | Role |
|--------|------|
| **Registry** | Stable, reviewed **knowledge** |
| **Anna** | **Reasoning** over registry + live context |
| **LLM** | **Assistive** drafting/expansion only |

**Explicit rule:** An LLM may **propose** definitions; the **registry** (after review) is **final authority**.

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
