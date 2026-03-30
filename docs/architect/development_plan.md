# BLACK BOX — Development Plan (Phase 5+)

**Canonical master roadmap:** [`docs/blackbox_master_plan.md`](../blackbox_master_plan.md) — this file lists **actionable tasks** for **Phase 5** and marks **Phase 6 / 7** as out of scope for the current sprint.

**Status synchronization:** Updates that change phase scope or completion must update **`docs/blackbox_master_plan.md`** and **`docs/architect/directives/directive_execution_log.md`** in the same change set (`Plan/log status sync: PASS`).

---

## Phase 5 — Canonical structure (how subsections relate)

**Governance:** This section is **normative** for interpreting Phase **5** task blocks. It does **not** replace **`docs/working/current_directive.md`**; the active directive still selects the current implementation slice from this plan ([`development_governance.md`](development_governance.md) — plan before directive, one active directive).

| Layer | Plan home | What it is | Dependency note |
|-------|-----------|------------|------------------|
| **A — Engine spine** | **5.0–5.7** + **First slice** checklist | Participant/tier model, market data, store, strategy, **Layer 3** binding, **Layer 4** intent + **Billy** + **venue adapter** (paper/sandbox first), risk/controls, observability. **Exchange connectivity** is part of this layer. | **Not** blocked by full **5.8** (University) governance/runtime; spine can advance per directive while University specs mature. |
| **B — Engine-native context** | **5.9** | `modules/context_ledger/`, **`contextProfile`**, context bundles — **platform** infrastructure for Anna, orchestration, and future agents ([`hydration_context_governance.md`](hydration_context_governance.md) §10). | Implement when **directed**; ledger contracts are what **5.8** and Anna **consume**. Overlaps the “foundational ledger” intent in the **5.8** blockquote without requiring Dean/college/harness to ship first. |
| **C — University platform** | **5.8** | **Global** learning layer: **Dean** (intake/routing), **college** = **domain silo** (many colleges; default **single** primary enrollment; **dual** enrollment only Dean-approved), **Professor**, **Exam board**, curriculum schemas, **scored** evaluation, promotion/rejection. Same **University-wide** method stack applies across colleges; colleges differ by **domain** and **benchmarks**, not ad hoc per-college core training paradigms unless the architect records an exception. | **Ordering rule:** do **not** begin **5.8** before **Pillars 2 and 3** are complete (see **5.8** blockquote below). Answers *how humans and governance interact with training* and *how learning is measured*; it does **not** replace the engine spine. |

**Authoritative University specs:** [`blackbox_university.md`](blackbox_university.md), [`anna_university_methodology.md`](anna_university_methodology.md), staging subtree [`university/README.md`](../../university/README.md).

---

## Phase 5 — Core trading engine (next active build)

**Goal:** First working **Anna + Billy** path from **live data** → **signal** → **Layer 3 approval** → **Layer 4 intent** → **venue execution** (paper/sandbox first), while locking in the canonical **multi-participant, human-selected risk tier** model from day one.

### 5.0 Multi-participant + risk tier model — tasks

- [ ] Define canonical **participant identity** fields for all Phase 5 artifacts: `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`.
- [ ] Bind participant/account/wallet handling to the Phase **4.2** wallet/account architecture; do not invent a parallel identity model.
- [ ] Define exactly **three** human-selected risk tiers (**Tier 1 / Tier 2 / Tier 3**) and persist the selected tier as operator-owned state.
- [ ] Ensure Anna cannot assign or escalate risk tiers; tier changes must come from a human/operator path.
- [ ] Model future bot participants as constrained participants that can request tier-scoped strategies/signals but cannot override tiers, approvals, or risk boundaries.

### 5.1 Market data ingestion — tasks

- [ ] Select and integrate **primary** feed (e.g. Pyth) for initial symbol set (e.g. SOL).
- [ ] Implement **fallback** (e.g. Coinbase REST) when primary fails freshness/health.
- [ ] Define **canonical snapshot schema**; implement **normalization** pipeline.
- [ ] Add **health checks** and **gap detection**; alert or fail closed per policy.

### 5.2 Market data store — tasks

- [ ] Provision **production** (non-sandbox) store for time-series / snapshots.
- [ ] Expose **query** API or batch readers for strategy and backtest.
- [x] Add participant/tier-aware read contracts so downstream signal, approval, and audit artifacts remain scoped even if raw market data is shared.

### 5.3 Strategy engine — tasks

- [x] Implement **deterministic** strategy v1 (single symbol / small universe).
- [x] Emit **signals** with **confidence** and structured fields (align to master plan signal contract).
- [x] Wire **backtest / simulation** loop reading **stored** data only.
- [x] Add **pre-trade fast gate**: EV after costs, uncertainty/abstain, and capped sizing before any live candidate is emitted.
- [x] Ensure strategy selection is **tier-aligned**; Anna must adapt inside the selected tier and never mix or escalate tier behavior.
- [x] Allow self-directed paper/backtest experiments within fixed guardrails; no self-service risk-tier changes.

