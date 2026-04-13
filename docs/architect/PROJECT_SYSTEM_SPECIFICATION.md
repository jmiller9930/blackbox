# BLACK BOX — Project System Specification

## Preface — snapshot, drift, and how to read this repo

**As of 2026-04:** The platform has **grown in layers** (early “Layer 1–4” sandbox stack, Anna messaging, learning/execution scripts, lab **Docker** operator UI, Slack/OpenClaw bridges, training bundles). **No single file** was written on day one as the eternal wiring diagram; **several documents** capture overlapping truths from different eras. When they disagree on a detail, treat **`docs/blackbox_master_plan.md`** as the **roadmap / implemented-status** tie-breaker for phases, and treat **this specification** plus **runtime paths you can run** (`scripts/runtime/…`, `UIUX.Web/…`, `modules/…`) as **evidence of what is actually in the tree**.

If you need **one sentence:** BLACK BOX is a **governance-heavy trading intelligence codebase** with **multiple operator surfaces** (legacy read-only sandbox dashboard, lab **UIUX.Web** API + dashboard, Telegram/Slack messaging), **not** a single shrink-wrapped “product install” with one installer.

---

## Purpose

This document gives a high-level, architect-turnover view of what BLACK BOX is, what it is not, and what is currently implemented.

It is intended to prevent role/mission confusion during handoff.

---

## Where the “whole system” is documented (stitch map)

Use this table to find **which doc answers which question**. Everything below is **in-repo**; paths are relative to the repository root.

| Question | Start here | Notes |
|----------|----------------|-------|
| **Roadmap, phase status, what is “closed” vs next** | [`../blackbox_master_plan.md`](../blackbox_master_plan.md) | Single source of truth for **phase narrative**; keep aligned with reality. |
| **Task spine / engineering checklist (large)** | [`development_plan.md`](development_plan.md) | Deep slice plans; not a substitute for master plan status. |
| **Operational “what can I run today” (sandbox / layers lens)** | [`../blackbox_system_usage_current.md`](../blackbox_system_usage_current.md) | Emphasizes **Playground, legacy operator dashboard, approval** paths; **distinct** from lab **UIUX.Web** dashboard (see master plan). |
| **Lab operator web (Anna training / bundle / trade chain)** | [`../blackbox_master_plan.md`](../blackbox_master_plan.md) (search *Operator web dashboard*), [`development_plan.md`](development_plan.md) (Pillar 1), code under **`UIUX.Web/`** + **`modules/anna_training/`** | Typically deployed via **`UIUX.Web/docker-compose.yml`** on **clawbot** per project workflow docs; **not** the same as `scripts/runtime/operator_dashboard/`. |
| **Messaging ingress (Telegram / Slack), routing, grounding** | This spec (sections below), [`global_clawbot_proof_standard.md`](global_clawbot_proof_standard.md), [`../runtime/execution_context.md`](../runtime/execution_context.md) | Proof often requires **clawbot** host, not only a Mac clone. |
| **Slack → OpenClaw conversational operator (program)** | [`slack_conversational_operator/canonical_development_plan.md`](slack_conversational_operator/canonical_development_plan.md) + LDD in the same folder | Future/concurrent slice; **not** all of BBX is implied by Anna messaging closure alone. |
| **Local Mac vs clawbot vs Git** | [`local_remote_development_workflow.md`](local_remote_development_workflow.md) | Avoids “SSH works therefore I edited the server” confusion. |
| **Directive contracts and closure** | [`directives/README.md`](directives/README.md), [`directives/directive_execution_log.md`](directives/directive_execution_log.md) | Work packages and evidence trail. |

**Installed / runtime reality (high level):**

- **Repository:** Python package layout, **`scripts/runtime/`** CLIs, **`modules/`** libraries, tests under **`tests/`**.
- **Primary lab host for mandated proofs:** **`clawbot.a51.corp`**, canonical tree **`~/blackbox`** — see **`execution_context`** and proof standard.
- **Sandbox read-only dashboard (older stack):** `scripts/runtime/operator_dashboard/` — local WSGI, sandbox DB.
- **Lab operator stack (Docker):** `UIUX.Web/` — **`api_server.py`**, **`dashboard.html`**, nginx image; **rebuild/restart** rules apply when operator-visible assets change.
- **Messaging:** Telegram and Slack paths per master plan and messaging modules; OpenClaw bridge where bridged — not identical to the BBX conversational operator program doc (different scope envelope).

---

## System Definition

BLACK BOX is a **trading-focused intelligence system** being built in phased increments.

