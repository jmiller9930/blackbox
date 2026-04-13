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

### Primary outcomes contract (operator-priority)

These outcomes define operational success for the program. They are written as cross-cutting contract priorities so implementation can remain directive-driven without losing target-state alignment.

1. **Core engine completion (Pillar 1):**
   - complete deterministic, test-backed core engine surfaces (`5.0` through `5.7` + first-slice integration path)
   - prove end-to-end replayability and fail-closed behavior
   - include deterministic **Pyth market-data ingestion into SQLite** (normalized snapshot writes + replayable read path) as a required completion surface, not optional follow-up
2. **Context engine for every online bot:**
   - every online agent must pass context-profile and activation gates before being treated as online-ready
   - context inputs and authority boundaries must remain explicit, auditable, and fail-closed
3. **Exchange wiring with governance:**
   - BLACK BOX must support controlled venue wiring (paper/sandbox first, then tightly gated progression)
   - no bypass of approval, risk-tier, or kill-switch controls
4. **University curriculum injection and routing:**
   - curriculum must be submitted in a strict contract format
   - Dean intake/routing must place curriculum into the intended college path with auditable updates
5. **Human coaching loop (`@Anna` interactive justification):**
   - operators must be able to challenge strategy rationale in live interaction channels
   - coaching interactions can inform learning only through structured promotion gates (staging -> validated), never by implicit chat-only mutation

### Usable intelligence contract (Anna conversation + decision quality)

This contract is mandatory for context/training work that claims conversational or decision capability.

**Objective:** Anna must demonstrate usable intelligence in live human interaction and decision support, not generic patterned responses.

**Required behavior contract:**

1. **Context-grounded conversation:** responses must be grounded in active context inputs (policy, market state, participant scope, and recent interaction evidence).
2. **Direction-taking:** Anna must ingest human direction and convert it into explicit next-step reasoning or bounded action proposals.
3. **Challenge/defense loop:** Anna must be able to justify rationale, accept challenge, and revise or abstain when evidence is weak.
4. **Decision usefulness:** outputs must produce actionable, policy-compliant decision support under guardrails (or explicit fail-closed abstain).
5. **No generic fallback acceptance:** generic, unsupported, or template-like patterned output does not satisfy this contract.

**Minimum output contract (for in-scope responses):**

- thesis or decision recommendation
- constraints applied (guardrails/risk-tier/policy)
- evidence/provenance refs (or explicit insufficiency)
- confidence + uncertainty statement
- action class: `propose` / `revise` / `abstain`

**Fail-closed rules:**

- missing required context quality -> abstain/clarify (no synthetic confidence)
- missing provenance for material claims -> reject as non-compliant
- policy/guardrail conflict -> reject or downgrade to abstain

**Proof hooks (required for acceptance):**

- deterministic conversation test matrix (direction-taking, challenge/defense, revise/abstain paths)
- deterministic decision-support matrix (proposal quality under valid/invalid context)
- replayable artifacts showing context inputs, provenance refs, and final action class
- explicit rejection cases proving generic patterned output is blocked

**Testability statement:** Core engine tests validate deterministic runtime behavior, but operational readiness is not fully represented unless these cross-cutting outcomes are contracted and proven through governed directives and replayable artifacts.

**Scope note while Pillar 1 lock is active:** implementation remains restricted to Pillar 1 directives. Outcomes involving University or expanded context/training flows are planning targets until lock removal is explicitly contracted.

### Post-core-engine sequencing gate (non-negotiable)

After the currently active core-engine segment is canonically accepted, do not advance into unrelated new build scope until the following are explicitly contracted in governed docs and reviewed with the operator:

1. **Human operations definition ("operations ="):**
   - how a human kicks off, runs, pauses, resumes, and recovers the system
   - what interfaces are used for day-to-day control, status, and intervention
   - what minimum docs/runbooks must exist for normal and failure paths
2. **Anna education and oversight loop:**
   - how a human (for example, a trade master) trains Anna through interactive coaching
   - how schoolwork/progress is inspected, reviewed, and approved or rejected
   - how curriculum updates are injected and routed (Dean -> college -> exam board path)
3. **Strategy transparency and provenance:**
   - how operators inspect strategies Anna generates
   - how operators verify why a strategy was produced (inputs, context, constraints, evidence chain)
   - how Anna defends or revises strategy rationale under challenge
4. **Anna <-> Billy trading interaction boundaries:**
   - whether and how Anna can signal Billy to place a trade
   - whether and how Anna can run simulations vs submit real-trade intents
   - strict approvals/risk-tier/kill-switch controls for any real-path action
5. **Novel-strategy governance:**
   - how Anna proposes novel trades while remaining grounded and policy-compliant
   - how novelty is evaluated, accepted, deferred, or rejected by explicit gates

**Canonical rule for this gate:** No "implied readiness" claims. Each item above must be represented as contract language (scope, out-of-scope, pass/fail criteria, and proof hooks) before it is treated as executable program scope.

### Coherent development schedule (post-core planning sequence)

This schedule consolidates the agreed next-step priorities into one execution order. It is planning authority for sequencing only; active implementation still follows `current_directive.md` and lock posture.

#### Schedule S0 — complete active architect gate

- Finish the currently active architect-owned intake-cycle refresh/publication-readiness directive and record deterministic verdict artifacts.
- If authorized by operator packet, open a **temporary lock-lift execution window** strictly for finishing this schedule through core-engine final completion.
- Mandatory choreography: any temporary lock-lift window must be followed by explicit **Pillar 1 lock reinstatement** before any Pillar 2/non-core expansion.

#### Schedule S1 — context engine hardening (highest priority polish)

Target: close the critical context-engine gaps identified in code review before broader training expansion.

1. Upgrade online-activation proof gate from "file exists/non-empty" to fresh replayable proof checks (hash/timestamp/run-id linked evidence).
2. Extend runtime context profile enforcement beyond `allowedContextClasses` to include deferred profile semantics (`bundleSections`, write/reuse policy constraints) with fail-closed behavior.
3. Add deterministic write-safety hardening for ledger persistence paths (multi-writer safety / atomicity protections where needed).
4. Add context quality checks for downstream strategy consumption (freshness, relevance, and minimum evidence coverage gates).

#### Schedule S2 — hard-core training loop (no-polish lane)

Target: run a strict training spine welded to the context engine, optimized for measurable trading capability rather than UI polish.

1. Candidate generation under fixed guardrails.
2. Counterfactual/off-policy replay scoring.
3. Walk-forward + regime-shift validation.
4. Uncertainty/disagreement abstain gates.
5. Champion-challenger promotion lane with binary pass/fail promotion packets.

#### Schedule S3 — exchange progression under strict controls

Target: preserve deterministic safety while advancing execution realism.

1. Paper lane reliability proof.
2. Sandbox lane reliability proof (Billy-scoped adapter path).
3. Optional tiny live lane only after explicit pass thresholds and rollback contract are satisfied.

#### Core-engine final completion target (required before lock reinstatement)

Before this schedule is considered complete, the core-engine final acceptance package must show:

1. **Drift exchange connectivity path is wired** under governed controls (paper/sandbox required; tiny live only if explicitly authorized by directive).
2. **Anna context path is operational** (context bundle + policy constraints materially influence strategy decisions, not dictionary-only responses).
3. **Anna training path is operational** in the hard-core loop (candidate -> evaluation -> promotion/reject packets with replayable evidence).
4. **Anna trading activity path is testable** (simulation mandatory; real-path activity only through approval/risk/kill-switch controls).
5. **Documentation sufficiency** for operator use and agent handoff (kickoff, operation, recovery, and rationale/provenance inspection paths).

After these are accepted canonically, reinstate Pillar 1 lock and record the retained-lock publication packet before any non-core scope progression.

#### Schedule S4 — human operations and education oversight contract package

Target: ensure human usability and governance visibility before broader expansion.

1. Define "operations =" contract (kickoff, run, pause/resume, recovery, observability, runbook minimums).
2. Define Anna coaching and schoolwork review flow (human challenge -> structured staging -> exam-board gate -> promotion/reject).
3. Define strategy transparency/provenance contract (why generated, evidence chain, rationale defense/revision path).
4. Define Anna<->Billy interaction boundary contract (simulate vs real intent signaling rules).

#### Schedule S5 — University/Gnosis expansion (deferred by design)

Target: resume full-stack University and optional external context-provider expansion only after S1-S4 are contracted and proven.

- University/Dean/college/exam-board orchestration and broader multi-agent education stack.
- Optional external context-provider (Gnosis-like) adapter work after in-repo context contracts remain authoritative and stable.

**Scheduling rule:** execute S1 before S2; execute S2 before S3; execute S4 before non-Pillar expansion claims; S5 remains deferred until prior schedules are met with replayable proof.

---

### Operator web dashboard — trade chain & strategy designation (as-built, 2026-04)

**Pillar 1 operator surface (lab):** `UIUX.Web/dashboard.html`, `UIUX.Web/api_server.py`, `modules/anna_training/dashboard_bundle.py`, `modules/anna_training/operator_trading_strategy.py`. Poll **`GET /api/v1/dashboard/bundle`** (aggregate: sequential status, wallet subset, **trade_chain**, **operator_trading**, liveness).

| Capability | Location / notes |
|------------|-------------------|
| Trade chain table | Baseline row + Anna rows from `strategy_registry` lifecycles (`anna_test` vs `anna_strategy` buckets); event columns = recent `market_event_id` window |
| vs baseline | **`_pair_vs_baseline_for_cells`**: WIN / NOT WIN / EXCLUDED; baseline leg paper/live; Anna leg includes **`paper_stub`** when PnL + MAE present |
| Comparative headline | **`trade_chain.anna_vs_baseline_aggregate`** + UI title line; **`trade_chain.scorecard`** per-row counts |
| Operator trading strategy | **`operator_trading`** in `state.json`: `designated_strategy_id`, `cookie_jar`; **not** a rewrite of ledger **`lane=baseline`** |
| Registry-backed controls | **`operator_trading.eligible_strategy_ids`** = sustained QEL lifecycles (candidate → promoted); test/experiment excluded |
| API | **`POST /api/v1/operator/trading-strategy`** — `action` promote / demote; demote may replace with **`baseline`** (default system strategy) |
| Cursor rule | **Commit + push** after substantive work: [`git-complete-push-origin.mdc`](../../.cursor/rules/git-complete-push-origin.mdc) |

**Deploy:** `git pull` + restart API; hard-refresh browser — stale static files explain “no UI change” on clawbot.

### Slack conversational operator — canonical directive sequence (BBX-SLACK-*)

**Canonical plan (governance + engineering):** [`slack_conversational_operator/canonical_development_plan.md`](slack_conversational_operator/canonical_development_plan.md)

**Low-level design:** [`slack_conversational_operator/slack_conversational_operator_system_ldd.md`](slack_conversational_operator/slack_conversational_operator_system_ldd.md)

Directive-driven delivery: **one bounded slice at a time**, proof returned, operator test, accept or reject. Phases **0–7** map to **BBX-SLACK-001** through **008**; deferred scope is **BBX-SLACK-009**. **Constraint:** Jupiter V2 trading policy behavior remains **untouched** by this workstream unless separately authorized.

**Ordering note:** Implement **001–004** (governance lock → transport → intent → grounded tools) before named-agent overlays (**006**) and full context integration (**005**) per the recommended order in the canonical plan.

---

## Phase 5 — Core trading engine (next active build)

**Goal:** First working **Anna + Billy** path from **live data** → **signal** → **Layer 3 approval** → **Layer 4 intent** → **venue execution** (paper/sandbox first), while locking in the canonical **multi-participant, human-selected risk tier** model from day one.

### 5.0 Multi-participant + risk tier model — tasks

- [ ] Define canonical **participant identity** fields for all Phase 5 artifacts: `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`.
- [ ] Bind participant/account/wallet handling to the Phase **4.2** wallet/account architecture; do not invent a parallel identity model.
- [ ] Define exactly **three** human-selected risk tiers (**Tier 1 / Tier 2 / Tier 3**) and persist the selected tier as operator-owned state.
- [ ] Ensure Anna cannot assign or escalate risk tiers; tier changes must come from a human/operator path.
- [ ] Model future bot participants as constrained participants that can request tier-scoped strategies/signals but cannot override tiers, approvals, or risk boundaries.

#### 5.0.1 Multi-participant identity + risk-tier contract lock

**Directive:** **CANONICAL #017** — lock the architect-owned participant identity and risk-tier interaction contract so downstream Phase 5 implementation slices consume one deterministic field/boundary model before execution-adapter work advances.

- **Status:** **Closed (2026-03-31)** — architect contract-lock acceptance completed with synchronized governed-doc wording and closeout packet.
- [x] Define canonical participant scope field contract table across signal, candidate-trade, approval, execution-intent, and outcome artifacts.
- [x] Define fail-closed rules for missing/ambiguous participant scope (`participant_id`, account/wallet context, selected `risk_tier`, interaction path).
- [x] Define authority boundaries: only human/operator paths can assign or change `risk_tier`; Anna/Billy and future bots consume scope but cannot escalate or substitute it.
- [x] Synchronize governed docs for the lock (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`) with matching status granularity.

**Canonical participant-scope contract (locked by #017):**

| Artifact surface | Required participant scope fields | Contract rule |
|------------------|-----------------------------------|---------------|
| Signal output artifact | `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path` | Signal is invalid if any field is missing, empty, or ambiguous. |
| Candidate-trade artifact | Same six fields above | Candidate artifact must preserve signal scope exactly; scope drift is invalid. |
| Approval artifact (Layer 3) | Same six fields above | Approval decision must bind to one deterministic participant scope; mixed scope is invalid. |
| Execution-intent artifact (Layer 4 input) | Same six fields above | Intent is invalid without exact approval-bound scope and must fail closed before execution adapter entry. |
| Outcome/audit artifact | Same six fields above | Outcome rows must retain originating participant scope for replay and audit; missing scope is invalid. |

**Fail-closed rules (locked by #017):**

- Missing required participant scope fields on any in-scope artifact invalidates the artifact and blocks lane progression.
- Mismatch across linked artifacts (`signal` -> `candidate` -> `approval` -> `intent` -> `outcome`) invalidates the chain.
- Unknown `participant_id`, unresolved account/wallet context, or ambiguous `interaction_path` invalidates the artifact.
- Invalid or absent `risk_tier` blocks progression; no defaulting, coercion, or silent fill-in is allowed.

**Authority boundaries (locked by #017):**

- Only human/operator pathways may assign or change `risk_tier`.
- Anna, Billy, and future bot participants may consume participant scope but may not assign, escalate, substitute, or merge participant/account/tier scope.
- Layer 3 approval and Layer 4 intent flow must consume the already-selected tier; neither layer grants tier mutation authority.

#### 5.0.2 Signal / intent / outcome artifact contract lock

**Directive:** **CANONICAL #018** — lock artifact-level signal/intent/outcome contract tables (including participant scope propagation and fail-closed validation requirements) before implementation directives for Phase 5.5+ execution surfaces.

- **Status:** **Closed (2026-03-31)** — architect contract lock accepted and synchronized.
- [x] Define canonical `SignalArtifactV1`, `ExecutionIntentV1`, and `ExecutionOutcomeV1` required-field tables with participant-scope carry-forward rules.
- [x] Define linkage and replay requirements (`signal_id`, `candidate_id`, `approval_id`, `intent_id`, `execution_id`, timestamps, and deterministic trace references) for lane-safe auditing.
- [x] Define fail-closed validation matrix and reason-code expectations for missing/ambiguous/mismatched artifact chains.
- [x] Synchronize governed docs for the lock (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`) with matching status granularity.