### 5.4 Signal → approval binding — tasks

> **Phase 5.4 — COMPLETE** (2026-03-30): Candidate trade artifact (`CandidateTradeV1`), Layer 3 routing (`trade_candidate_approvals` + approval interface `/api/trade-approvals`), and participant scope on the artifact are implemented and architect-closed. Proof: `docs/working/shared_coordination_log.md`.

- [x] Create **candidate trade artifact** from signal (size, risk, expiry).
- [x] Route to **Layer 3** approval flow; **no** execution without **APPROVED** artifact.
- [x] Include participant scope on the artifact: participant id/type, account/wallet context, selected risk tier, and strategy profile.

### 5.5 Execution adapter — tasks

- [ ] Implement **single venue** adapter (e.g. Coinbase); **paper/sandbox** first, then **small-size live** behind gates.
- [ ] Consume **Layer 4 execution intent** per [`layer_4_execution_interface_design.md`](layer_4_execution_interface_design.md) (section 13 mitigations).
- [ ] Integrate **Billy** for **edge execution** (execution only; no signal invention).
- [ ] Enforce participant/account/tier scope at execution time; Billy must not substitute wallets, merge scopes, or expand risk.

### 5.6 Risk & controls — tasks

- [ ] Enforce **per-trade** and **per-account** limits.
- [ ] Enforce **per-participant** and **per-tier** limits.
- [ ] Enforce **approval expiry** (aligned with Layer 3/4).
- [ ] Wire **global kill switch** and Layer 4 kill contract.
- [ ] **Position / PnL** tracking (minimum viable).

### 5.7 Observability & operations — tasks

- [ ] **Metrics:** feed health, signals, approvals, executions.
- [ ] **Logs** and **failure** taxonomy; runbook links.
- [ ] **Runbooks:** halt, rollback, revoke paths.
- [ ] Audit all signals/executions by participant, account/wallet context, and risk tier.

### 5.8 University / learning system — core engine tasks

> **Core engine rule:** University is part of the core engine, not a side project. It is sequenced work, not optional work.
>
> **Ordering rule:** Do **not** begin this work before **Pillars 2 and 3** are complete. University is a later core-engine workstream that extends the engine after the higher-priority pillars are in place.
>
> **Foundational dependency rule:** The first University build task is the interim structured memory/context ledger. This module is foundational for student context, Dean context, and exam-board context, and may need to be promoted into BLACK BOX core-engine scope rather than treated as a narrow college-only utility.

- [ ] Canonically adopt [`blackbox_university.md`](blackbox_university.md) as the bot-agnostic University standard inside the core engine roadmap (includes **Karpathy-aligned** autonomous research + curriculum reference for all agents).
- [ ] Canonically adopt [`anna_university_methodology.md`](anna_university_methodology.md) as the Anna-specific University supplement inside the core engine roadmap.
- [ ] Canonically adopt the in-repo University subtree as the staging area for the future standalone multi-project University project: [`../../university/README.md`](../../university/README.md), [`../../university/docs/UNIVERSITY_SYSTEM_DRAFT.md`](../../university/docs/UNIVERSITY_SYSTEM_DRAFT.md), [`../../university/templates/dean_curriculum_submission_v1.md`](../../university/templates/dean_curriculum_submission_v1.md).
- [ ] Build the interim structured memory/context ledger first as the foundational context module for University-connected students, Dean review, and exam-board supervision.
- [ ] Place the interim context ledger at `modules/context_ledger/` and treat it as BLACK BOX core-engine scope with a reusable contract for University-connected consumers.
- [ ] Define the first context-ledger interface explicitly: `add_record`, `query_records`, `build_context_bundle`, `export_records`.
- [ ] Define and bring online the **Dean** as the University-wide intake and governance agent for curriculum routing, college hydration, sponsor exports, and graduation coordination.
- [ ] Define the strict **Dean submission template** as the mandatory human intake contract; malformed submissions must be rejected rather than interpreted loosely.
- [ ] Define **curriculum JSON schema v1** and **enrollment record schema v1** for University tracks and student onboarding.
- [ ] Define the **college contract**: one primary student enrollment by default, explicit Dean-approved dual-enrollment exception path, college-specific professor, and college-specific exam board.
- [ ] Define the **context bundle contract** for University-connected students: identity, semantic memory, staging memory, episodic memory, live context, and system/tool facts.
- [ ] Implement a University-wide **context engineering** layer that combines structured retrieval, memory, typed context assembly, and benchmark/policy context; do not rely on naive chunk-only RAG as the full context strategy.
- [ ] Build the first evaluation harness for scored promotion / rejection decisions under audit and policy.
- [ ] Define binary pass/fail exam contracts per college so “student got smarter” is measurable and sponsor-aligned rather than subjective.
- [ ] Implement Anna as the first **reference student** track with operator-provided curriculum, staged promotion, and explicit promotion / rejection outcomes.
- [ ] Bake the carry-forward student persona into Anna’s canonical BLACK BOX architecture: capital preservation, RCS, and RCA must persist across Bachelor, Master, and PhD rather than being dropped at higher tiers. **Review flag: 2026-03-28.**
- [ ] Add teacher-student workflow scaffolding for RAG, distillation, synthetic data, and adversarial evaluation inside guardrails.
- [ ] Evaluate adjacent method families beyond AutoResearch for measurable value in University, including contextual retrieval, DSPy-style optimization, adversarial evaluation, and teacher-student distillation.
- [ ] Add grounded evaluation and calibration loops so Anna can improve without treating conversation alone as canonical truth.
- [ ] For Master-tier trading-college work, add parallel candidate-analysis support so Anna can review multiple strategy candidates simultaneously while maintaining one governed live-action lane.
- [ ] Add resource checks and alerting for Master-tier parallel candidate analysis so Anna uses only safe available depth, degrades gracefully under constraint, and never exceeds the configured ceiling (`25` initial target).
- [ ] Keep Slack/chat/episodic context non-canonical unless promoted through the structured curriculum / registry path.
- [ ] Wire the primary BLACK BOX Slack curriculum-submission path to the Dean so a sponsor can submit text or attachments that hydrate the correct college and kick off learning.
- [ ] Ensure University remains governance-bound: no bypass of approvals, risk tiers, execution planes, or human-on-the-loop controls.

