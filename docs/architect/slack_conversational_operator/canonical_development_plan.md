# Canonical Development Plan — Slack → OpenClaw / BlackBox Conversational Operator

**Status:** Canonical (governance + engineering handoff)  
**Project:** Slack → OpenClaw / BlackBox Conversational Operator System  
**Scope:** Foundational operator interface, grounded trading answers, extensible routing  
**Constraint:** **V2 trading policy behavior remains untouched** unless separately authorized.

**Companion LDD:** [`slack_conversational_operator_system_ldd.md`](slack_conversational_operator_system_ldd.md)  
**Related:** [`../development_plan.md`](../development_plan.md) (Phase 5+ spine), [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md) (master plan).

**Governance alignment:** This document is the **canonical narrative** for phases, operator accept/reject tests, and proof bars. **Per-phase closure** (documentation sync, git proof, execution log, architect handoff) follows the **standard directive form**: one file per slice under [`../directives/`](../directives/) — `directive_bbx_slack_001_governance_lock.md` through `directive_bbx_slack_009_deferred_scope_fence.md` — aligned with [`../directives/DIRECTIVE_TEMPLATE.md`](../directives/DIRECTIVE_TEMPLATE.md) and indexed in [`../directives/README.md`](../directives/README.md). The plan below remains authoritative for **what** each phase means; the directive file is the **contracted closure vehicle** for **when** that slice is officially opened or closed.

---

## Plan intent

We are building a **Slack-native conversational operator interface** for BlackBox. The user should be able to speak naturally. The backend should interpret intent, ask clarifying questions when needed, route to grounded tools and APIs, and return auditable answers. Named agents may exist, but they are **optional routing overlays**, not separate truth systems.

This plan is **not** one giant build. It is a **sequence of directives**. Each directive must produce **implementation plus proof**. Each directive is subject to **operator validation** and explicit **accept or reject**.

**Implementation posture (architect):** This program is **not** a greenfield Slack stack. OpenClaw and existing bridges are **already live**; BBX-SLACK is **interception and grounding** — insert the operator router and tool layer into the **current** path. **Inventory the live route map** on clawbot, then change behavior with explicit **preserved vs narrowed** proof. See companion LDD [`slack_conversational_operator_system_ldd.md`](slack_conversational_operator_system_ldd.md) **§0.5** (posture), **§24** (inventory, interception, cutover, architect questions), and **§25** (**readiness gate — no BBX-SLACK-002 implementation start** until the **§25.3** governance return package is complete and accepted).

---

## Phase 0 — Governance lock

### Directive BBX-SLACK-001

**Objective:** Lock the architectural contract before implementation begins.

**Required outcome:** Engineering records and works against the following fixed model:

- Slack is the communication surface.
- OpenClaw / BlackBox is the default interpreter and router.
- Specialists are hidden implementation modules.
- Context assists interpretation and continuity, but does not replace truth sources.
- All factual answers must come from grounded tools and APIs.
- Named agents are optional routing hints only.
- V2 remains untouched by this workstream.

**Proof required:** A committed canonical plan section or LDD section that states the above without ambiguity and includes the MVP scope boundary.

**Operator test:** Read the committed text and confirm it matches the intended model.

**Accept if:** The contract is explicit, bounded, and does not blur default path versus named-agent overlays.

**Reject if:** It still leaves room for parallel truth systems or requires users to learn commands up front.

---

## Phase 1 — End-to-end transport path

### Directive BBX-SLACK-002

**Objective:** Create the actual Slack → OpenClaw → operator router path as the **single default ingress**.

**Required outcome:** A Slack message reaches the backend, passes through OpenClaw, enters **one** operator router package, and returns a response to Slack through the same path.

This directive is **transport only**. No rich domain intelligence yet. It proves the path exists and is stable.

**Required behavior:**

- Slack ingress is the primary surface.
- OpenClaw dispatch is the primary bridge.
- Bolt or any alternate ingress remains secondary and **converges** on the same operator router path.
- The system returns a simple grounded acknowledgment or health response.

**Proof required:**

- A live Slack thread showing a message sent and a response returned through the new path.
- A trace ID logged across the request.
- Proof that OpenClaw dispatch passed the expected context payload into the Python side.

**Operator test:** Send a simple Slack message and verify the reply returns through the intended path.

**Accept if:** The message reliably traverses the path and the trace is auditable.

**Reject if:** There are split paths, hidden fallbacks, or the OpenClaw hop is still ambiguous.

---

## Phase 2 — Intent and clarification loop

### Directive BBX-SLACK-003

**Objective:** Add lightweight intent extraction and targeted clarification behavior.

**Required outcome:** The system can take ordinary operator questions, infer the likely domain, and either answer or ask **one short** clarifying question when ambiguity blocks safe routing.

**Required behavior:**

- No rigid user command vocabulary required.
- Internal intents exist for routing and testing only.
- Clarification is used to **avoid guessing**, not as a default interrogation pattern.
- Defaults are applied where safe and documented.

**Example success cases:** “show me the last 15 trades”; “why did that trade fire”; “is V3 synced”; “what policy opened this position”.

**Proof required:** At least three Slack examples: (1) direct answer without clarification, (2) answer after a single clarifying question, (3) answer after resolving a reference from prior thread context. Each example must log: intent, resolved slots, tools planned or called, trace ID.

**Operator test:** Use ordinary, messy phrasing and verify the system either resolves it or asks a sane narrowing question.

**Accept if:** The system brackets user intent without requiring syntax memorization.

**Reject if:** It guesses unsafely, over-questions, or still behaves like a command bot.

---

## Phase 3 — Grounded tool layer

### Directive BBX-SLACK-004

**Objective:** Wire the operator router to a **shared, explicit tool layer** for factual answers.