**Canonical artifact contract tables (locked by #018):**

| Contract | Required fields | Contract rule |
|----------|-----------------|---------------|
| `SignalArtifactV1` | `signal_id`, `candidate_id`, `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `symbol`, `strategy_id`, `strategy_version`, `signal_side`, `signal_strength`, `confidence_score`, `context_hash`, `trace_id`, `generated_at_utc` | Signal artifact is invalid if any required field is missing, empty, or not deterministic for replay. |
| `ExecutionIntentV1` | `intent_id`, `approval_id`, `candidate_id`, `signal_id`, `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `execution_idempotency_key`, `context_hash`, `order_side`, `order_type`, `quantity`, `submitted_at_utc`, `expires_at_utc`, `trace_id` | Intent artifact must bind to one approved candidate and carry unchanged participant scope with strict idempotency semantics. |
| `ExecutionOutcomeV1` | `outcome_id`, `intent_id`, `execution_id`, `approval_id`, `candidate_id`, `signal_id`, `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `outcome_class`, `venue_status`, `filled_quantity`, `avg_fill_price`, `fees_total`, `recorded_at_utc`, `trace_id` | Outcome artifact must retain full chain references and participant scope from intent through execution result. |

**Linkage and replay requirements (locked by #018):**

- Artifact chain is strictly `signal_id` -> `candidate_id` -> `approval_id` -> `intent_id` -> `execution_id` -> `outcome_id`.
- Every downstream artifact must reference upstream IDs exactly; no implicit remap, default, or synthetic join is allowed.
- `context_hash` in `ExecutionIntentV1` must match approved pre-execution context; hash mismatch invalidates progression.
- Replay must be deterministic using artifact IDs + timestamps + `trace_id`; if deterministic replay cannot be reconstructed, the chain is invalid.

**Fail-closed validation matrix (locked by #018):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `ART-REQ-001` | Missing required field | Reject artifact and block progression. |
| `ART-SCOPE-002` | Ambiguous or missing participant scope | Reject artifact and block progression. |
| `ART-LINK-003` | Chain-link mismatch across required IDs | Reject artifact and block progression. |
| `ART-HASH-004` | `context_hash` mismatch or absent when required | Reject artifact and block progression. |
| `ART-IDEMP-005` | Idempotency conflict on intent/execution linkage | Reject artifact and block progression. |
| `ART-TIME-006` | Non-deterministic or invalid timestamp ordering | Reject artifact and block progression. |

#### 5.0.3 Signal / intent / outcome artifact runtime implementation

**Directive:** **CANONICAL #019** — implement runtime models and fail-closed validators for the #018 artifact contracts so execution-adapter work consumes deterministic, test-backed artifact enforcement.

- **Status:** **Closed (2026-03-31)** — architect validated implementation and synchronized closeout artifacts.
- [x] Implement runtime `SignalArtifactV1`, `ExecutionIntentV1`, and `ExecutionOutcomeV1` models and validators aligned to #018 required fields.
- [x] Implement deterministic chain-validation helpers enforcing `signal_id` -> `candidate_id` -> `approval_id` -> `intent_id` -> `execution_id` -> `outcome_id`.
- [x] Implement fail-closed reason-code behavior for `ART-REQ-001` through `ART-TIME-006` without silent defaults/coercion.
- [x] Add deterministic tests for valid chains and each required rejection class.
- [x] Record implementation proof and architect validation artifacts in governed docs.

### 5.1 Market data ingestion — tasks

- [ ] Select and integrate **primary** feed (e.g. Pyth) for initial symbol set (e.g. SOL).
- [ ] Implement **fallback** (e.g. Coinbase REST) when primary fails freshness/health.
- [ ] Define **canonical snapshot schema**; implement **normalization** pipeline.
- [ ] Add **health checks** and **gap detection**; alert or fail closed per policy.

#### 5.1.1 Market-data ingestion contract lock

**Directive:** **CANONICAL #020** — lock the architect-owned Phase 5.1 market-data ingestion contract (primary/fallback source semantics, snapshot schema, freshness/divergence fail-closed rules, and deterministic reason-code matrix) before implementation directives.

- **Status:** **Closed (2026-03-31)** — architect contract lock accepted and synchronized.
- [x] Define canonical `MarketSnapshotV1` required-field table and normalization requirements for SOL-first ingestion.
- [x] Define primary-source and fallback-source authority rules (when fallback is allowed, when ingestion must fail closed).
- [x] Define freshness/divergence fail-closed matrix with deterministic rejection reason codes for stale, gap, and source-mismatch conditions.
- [x] Define replay/proof hooks required for follow-on implementation directive(s).
- [x] Synchronize governed docs for #020 (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`).