### 5.9 Engine-native shared context (`modules/context_ledger/`) — tasks

> **Architect intent:** Context is **engine-native**, not Anna-only. **Gnosis** (external context-as-a-service) is a **future** adapter target — **not** a shipping dependency. Contracts and interim behavior live in **`modules/context_ledger/`** first; see [`modules/context_ledger/README.md`](../../modules/context_ledger/README.md) and [`docs/architect/hydration_context_governance.md`](hydration_context_governance.md) §10 (gap closed/open matrix).

- [ ] Finalize **context bundle contract** (versioning, validation state, reuse rules) aligned with `ContextBundle` / `ContextRecord` in `modules/context_ledger/base.py` and University bundle language.
- [ ] Wire **Anna** as first consumer to the ledger **without** breaking existing Anna memory / task / artifact paths (incremental migration map).
- [ ] Enforce **agent-scoped views** of engine-global context using **`contextProfile`** in [`agents/agent_registry.json`](../agents/agent_registry.json) at runtime (beyond static markdown).
- [ ] Define **online activation** checklist: registry + `contextProfile` + runtime + messaging/OpenClaw + proof hooks (architect-owned wording).
- [ ] Specify **Foreman / orchestration** use of context packets for multi-agent routing (directive).
- [ ] Document **Gnosis compatibility boundary** (adapter interface only; no hard dependency in core).

### First slice (approved paper loop) — checklist

Aligned with **Phase 5 — First approved slice** in [`blackbox_master_plan.md`](../blackbox_master_plan.md).

- [ ] Pyth ingestion (**SOL**).
- [ ] Normalized snapshot store.
- [ ] Deterministic strategy → SOL signal contract with participant/account/tier scope.
- [ ] L3 approval binding.
- [ ] Execution intent contract post-approval.
- [ ] Billy poll + Coinbase **sandbox** adapter.
- [ ] Outcome ingestion + durable storage.

**Stop condition:** “One approved, participant-scoped signal → one paper trade → verified outcome → stored” before scope expansion.

---

## Phase 6 — Intelligence & self-improvement

> **FUTURE EXPANSION.** Phase 6 remains beyond the current active engine build. University is no longer parked here as an optional stub; its core-engine work is now tracked in **Phase 5.8**.

No scheduled tasks yet beyond what is already defined in the core-engine roadmap. See [Phase 6 — Intelligence & Self-Improvement (Future)](../blackbox_master_plan.md#phase-6--intelligence--self-improvement-future) in the master plan.

---

## Phase 7 — Bot hub / ecosystem

> **NOT IN SCOPE for current sprint. FUTURE / STUB ONLY.**

No scheduled tasks. See [Phase 7 — Bot Hub / Ecosystem (Future)](../blackbox_master_plan.md#phase-7--bot-hub--ecosystem-future) in the master plan.

---

## Document control

- **Path:** `docs/architect/development_plan.md`
- **Purpose:** Actionable development tasks; **not** a substitute for the master plan’s full architecture narrative.
