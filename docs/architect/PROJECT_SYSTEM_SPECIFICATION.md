# BLACK BOX — Project System Specification

## Purpose

This document gives a high-level, architect-turnover view of what BLACK BOX is, what it is not, and what is currently implemented.

It is intended to prevent role/mission confusion during handoff.

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