**Canonical `MarketSnapshotV1` contract (locked by #020):**

| Field | Requirement | Contract rule |
|-------|-------------|---------------|
| `snapshot_id` | required, non-empty | Unique deterministic row identifier for replay/audit. |
| `symbol` | required, normalized uppercase | Canonical symbol token (initial scope: `SOL`). |
| `source` | required (`primary` or `fallback`) | Records which authority path produced the snapshot. |
| `source_name` | required, non-empty | Concrete provider identifier (e.g. `pyth`, `coinbase`). |
| `event_time_utc` | required ISO-8601 UTC | Source event timestamp used for freshness ordering. |
| `observed_at_utc` | required ISO-8601 UTC | Ingestion-observation timestamp for pipeline ordering. |
| `bid` | required decimal > 0 | Best bid in normalized decimal form. |
| `ask` | required decimal > 0 | Best ask in normalized decimal form. |
| `last` | required decimal > 0 | Last traded/quoted normalized value. |
| `mid` | required decimal > 0 | Deterministic midpoint; must align with `bid`/`ask`. |
| `spread_bps` | required decimal >= 0 | Deterministic spread metric for quality checks. |
| `freshness_ms` | required integer >= 0 | Pipeline-computed age against active freshness window. |
| `sequence_id` | required integer >= 0 | Monotonic per source stream for gap detection. |
| `trace_id` | required, non-empty | Cross-artifact correlation ID for replay/proof. |

**Normalization rules (locked by #020):**

- `symbol` is uppercase and trimmed; unsupported symbols are rejected.
- Price fields (`bid`, `ask`, `last`, `mid`) are decimal-normalized and must remain positive.
- `mid` must match deterministic midpoint calculation from normalized `bid`/`ask`.
- Timestamp fields are strict UTC ISO-8601; non-UTC or non-parseable values are rejected.
- Sequence and freshness fields are computed deterministically in ingestion flow; silent defaults are forbidden.

**Source authority rules (locked by #020):**

- **`MKT-SRC-001` Primary-first:** primary source is authoritative when healthy and fresh.
- **`MKT-SRC-002` Fallback eligibility:** fallback may be used only when primary is unavailable/unhealthy/stale beyond configured threshold.
- **`MKT-SRC-003` No silent source swap:** fallback activation must emit explicit source marker and reason code.
- **`MKT-SRC-004` Divergence guard:** when both sources are available, divergence above threshold invalidates ingestion for that cycle.
- **`MKT-SRC-005` Dual-path failure:** if neither source satisfies freshness/health constraints, ingestion fails closed.

**Fail-closed reason-code matrix (locked by #020):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `MKT-REQ-001` | Missing required `MarketSnapshotV1` field(s) | Reject snapshot and block ingestion output. |
| `MKT-NORM-002` | Normalization/parsing failure | Reject snapshot and block ingestion output. |
| `MKT-FRESH-003` | Snapshot exceeds freshness window | Reject snapshot and block ingestion output. |
| `MKT-GAP-004` | Sequence gap/regression detected | Reject snapshot and block ingestion output. |
| `MKT-DIV-005` | Primary/fallback divergence above threshold | Reject snapshot and block ingestion output. |
| `MKT-SRC-006` | Unauthorized fallback/source-path use | Reject snapshot and block ingestion output. |
| `MKT-TIME-007` | Invalid timestamp ordering (`event`/`observed`) | Reject snapshot and block ingestion output. |

**Proof hooks for follow-on implementation directive(s):**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `MKT-PROOF-001` | Ingestion unit tests (schema + normalization + source authority) | Deterministic pass/fail coverage for all required rule IDs | Missing coverage for any required fail-closed branch |
| `MKT-PROOF-002` | Replay command over fixed sample snapshots | Replayed output is deterministic and reason-code stable | Output drift or nondeterministic reason selection |
| `MKT-PROOF-003` | Shared-log proof block with commands/results | Architect can replay decisions from logged evidence | Narrative-only claim without replayable command trail |

#### 5.1.2 Market-data ingestion runtime contract implementation

**Directive:** **CANONICAL #021** — implement deterministic runtime ingestion validators/readers from the #020 contract lock so downstream strategy and approval surfaces consume fail-closed, test-backed `MarketSnapshotV1` artifacts.

- **Status:** **Closed (2026-03-31)** — architect validated runtime implementation and synchronized closeout artifacts.
- [x] Implement `MarketSnapshotV1` runtime parser/validator path aligned to #020 required fields and normalization rules.
- [x] Implement primary/fallback authority evaluator that enforces `MKT-SRC-001` ... `MKT-SRC-006` without silent source switching.
- [x] Implement freshness/gap/divergence checks with deterministic reason-coded reject behavior (`MKT-REQ-001` ... `MKT-TIME-007`).
- [x] Add deterministic tests for valid ingestion plus each required fail-closed branch.
- [x] Record developer proof in `docs/working/shared_coordination_log.md` and request architect validation.

### 5.2 Market data store — tasks

- [ ] Provision **production** (non-sandbox) store for time-series / snapshots.
- [ ] Expose **query** API or batch readers for strategy and backtest.
- [x] Add participant/tier-aware read contracts so downstream signal, approval, and audit artifacts remain scoped even if raw market data is shared.

#### 5.2.1 Market-data store contract lock

**Directive:** **CANONICAL #022** — lock the architect-owned Phase 5.2 market-data store contract (durable snapshot row schema, idempotent write semantics, deterministic query/read contracts, and fail-closed persistence/query reason matrix) before runtime implementation directives.

- **Status:** **Closed (2026-03-31)** — architect contract-lock slice accepted and synchronized.
- [x] Define canonical `MarketSnapshotStoreRowV1` field contract and required key/index constraints for deterministic replay (`snapshot_id`, symbol/source lineage, sequence/timestamp ordering, trace linkage).
- [x] Define write-path contract (idempotency/duplicate handling, timestamp and sequence ordering constraints, and fail-closed behavior for invalid persistence attempts).
- [x] Define query/read contract for strategy and audit consumers (time-window ordering guarantees, symbol/source filters, participant-scoped consumption metadata expectations).
- [x] Define deterministic fail-closed reason-code matrix and proof hooks for follow-on implementation directive(s).
- [x] Synchronize governed docs for #022 (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`).

**Canonical `MarketSnapshotStoreRowV1` contract (locked by #022):**

| Field | Requirement | Contract rule |
|-------|-------------|---------------|
| `snapshot_id` | required, non-empty | Canonical primary key for durable snapshot replay. |
| `symbol` | required, uppercase token | Canonical symbol filter key (initial scope includes `SOL`). |
| `source` | required (`primary` or `fallback`) | Source-authority lineage from ingestion contract. |
| `source_name` | required, non-empty | Concrete provider name used for replay diagnostics. |
| `event_time_utc` | required ISO-8601 UTC | Source event time used for deterministic ordering. |
| `observed_at_utc` | required ISO-8601 UTC | Ingestion observation timestamp for write ordering checks. |
| `sequence_id` | required integer >= 0 | Monotonic per `(symbol, source_name)` stream. |
| `bid` | required decimal > 0 | Stored normalized bid value. |
| `ask` | required decimal > 0 | Stored normalized ask value. |
| `last` | required decimal > 0 | Stored normalized last value. |
| `mid` | required decimal > 0 | Stored midpoint, aligned with ingestion normalization rule. |
| `spread_bps` | required decimal >= 0 | Stored spread metric for deterministic downstream reads. |
| `freshness_ms` | required integer >= 0 | Stored freshness measurement from ingestion contract. |
| `trace_id` | required, non-empty | Replay correlation key across store/read/audit artifacts. |
| `persisted_at_utc` | required ISO-8601 UTC | Canonical write timestamp emitted by store path. |

**Key/index constraints (locked by #022):**

- Primary key: `snapshot_id`.
- Uniqueness key: `(symbol, source_name, sequence_id)` to prevent silent sequence duplication.
- Read index: `(symbol, event_time_utc, sequence_id, snapshot_id)` for deterministic ordered window reads.
- Optional source-filter index: `(symbol, source, event_time_utc)` for primary/fallback scoped reads.
- Trace index: `trace_id` for replay/audit lookup.

**Write-path contract (locked by #022):**

- Store writes are idempotent by `snapshot_id` and by `(symbol, source_name, sequence_id)`.
- Duplicate writes with byte-equivalent canonical payload are treated as idempotent no-op success.
- Duplicate keys with conflicting payload values fail closed (no overwrite/coercion).
- Sequence/timestamp ordering regression for an existing `(symbol, source_name)` stream fails closed.
- Any missing required field or non-canonical normalized value fails closed before persistence.

**Query/read contract (locked by #022):**

- Required query inputs: `symbol`, `window_start_utc`, `window_end_utc`; optional `source` filter.
- Deterministic ordering is mandatory: `event_time_utc ASC`, then `sequence_id ASC`, then `snapshot_id ASC`.
- Query windows must fail closed on invalid time ranges, ambiguous filters, or unsupported symbols.
- Consumer-facing reads must carry participant-scope metadata (`participant_id`, `account_id`, `risk_tier`, `interaction_path`) for downstream audit linkage even when raw market data is shared.
- Pagination/cursor semantics (where used) must be deterministic and replay-safe against the canonical ordering tuple above.

**Fail-closed reason-code matrix (locked by #022):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `MKS-REQ-001` | Missing required store-row field(s) | Reject write/read request and emit deterministic failure reason. |
| `MKS-IDEMP-002` | Duplicate key with conflicting payload | Reject write (no overwrite) and preserve existing canonical row. |
| `MKS-ORDER-003` | Sequence/timestamp ordering regression | Reject write and block persistence for the violating row. |
| `MKS-WRITE-004` | Persistence constraint/write-path failure | Reject write and emit deterministic store failure reason. |
| `MKS-QUERY-005` | Invalid or ambiguous query window/filter | Reject query and block downstream consumption for that call. |
| `MKS-SCOPE-006` | Missing participant-scoped consumption metadata | Reject consumer read contract and block downstream artifact emission. |
| `MKS-REPLAY-007` | Non-deterministic ordering/cursor replay drift | Reject query result as invalid for replay-bound consumers. |

**Proof hooks for follow-on implementation directive(s):**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `MKS-PROOF-001` | Store write/validation unit tests | Deterministic coverage of write-path idempotency + fail-closed reason codes | Missing coverage for any required write-path rejection branch |
| `MKS-PROOF-002` | Deterministic query replay test command | Ordered reads reproduce stable tuples and source-filter behavior | Ordering/cursor drift across repeated replay runs |
| `MKS-PROOF-003` | Shared-log proof block with commands/results | Architect can replay write/query decisions from logged evidence | Narrative-only claims without replayable command trail |

#### 5.2.2 Market-data store runtime contract implementation

**Directive:** **CANONICAL #023** — implement the runtime store writer/query reader path from #022 so Phase 5 strategy/approval/audit consumers can persist and replay deterministic `MarketSnapshotStoreRowV1` rows with fail-closed guarantees.

- **Status:** **Closed (2026-03-31)** — architect validated runtime implementation and synchronized closeout artifacts.
- [x] Implement runtime `MarketSnapshotStoreRowV1` write path with #022 key/index/idempotency constraints and deterministic fail-closed reason codes (`MKS-REQ-001` ... `MKS-WRITE-004`).
- [x] Implement runtime query/read path with deterministic ordering, required filters, participant-scoped consumption metadata checks, and fail-closed behavior (`MKS-QUERY-005` ... `MKS-REPLAY-007`).
- [x] Add deterministic tests for valid writes/reads plus every required fail-closed branch and replay-stability path.
- [x] Record developer proof in `docs/working/shared_coordination_log.md` and request architect validation (`have the architect validate shared-docs`).
- [x] Synchronize governed docs at closeout (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`).

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

- [ ] Implement Billy's **first real market integration** to Drift with explicit onboarding/doctor/activation proof before any live-order path is considered valid.
- [ ] Consume **Layer 4 execution intent** per [`layer_4_execution_interface_design.md`](layer_4_execution_interface_design.md) (section 13 mitigations).
- [ ] Integrate **Billy** for **edge execution** (execution only; no signal invention).
- [ ] Enforce participant/account/tier scope at execution time; Billy must not substitute wallets, merge scopes, or expand risk.

#### 5.5.1 Execution-adapter runtime contract lock

**Directive:** **CANONICAL #024** — lock architect-owned Phase 5.5 execution-adapter runtime contract language (intent-to-adapter request mapping, participant-scope/risk boundaries, idempotent venue submission semantics, and fail-closed reason/proof matrix) before developer runtime implementation directives.

- **Status:** **Closed (2026-03-31)** — architect contract-lock acceptance completed with synchronized governed-doc wording and closeout packet.
- [x] Define canonical adapter request/outcome field contract tables bound to `ExecutionIntentV1` lineage (`intent_id`, `approval_id`, participant scope, venue order fields, idempotency key, and trace fields).
- [x] Define deterministic pre-submit gates (`approval` binding, intent expiry, participant/account/tier scope integrity, and context-hash continuity) with fail-closed behavior.
- [x] Define adapter-level fail-closed reason-code matrix and deterministic response expectations for unavailable venue, idempotency conflicts, and order-submit rejects.
- [x] Define proof hooks for the follow-on implementation directive (unit coverage, replayable paper/sandbox submission trail, shared-log evidence contract).
- [x] Synchronize governed docs for #024 (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`).

**Canonical execution-adapter contract tables (locked by #024):**

| Contract | Required fields | Contract rule |
|----------|-----------------|---------------|
| `ExecutionAdapterRequestV1` | `intent_id`, `approval_id`, `candidate_id`, `signal_id`, `trace_id`, `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `order_side`, `order_type`, `quantity`, `limit_price` (nullable by `order_type`), `time_in_force`, `venue_order_idempotency_key`, `submit_by_utc`, `intent_expires_at_utc`, `context_hash` | Request is invalid unless lineage, participant scope, venue order fields, and timing/idempotency fields are complete and deterministic. |
| `ExecutionAdapterOutcomeV1` | `outcome_id`, `intent_id`, `approval_id`, `candidate_id`, `signal_id`, `trace_id`, `participant_id`, `account_id`, `risk_tier`, `venue_name`, `venue_order_id`, `venue_status`, `submitted_at_utc`, `acknowledged_at_utc` (nullable), `rejected_at_utc` (nullable), `failure_code` (nullable), `failure_reason` (nullable) | Outcome must preserve full lineage and participant scope, with deterministic venue status/failure payload for replay/audit. |

**Deterministic pre-submit gates (locked by #024):**

| Gate ID | Gate | PASS condition | FAIL-CLOSED behavior |
|---------|------|----------------|----------------------|
| `EXA-GATE-001` | Approved-intent binding | `intent_id` binds to one approved `approval_id` + `candidate_id` + `signal_id` chain | Reject request with `EXA-BIND-001`; do not submit to venue |
| `EXA-GATE-002` | Intent expiry window | `submit_by_utc` and `intent_expires_at_utc` are valid and current at submit time | Reject request with `EXA-EXP-002`; do not submit to venue |
| `EXA-GATE-003` | Participant/account/tier scope integrity | Request participant scope matches the approved intent scope exactly | Reject request with `EXA-SCOPE-003`; do not submit to venue |
| `EXA-GATE-004` | Context-hash continuity | Request `context_hash` matches approved intent context hash | Reject request with `EXA-HASH-004`; do not submit to venue |
| `EXA-GATE-005` | Idempotency key admissibility | `venue_order_idempotency_key` is present and not in conflict for the same venue/account scope | Reject request with `EXA-IDEMP-005`; do not submit to venue |

**Execution-adapter fail-closed reason-code matrix (locked by #024):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `EXA-REQ-001` | Missing/invalid required adapter request fields | Reject request before venue call; emit deterministic failure payload |
| `EXA-BIND-001` | Intent/approval/candidate/signal chain mismatch | Reject request before venue call; emit deterministic failure payload |
| `EXA-EXP-002` | Intent submit/expiry window violation | Reject request before venue call; emit deterministic failure payload |
| `EXA-SCOPE-003` | Participant/account/tier scope mismatch | Reject request before venue call; emit deterministic failure payload |
| `EXA-HASH-004` | Context-hash mismatch or absence | Reject request before venue call; emit deterministic failure payload |
| `EXA-IDEMP-005` | Venue idempotency conflict | Reject duplicate/conflicting submission; no silent overwrite |
| `EXA-VENUE-006` | Venue unavailable/unhealthy timeout path | Fail closed with deterministic venue-unavailable outcome |
| `EXA-VENUE-007` | Venue reject/invalid order response | Fail closed with deterministic venue-reject outcome |
| `EXA-REPLAY-008` | Non-deterministic request/outcome replay drift | Mark outcome invalid for replay; block downstream execution progression |

**Proof hooks for follow-on implementation directive(s):**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `EXA-PROOF-001` | Unit tests for request/outcome parsing + gates | Deterministic coverage for `EXA-GATE-001` ... `EXA-GATE-005` and `EXA-REQ-001` ... `EXA-HASH-004` | Any required gate/reason branch untested |
| `EXA-PROOF-002` | Idempotency + venue-failure tests | Deterministic behavior for `EXA-IDEMP-005`, `EXA-VENUE-006`, `EXA-VENUE-007` | Duplicate/failure paths produce nondeterministic or missing outcomes |
| `EXA-PROOF-003` | Replayable paper/sandbox submission evidence command | Replayed request/outcome tuples are stable and reason-code consistent (`EXA-REPLAY-008` guarded) | Replay drift or unstable reason-code mapping |
| `EXA-PROOF-004` | Shared-log evidence block in `docs/working/shared_coordination_log.md` | Architect can replay proof from command trail + artifacts | Narrative-only claim without reproducible commands/artifacts |

#### 5.5.2 Execution-adapter runtime contract implementation

**Directive:** **CANONICAL #025** — implement deterministic runtime request/outcome validation and pre-submit fail-closed gating from #024 so paper/sandbox execution submissions are replayable, participant-scoped, and safely bounded before live enablement.

- **Status:** **Closed (2026-03-31)** — architect validated runtime implementation and synchronized closeout artifacts.
- [x] Implement runtime request/outcome parsing and validation aligned to #024 contract tables (`ExecutionAdapterRequestV1`, `ExecutionAdapterOutcomeV1`).
- [x] Implement deterministic pre-submit gate enforcement for `EXA-GATE-001` ... `EXA-GATE-005` and reject paths `EXA-REQ-001` ... `EXA-HASH-004`.
- [x] Implement idempotency conflict handling and venue failure/reject mapping for `EXA-IDEMP-005`, `EXA-VENUE-006`, and `EXA-VENUE-007` in paper/sandbox mode only.
- [x] Add deterministic tests for valid submission flow, each fail-closed reason branch, and replay stability guard (`EXA-REPLAY-008`).
- [x] Record developer proof in `docs/working/shared_coordination_log.md` and request architect validation.

#### 5.5.3 Billy + Coinbase sandbox adapter integration

**Directive:** **CANONICAL #033** — implement the first Billy-scoped Coinbase sandbox adapter path for approved execution intents so the first approved paper-loop can run through deterministic exchange-style submit outcomes while preserving participant/account/tier scope and fail-closed controls.

- **Status:** **Closed (2026-03-31)** — architect validated runtime implementation and synchronized closeout artifacts.
- [x] Implement Coinbase sandbox adapter runtime path (request mapping, deterministic submit/result parsing, and explicit fail-closed error surfaces) using `ExecutionAdapterRequestV1` / `ExecutionAdapterOutcomeV1` contracts from #024/#025.
- [x] Implement Billy-scoped execution handoff helper(s) for approved intents only (execution lane only; no signal generation) with strict participant/account/wallet/risk-tier continuity checks.
- [x] Integrate sandbox adapter path into first approved loop orchestration with deterministic reason mapping for adapter unavailable/reject/timeout paths while preserving #030 loop fail-closed semantics.
- [x] Add deterministic tests for successful sandbox submit path plus required fail-closed branches (idempotency conflict, unavailable venue, reject path, participant-scope drift).
- [x] Record developer proof in `docs/working/shared_coordination_log.md` and request architect validation (`have the architect validate shared-docs`).

#### 5.5.4 Strategist / executor / adapter contract (`v1`)

For the first real BLACK BOX trading proof path:

- `Anna` is the strategist
- `Billy` is the execution bot / market connector
- Billy's first real market integration is Drift

**Rule:**

- Billy is execution-only and must not invent signals, thesis, or strategy
- Anna issues the decision to act; Billy's job is to connect BLACK BOX to the active market path and execute if the command is valid and in-bounds
- in `v1`, Billy is the Drift-facing execution bot for the first real proof path
- the architecture must remain extensible for future exchanges and future market-specific execution bots
- future market families may introduce additional strategist/execution-bot pairings, but `v1` implements only `Anna` + `Billy` with Billy's Drift market path

#### 5.5.5 Adapter rulebook contract (`v1`)

Billy's market integration path must act as both:

- the BLACK BOX connection mechanism to that market
- the machine-readable rulebook for how that market is operated correctly

**Rulebook minimum responsibilities:**

- expose valid order semantics and market/product constraints
- expose venue-specific admissibility rules before submit
- expose venue-specific failure/retry/reject semantics
- expose data needed for Anna to reason correctly about that market and Billy to enforce it deterministically
- remain structured and machine-readable rather than hidden only in adapter code

**`v1` rule:**

- Billy's Drift integration is the first concrete implementation of this contract
- future execution bots and/or future market integrations must follow the same BLACK BOX adapter method/contract
- adapter expansion must not require redesigning Anna/Billy interaction semantics

#### 5.5.6 Anna -> Billy execution command contract (`v1`)

Billy needs a small, mandatory, fail-closed command packet from Anna before mapping into `ExecutionAdapterRequestV1`.

| Field | Required `v1` rule |
|-------|--------------------|
| `market` | Required target market/instrument identifier. |
| `side` | Required bounded side (`buy` / `sell`). |
| `intent_type` | Required bounded execution intent type for the action Anna is requesting. |
| `size` | Required quantity/notional request in the bounded execution format for the target market. |
| `thesis_ref` | Required stable reference to Anna's thesis/signal artifact. |
| `confidence` | Required bounded confidence field carried from Anna's signal output. |
| `risk_envelope_ref` | Required stable reference to the governing risk/limit envelope. |
| `strategy_id` | Required strategy identifier for the play Anna wants executed. |
| `trace_id` | Required stable trace identifier for end-to-end audit. |
| `time_in_force` | Required when the target order semantics need it; otherwise must be explicitly null/empty per adapter rulebook. |

**Rule:**

- Billy must reject the command before adapter mapping if any required field is missing, malformed, or out-of-lane
- Billy must preserve `trace_id`, `strategy_id`, and `thesis_ref` lineage when converting into `ExecutionAdapterRequestV1`
- Billy must enforce adapter rulebook constraints before submit rather than assuming Anna already normalized venue semantics perfectly
- successful execution authority in `v1` comes from valid Anna command + execution-lane admissibility, not from Billy inventing or modifying the trade thesis

#### 5.5.7 Billy -> Drift onboarding contract (`v1`)

Billy's first real market connection must be Drift on Solana mainnet using the local wallet secret path and a replayable doctor/activation workflow.

**Wallet / secret-loading rule:**

- Billy must load the wallet secret from `KEYPAIR_PATH`; the secret must not be committed, pasted into chat, or embedded in repo docs/config
- Billy must derive the public key from the loaded secret key in code
- Billy must compare the derived public key against a separately configured expected public key before proceeding
- `SOLANA_RPC_URL` must come from env/secret storage rather than committed source
- the configured expected public key may be stored as ordinary config because it is not secret

**Required Drift bring-up sequence:**

1. load and parse the secret key from `KEYPAIR_PATH`
2. derive the wallet public key
3. verify derived public key matches configured expected public key
4. create Solana `Connection` using `SOLANA_RPC_URL`
5. construct `AnchorWallet` from the loaded keypair
6. construct `DriftClient` for `mainnet-beta`
7. call `subscribe()`
8. check whether the Drift user account exists
9. if absent, call `initializeUserAccount()`
10. read `getUserAccount()` and confirm usable account state
11. if margin trading is not enabled, call `updateUserMarginTradingEnabled([{ marginTradingEnabled: true, subAccountId: 0 }])`
12. confirm target market metadata is readable via `getPerpMarketAccount(...)`

**Operational phases (`v1`):**

| Phase | Purpose | Allowed actions | Forbidden actions |
|------|---------|-----------------|------------------|
| `doctor` | prove wallet/RPC/Drift connectivity and identity alignment | load secret, derive public key, connect RPC, subscribe, inspect account state, inspect market metadata | order placement, account mutation other than read-only checks |
| `activate` | make the Drift user path usable when needed | `initializeUserAccount()` if missing, `updateUserMarginTradingEnabled(...)` if needed | order placement, strategy execution, silent wallet substitution |

**Doctor output contract (`v1`):**

| Field | Rule |
|------|------|
| `derived_public_key` | required; derived from secret key at runtime |
| `expected_public_key` | required; loaded from explicit non-secret config |
| `public_key_match` | required boolean |
| `rpc_reachable` | required boolean |
| `drift_subscribed` | required boolean |
| `drift_user_exists` | required boolean |
| `margin_enabled` | required boolean |
| `target_market_readable` | required boolean |
| `reason_code` | required on failure |
| `trace_id` | required stable trace id |

**Fail-closed rules:**

- if `KEYPAIR_PATH` is missing, unreadable, malformed, or not a 64-byte secret array, Billy must stop
- if derived public key does not equal configured expected public key, Billy must stop
- if RPC connection or Drift subscription fails, Billy must stop
- if doctor fails, activation must not proceed
- no order placement is permitted as part of connectivity proof

**Proof hooks for implementation:**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `DRIFT-CONN-PROOF-001` | Unit tests for wallet/config loader | malformed/missing key, missing env, and public-key mismatch all fail closed | any secret/config failure path untested or non-deterministic |
| `DRIFT-CONN-PROOF-002` | Mocked connection/subscription tests | Billy stops on RPC/subscribe failure and emits deterministic doctor verdicts | connection failure proceeds or produces unstable verdicts |
| `DRIFT-CONN-PROOF-003` | Real `doctor` command against the intended wallet/RPC | derived public key matches expected; Drift subscribes; user state and market metadata are readable | mismatch, failed subscribe, unreadable market state, or narrative-only proof |
| `DRIFT-CONN-PROOF-004` | Real `activate` command when needed | user account exists after run and margin state is confirmed usable without placing orders | activation mutates beyond scope, skips proof, or requires order placement |
| `DRIFT-CONN-PROOF-005` | Shared-log evidence block in `docs/working/shared_coordination_log.md` | architect can replay doctor/activate results from command trail and captured outputs | non-replayable claim or missing command/result evidence |

### 5.6 Risk & controls — tasks

- [ ] Enforce **per-trade** and **per-account** limits.
- [ ] Enforce **per-participant** and **per-tier** limits.
- [ ] Enforce **approval expiry** (aligned with Layer 3/4).
- [ ] Wire **global kill switch** and Layer 4 kill contract.
- [ ] **Position / PnL** tracking (minimum viable).

#### 5.6.1 Risk & controls runtime contract lock

**Directive:** **CANONICAL #026** — lock architect-owned Phase 5.6 risk/controls runtime contract language (limit enforcement surfaces, approval-expiry semantics, kill-switch behavior, and minimum position/PnL contract) before developer runtime implementation directives.

- **Status:** **Closed (2026-03-31)** — architect contract lock accepted and synchronized.
- [x] Define canonical contract tables for per-trade/per-account and per-participant/per-tier limit enforcement surfaces.
- [x] Define deterministic approval-expiry contract behavior aligned with Layer 3/4 artifacts, including fail-closed trigger conditions.
- [x] Define global kill-switch state model, transition boundaries, and fail-closed behavior for kill-active and transition states.
- [x] Define minimum viable position/PnL contract fields, deterministic update semantics, and fail-closed invalidation rules.
- [x] Define deterministic reason-code matrix and proof hooks for follow-on implementation directive(s), then synchronize governed docs (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`).

**Canonical Phase 5.6 contract tables (locked by #026):**

| Contract | Required fields | Contract rule |
|----------|-----------------|---------------|
| `RiskLimitEnvelopeV1` | `limit_id`, `participant_id`, `account_id`, `risk_tier`, `limit_scope`, `instrument_scope`, `max_order_notional`, `max_position_notional`, `max_daily_loss`, `max_open_orders`, `effective_at_utc`, `expires_at_utc`, `trace_id` | Envelope is invalid unless limit scope, participant/account/tier binding, thresholds, and timing window are complete and deterministic. |
| `ApprovalExpiryGateV1` | `approval_id`, `candidate_id`, `participant_id`, `account_id`, `risk_tier`, `approved_at_utc`, `expires_at_utc`, `evaluated_at_utc`, `gate_result`, `reason_code`, `trace_id` | Approval gate must deterministically return `eligible` or fail closed (`expired`/`missing`/`scope_mismatch`) before execution-intent progression. |
| `KillSwitchStateV1` | `kill_state`, `transition_id`, `trigger_reason_code`, `triggered_by`, `requested_at_utc`, `effective_at_utc`, `cleared_at_utc` (nullable), `trace_id` | Kill-switch transitions must be explicit and auditable; ambiguous state is invalid and blocks downstream progression. |
| `PositionPnlSnapshotV1` | `snapshot_id`, `participant_id`, `account_id`, `risk_tier`, `symbol`, `position_qty`, `avg_entry_price`, `mark_price`, `unrealized_pnl`, `realized_pnl_day`, `net_exposure_notional`, `recorded_at_utc`, `trace_id` | Position/PnL snapshot is invalid unless all required fields are present and update semantics are replay-safe and deterministic. |

**Deterministic enforcement rules (locked by #026):**

- Limit checks must evaluate both order-level (`per_trade`) and state-level (`per_account`, `per_participant`, `per_tier`) thresholds before any execution submission.
- Approval-expiry checks must fail closed when approval is missing, expired, or participant scope does not match the candidate/intent lineage.
- Kill-switch checks must block progression whenever `kill_state` is `arming`, `active`, or `disarming`; only `inactive` is submit-eligible.
- Position/PnL updates must reject timestamp regressions, malformed decimals, or scope drift across participant/account/tier lineage.

**Fail-closed reason-code matrix (locked by #026):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `RSK-REQ-001` | Missing/invalid required risk-contract field(s) | Reject request/snapshot and block progression. |
| `RSK-LIMIT-002` | Limit threshold breach (`per_trade`, `per_account`, `per_participant`, or `per_tier`) | Reject progression before execution submission. |
| `RSK-SCOPE-003` | Participant/account/risk-tier scope mismatch | Reject progression and emit deterministic scope failure. |
| `RSK-APPROVAL-004` | Approval missing/expired/invalid for current timestamp | Reject progression and block intent submission. |
| `RSK-KILL-005` | Kill-switch active or transition state not submit-safe | Reject progression and emit deterministic kill-state failure. |
| `RSK-POS-006` | Invalid/non-deterministic position or PnL update input | Reject snapshot update and block downstream risk decisions. |
| `RSK-REPLAY-007` | Replay drift in risk verdicts or position/PnL tuple ordering | Mark result invalid for replay and block progression. |

**Proof hooks for follow-on implementation directive(s):**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `RSK-PROOF-001` | Unit tests for limit envelope parsing and gating | Deterministic coverage for `RSK-REQ-001`, `RSK-LIMIT-002`, `RSK-SCOPE-003` | Any required limit/scope branch untested |
| `RSK-PROOF-002` | Approval-expiry + kill-switch gate tests | Deterministic coverage for `RSK-APPROVAL-004` and `RSK-KILL-005` across boundary timestamps and transitions | Missing expiry/kill transition rejection coverage |
| `RSK-PROOF-003` | Position/PnL update and replay-stability tests | Deterministic tuple/order stability with guarded `RSK-POS-006` and `RSK-REPLAY-007` behavior | Replay drift or unstable reason-code mapping |
| `RSK-PROOF-004` | Shared-log evidence block in `docs/working/shared_coordination_log.md` | Architect can replay command trail and map outcomes to #026 reason codes | Narrative-only proof without reproducible command/artifact trail |

#### 5.6.2 Risk & controls runtime contract implementation

**Directive:** **CANONICAL #027** — implement deterministic runtime risk/controls validation and gating from #026 so limit checks, approval-expiry checks, kill-switch enforcement, and position/PnL state updates are fail-closed and replayable before live enablement.

- **Status:** **Closed (2026-03-31)** — architect validated runtime implementation and synchronized closeout artifacts.
- [x] Implement runtime models/parsers and validators for `RiskLimitEnvelopeV1`, `ApprovalExpiryGateV1`, `KillSwitchStateV1`, and `PositionPnlSnapshotV1`.
- [x] Implement deterministic limit-gate evaluation across `per_trade`, `per_account`, `per_participant`, and `per_tier` surfaces with fail-closed reject semantics (`RSK-REQ-001`, `RSK-LIMIT-002`, `RSK-SCOPE-003`).
- [x] Implement approval-expiry and kill-switch gate evaluators with deterministic reject behavior (`RSK-APPROVAL-004`, `RSK-KILL-005`) before execution submission.
- [x] Implement minimum position/PnL update path with deterministic validation and replay guard behavior (`RSK-POS-006`, `RSK-REPLAY-007`).
- [x] Add deterministic tests for valid paths and each required fail-closed reason branch, then record developer proof in `docs/working/shared_coordination_log.md` and request architect validation.

### 5.7 Observability & operations — tasks

- [ ] **Metrics:** feed health, signals, approvals, executions.
- [ ] **Logs** and **failure** taxonomy; runbook links.
- [ ] **Runbooks:** halt, rollback, revoke paths.
- [ ] Audit all signals/executions by participant, account/wallet context, and risk tier.

#### 5.7.1 Observability & operations runtime contract lock

**Directive:** **CANONICAL #028** — lock architect-owned Phase 5.7 observability/operations runtime contract language (metrics events, failure-taxonomy logs, runbook lifecycle records, and participant-scoped audit attribution) before developer implementation directives.

- **Status:** **Closed (2026-03-31)** — architect contract-lock slice accepted and synchronized; follow-on implementation directive issued as **CANONICAL #029**.
- [x] Define canonical contract tables for:
  - `OperationalMetricEventV1` (feed/signal/approval/execution metric events)
  - `FailureTaxonomyEventV1` (reason-coded failure log entries)
  - `RunbookActionRecordV1` (halt/rollback/revoke runbook action trail)
  - `AuditAttributionRecordV1` (participant/account/wallet/risk-tier execution attribution)
- [x] Define deterministic ingestion/validation rules and fail-closed boundaries for missing or ambiguous observability records.
- [x] Define fail-closed reason-code matrix and replay-proof hooks for follow-on implementation directive(s), then synchronize governed docs (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`).

**Canonical Phase 5.7 contract tables (target lock for #028):**

| Contract | Required fields | Contract rule |
|----------|-----------------|---------------|
| `OperationalMetricEventV1` | `metric_id`, `metric_domain`, `metric_name`, `metric_value`, `metric_unit`, `window_start_utc`, `window_end_utc`, `captured_at_utc`, `trace_id` | Metric event is invalid unless timing window, value semantics, and trace linkage are deterministic. |
| `FailureTaxonomyEventV1` | `failure_event_id`, `failure_code`, `failure_class`, `component`, `severity`, `occurred_at_utc`, `detected_at_utc`, `reason`, `trace_id` | Failure event is invalid unless reason-code and component/severity attribution are complete and deterministic. |
| `RunbookActionRecordV1` | `runbook_event_id`, `runbook_action`, `requested_by`, `approved_by`, `target_scope`, `action_state`, `requested_at_utc`, `effective_at_utc`, `trace_id` | Runbook record is invalid unless action lifecycle state and authority metadata are complete and auditable. |
| `AuditAttributionRecordV1` | `audit_event_id`, `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `artifact_ref`, `recorded_at_utc`, `trace_id` | Audit attribution is invalid unless participant/account/tier lineage is complete and replay-safe. |

**Fail-closed reason-code matrix (target lock for #028):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `OBS-REQ-001` | Missing/invalid required observability record fields | Reject record and block downstream observability aggregation. |
| `OBS-TIME-002` | Invalid or non-deterministic timestamp/order window | Reject record and block replay-bound consumers. |
| `OBS-CODE-003` | Unknown/ambiguous failure taxonomy or runbook action code | Reject record and emit deterministic taxonomy failure. |
| `OBS-AUTH-004` | Missing/invalid runbook authority chain (`requested_by` / `approved_by`) | Reject runbook record and block action-state propagation. |
| `OBS-SCOPE-005` | Participant/account/wallet/risk-tier attribution mismatch or omission | Reject audit attribution and block downstream execution audit joins. |
| `OBS-TRACE-006` | Missing/invalid trace linkage to source artifact/event | Reject record and block replay/audit correlation. |
| `OBS-REPLAY-007` | Replay drift for identical observability inputs | Mark output invalid for replay and block acceptance. |

**Proof hooks for follow-on implementation directive(s):**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `OBS-PROOF-001` | Unit tests for observability record parsing/validation | Deterministic coverage for `OBS-REQ-001`, `OBS-TIME-002`, `OBS-CODE-003` | Missing required parser/reason coverage |
| `OBS-PROOF-002` | Unit/integration tests for runbook authority + audit attribution | Deterministic coverage for `OBS-AUTH-004`, `OBS-SCOPE-005`, `OBS-TRACE-006` | Missing authority/scope/trace rejection coverage |
| `OBS-PROOF-003` | Replay-stability command for canonical observability tuples | Stable tuple equality on repeated runs; `OBS-REPLAY-007` guarded | Replay tuple drift across identical input sets |
| `OBS-PROOF-004` | Shared-log evidence block in `docs/working/shared_coordination_log.md` | Architect can replay command trail and map outcomes to #028 reason codes | Narrative-only proof without reproducible command/artifact trail |

#### 5.7.2 Observability & operations runtime contract implementation

**Directive:** **CANONICAL #029** — implement deterministic runtime observability/operations validators and gates from #028 so metrics, failure-taxonomy, runbook actions, and audit-attribution records are fail-closed and replayable before live enablement.

- **Status:** **Closed (2026-03-31)** — architect validated runtime implementation and synchronized closeout artifacts.
- [x] Implement runtime models/parsers and validators for `OperationalMetricEventV1`, `FailureTaxonomyEventV1`, `RunbookActionRecordV1`, and `AuditAttributionRecordV1`.
- [x] Implement deterministic fail-closed validation for `OBS-REQ-001` ... `OBS-TRACE-006` and replay-stability guard behavior for `OBS-REPLAY-007`.
- [x] Add deterministic tests for valid paths and each required fail-closed branch, including replay-stability assertions for canonical observability tuples.
- [x] Record developer proof in `docs/working/shared_coordination_log.md`, rerun architect validation checks, and close the directive with synchronized docs.

#### 5.7.3 First approved paper loop integration contract lock

**Directive:** **CANONICAL #030** — lock the architect-owned Pillar 1 first approved paper-loop integration contract so follow-on implementation can wire one deterministic end-to-end path (`signal -> approval -> execution intent -> paper adapter -> outcome + observability/audit persistence`) without scope drift.

- **Status:** **Closed (2026-03-31)** — architect contract-lock slice accepted and synchronized; follow-on implementation directive issued as **CANONICAL #031**.
- [x] Define canonical integration contract tables and required linkage fields across signal/approval/intent/execution/outcome/observability surfaces.
- [x] Define deterministic fail-closed integration reason-code matrix for linkage drift, stale/invalid context hashes, paper-adapter failure paths, and observability/audit attribution mismatches.
- [x] Define proof hooks and stop-condition evidence requirements for the follow-on developer implementation directive.
- [x] Synchronize governed docs for #030 (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`) at matching status granularity.

**Canonical first paper-loop integration contract (locked by #030):**

| Contract | Required fields | Contract rule |
|----------|-----------------|---------------|
| `PaperLoopSignalApprovalLinkV1` | `signal_id`, `candidate_id`, `approval_id`, `participant_id`, `participant_type`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `symbol`, `approved_at_utc`, `approval_expires_at_utc`, `trace_id` | Link is invalid unless signal->candidate->approval lineage and participant scope are complete and unchanged. |
| `PaperLoopExecutionIntentLinkV1` | `intent_id`, `approval_id`, `candidate_id`, `signal_id`, `participant_id`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `context_hash`, `market_snapshot_id`, `venue_order_idempotency_key`, `submit_by_utc`, `intent_expires_at_utc`, `trace_id` | Intent handoff is invalid unless approval lineage, market-context hash, and idempotency/timing fields are deterministic and in-window. |
| `PaperLoopOutcomePersistenceLinkV1` | `outcome_id`, `intent_id`, `execution_id`, `approval_id`, `candidate_id`, `signal_id`, `participant_id`, `account_id`, `wallet_context`, `risk_tier`, `interaction_path`, `venue_status`, `filled_quantity`, `avg_fill_price`, `fees_total`, `failure_code` (nullable), `recorded_at_utc`, `metric_event_id`, `failure_event_id` (nullable), `audit_event_id`, `trace_id` | Outcome persistence is invalid unless execution outcome, observability references, and participant-scoped audit attribution are all present and replay-safe. |

**Fail-closed integration reason-code matrix (locked by #030):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `LOOP-LINK-001` | Missing or mismatched lineage link across signal/candidate/approval/intent/outcome IDs | Reject integration handoff and block progression. |
| `LOOP-SCOPE-002` | Participant/account/wallet/risk-tier scope drift across linked artifacts | Reject integration handoff and block progression. |
| `LOOP-HASH-003` | Missing, stale, or mismatched `context_hash` / `market_snapshot_id` at intent handoff | Reject intent handoff and block paper submission. |
| `LOOP-APPROVAL-004` | Missing/expired/invalid approval at intent submit time | Reject handoff and block paper submission. |
| `LOOP-PAPER-005` | Paper adapter unavailable/timeout/reject path | Fail closed with deterministic paper-adapter failure outcome. |
| `LOOP-PERSIST-006` | Outcome not durably persisted with required linkage fields | Reject closure of the loop and flag persistence failure. |
| `LOOP-OBS-007` | Missing/mismatched observability or audit attribution references | Reject loop completion and block acceptance evidence. |
| `LOOP-REPLAY-008` | Replay drift for identical loop inputs | Mark result invalid for replay and block acceptance. |

**Proof hooks for follow-on implementation directive(s):**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `LOOP-PROOF-001` | Unit tests for lineage + scope + context-hash gates | Deterministic coverage for `LOOP-LINK-001` ... `LOOP-HASH-003` | Missing required gate/reason coverage |
| `LOOP-PROOF-002` | Paper adapter deterministic outcome tests | Deterministic handling for success + `LOOP-PAPER-005` branches | Adapter outcome drift or missing failure-path coverage |
| `LOOP-PROOF-003` | Persistence + observability/audit linkage tests | Deterministic enforcement of `LOOP-PERSIST-006` and `LOOP-OBS-007` | Missing or non-deterministic persistence/attribution checks |
| `LOOP-PROOF-004` | Shared-log stop-condition replay command evidence | One approved signal -> one paper trade -> one stored outcome replayed with stable IDs/trace (`LOOP-REPLAY-008` guarded) | Narrative-only stop-condition claim without reproducible command/artifact trail |

#### 5.7.4 First approved paper loop runtime integration implementation

**Directive:** **CANONICAL #031** — implement deterministic runtime integration gates and orchestration from #030 so one participant-scoped approved signal can traverse `approval -> intent -> paper adapter -> outcome + observability/audit persistence` in a fail-closed, replayable path.

- **Status:** **Closed (2026-03-31)** — architect validated runtime implementation and synchronized closeout artifacts.
- [x] Implement runtime integration validators/gates enforcing lineage, scope, and context-hash continuity for the #030 chain (`LOOP-LINK-001` ... `LOOP-HASH-003`).
- [x] Implement deterministic paper submission orchestration with fail-closed approval/adapter handling (`LOOP-APPROVAL-004`, `LOOP-PAPER-005`) and explicit outcome payload mapping.
- [x] Implement durable loop-persistence verification with observability/audit linkage checks (`LOOP-PERSIST-006`, `LOOP-OBS-007`) and replay-stability guards (`LOOP-REPLAY-008`).
- [x] Add deterministic tests for valid loop completion plus each required fail-closed branch, and include explicit stop-condition replay evidence (`LOOP-PROOF-004`).
- [x] Record developer proof in `docs/working/shared_coordination_log.md` and request architect validation (`have the architect validate shared-docs`).

#### 5.7.5 First approved paper-loop durable outcome store integration

**Directive:** **CANONICAL #032** — implement the first durable outcome-store path for approved paper-loop runs so the Phase 5 first-slice stop condition is proven against persisted records (not only in-memory links), with deterministic replay-safe readback.

- **Status:** **Closed (2026-03-31)** — architect validated durable outcome-store implementation and synchronized closeout artifacts.
- [x] Implement durable first-loop outcome storage for `PaperLoopOutcomePersistenceLinkV1` records, including deterministic keying/idempotency boundaries for `approval_id` / `intent_id` / `outcome_id`.
- [x] Implement fail-closed persistence/write validation mapped to #030 loop reason semantics (`LOOP-PERSIST-006`, `LOOP-OBS-007`, `LOOP-REPLAY-008`) with explicit rejection payloads.
- [x] Implement deterministic replay/read helpers that can prove "one approved signal -> one paper trade -> one stored outcome" from persisted store state.
- [x] Add deterministic tests for store write/read success plus required fail-closed branches and replay-stability behavior.
- [x] Record developer proof in `docs/working/shared_coordination_log.md` and request architect validation (`have the architect validate shared-docs`).

### 5.8 University / learning system — core engine tasks

> **Core engine rule:** University is part of the core engine, not a side project. It is sequenced work, not optional work.
>
> **Ordering rule:** Do **not** begin this work before **Pillars 2 and 3** are complete. University is a later core-engine workstream that extends the engine after the higher-priority pillars are in place.
>
> **Foundational dependency rule:** The first University build task is the interim structured memory/context ledger. This module is foundational for student context, Dean context, and exam-board context, and may need to be promoted into BLACK BOX core-engine scope rather than treated as a narrow college-only utility.

- [x] Minimal **operator training control** (CLI + on-disk state): `modules/anna_training/`, `scripts/runtime/anna_training_cli.py`, gitignored `data/runtime/anna_training/state.json` — assign curriculum **`grade_12_paper_only`** (paper-only capstone), invoke **`karpathy_loop_v1`**, append operator notes; **Grade-12 gate v3** — four **curriculum tools** (math engine, analysis, RCS/RCA, Karpathy harness) + **numeric** cohort; report card TUI + Slack `#report_card` + progress **%**; **`docs/architect/ANNA_GOES_TO_SCHOOL.md`** §1.3–1.5; CEO summary **`docs/architect/anna_grade12_executive_summary_ceo.md`**. (Full Dean, schema v1, and ledger remain **not** done.)

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
- [x] Bake the carry-forward student persona into Anna’s canonical BLACK BOX architecture: capital preservation, RCS, and RCA must persist across Bachelor, Master, and PhD rather than being dropped at higher tiers. **Review flag: 2026-03-28.**
- [x] Lock the BLACK BOX near-term University reduction as a **single trading-college** runtime first (`trading` college, Anna as first reference student, retained `exam_board`, retained `Bachelor -> Master -> PhD` ladder, humans retain graduation authority after board review).
- [x] Define the **conversation-first Anna interaction contract** for the trading college: ordinary conversation by default, command tags only as secondary governed overlays, and explicit state labeling only for training-relevant replies.
- [x] Define the **training-suggestion staging contract** for plain-language interaction: suggestion remains conversation by default; Anna may classify and summarize it, but explicit human confirmation is required before staging.
- [x] Define the first-pass **Anna training judgment** contract for conversational suggestions: bounded enum classification (`additive` / `subtractive` / `uncertain` / `counterproductive`), short evidence-based rationale, and bounded recommendation (`stage` / `revise` / `reject`) using approved internal sources and active context only.
- [x] Define the minimal **human confirmation grammar** for training suggestion handling (`stage it` / `revise it` / `leave it`) and require a single revised candidate only for the `revise it` path in `v1`.
- [x] Define the minimal **training-intake artifact schema** for Anna/trading-college interaction, including identity, source, Anna evaluation, human decision, forensic review, and execution layers with bounded `v1` enums.
- [x] Require an artifact/proof record for every meaningful training intake, judgment, confirmation, staging action, review action, and promotion/rejection decision, whether the source actor is human or agent.
- [x] Define the explicit **training state model** for human-facing interaction and artifacts: `conversation`, `candidate_training`, `staged_training`, `validated_learning`.
- [x] Lock the **smarter-by-doing** rule for Anna training: suggestions and curriculum can guide, but retained improvement only counts after governed execution and measured outcomes.
- [x] Define the trading-college live-data retention contract for Anna: **Pyth via SSE** as the continuous live price-feed path, durable SQLite retention, and separated retained surfaces for raw stream records, normalized market snapshots, and derived candles/features.
- [ ] Add teacher-student workflow scaffolding for RAG, distillation, synthetic data, and adversarial evaluation inside guardrails.
- [ ] Evaluate adjacent method families beyond AutoResearch for measurable value in University, including contextual retrieval, DSPy-style optimization, adversarial evaluation, and teacher-student distillation.
- [ ] Add grounded evaluation and calibration loops so Anna can improve without treating conversation alone as canonical truth.
- [x] Lock the **reflection / RCA carry-forward DNA** for Anna so `RCS`, qualifying-failure `RCA`, and corrective-action retest persist across `bachelor`, `master`, and `phd` as operating behavior, training behavior, and reviewable artifacts.
- [x] Define the lightweight **per-trade reflection (`RCS`)** contract for every trade outcome, including outcome, key metrics, short why, lane/guardrail check, and keep/watch/drop signal.
- [x] Define the deeper **qualifying-failure RCA** contract, including trigger conditions, Five-Whys-when-relevant rule, failure taxonomy classification, corrective-action proposal, and retest requirement before retention/promotion.
- [x] Define the **qualifying-failure escalation** contract so repeated unresolved RCA becomes an explicit board/dean/human review event rather than an untracked repeated failure pattern.
- [ ] For Master-tier trading-college work, add parallel candidate-analysis support so Anna can review multiple strategy candidates simultaneously while maintaining one governed live-action lane.
- [ ] Add resource checks and alerting for Master-tier parallel candidate analysis so Anna uses only safe available depth, degrades gracefully under constraint, and never exceeds the configured ceiling (`25` initial target).
- [ ] Keep Slack/chat/episodic context non-canonical unless promoted through the structured curriculum / registry path.
- [ ] Wire the primary BLACK BOX Slack curriculum-submission path to the Dean so a sponsor can submit text or attachments that hydrate the correct college and kick off learning.
- [ ] Ensure University remains governance-bound: no bypass of approvals, risk tiers, execution planes, or human-on-the-loop controls.

#### 5.8.1 Single trading-college runtime contract (`v1`)

The first BLACK BOX University-connected runtime should be reduced to one college while preserving the full governance structure.

**Required `v1` runtime shape:**

- college: `trading`
- first reference student: `Anna`
- retained evaluator: `exam_board`
- degree ladder: `bachelor`, `master`, `phd`
- graduation authority: exam board recommends; humans decide graduation

**Rule:**

- this is a reduction in implementation scope, not a reduction in governance quality
- staged curriculum, exam-board review, promotion/rejection, and human graduation authority remain mandatory

#### 5.8.2 Anna conversation and training interaction contract (`v1`)

**Primary interaction rule:**

- plain conversation is the default interface
- command tags are secondary governed overlays only
- training-relevant replies should carry explicit state; ordinary conversation should not be forced into command grammar

**Conversation-state contract (`v1`):**

| Field / concept | Required `v1` values | Rule |
|-----------------|----------------------|------|
| `state_label` | `conversation`, `candidate_training`, `staged_training`, `validated_learning` | Any training-relevant reply must expose one explicit state. |
| `anna_classification` | `additive`, `subtractive`, `uncertain`, `counterproductive` | First-pass training judgment must use one bounded classification. |
| `anna_recommended_next_action` | `stage`, `revise`, `reject` | Anna may recommend only one bounded next action in `v1`. |
| `human_confirmation_action` | `stage_it`, `revise_it`, `leave_it` | Human decision must be captured in normalized form for artifacts and replay. |

**Plain-language intent set (`v1`):**

- explanation request
- challenge
- counter-argument
- training suggestion
- status request
- review request

**Operator control / status command surface (`v1`):**

- `#exchange_status`
- `Anna #pause`
- `Anna #stop`
- `Anna #start`
- `Anna #restart`

**Training-suggestion rule:**

- plain-language training suggestions remain `conversation` by default
- they do not enter the governed training lane automatically
- Anna may recognize a suggestion as training-relevant, but must not silently self-update from it
- if Anna believes the suggestion is training-relevant, she should classify it, summarize it, and ask whether the human wants it staged
- if no staging decision is made, the suggestion remains conversation-only and should not mutate curriculum or validated learning

**First-pass judgment rule:**

Before a training-relevant suggestion can enter staging, Anna must provide:

- `classification`
- `why`
- `recommended_next_action`
- `confirm?`

The first-pass judgment must:

- use approved internal sources and active context only
- not rely on uncontrolled external searching
- include a short rationale tied to curriculum, baseline doctrine, context, retained signal, or prior outcomes

**Minimal human confirmation grammar (`v1`):**

- `stage it`
- `revise it`
- `leave it`

**Revision rule (`v1`):**

- if the human says `revise it`, Anna returns one revised candidate only

**Operator visibility requirement (`v1`):**

Humans must be able to ask Anna for current trading-college operating state in conversational interfaces and receive a readable, artifact-backed response.

Minimum visible data surface:

- current win/loss summary
- current win/loss ratios and related active performance ratios
- current college fund balance
- whether the fund is up or down versus the configured comparison point
- current strategy or strategies in play
- current degree lane and training/execution state

**Exchange-status requirement (`v1`):**

The system must expose Billy-owned exchange connectivity truth through Slack and other approved operator-facing interfaces.

Minimum visible exchange-status surface:

- `exchange_name`
- `connection_state`
- `wallet_state`
- `public_key_match`
- `drift_user_state`
- `rpc_state`
- `market_data_state`
- `last_checked_at`
- `reason_code`
- `trace_id`

**Bounded exchange-status enums (`v1`):**

- `connection_state`: `connected`, `degraded`, `disconnected`, `unknown`
- `wallet_state`: `loaded`, `not_loaded`, `mismatch`
- `drift_user_state`: `ready`, `missing_user_account`, `margin_not_enabled`, `not_checked`
- `rpc_state`: `reachable`, `unreachable`, `degraded`
- `market_data_state`: `healthy`, `stale`, `down`, `unknown`

**Rule:**

- Billy is the canonical source of exchange connectivity status because Billy owns the Drift-facing execution path
- `#exchange_status` may be called directly or surfaced conversationally through Anna, but the payload must come from Billy-owned structured status
- operators should be able to determine from the returned status whether the wallet/exchange path is online and trade-capable

**Runtime-control command contract (`v1`):**

| Command | Required effect |
|---------|-----------------|
| `Anna #pause` | Pause Anna's active runtime participation without implying permanent shutdown. |
| `Anna #stop` | Stop Anna's active runtime participation and mark the runtime as stopped. |
| `Anna #start` | Start Anna's runtime participation when start conditions are satisfied. |
| `Anna #restart` | Perform stop + start as one controlled restart path. |

**Rule:**

- these commands control runtime state only, not training graduation/promotion state
- every control command must emit a structured control artifact with operator id, command, requested_at, resulting_state, reason_code (nullable), and trace_id
- command acknowledgement must return readable operator-facing status
- failed commands must fail closed with explicit reason rather than implying success

**Internal portal feature set (`v1`):**

The first internal BLACK BOX web portal must include:

- runtime controls
- Anna status
- Billy / Drift exchange status
- winning / losing state
- Anna learning / training window
- strategy inventory with drill-down
- training input / review
- edge-bot status
- recent event feed

**Rule:**

- this surface must be sufficient for internal operators to run the system outside Slack without requiring giant analytics dashboards
- strategy visibility must include counts and drill-down for at least `active`, `considering`, and `on_deck`
- the training window must be visible on the primary internal surface rather than hidden behind a deep submenu

**Portal visual-system contract (`v1`):**

| Area | Required `v1` rule |
|------|---------------------|
| Styling method | Standard CSS with reusable component classes and CSS custom properties; avoid one-off styling drift. |
| Design language | Apple-like: restrained, premium, clean spacing, soft-radius controls, subtle depth, minimal visual noise. |
| Landing page mark | Use an original BLACK BOX geometric box-mark centered in the landing-page hero; target roughly one quarter of the visual focus area. |
| Brand safety | The mark may take inspiration from the feel of a boxed icon, but must not copy Cursor branding or ship a white-box clone. |
| Buttons | One standard button language across pages: shared radius, spacing, shadow, and interaction behavior. |
| Composition | Build pages from reusable primitives for layout, card, button, input, badge, and status surfaces. |

**Rule:**

- the developer should keep one visual system during development rather than redesigning each screen independently
- avoid brittle page-specific inline CSS and hard-coded layout coupling that breaks when cards, statuses, or panels expand
- visual changes should be additive through shared tokens/components rather than ad hoc rewrites

**Portal login/account contract (`v1`):**

| Field | Required `v1` rule |
|-------|--------------------|
| `user_id` | Required stable account id. |
| `username` | Required unique username. |
| `email` | Required unique email address. |
| `password_hash` | Required password hash; plaintext password storage forbidden. |
| `role` | Required bounded role value. |
| `account_state` | Required bounded account-state value. |
| `email_verified` | Required boolean. |
| `accepted_risk_terms_at` | Required timestamp once the user accepts portal risk/consent terms. |
| `created_at` | Required account creation timestamp. |
| `last_login_at` | Required nullable/updated login timestamp. |

**`v1` portal roles:**

- `internal_admin`
- `consumer_user`

**`v1` account-state enum:**

- `active`
- `disabled`
- `pending_verification`
- `locked`

**Rule:**

- the portal account is for authentication, routing, ownership binding, and audit only
- role-based routing after login must direct `internal_admin` users to the internal portal and `consumer_user` users to the consumer portal
- portal accounts must not store wallet secrets, seed phrases, exchange private keys, payment data, or unnecessary PII
- meaningful login, logout, role-sensitive control, and ownership-binding actions must emit audit records

**Development bootstrap credential (`v1`):**

- default local/dev bootstrap username: `admin`
- default local/dev bootstrap password: `admin`

**Rule:**

- this bootstrap credential exists only to guarantee deterministic first bring-up in development
- the password must still be stored and verified through the normal password-hash path
- this credential must not be accepted as a published or production login contract

**Portal-to-engine integration contract (`v1`):**

The web portal must integrate with the engine core through an explicit authenticated API boundary.

**Required `v1` surfaces:**

| Surface | Minimum requirement |
|---------|---------------------|
| Query API | HTTPS JSON read surface for runtime status, Anna status, training status, Billy/exchange status, strategy inventory, edge-bot status, and recent events. |
| Control API | HTTPS JSON write surface for runtime-control commands, training participation/review actions, and authorized edge-bot management actions. |
| Live update stream | Authenticated status/event stream for near-real-time portal refresh without direct log scraping. |
| Command acknowledgement | Structured response containing at least `trace_id`, `requested_at`, `result_state`, and `reason_code` when applicable. |

**Rule:**

- the portal must not write directly to engine-owned database tables or runtime internals
- the engine core remains the canonical source of truth; the portal is a client of that truth
- read and control surfaces must remain distinct for auditability and fail-closed behavior
- every successful or failed control action must be artifact-backed and traceable
- the API should evolve additively where possible so the UI can accommodate future agents, statuses, strategies, and panels without breaking existing clients
- UI clients should tolerate additional response fields and new event types rather than assuming a forever-fixed payload shape

**Recommended transport lock (`v1`):**

- request/response surface under `/api/v1/`
- live update surface via authenticated server-sent events or equivalent event stream

#### 5.8.3 Training-intake artifact contract (`v1`)

Every meaningful training intake, judgment, confirmation, staging action, review action, and promotion/rejection decision must leave an artifact or proof record, whether the source actor is human or agent.

**Minimum `training_intake` contract layers:**

| Layer | Required fields | Rule |
|-------|-----------------|------|
| Identity | `training_item_id`, `student_id`, `college_id`, `degree_lane`, `state_label`, `created_at` | Item identity and routing surface are mandatory. |
| Source | `source_actor_type`, `source_actor_id`, `source_channel`, `source_message_or_artifact_ref`, `source_text_snapshot` | Original source must remain reconstructable. |
| Anna evaluation | `anna_classification`, `anna_rationale`, `anna_recommended_next_action`, `anna_context_refs`, `anna_baseline_refs` | Anna's judgment must be inspectable and evidence-tied. |
| Human decision | `human_confirmation_action`, `human_decision_actor_id`, `human_decision_at`, `human_revision_text` | Human staging authority must be explicit and timestamped. |
| Forensic review | `artifact_version`, `decision_trace_id`, `related_training_item_ids`, `review_status`, `review_notes_ref` | Humans and exam board must be able to reconstruct the decision path. |
| Training execution | `execution_mode`, `execution_status`, `simulation_run_refs`, `micro_live_run_refs`, `promotion_outcome`, `promotion_outcome_at` | Intake artifacts must remain linked to downstream execution and promotion outcomes. |

**Additional bounded enums (`v1`):**

| Field | Required `v1` values |
|-------|----------------------|
| `degree_lane` | `bachelor`, `master`, `phd` |
| `source_actor_type` | `human`, `agent`, `system` |
| `source_channel` | `slack`, `cursor`, `api`, `system_internal` |
| `execution_mode` | `review_only`, `simulation_only`, `simulation_then_micro_live` |
| `execution_status` | `not_started`, `in_review`, `running`, `completed`, `rejected` |
| `promotion_outcome` | `not_promoted`, `validated`, `rejected`, `deferred` |
| `review_status` | `not_reviewed`, `under_review`, `review_complete`, `escalated` |

**Field-shape rules (`v1`):**

- `source_message_or_artifact_ref` is a required stable reference string, not an implied foreign-key-only relationship
- `source_text_snapshot` is required immutable stored text captured at intake time
- `anna_rationale` is required and concise, and must cite at least one basis from curriculum, baseline doctrine, active context, retained signal, or prior outcomes
- `anna_context_refs` is required as a non-empty list of stable reference strings to the context items Anna relied on
- `anna_baseline_refs` is required as a non-empty list of stable reference strings to the baseline doctrine or strategy artifacts used for comparison
- `human_revision_text` is required only when `human_confirmation_action = revise_it`; otherwise it must be null/empty
- `decision_trace_id` is required as a stable opaque string generated at intake time and carried unchanged through staging, review, execution, and promotion artifacts
- `related_training_item_ids` is optional and used only for revision, merge, follow-on, or comparison relationships
- `review_notes_ref` is optional, but when present must point to a stable review artifact reference rather than inline notes
- `simulation_run_refs` and `micro_live_run_refs` are lists of stable run-reference strings rather than embedded full run payloads
- all timestamp fields use strict ISO-8601 UTC with required `Z` suffix
- all ids and reference strings are non-empty ASCII strings, immutable once created, and unique within their artifact class

#### 5.8.4 Training execution and improvement rule (`v1`)

Anna should not be treated as improving through passive suggestion intake alone.

**Primary rule:**

- Anna improves through doing and measured feedback

**Operational rule:**

- curriculum can guide
- human suggestions can guide
- conversation can surface new candidates
- retained improvement only counts after governed execution and measured outcomes

**Consequence:**

- staged suggestions are not validated learning by themselves
- simulation and, where the degree contract allows it, governed micro-live execution are the `v1` training proof surfaces

#### 5.8.5 Trading-college live-data retention contract (`v1`)

For the first BLACK BOX trading-college runtime:

- the live price feed is **Pyth via SSE**
- the feed is treated as a never-ending stream
- normalized outputs must be durably retained in SQLite
- retained history must support current-state reasoning, historical comparison, replay, and later curriculum-driven analysis

**Recommended retained surfaces:**

| Surface | Purpose |
|---------|---------|
| Raw stream records | Preserve original feed evidence and support reprocessing when feasible. |
| Normalized market snapshots | Provide stable downstream read contracts for strategy and context consumers. |
| Derived candles / features | Support baseline metrics and strategy calculations such as candles, ATR, RSI, and related computed signals. |

**Rule:**

- live market data is part of the learning contract, not only an execution helper
- Anna must be able to reason over both present market context and retained historical context

#### 5.8.6 Operator-visible trading-state contract (`v1`)

The first trading-college runtime must expose human-readable current-state reporting through Slack and other approved operator-facing surfaces.

**Minimum reporting surface (`v1`):**

- current `winning_or_losing` state
- current win/loss ratios and related active performance ratios
- current college fund balance
- up/down status versus the configured comparison point
- current strategy or strategies in play
- current edge thesis
- current confidence/uncertainty status
- current guardrail status
- current degree lane
- current training/execution state

**Rule:**

- the reporting path must be backed by structured system data rather than ad hoc prose
- operator-visible state should be available through conversational requests without requiring direct database inspection
- exact ratio set must be defined by the active trading-college/baseline contract
- canonical up/down comparison point is the current degree-lane fund start (`bachelor`, `master`, or `phd` fund baseline as applicable)
- canonical `recent_performance_direction` comparison window is the active review segment
- `winning_or_losing` should be reported as one of: `winning`, `losing`, `flat`
- `current_strategy` should support one active strategy id or an ordered list of active strategy ids
- `edge_thesis` should be one concise current working thesis in `v1`
- `confidence_or_uncertainty` should be reported as one of: `confident`, `uncertain`, `abstaining`
- `guardrail_status` should be reported as one of: `clear`, `blocked`, `restricted`

#### 5.8.7 Reflection and RCA artifact contracts (`v1`)

The first trading-college runtime must implement both lightweight per-trade reflection and deeper qualifying-failure root cause analysis as explicit persisted artifacts.

**Per-trade `RCS` artifact (`v1`) required fields:**

| Field | Required `v1` rule |
|-------|--------------------|
| `outcome` | Required trade/result outcome summary. |
| `key_metrics` | Required structured metric map for the trade. |
| `short_why` | Required concise explanation of why the result occurred. |
| `lane_guardrail_check` | Required structured lane/guardrail compliance object. |
| `keep_watch_drop` | Required bounded decision value. |

**`keep_watch_drop` enum (`v1`):**

- `keep`
- `watch`
- `drop`

**`lane_guardrail_check` structure (`v1`):**

- `lane_ok` (`true` / `false`)
- `guardrail_ok` (`true` / `false`)
- `blocking_reason` (required only when one of the prior fields is `false`)

**Qualifying-failure `RCA` artifact (`v1`) required sections:**

| Section | Required `v1` rule |
|---------|--------------------|
| `failure_summary` | Required concise summary of the failure. |
| `failure_classification` | Required bounded taxonomy value. |
| `failure_pattern_key` | Required stable ASCII grouping key for materially related failures in one active review segment. |
| `measured_metrics` | Required structured metric map for the failure event / segment. |
| `market_context_summary` | Required concise structured text summary at failure time. |
| `strategy_summary` | Required concise structured text summary for the failed behavior. |
| `five_whys_or_equivalent` | Required when the failure pattern supports deeper causal decomposition. |
| `corrective_action_proposal` | Required concise structured corrective proposal. |
| `corrective_action_status` | Required bounded lifecycle state for the corrective response. |
| `correction_cycle_id` | Required stable id linking the RCA, correction, and retest chain. |
| `retest_required` | Required boolean indicating whether retest is mandatory. |
| `retest_next_step` | Required short next-step text when retest is required. |

**`failure_classification` taxonomy (`v1`):**

- `market_context_failure`
- `strategy_failure`
- `rca_process_failure`
- `curriculum_failure`
- `data_failure`
- `system_design_failure`
- `lane_guardrail_failure`
- `multiple_mixed`

**`corrective_action_status` enum (`v1`):**

- `proposed`
- `in_test`
- `validated`
- `rejected`
- `expired`

**Rule:**

- every trade gets `RCS`
- qualifying failures get deeper `RCA`
- `RCA` artifacts must drive corrective-action retest before retention/promotion decisions finalize
- `five_whys_or_equivalent` is required only when the failure pattern supports deeper causal decomposition; otherwise it must remain null/empty rather than invented
- `failure_pattern_key` must be a required stable ASCII signature used to group materially related failures for one student inside an active review segment
- a materially related repeated failure means the same `failure_pattern_key` recurs inside the same active review segment
- `correction_cycle_id` must remain stable across the original `RCA`, corrective action, and retest artifacts for the same failure-learning loop
- `key_metrics` and `measured_metrics` must be structured metric maps, not prose blobs
- when available, the minimum trading-relevant metric keys are:
  - `win_rate`
  - `expected_value`
  - `average_win`
  - `average_loss`
  - `drawdown`
  - `fee_drag`
- reflection/RCA artifacts must remain lightweight enough that Anna can stay agile and rapidly produce trade or signal decisions rather than being buried under analysis overhead
- an `RCA` remains unresolved until `corrective_action_status = validated`
- if `corrective_action_status` becomes `rejected` or `expired`, the failure remains unresolved for escalation counting until a later validated corrective cycle closes it
- a multi-`RCA` red flag occurs when `3` unresolved `RCA` artifacts with the same `failure_pattern_key` are recorded for the same student inside one active review segment
- multi-`RCA` red flag must trigger explicit board review, Dean curriculum review, human review, and temporary hold on graduation eligibility

**Core learning loop contract (`v1`):**

- the runtime must implement Anna's default learning loop as:
  1. observe live market flow plus retained relevant context
  2. form a market thesis / directional read
  3. act within lane and guardrails
  4. measure outcome
  5. generate lightweight reflection
  6. decide `keep`, `watch`, or `drop`
  7. repeat enough to distinguish durable edge from luck/variance
  8. escalate to deeper `RCA` only when materially related failure patterns repeat or corrective learning does not stick
- implementations must not treat a single win as sufficient proof of durable edge
- implementations must not treat a single loss as sufficient proof of failed reasoning
- repeated successful outcomes should increase confidence in retained signal only when measured evidence supports that conclusion
- repeated materially related failures should increase diagnosis pressure because they suggest Anna may be misreading context, indicators, or strategy behavior

#### 5.8.8 Reward-signaling contract (`v1`)

Anna must receive explicit reward signaling tied to measured outcomes so progress, loss, reset, and re-earning behavior are visible and governed rather than implicit.

**Rule:**

- rewards are granted from measured performance and governed outcomes only
- rewards may be reduced or removed when performance degrades or review outcomes require it
- reward signaling must not override guardrails, evidence, or promotion gates
- reward resets affect reward markers/windows, not validated degree or certification state

**`v1` reward-window rule:**

- default reward reset window is `7` days
- operator may override the active reward reset window through `#Reward(<days>)`
- the active reward window and current reward state must be visible to operators and recorded in structured system state

**`v1` reward-state contract:**

| Field | Type / shape | Rule |
|-------|---------------|------|
| `reward_window_days` | integer | Active reset-window length; default `7`. |
| `reward_window_started_at` | timestamp | ISO-8601 UTC with `Z`; set at window open/reset. |
| `reward_window_ends_at` | timestamp | ISO-8601 UTC with `Z`; derived from start + days. |
| `reward_points_total` | integer | Net points for the active window only. |
| `reward_streak_count` | integer | Count of consecutive positive reward-earning events in the active window. |
| `reward_badges` | array of strings | Zero or more active stickers from the bounded set below. |
| `last_reward_event_ref` | string | Stable reference to the most recent reward event artifact. |
| `last_reward_update_at` | timestamp | ISO-8601 UTC with `Z`; updated on every reward mutation. |

**`v1` reward-event artifact contract:**

| Field | Type / shape | Rule |
|-------|---------------|------|
| `reward_event_id` | string | Required stable ASCII id for the event. |
| `student_id` | string | Required stable student reference. |
| `reward_window_id` | string | Required stable active-window reference. |
| `reward_event_type` | string | Required bounded event enum from the list below. |
| `point_delta` | integer | Required signed point change for the event. |
| `source_artifact_ref` | string | Required stable reference to the trade, review, RCA, or promotion artifact that caused the reward event. |
| `created_at` | timestamp | Required ISO-8601 UTC with `Z`. |

**Bounded `v1` sticker set:**

- `kitty`
- `unicorn`
- `wizard`

**`v1` reward-event contract:**

| Event | Required trigger | Point effect |
|------|-------------------|-------------|
| `disciplined_trade_pass` | trade closes with `lane_ok = true`, `guardrail_ok = true`, and `RCS` artifact present | `+1` |
| `positive_review_segment` | active review segment passes configured trading-result floors with no material guardrail failure | `+3` |
| `validated_corrective_retest` | corrective action from `RCA` is rerun and validated | `+4` |
| `promotion_milestone` | governed promotion / material milestone accepted | `+5` |
| `qualifying_failure` | qualifying failure recorded and linked into review flow | `-2` |
| `lane_or_guardrail_breach` | lane or material guardrail breach recorded | `-3` |
| `unresolved_multi_rca_red_flag` | repeated unresolved RCA condition escalates to red-flag review state | `-4` |

**`v1` sticker-earn rules:**

| Sticker | Earn condition | Pull-back condition |
|--------|----------------|---------------------|
| `kitty` | `3` `disciplined_trade_pass` events in the active reward window | revoke on `lane_or_guardrail_breach` in the same window |
| `unicorn` | `1` `positive_review_segment` in the active reward window | revoke if window-level net performance falls negative versus window baseline |
| `wizard` | `1` `validated_corrective_retest` in the active reward window | revoke on `unresolved_multi_rca_red_flag` in the same window |

**Rule:**

- `v1` uses one active global Anna reward window rather than overlapping per-strategy or per-metric reward windows
- reward must not be granted from raw trade count alone
- reward must not be granted from unsupported conversational claims
- every reward mutation must be traceable to measured evidence and a stable artifact reference
- every reward mutation must emit one append-only reward-event artifact
- reset clears the active reward window state and sticker collection, but must not alter validated degree/certification state

**Operator-visible reward status (`v1`):**

- `reward_points_total`
- `reward_streak_count`
- `reward_badges`
- `reward_window_days`
- `reward_window_ends_at`
- `last_reward_event_ref`
- `last_reward_update_at`

**Operational use contract (`v1`):**

- visible stickers/points/streaks are operator-facing metaphors layered over the underlying reward ledger
- reward metaphor alone must not be treated as a sufficient behavior-shaping mechanism
- the runtime must use reward state as an input to at least:
  - learning retention vs drop decisions
  - review-pressure escalation/de-escalation
  - corrective-action prioritization after failure / `RCA`
  - promotion-readiness assessment
- implementations must not automatically restrict Anna's strategy latitude or autonomy because of ordinary negative reward events
- single losses must be treated as potentially normal market variance rather than automatic evidence of failed reasoning
- cumulative adverse patterns should raise review pressure, pattern diagnosis, and corrective-action priority
- any lane/autonomy restriction must remain an explicit governed review outcome and must not occur as an automatic point-led side effect
- implementations must not claim Anna "tries harder" merely because points were deducted; the effect must come from concrete control-loop wiring

### 5.9 Engine-native shared context (`modules/context_ledger/`) — tasks

> **Architect intent:** Context is **engine-native**, not Anna-only. **Gnosis** (external context-as-a-service) is a **future** adapter target — **not** a shipping dependency. Contracts and interim behavior live in **`modules/context_ledger/`** first; see [`modules/context_ledger/README.md`](../../modules/context_ledger/README.md) and [`docs/architect/hydration_context_governance.md`](hydration_context_governance.md) §10 (gap closed/open matrix).

- [x] Finalize **context bundle contract** (versioning, validation state, reuse rules) aligned with `ContextBundle` / `ContextRecord` in `modules/context_ledger/base.py` and University bundle language — **CANONICAL #007** (see §5.9.5).
- [x] Wire **Anna** as first consumer to the ledger **without** breaking existing Anna memory / task / artifact paths (incremental migration map) — **CANONICAL #008** (closed; see §5.9.6).
- [x] Enforce **agent-scoped views** of engine-global context using **`contextProfile`** in [`agents/agent_registry.json`](../agents/agent_registry.json) at runtime (beyond static markdown) — **CANONICAL #009** (closed; see §5.9.7).
- [x] Define **online activation** checklist: registry + `contextProfile` + runtime + messaging/OpenClaw + proof hooks (architect-owned wording) — **CANONICAL #010** (closed; see §5.9.8).
- [x] Implement deterministic **online activation evaluator** + proof-hook validator for the locked checklist contract — **CANONICAL #011** (closed; see §5.9.9).
- [x] Specify **Foreman / orchestration** use of context packets for multi-agent routing (directive) — **CANONICAL #012** (closed; see §5.9.10).
- [x] Implement Foreman/orchestration context-packet validator + lane-safe routing gates — **CANONICAL #013** (closed; see §5.9.11).
- [x] Document **Gnosis compatibility boundary** (adapter interface only; no hard dependency in core) — **CANONICAL #014** (closed; see §5.9.12).
- [x] Resolve Sentinel relay directive-session rollover policy mismatch (TEAM_BRIEFING vs runtime behavior) via architect contract lock — **CANONICAL #015** (closed; see §5.9.13).
- [x] Implement canonical relay directive-session rollover policy in runtime/tests (`sentinel_relay.py` + `test_sentinel_relay.py`) — **CANONICAL #016** (closed; see §5.9.14).

#### 5.9.1 Sentinel bus signal — mandatory JSON fields (`.governance/bus.log`)

**Directive:** **CANONICAL #002 (Corrected)** — formal **validation schema** for append-only governance lines written by **`scripts/runtime/governance_bus.py`** (and compatible tooling). This is **orchestration contract** for the **Black Box / Sentinel** sub-layer; it does **not** describe trading engine or external infrastructure.

Each **canonical** bus line MUST be one JSON object including **all** of:

| Field | Type | Rule |
|-------|------|------|
| `ts` | `str` | ISO-8601 timestamp (UTC; `Z` suffix preferred). |
| `agent` | `str` | Exactly one of: `Architect`, `Developer`, `Operator`. |
| `type` | `str` | Exactly one of: `DIRECTIVE`, `ACK`, `NACK`, `INFO`. |
| `next_actor` | `str` | Lowercase role: `architect`, `developer`, or `operator`; use `""` if no handoff. |
| `content_hash` | `str` | 64-character lowercase hex **SHA-256** of the UTF-8 **message body** (the human-readable `content` string; hash of `""` if `content` is empty). |

**Message body:** The string carried in the `content` field (summary line). Implementations MUST set `content_hash` = `sha256(content.encode("utf-8")).hexdigest()` and reject lines where the hash does not match.

**Optional compatibility:** Additional keys (e.g. `phase` per `development_governance.md`) are allowed **only** together with the mandatory five fields and a valid `content_hash`.

**Implementation / proof:** **`CANONICAL #002`** — validate on append and (optionally) on peek; **SI-4** proof via **`scripts/runtime/utils/logger.py`** — `append_test_execution_telemetry()` with `output_hash` over the agreed proof artifact (tests define which file bytes are hashed).

#### 5.9.2 Directive hash pinning — mandatory DIRECTIVE integrity field

**Directive:** **CANONICAL #003** — ensure directive handoff integrity by pinning every DIRECTIVE signal to the exact contents of `docs/working/current_directive.md`.

For bus lines where `type` is `DIRECTIVE`, implementations MUST include:

| Field | Type | Rule |
|-------|------|------|
| `directive_hash` | `str` | 64-character lowercase hex SHA-256 of the UTF-8 bytes of `docs/working/current_directive.md` at signal emission time. |

**Authorization rule:** `--peek` and `--developer-phase-b` MUST refuse exit 0 if the local `current_directive.md` hash does not match the latest applicable DIRECTIVE `directive_hash` (even when `next_actor` matches).

**Compatibility note:** Non-`DIRECTIVE` lines do not require `directive_hash`.

#### 5.9.3 Sentinel relay daemon — governance dispatch automation

**Directive:** **CANONICAL #005** — implement a Sentinel-standalone relay daemon that tails `.governance/bus.log`, enforces pre-dispatch hash gate checks, and dispatches architect/developer turns with one-agent-at-a-time safety, strike escalation, timeout, and crash recovery.

- [x] Implement `scripts/runtime/sentinel_relay.py` with kill switch, PID lock, one-at-a-time dispatch, hash gate pre-check, strike escalation model routing, timeout and crash recovery.
- [x] Add synthetic test coverage in `tests/test_sentinel_relay.py` (9 scenarios).
- [x] Align governance and architecture docs for relay-driven Rule 11 escalation semantics.

#### 5.9.4 Sentinel relay startup reconciliation hardening

**Directive:** **CANONICAL #006** — harden relay startup reconciliation so crash-recovery replay is deterministic, architect-prime handling remains explicit for ambiguous startup state, and startup signaling does not silently take turn ownership from the active directive lane.

- **Status:** **Closed (2026-03-30)** — architect Phase C rerun passed (`python3 -m pytest tests/test_sentinel_relay.py -q` -> `14 passed`), with replay-safe startup offset handling and lane-safe startup INFO behavior validated.
- [x] Ensure startup reconciliation preserves canonical turn ownership semantics (no unconditional startup signal that reassigns `next_actor` away from the active directive lane).
- [x] Ensure restart/tail behavior does not silently drop unread bus lines during crash recovery or process interruption.
- [x] Add synthetic tests for startup reconciliation: ambiguous-state architect-prime dispatch, bus-authorized role dispatch, and replay safety.

#### 5.9.5 Context bundle contract v1 (schema + validation)

**Directive:** **CANONICAL #007** — lock an explicit **envelope** contract for `ContextBundle` (distinct from per-record `schema_version` on `ContextRecord`), with machine validation and tests before runtime agent wiring.

- **Status:** **Closed (2026-03-30)** — architect validation rerun passed (`python3 -m pytest tests/test_context_ledger.py tests/test_ledger_storage.py -q` -> `12 passed`), with contract version enforcement, schema-level rejection behavior, and README contract documentation validated.

| Mechanism | Location |
|-----------|----------|
| `bundle_contract_version` (default `1.0.0`), `validation_state`, `validation_errors` | `modules/context_ledger/base.py` → `ContextBundle` |
| `validate_context_bundle_dict` / `validate_context_bundle_json`; `ContextBundleContractError` | `modules/context_ledger/bundle_contract.py` |
| Ledger-built bundles marked **valid** | `ContextLedger.build_context_bundle` in `store.py` |

**Rules:** Unsupported `bundle_contract_version` values are rejected at validation time; unknown top-level JSON keys are rejected (`extra='forbid'` on `ContextBundle`). **Reuse** semantics are documented in `modules/context_ledger/README.md`.

#### 5.9.6 Anna first-consumer ledger wiring (read-only integration)

**Directive:** **CANONICAL #008** — wire Anna as the first runtime consumer of the ledger contract through an additive, non-breaking path that preserves existing memory/task/artifact behavior while introducing test-backed valid/invalid bundle handling.

- **Status:** **Closed (2026-03-30)** — architect validation rerun passed:
  - `python3 -m pytest tests/test_anna_context_ledger_integration.py tests/test_anna_pipeline.py tests/test_anna_directive_4_6_3.py -q` -> `13 passed`
  - `python3 -m pytest tests/test_context_ledger.py tests/test_anna_market_data_integration.py -q` -> `23 passed`
- **Implementation notes:** `context_ledger_consumer.py` adds optional validated bundle attachment; `analysis.py`/`anna_analyst_v1.py` consume bundle JSON/path additively; no caller engagement keeps legacy output shape unchanged.
- **Documentation notes:** incremental migration behavior and `ANNA_CONTEXT_BUNDLE_PATH` are documented in `modules/context_ledger/README.md` and `scripts/runtime/README.md`.

#### 5.9.7 ContextProfile runtime enforcement (agent-scoped views)

**Directive:** **CANONICAL #009** — enforce runtime agent-scoped context views via `contextProfile` contracts in `agents/agent_registry.json`, with explicit allow-list behavior, deterministic tests, and no regression for non-context-aware paths.

- **Status:** **Closed (2026-03-30)** — architect validation rerun passed:
  - `python3 -m pytest tests/test_context_profile_runtime.py tests/test_anna_context_ledger_integration.py tests/test_context_ledger.py -q` -> `24 passed`
  - `python3 -m pytest tests/test_anna_pipeline.py tests/test_anna_directive_4_6_3.py tests/test_anna_context_ledger_integration.py tests/test_context_profile_runtime.py -q` -> `23 passed`
- **Implementation notes:** `context_profile_runtime.py` resolves/enforces `allowedContextClasses` from `agents/agent_registry.json`; Anna consumer path fails closed on missing/disallowed profile conditions while preserving non-engaged legacy behavior.
- **Documentation notes:** runtime/context-ledger docs explicitly split shipped enforcement (`allowedContextClasses` vs records) from deferred envelope-level `bundleSections` enforcement.

#### 5.9.8 Online activation checklist + proof hooks (contract lock)

**Directive:** **CANONICAL #010** — lock the architect-owned online activation checklist contract for context-enabled agents (registry + profile + runtime + messaging/OpenClaw + proof hooks), and add deterministic validation coverage for checklist/proof-hook resolution.

- **Status:** **Closed (2026-03-30)** — architect-owned contract lock completed in governed docs; execution-closeout recorded in `directive_execution_log.md` with closeout packet `directive_010_online_activation_contract_lock_closeout.md`.

**Canonical checklist contract (fail-closed):**

| Gate ID | Gate | Pass condition | Fail condition (must fail closed) | Required reason fields |
|---------|------|----------------|-----------------------------------|------------------------|
| `ACT-REG-001` | Registry contract presence | Target agent entry in `agents/agent_registry.json` contains `contextProfile` and expected contract version keys | Missing profile or contract keys, or incompatible version marker | `reason_code`, `reason`, `evidence_refs` |
| `ACT-RT-002` | Runtime enforcement path presence | Runtime path resolves and enforces profile-backed context constraints before online-ready state is granted | Missing/disabled enforcement path, bypassed enforcement, or non-deterministic gate behavior | `reason_code`, `reason`, `evidence_refs` |
| `ACT-MSG-003` | Messaging/OpenClaw boundary declaration | Agent-facing messaging boundary is explicitly declared (supported ingress path and non-authorized paths documented) | Boundary absent/ambiguous or implies unauthorized messaging path | `reason_code`, `reason`, `evidence_refs` |
| `ACT-PROOF-004` | Deterministic proof hooks | Required proof artifacts exist: test evidence, shared-log proof block, and artifact references sufficient for architect replay | Missing or stale proof artifacts, or unverifiable evidence chain | `reason_code`, `reason`, `evidence_refs` |

**Online-ready decision rule:** agent is `online_ready=true` only when **all** gates pass. Any failed gate sets `online_ready=false` and requires operator-visible failure reasons (fail closed; no partial activation).

#### 5.9.9 Online activation evaluator + proof-hook validator (implementation)

**Directive:** **CANONICAL #011** — implement deterministic runtime evaluation of the 5.9.8 checklist contract (gate-by-gate status + fail-closed decision + proof-hook verification), with tests and architect-verifiable evidence.

- **Status:** **Closed (2026-03-30)** — architect validation rerun passed:
  - `python3 -m pytest tests/test_online_activation_evaluator.py -q` -> `8 passed`
  - `python3 -m pytest tests/test_context_profile_runtime.py tests/test_context_ledger.py -q` -> `17 passed`
- **Implementation notes:** `online_activation_evaluator.py` adds `GateResult`, `OnlineActivationReport`, `ProofHookSpec`, and deterministic `evaluate_online_activation()` checks for all four #010 gates with required reason fields and fail-closed `online_ready` semantics.
- **Documentation notes:** evaluator scope and boundaries are recorded in `modules/context_ledger/README.md` and `scripts/runtime/README.md`; live channel/execution checks remain out of scope.

#### 5.9.10 Foreman / orchestration context packet contract (directive lock)

**Directive:** **CANONICAL #012** — lock the architect-owned contract for how Foreman/orchestration lanes consume context packets for multi-agent routing, including fail-closed routing rules, packet provenance requirements, and proof-hook expectations before runtime implementation.

- **Status:** **Closed (2026-03-30)** — architect contract lock completed in governed docs with explicit fail-closed packet requirements, lane-authority rules, and proof-hook replay contract. Runtime implementation is deferred to **CANONICAL #013**.
- [x] Define canonical context-packet fields required for routing (`packet_id`, producer, scope/authority, freshness marker, and evidence references) and reject rules for missing/ambiguous packets.
- [x] Define lane-ownership and turn-safe routing constraints so orchestration cannot bypass `current_directive.md` / bus authority when context packets are stale or unverifiable.
- [x] Define deterministic proof hooks for packet-routing validation (required artifacts + replay commands) and list explicit out-of-scope runtime work for this contract-lock slice.
- [x] Add architect-owned docs updates for the contract in governed files (`development_plan.md`, `current_directive.md`, and closeout packet) without changing Foreman runtime code in this directive.

**Canonical context-packet contract (fail-closed):**

| Field group | Required fields | Contract rule |
|-------------|-----------------|---------------|
| Identity / provenance | `packet_id`, `producer_role`, `producer_agent`, `created_at_utc`, `directive_hash` | Missing/empty fields fail validation; packet is ineligible for routing. |
| Scope / authority | `target_lane`, `next_actor`, `allowed_consumers`, `lane_epoch` | Packet must match active governance lane and consumer role; mismatch or ambiguity blocks routing. |
| Evidence / integrity | `evidence_refs`, `validation_marker` | Packet must carry replayable evidence references and a deterministic validation marker; opaque or missing evidence blocks routing. |

**Fail-closed lane and freshness rules:**

- Packets with missing metadata, unknown lane ownership, or malformed authority fields are rejected.
- Packets with `directive_hash` mismatch against active `docs/working/current_directive.md` are rejected.
- Packet presence does not grant authority by itself; bus lane authority (`governance_bus.py --peek`) remains required.
- Stale `lane_epoch` or stale packet timestamp relative to the active lane transition is rejected.

**Proof-hook contract for runtime implementation:**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `CTXPKT-PROOF-001` | Validator unit tests (`tests/test_foreman_operator_controller.py` and/or new packet-validator suite) | Deterministic pass/fail for required fields and reject semantics | Missing coverage for any required fail-closed branch |
| `CTXPKT-PROOF-002` | Governance lane replay (`python3 scripts/runtime/governance_bus.py --peek`) + packet check command | Packet accepted only when lane ownership and directive hash both match | Acceptance despite lane/hash mismatch |
| `CTXPKT-PROOF-003` | Shared proof block in `docs/working/shared_coordination_log.md` with command transcripts | Architect can replay packet decision path from logged evidence | Narrative-only proof without replayable artifacts |

#### 5.9.11 Foreman / orchestration context packet validator (implementation)

**Directive:** **CANONICAL #013** — implement deterministic runtime packet validation and lane-safe routing gate behavior from the #012 contract, with fail-closed verdicts and test-backed replay proof.

- **Status:** **Closed (2026-03-30)** — architect validation rerun passed:
  - `python3 -m pytest tests/test_context_packet_validator.py -q` -> `10 passed`
  - `python3 -m pytest tests/test_context_ledger.py tests/test_online_activation_evaluator.py -q` -> `17 passed`
  - `python3 -m pytest tests/test_foreman_operator_controller.py -q` -> `6 passed`
- **Implementation notes:** packet validation is implemented in `modules/context_ledger/context_packet_validator.py` and wired through `scripts/runtime/foreman_v2/context_packet_gate.py` with fail-closed checks for required fields, directive hash, lane epoch, lane actor, freshness, consumer allow-list, and bus hash-gate authority.
- **Documentation notes:** validator usage and replay commands are documented in `modules/context_ledger/README.md`, `scripts/runtime/foreman_v2/README.md`, and `scripts/runtime/README.md`.
- [x] Implement contract validator path for context packets used by Foreman/orchestration routing, including required fields and reason-coded fail-closed verdicts.
- [x] Enforce lane/hash/freshness checks before packet-driven routing decisions so packets cannot bypass governance authority.
- [x] Add deterministic tests for valid packet acceptance plus each required rejection class (missing fields, stale epoch/timestamp, lane mismatch, directive hash mismatch, unauthorized consumer).
- [x] Update runtime/docs surfaces for validator usage and proof replay commands, then append developer proof in `docs/working/shared_coordination_log.md`.

#### 5.9.12 Gnosis compatibility boundary (contract lock)

**Directive:** **CANONICAL #014** — lock the architect-owned compatibility boundary for optional future Gnosis adapter integration, preserving BLACK BOX engine-native context contracts as canonical and fail-closed by default when optional external adapters are unavailable or mismatched.

- **Status:** **Closed (2026-03-31)** — architect contract lock completed in governed docs; architect verification reran `python3 -m pytest tests/test_sentinel_relay.py -q` -> `14 passed` to confirm relay governance controls remained intact while locking adapter-boundary semantics.
- [x] Define adapter-only boundary contract (no runtime dependency): canonical in-repo context remains authoritative.
- [x] Define fail-closed semantics for adapter-unavailable, adapter-unhealthy, and contract-mismatch states.
- [x] Define minimal future adapter interface expectations (inputs/outputs, version compatibility, proof hooks) without implementing runtime adapter code.
- [x] Synchronize governed docs (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, closeout packet) with matching status granularity.

**Canonical Gnosis compatibility boundary (contract lock):**

| Contract area | Rule |
|---------------|------|
| Source authority | `modules/context_ledger/` contracts (`ContextRecord` / `ContextBundle`) remain authoritative; Gnosis is adapter-only. |
| Runtime dependency | Core context-ledger operation must remain online when Gnosis is absent; no hard startup/runtime dependency. |
| Write safety | Adapter mismatch or schema/version mismatch must fail closed and must not mutate canonical in-repo bundle/record contracts. |
| Data movement | Import/export boundaries must be explicit and auditable (`direction`, `version`, `evidence_ref`) before any runtime adapter directive is accepted. |

**Fail-closed adapter-state semantics:**

| State | Required behavior |
|-------|-------------------|
| `adapter_unavailable` | Continue core ledger operation; mark adapter path unavailable and block adapter-mediated sync actions. |
| `adapter_unhealthy` | Continue core ledger operation; reject adapter I/O for the cycle and require operator-visible reason codes. |
| `adapter_contract_mismatch` | Reject adapter payloads and keep canonical contract unchanged; no coercion or silent field dropping. |

**Future adapter interface expectations (no implementation in #014):**

- Adapter contract version must be explicit and compared against in-repo compatibility mapping before data exchange.
- Inputs must be immutable snapshots (`bundle_json`, `bundle_contract_version`, `directive_hash`, `context_profile_scope`).
- Outputs must include deterministic status and evidence hooks (`adapter_result`, `reason_code`, `evidence_refs`) for replay.
- Proof hooks for any runtime adapter directive must include deterministic contract tests plus shared-log replay commands.

#### 5.9.13 Sentinel relay directive-session rollover policy alignment (contract lock)

**Directive:** **CANONICAL #015** — lock architect-owned policy for relay chat-session rollover semantics so TEAM_BRIEFING requirements and runtime behavior are explicitly reconciled before any further relay implementation directives.

- **Status:** **Closed (2026-03-31)** — architect contract lock completed; policy is now explicit and canonical, and runtime alignment is issued as **CANONICAL #016** implementation work.
- [x] Define canonical policy for `DIRECTIVE` rollover session behavior (`architect_chat_id` / `developer_chat_id`) and strike/escalation interactions.
- [x] Define whether policy changes require runtime updates, docs-only realignment, or both, with explicit acceptance gates.
- [x] Define required proof hooks (tests + state-file assertions + bus replay expectations) for the follow-on implementation directive.
- [x] Synchronize governed docs (`development_plan.md`, `blackbox_master_plan.md`, `directive_execution_log.md`, `current_directive.md`) with matching status granularity.

**Canonical session-rollover policy (locked by #015):**

| Event | `architect_chat_id` | `developer_chat_id` | Contract rule |
|-------|----------------------|---------------------|---------------|
| New `DIRECTIVE` signal | Reset to `""` | Reset to `""` | New work package starts from a fresh relay session context for both lanes. |
| `NACK` retry (`next_actor=developer`) | Preserve | Preserve | Retry remains warm within the same directive lane unless escalation rule overrides. |
| Strike 3 model escalation | Preserve | Reset to `""` before spawn | Escalated developer model must start fresh context. |
| Startup reconciliation (`status=dispatching` or incomplete developer run) | Preserve persisted value until next rule-triggered reset | Preserve persisted value until next rule-triggered reset | Startup path does not independently clear IDs; reset behavior is event-driven by DIRECTIVE/escalation policy. |
| `--tail-only` startup at offset 0 | Preserve | Preserve | Tail bootstrap mutates offsets only; no chat-id mutation. |

**Runtime mismatch classification and implementation decision:**

- TEAM_BRIEFING reset-on-`DIRECTIVE` semantics are canonical.
- Existing relay warm-session-on-`DIRECTIVE` behavior in `scripts/runtime/sentinel_relay.py` is classified as **policy drift** and must be corrected by implementation directive.
- Required implementation directive is **CANONICAL #016** (below).

#### 5.9.14 Sentinel relay directive-session rollover runtime alignment (implementation)

**Directive:** **CANONICAL #016** — implement the #015 session-rollover policy in relay runtime/tests so new directives reset both session IDs, retries remain warm, escalation clears only developer session context, and proof is deterministic.

- **Status:** **Closed (2026-03-31)** — architect Phase C validation rerun passed (`python3 -m pytest tests/test_sentinel_relay.py -q` -> `17 passed`), confirming runtime alignment with #015 session policy.
- [x] Update `scripts/runtime/sentinel_relay.py` DIRECTIVE handling to reset both `architect_chat_id` and `developer_chat_id`.
- [x] Preserve warm retry behavior for `NACK` paths, including short retry prompt behavior and role-scoped `--continue`.
- [x] Preserve strike-3 escalation behavior (`escalated=True`, developer chat reset) and no-dispatch operator handoff at strike 4+.
- [x] Align `tests/test_sentinel_relay.py` session-persistence coverage to explicit fresh/warm/reset cycle assertions under the #015 policy.
- [x] Record replayable proof in `docs/working/shared_coordination_log.md` and request architect validation.

#### 5.9.15 Context trigger contract (`v1`)

**Directive:** lock the exact routing triggers that cause context assembly for an agent so future agents do not require bespoke interpretation or hidden wiring.

**Rule:**

- context assembly occurs only when a runtime path explicitly targets a specific agent
- approved `v1` targeting triggers are:
  - explicit app/agent mention in an approved shared channel
  - explicit direct message / direct conversation bound to that agent
  - orchestrator / Foreman routing that names the target agent
  - approved internal API/runtime invocation naming the target agent
- incidental prose mention of an agent name must not by itself grant turn ownership, emit canonical context, or mutate reusable memory
- routed conversation handling must respect the target agent's `conversationParticipationMode` in `agents/agent_registry.json`
- every online agent must be onboarded through the same `contextProfile` + runtime enforcement path; bespoke one-off context wiring is non-compliant

**Proof expectations for implementation:**

- deterministic tests for accepted vs rejected trigger paths
- replayable evidence that an untargeted mention does not hydrate or mutate context
- replayable evidence that a valid targeted invocation assembles only the target agent's allowed context classes

#### 5.9.16 Context ingestion-source contract (`v1`)

**Directive:** lock the approved source surfaces that may create or update context records, including explicit `v1` exclusions.

**Canonical backend rule:**

- the `v1` context engine backend is the in-repo append-only JSONL ledger in `modules/context_ledger/`
- typed `ContextRecord` / `ContextBundle` contracts are canonical
- semantic/vector retrieval may be added later only as an optional retrieval aid; it is not the canonical backend in `v1`

**Approved `v1` context-ingestion sources:**

- approved human text interactions from `slack`, `cursor`, and approved `api` surfaces
- agent actions and agent-produced artifacts
- runtime/system artifacts, logs, proofs, and structured state snapshots
- approved live/stored market and system data sources allowed by the target agent's `contextProfile`

**Explicit `v1` exclusions:**

- raw voice/audio is not a first-class canonical context source
- speech may enter context only after an approved transcription path converts it into a bounded text/API artifact with stable source references
- ambient untargeted chat capture must not be promoted into canonical reusable memory

**Rule:**

- source ingestion must remain append-only and auditable
- reusable memory promotion must follow validation/promotion policy; episodic chat remains non-canonical until promoted
- every persisted context write must be attributable to a bounded source surface plus stable source reference

**Proof expectations for implementation:**

- deterministic tests for source acceptance/rejection
- replayable proof that raw voice/audio is rejected unless transformed through an approved transcript artifact path
- replayable proof that append-only writes preserve source attribution and contract validation

### First slice (approved paper loop) — checklist

Aligned with **Phase 5 — First approved slice** in [`blackbox_master_plan.md`](../blackbox_master_plan.md).

- [x] Pyth ingestion (**SOL**).
- [x] Normalized snapshot store.
- [x] Deterministic strategy → SOL signal contract with participant/account/tier scope.
- [x] L3 approval binding.
- [x] Execution intent contract post-approval.
- [x] Billy poll + Coinbase **sandbox** adapter.
- [x] Outcome ingestion + durable storage.

**Stop condition:** “One approved, participant-scoped signal → one paper trade → verified outcome → stored” before scope expansion.

#### 5.7.6 Post-first-slice transition gate (architect-owned)

**Directive:** **CANONICAL #034** — perform architect-owned post-first-slice transition gating after #033 closure so Pillar 1 completion evidence is reconciled and the next authorized scope is explicitly contracted without violating the active Pillar 1 lock.

- **Status:** **Closed (2026-03-31)** — architect transition gate accepted and synchronized; Pillar 1 lock posture remains active and next contracted scope issued as **CANONICAL #035** (architect-owned).
- [x] Verified and documented first-slice completion evidence chain (#030-#033), including deterministic replay proof continuity (`True out-1`, `True 1 True`) and fail-closed boundary continuity in governed docs.
- [x] Reconciled Pillar 1 completion posture across governed docs and recorded that lock transition remains blocked pending explicit governed lock-removal decision.
- [x] Defined the next contracted directive target in governed docs without freehand scope expansion beyond Rule 10.
- [x] Published/maintained directive state through hash-pinned atomic bus operations only.

#### 5.7.7 Pillar 1 exit-readiness contract lock (architect-owned)

**Directive:** **CANONICAL #035** — lock architect-owned Pillar 1 exit-readiness contracts so post-first-slice progression remains deterministic, governance-bound, and non-implied while the Pillar 1 lock remains active.

- **Status:** **Closed (2026-03-31)** — architect-owned contract lock accepted and synchronized; next contracted slice issued as **CANONICAL #036** (architect-owned lock-lift decision-packet contract).
- [x] Convert primary-outcomes and post-core-engine sequencing constraints into explicit pass/fail contract language tied to governed artifacts (scope, out-of-scope, proof hooks, acceptance boundaries).
- [x] Define lock-lift prerequisite gates and operator decision hooks required before any beyond-Pillar-1 directive can be issued.
- [x] Produce the next contracted directive map (architect-owned vs developer-owned follow-ons) without authorizing non-Pillar work while lock is active.
- [x] Publish/maintain directive state through hash-pinned atomic bus operations only.

**Pillar 1 exit-readiness gate contract (locked by #035):**

| Gate ID | Gate | Scope (required) | Out of scope while lock active | Proof hook | Acceptance boundary |
|---------|------|------------------|---------------------------------|------------|---------------------|
| `P1-EXIT-001` | Primary outcomes contract gate | Core-engine outcomes are explicit, reason-coded, and traceable to governed docs | Any implied "done" claim without written contract language | `P1-EXIT-PROOF-001` plan/master/log sync audit | Gate passes only when all outcome contracts are present and synchronized |
| `P1-EXIT-002` | Post-core sequencing gate | Human-ops, education oversight, transparency/provenance, Anna↔Billy boundaries, and novelty governance are each explicitly contracted | Starting unrelated build work because first slice succeeded | `P1-EXIT-PROOF-002` checklist replay in shared log | Gate passes only when each sequencing item has scope, out-of-scope, pass/fail, and proof hooks |
| `P1-EXIT-003` | Lock-lift prerequisite gate | Lock-lift requires explicit operator decision contract and named follow-on directive authority | Any beyond-Pillar directive without governed lock-lift record | `P1-EXIT-PROOF-003` lock-lift prerequisite matrix + decision-hook table | Gate passes only when lock state and decision authority are explicit and reproducible |
| `P1-EXIT-004` | Directive-lane ownership gate | Next directive map must specify lane owner and prohibited drift for each follow-on | Dual-owner ambiguity or implied developer start | `P1-EXIT-PROOF-004` atomic bus/hash-gate command trail | Gate passes only when lane ownership is explicit and bus state matches directive authority |

**Lock-lift prerequisites and operator decision hooks (locked by #035):**

- `LOCK-LIFT-001`: operator decision record is required before any directive can authorize beyond-Pillar scope.
- `LOCK-LIFT-002`: decision record must name lock state (`retain` or `lift`), rationale, covered gate IDs, and evidence references.
- `LOCK-LIFT-003`: if lock is retained, next directive must remain architect-owned and Pillar-safe.
- `LOCK-LIFT-004`: if lock is lifted, next directive must explicitly state newly authorized scope and preserve fail-closed governance boundaries.

**Next directive map (contracted by #035):**

| Canonical ID | Lane owner | Contract purpose | Scope boundary |
|--------------|------------|------------------|----------------|
| `#036` | Architect | Lock-lift decision-packet contract and explicit lane-release criteria | Pillar 1 lock remains active; no developer implementation authorization |
| `#037` (conditional) | Architect | Lock-retained continuity directive or lock-lift publication directive, depending on #036 outcome | Must be explicitly published; no implied beyond-Pillar progression |

#### 5.7.8 Pillar 1 lock-lift decision packet contract (architect-owned)

**Directive:** **CANONICAL #036** — define the lock-lift decision-packet contract and publication gates so Pillar 1 can only remain locked or be lifted through explicit operator-authorized, hash-pinned governance artifacts.

- **Status:** **Closed (2026-03-31)** — architect-owned contract lock accepted and synchronized; follow-on publication slice issued as **CANONICAL #037**.
- [x] Define canonical decision-packet schema and required fields for lock state transitions (`retain` / `lift`) with deterministic validation semantics.
- [x] Define operator decision hooks and acceptance boundaries for publishing lock-retained versus lock-lifted follow-on directives.
- [x] Define lane-release criteria (architect hold vs developer authorization) tied to explicit pass/fail gates and proof hooks.
- [x] Publish/maintain directive state through hash-pinned atomic bus operations only.

**Canonical lock-lift decision-packet schema (locked by #036):**

| Field | Requirement | Contract rule |
|-------|-------------|---------------|
| `decision_packet_id` | required, non-empty | Deterministic unique decision identity for replay and audit joins. |
| `canonical_id` | required, exact | Must equal the active lock-governance slice canonical ID at publication time. |
| `lock_state` | required enum (`retain` or `lift`) | Any other value is invalid and fails closed. |
| `decision_timestamp_utc` | required ISO-8601 UTC | Decision time must be parseable and replay-stable. |
| `operator_identity` | required, non-empty | Human/operator authority identity for lock-state ownership. |
| `architect_identity` | required, non-empty | Architect publication identity for deterministic lane accountability. |
| `covered_gate_ids` | required non-empty list | Must explicitly enumerate gate IDs evaluated for this decision packet. |
| `rationale` | required, non-empty | Rationale must be explicit; empty or ambiguous text fails closed. |
| `evidence_refs` | required non-empty list | Evidence pointers must be replayable (governed docs/tests/artifacts). |
| `effective_scope` | required object | Must declare authorized scope and prohibited scope for follow-on directives. |
| `next_directive_contract` | required object | Must declare canonical follow-on ID, lane owner, and publication mode. |
| `directive_hash_at_decision` | required 64-char SHA-256 | Must match `docs/working/current_directive.md` hash at decision capture. |

**Deterministic validation matrix (locked by #036):**

| Rule ID | Failure class | Required behavior |
|---------|---------------|-------------------|
| `LDP-REQ-001` | Missing/empty required decision-packet fields | Reject packet and block follow-on publication. |
| `LDP-ENUM-002` | Invalid `lock_state` value | Reject packet and block follow-on publication. |
| `LDP-GATE-003` | Missing/ambiguous gate coverage list | Reject packet and block follow-on publication. |
| `LDP-EVID-004` | Missing/non-replayable evidence references | Reject packet and block follow-on publication. |
| `LDP-SCOPE-005` | Effective scope missing or contradictory | Reject packet and block follow-on publication. |
| `LDP-AUTH-006` | Missing operator/architect authority identity | Reject packet and block follow-on publication. |
| `LDP-HASH-007` | `directive_hash_at_decision` mismatch | Reject packet and block follow-on publication. |
| `LDP-REPLAY-008` | Replay drift for identical packet content | Mark packet invalid for governance use and block publication. |

**Lock-state publication gates (locked by #036):**

| Gate ID | Gate | PASS condition | FAIL-CLOSED behavior |
|---------|------|----------------|----------------------|
| `LDP-PUB-001` | Retain publication gate | `lock_state=retain` and packet satisfies `LDP-REQ-001` ... `LDP-HASH-007` | Do not publish non-Pillar directive; keep architect lane active |
| `LDP-PUB-002` | Lift publication gate | `lock_state=lift` and packet explicitly authorizes beyond-Pillar scope with gate/evidence references | Do not publish beyond-Pillar directive; remain in architect/operator governance lane |
| `LDP-PUB-003` | Decision consistency gate | Exactly one active decision packet is canonical for the publication event | Reject publication on conflicting or duplicate packets |
| `LDP-PUB-004` | Freshness gate | Decision packet timestamp/hash align to current governed state | Reject stale packet and require refreshed decision packet |

**Lane-release contract (locked by #036):**

- `LDP-LANE-001`: default ownership remains architect while lock-state publication is unresolved.
- `LDP-LANE-002`: developer lane release is allowed only when a follow-on directive explicitly sets `next_actor=developer` with contracted scope, acceptance criteria, and out-of-scope boundaries.
- `LDP-LANE-003`: unresolved decision conflicts or stale packets hand control to operator (`next_actor=operator`) for explicit reconciliation.
- `LDP-LANE-004`: no dual-owner interpretation is allowed; each publication event must name exactly one next actor.

**Proof hooks for follow-on publication directive(s):**

| Hook ID | Required artifact / command | PASS condition | FAIL condition |
|---------|-----------------------------|----------------|----------------|
| `LDP-PROOF-001` | Decision-packet schema/validation evidence in governed docs | Required fields/rules/gates are explicit and synchronized | Missing schema/rule/gate contract language |
| `LDP-PROOF-002` | Shared-log publication trail with gate result and lane outcome | Architect can replay retain/lift publication decision path | Narrative-only claim without reproducible decision trail |
| `LDP-PROOF-003` | Hash-pinned bus evidence (`ACK`, `COMMIT`, atomic `DIRECTIVE`) | Bus lane and directive hash align to published state | Hash mismatch or non-atomic directive publication |

#### 5.7.9 Pillar 1 lock-state publication directive (architect-owned)

**Directive:** **CANONICAL #037** — publish and enforce a lock-state decision packet instance using #036 contract gates so the next authoritative lane is explicit (`retain` continuity or `lift` authorization), fail-closed, and hash-pinned.

- **Status:** **Closed (2026-03-31)** — architect published canonical retain decision packet, recorded publication-gate verdicts, and issued follow-on architect-owned continuity directive as **CANONICAL #038**.
- [x] Publish a canonical lock-state decision packet instance (`retain` or `lift`) with complete required fields and gate coverage references from #036.
- [x] Record publication gate verdict (`LDP-PUB-001` ... `LDP-PUB-004`) and resulting lane ownership outcome in governed docs.
- [x] If `retain`: publish an architect-owned continuity directive that remains Pillar 1 safe with explicit out-of-scope lock boundaries.
- [x] If `lift`: fail closed when no valid lift packet is selected; do not publish beyond-Pillar scope.
- [x] Maintain directive issuance/re-issuance discipline through atomic governance operations only (`--issue-directive-atomic` / `--publish-directive-atomic`).

#### 5.7.10 Pillar 1 lock-retained continuity directive (architect-owned)

**Directive:** **CANONICAL #038** — enforce lock-retained continuity after #037 so Pillar 1 scope remains explicit, fail-closed, and architect-owned until an explicitly authorized lock-lift decision packet is published.

- **Status:** **Closed (2026-03-31)** — architect-owned retained-lock continuity slice accepted/closed with explicit scope boundaries, deterministic lane ownership, and lock-lift evidence package contract; follow-on architect-owned continuity enforcement issued as **CANONICAL #039**.
- [x] Publish explicit retained-lock continuity boundaries (`allowed_scope`, `prohibited_scope`) and carry-forward gate IDs in governed docs.
- [x] Keep lane ownership deterministic (`next_actor=architect`) and reject implied developer/beyond-Pillar starts.
- [x] Define the exact evidence package required for any future lock-lift publication attempt (operator authority record, gate coverage, hash alignment, freshness).
- [x] Maintain directive issuance/re-issuance discipline through atomic governance operations only (`--issue-directive-atomic` / `--publish-directive-atomic`).

#### 5.7.11 Pillar 1 retained-lock continuity enforcement gate (architect-owned)

**Directive:** **CANONICAL #039** — keep retained-lock governance fail-closed after #038 by enforcing operator-authority intake rules and lane-safe publication prerequisites before any future lock-lift decision packet can alter scope ownership.

- **Status:** **Closed (2026-03-31)** — architect-owned enforcement slice accepted/closed; retained-lock intake prerequisites and fail-closed classification contract are now explicit and synchronized; follow-on architect-owned intake reconciliation gate issued as **CANONICAL #040**.
- [x] Reassert retained-lock continuity boundaries in governed docs and reject any implied developer or beyond-Pillar starts.
- [x] Define a deterministic operator-authority intake checklist for future lock-lift publication attempts (authority record, packet completeness, gate coverage references, hash/freshness alignment).
- [x] Define fail-closed outcomes for missing/incomplete/conflicting lock-lift intake evidence (`blocked`, `deferred`, or `closed_without_completion`) without releasing lane ownership.
- [x] Maintain directive issuance/re-issuance discipline through atomic governance operations only (`--issue-directive-atomic` / `--publish-directive-atomic`).

**Operator-authority intake checklist (locked by #039):**

| Intake ID | Requirement | PASS condition | FAIL-CLOSED handling |
|-----------|-------------|----------------|----------------------|
| `INTAKE-AUTH-001` | Operator authority record present | Named operator authority artifact includes identity and decision timestamp | `blocked`; lane remains architect |
| `INTAKE-PKT-002` | Decision packet completeness | Packet references #036 gate contracts (`LDP-REQ-*`, `LDP-PUB-*`) with no missing mandatory fields | `deferred`; request refreshed packet evidence |
| `INTAKE-HASH-003` | Directive hash alignment | `directive_hash_at_decision` matches active directive hash at intake time | `blocked`; stale/mismatched hash rejected |
| `INTAKE-FRESH-004` | Freshness and replay safety | Intake timestamp and evidence are fresh, monotonic, and replay-safe for the publication event | `closed_without_completion`; require new intake cycle |

**Fail-closed intake verdict matrix (locked by #039):**

- `accepted_for_follow_on_gate`: all `INTAKE-*` checks pass; architect may issue next architect-owned publication-review directive.
- `blocked`: missing/invalid authority or hash alignment; no lane release and no beyond-Pillar publication.
- `deferred`: intake evidence incomplete but recoverable; architect lane retained until refreshed evidence is provided.
- `closed_without_completion`: conflicting/replay-unsafe intake evidence; close cycle intentionally and require a new governed intake attempt.

#### 5.7.12 Pillar 1 operator-authority intake reconciliation gate (architect-owned)

**Directive:** **CANONICAL #040** — operationalize #039 intake contracts by reconciling real intake attempts against `INTAKE-*` checks and publishing deterministic fail-closed verdict evidence before any lock-lift publication gate can be considered.

- **Status:** **Closed (2026-03-31)** — architect completed intake reconciliation against #039 contracts, recorded deterministic per-check outcomes, and closed the cycle with canonical verdict `closed_without_completion` due hash/freshness mismatch against the active intake event; follow-on architect-owned refresh gate issued as **CANONICAL #041**.
- [x] Evaluated intake evidence against `INTAKE-AUTH-001` ... `INTAKE-FRESH-004` and recorded deterministic per-check verdicts in governed docs.
- [x] Produced a canonical verdict packet for the intake cycle (`closed_without_completion`) with explicit rationale and fail-closed handling.
- [x] Preserved deterministic lane ownership (`next_actor=architect`) with no implied developer or beyond-Pillar release.
- [x] Maintained directive issuance/re-issuance discipline through atomic governance operations only (`--issue-directive-atomic` / `--publish-directive-atomic`).

**Reconciliation verdict packet (#040):**

| Intake ID | Result | Deterministic rationale |
|-----------|--------|-------------------------|
| `INTAKE-AUTH-001` | `PASS` | Prior retained decision packet captures `operator_identity` and `decision_timestamp_utc` fields. |
| `INTAKE-PKT-002` | `DEFERRED` | Available packet evidence is publication-centric (`LDP-PUB-*`) and does not provide a fresh intake-cycle completeness map for all required `LDP-REQ-*` fields. |
| `INTAKE-HASH-003` | `BLOCKED` | `directive_hash_at_decision` from retained packet (`c9d64...`) does not align with active intake directive hash for #040 (`741c00...`). |
| `INTAKE-FRESH-004` | `CLOSED_WITHOUT_COMPLETION` | Retained packet evidence is replay-unsafe for a new publication event and requires a fresh governed intake cycle. |

#### 5.7.13 Pillar 1 intake-cycle refresh and publication-readiness gate (architect-owned)

**Directive:** **CANONICAL #041** — enforce a fresh, hash-aligned, replay-safe intake cycle after #040 so any future lock-state publication review is grounded in current operator-authority evidence and complete `LDP-REQ-*` / `LDP-PUB-*` coverage.

- **Status:** **Active (2026-03-31)** — architect-owned intake refresh gate is active; relay lane remains `next_actor=architect`.
- [ ] Require a fresh intake packet instance with explicit authority metadata and complete #036 contract coverage references (`LDP-REQ-*`, `LDP-PUB-*`).
- [ ] Require directive-hash alignment to the active directive at intake capture time and fail closed on mismatch.
- [ ] Require freshness/replay-safety proof for the intended publication event and classify outcomes deterministically (`accepted_for_follow_on_gate`, `blocked`, `deferred`, `closed_without_completion`).
- [ ] Preserve deterministic lane ownership and maintain atomic directive issuance/re-issuance discipline only (`--issue-directive-atomic` / `--publish-directive-atomic`).

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