**Required outcome:** All factual answers about trades, PnL, policy, ingest, wallet, and dashboard state come from **named backend tools or APIs**, not from free-form model reasoning.

**Minimum domains for MVP (trades / PnL; policy explanation; ingest / sync health; wallet / bankroll; dashboard / tile explanation)**.

**Required behavior:**

- Every answer must be traceable to a tool call or API source.
- No persona gets a different truth source.
- The default path and named-agent path must use the **same** tools.

**Proof required:** For each MVP domain: the intent, the tool invoked, the source of truth used, the returned answer in Slack, and the trace/log record.

**Operator test:** Ask one question in each domain and confirm the answer is grounded and consistent.

**Accept if:** The same question asked through default path and named invoke returns the same underlying facts.

**Reject if:** Any path bypasses the tool layer or produces conflicting facts.

---

## Phase 4 — Context integration

### Directive BBX-SLACK-005

**Objective:** Use context to improve interpretation **without** turning it into a shadow truth source.

**Required outcome:** The system can carry forward thread-local meaning and recent context so references like “that trade” or “the last one” are resolved correctly.

**Required behavior:**

- Conversation context is used for reference resolution and slot carryforward.
- Context engine status may inform system-health questions.
- Context **never** substitutes for ledger, policy, wallet, or bundle truth.

**Scope:** Thread memory; recent-turn context; basic recent-event awareness; context-engine status only where relevant.

**Proof required:** Slack examples showing: (1) a follow-up that depends on prior thread context, (2) a system-health question that surfaces context-engine status appropriately, (3) a factual trading question that still uses tool truth rather than context memory.

**Operator test:** Hold a short thread conversation and verify continuity works.

**Accept if:** Context clearly improves interpretation but never invents trading facts.

**Reject if:** Context starts acting like a second database.

---

## Phase 5 — Named-agent overlays

### Directive BBX-SLACK-006

**Objective:** Support named agents as optional routing and presentation overlays **without** introducing separate truth systems.

**Required outcome:** The user may say “Anna,” or another allowed name, but that only changes routing preference and response style. It does not change the underlying data contract.

**Required behavior:**

- Named invoke remains optional.
- Default path remains primary.
- Named-agent answers still use the same tool layer.
- Persona affects framing, not truth.

**Proof required:** A paired test: same question through default path; same question through named invoke; proof that the same tools and sources were used; visible difference only in style or framing if desired.

**Operator test:** Ask one question both ways and compare results.

**Accept if:** Facts are identical and only routing or tone differs.

**Reject if:** Named agents become separate informal Q&A systems.

---

## Phase 6 — Auditability and operator proof

### Directive BBX-SLACK-007

**Objective:** Make every turn inspectable and testable.

**Required outcome:** Each handled message produces an auditable record with traceability from Slack turn → routing decision → tool calls → source references.

**Required behavior:** Every routed answer logs: trace ID, intent, resolved slots, tools used, source references, and any clarification path taken. Where suitable, operator-visible proof surfaces can be shown in a compact debug mode or support artifact.

**Proof required:** A sample audit bundle for several turns showing the full path end-to-end.

**Operator test:** Take one surprising or disputed answer and trace exactly how it was produced.

**Accept if:** You can reconstruct the answer path without guesswork.

**Reject if:** The backend remains a black box once the answer is returned.

---

## Phase 7 — MVP stabilization

### Directive BBX-SLACK-008

**Objective:** Harden the Phase 1–6 path before optional expansion.

**Required outcome:** The operator system is stable enough to use for common questions in Slack without falling apart under routine ambiguity.

**Required behavior:** Rate limiting; basic allowlist / safety boundaries; graceful error handling; clear “I cannot answer that yet” when source data is unavailable; no silent failures.

**Proof required:** Smoke test script, clawbot runtime test, and live Slack test with expected pass criteria.

**Operator test:** Run the standard verification ladder and confirm stable behavior.

**Accept if:** The MVP is operational, bounded, and predictable.

**Reject if:** It still depends on manual heroics or hidden assumptions.

---

## Deferred work — not in MVP

### Directive BBX-SLACK-009

**Objective:** Explicitly defer nonessential expansion so MVP is not overloaded.

**Deferred items:**

- Doc Q&A (beyond minimal citations if any)
- Broad retrieval beyond core trading domains
- Training-system integration
- Autonomous multi-agent behavior
- Large vocabulary / ontology systems
- Non-Slack surfaces beyond what is needed for compatibility

**Proof required:** These items are clearly labeled as out of scope for MVP.

**Accept if:** Engineering stays focused on the operator path first.

**Reject if:** MVP gets polluted with side projects.

---

## Operator acceptance loop

For every directive, the execution cycle is:

1. Directive issued.
2. Engineering implements the bounded slice.
3. Engineering returns proof.
4. Operator tests the delivered behavior.
5. Architect reviews the proof and operator result.
6. Directive is **accepted** or **rejected**.
7. If rejected, a **corrective directive** is issued with the failure reason and narrowed scope.

That loop is the governing model. **No directive is considered complete** until the operator-facing behavior and proof both pass.

---

## Recommended initial directive order

1. BBX-SLACK-001  
2. BBX-SLACK-002  
3. BBX-SLACK-003  
4. BBX-SLACK-004  

Do **not** start named-agent overlays or broader context behavior until the default Slack path is grounded and stable.

After that:

5. BBX-SLACK-005  
6. BBX-SLACK-006  
7. BBX-SLACK-007  

Then defer everything else until the MVP is accepted (per BBX-SLACK-008 / 009).

---

## Final planning judgment

*(Architect-owned: record final sequencing judgment vs Pillar 1 lock and `development_plan.md` when this program is formally authorized.)*