It is designed to:
- interpret market/trading questions,
- produce structured, policy-aware reasoning,
- support learning workflows and operator visibility,
- and mature toward a system that can learn through validated action loops.

It is **not** currently a fully autonomous live trading execution system.

---

## Product Intent (North Star)

Build an intelligent trading assistant platform that:
- reasons in market context,
- uses verified data where required,
- learns from outcomes through explicit validation paths,
- remains auditable and governance-constrained.

Long-term intent includes intelligence that improves through action feedback, but only within controlled, human-governed phase boundaries.

**Project governance declaration:** BLACK BOX treats **agent training**—especially developing **Anna** as a **strategist** and **analyst**—as **core product intent**, not an optional experiment. Execution authority, risk-tier selection, and live venue access remain **human-governed** and **directive-governed**. Canonical wording and boundaries: [`development_governance.md`](development_governance.md) — *Project declaration — agent training (analyst and strategist)*.

---

## What The System Is Today (Implemented)

### 1) Multi-surface agent interaction layer
- Telegram and Slack-facing interaction paths are implemented through shared dispatch abstractions.
- Persona ownership is enforced (`Anna`, `DATA`, `Cody`, system path).
- Routing and message formatting are deterministic where required by directives.

### 2) Anna analyst runtime
- Anna path is implemented and callable through the messaging interface.
- Anna supports structured analysis output and concept explanation behavior.
- Current live-data grounding v1 is implemented with strict no-data fallback behavior.

### 3) Live data grounding v1 (4.6.3.5.A closure state)
- Deterministic live-data question detection.
- Read-only market-data client integration.
- Explicit fallback when verified live data is unavailable:
  - `I don’t have access to live market data for that request right now.`
- Containment added to prevent ungrounded market-like output leakage on system greeting paths.

### 4) Observability and proof-driven workflow
- Directive execution and closure evidence are tracked in architect directive docs and execution logs.
- Phase/directive closure is evidence-based, with clawbot host verification requirements where mandated.

---

## What The System Is Not (Current Constraints)

As of current implementation state, BLACK BOX is **not**:
- a live autonomous order execution engine,
- a self-modifying autonomous planner,
- a system that can invent market truth without verified sources,
- a system allowed to bypass persona/routing governance.

Trading intent is central, but execution autonomy remains gated by phase governance and explicit proof standards.

---

## Core Runtime Topology (Current)

### Primary architectural path (messaging)
- Inbound message
- Route classification (agent/system ownership)
- Shared dispatch pipeline
- Persona-safe formatting
- Slack/Telegram transport output

### Slack/OpenClaw bridge (current operational reality)
- OpenClaw Slack extension is bridged to BLACK BOX ingress scripts for directive-governed behavior.
- Route-aware outbound enforcement applies final persona and containment rules before send.

### Host and proof reality
- Primary verification host: `clawbot.a51.corp` (`~/blackbox`) for required live/runtime proofs.
- Local tests provide confidence; required closure may still depend on clawbot and live channel evidence.

---

## Data, Learning, and Validation Position

### Implemented now
- Structured analysis and message-path behavior with explicit constraints.
- Outcome/reporting visibility components from prior phases.

### Not fully implemented yet
- Full learning-core extraction and generalized lifecycle engine (`4.6.3.2`) is planned/activating next.
- Broad autonomous promotion/validation workflows are not yet the active production contract.

---

## Canonical Governance Sources

For authoritative interpretation, use:
- `docs/architect/development_governance.md` (workflow + **project declaration** on agent training)
- `docs/architect/blackbox_university.md` (University platform standard; **Karpathy-aligned** autonomous research + curriculum + live data ingestion for **all** enrolled agents)
- `docs/blackbox_master_plan.md` (canonical roadmap + implemented status)
- `docs/runtime/execution_context.md` (runtime/proof context)
- `docs/architect/global_clawbot_proof_standard.md` (closure proof standard)
- `docs/architect/directives/README.md` (directive registry/status)
- `docs/architect/directives/directive_execution_log.md` (running execution history)
- `AGENTS.md` (role boundaries and exclusions)

---

## Current Phase Position (At Time of This Spec)

- 4.6.3.3: closed (messaging abstraction)
- 4.6.3.4.C: closed (Slack Anna activation path)
- 4.6.3.5.A: closed (live grounding v1 + identity containment on hello path)
- Next architect-directed work: 4.6.3.2 learning core (real implementation kickoff)

---

## One-Sentence Summary

BLACK BOX is a trading-domain intelligence system under phased governance: already strong on routed analyst interaction and grounded-response containment, and now transitioning into deeper learning-core implementation rather than uncontrolled autonomous trading behavior.
