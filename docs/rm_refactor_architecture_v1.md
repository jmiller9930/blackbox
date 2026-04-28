# Reasoning Model refactor — architecture response v1

**Document:** `rm_refactor_architecture_v1.md`  
**Date:** 2026-04-27  
**To:** Architect / Operator  
**From:** Engineering (architecture response — **documentation only**; no implementation under this directive)

**Purpose:** Answer **Directive 0 — Reasoning Model refactor: centralize the brain**. This file is the required deliverable: **architecture response**, not trading patches or code changes.

**One-line intent:** Centralize all intelligence inside the **Reasoning Model (RM)** box so the project can evolve from a deterministic indicator reactor into a **governed crypto-perps reasoning system** based on state, memory, expected value, and validated learning.

**Related:** [`renaissance_v4/game_theory/directives/GT_DIRECTIVE_028_crypto_perps_reasoning_architecture_directive_0_v1.md`](../renaissance_v4/game_theory/directives/GT_DIRECTIVE_028_crypto_perps_reasoning_architecture_directive_0_v1.md), [`docs/student_reasoning_wiring_report_v1.md`](student_reasoning_wiring_report_v1.md).

---

## Section 1 — Current confirmed state

### 1.1 Intelligence characterization (today)

| Question | Answer (confirmed from code + wiring reports) |
|----------|-----------------------------------------------|
| Indicator-driven | **YES** — primary decision scalar comes from bars-derived indicators and fixed scoring (`entry_reasoning_engine_v1`). |
| Deterministic (core path) | **YES** — same packet + retrieval list yields same `decision_synthesis_v1` absent optional router escalation. |
| Probabilistic (HMM / posteriors) | **NO** — no latent state model or sampled decisions in the entry engine. |
| EV-based action selection | **NO** — no expected-value-of-action layer in the entry engine; batch **expectancy** metrics exist elsewhere for scorecards and governance, not as RM-owned EV driving direction. |
| Learning in the ML / adaptive-weight sense | **NO** — no gradient updates to a unified reasoning model. |
| Memory-driven pattern similarity | **NO** — retrieval is largely signature-key based; memory scoring is heuristic and constrained by pre-reveal slice shape; not “similar setups” in embedding sense. |
| Hybrid | **YES** — fixed signal engine + LLM narrative + seal/authority + optional governance overlays (`student_decision_authority_v1`, 026c lifecycle tracks). |

### 1.2 Plumbing phase — closed for “can we inspect decisions?”

Engineering confirms the following **working plumbing** (isolated test mode and traces):

- **Structured annex** (`student_context_annex_v1`) can be attached **before** the Student LLM so prompt context includes entry-reasoning fields (`student_context_builder_v1`, seam in `student_proctor_operator_runtime_v1`).
- **Student test mode** can produce multiple sealed decisions with traces (`learning_trace_events_v1`, fingerprint reports under `runtime/student_test/`).
- **Authority and seal** paths can be aligned and counted in acceptance artifacts.
- **Decision fingerprint reports** exist and support inspection: context → raw answer → parse → authority → seal.

This closes **basic plumbing + inspectability**. It does **not** close **unified RM intelligence**.

---

## Section 2 — Target architecture

### 2.1 Boundary rule

**Anything that decides, reasons, scores intelligence, evaluates memory, estimates market state, computes expected value, grades decision quality, or governs learning** belongs **inside the Reasoning Model box**.

**No brain logic outside RM.** The system must not accumulate parallel “brains” in scattered modules, hidden heuristics, UI-only inference, policy adapters that encode undeclared reasoning, or one-off exam scripts that grade reasoning without RM audit surfaces.

Deterministic **market math** feeds RM via a **feature layer**; RM owns **interpretation**, **aggregation**, **memory semantics**, **EV**, **governance**, and **exam/rubric logic** as specified in phased work.

### 2.2 Layers (normative)

| Layer | Owns | Does not |
|-------|------|----------|
| **DATA** | Factual truth: bars, funding/OI/liquidation feeds **when available**, fills, Referee outcomes, ledgers, policy registry pointers, runtime logs, trace artifacts | Reasoning, decisions, final scores |
| **Feature / signal layer** | Observable deterministic facts: RSI, EMA, ATR, returns, rolling vol, volume/funding/OI/liquidation **features**, labels | Final trade action, EV, regime posteriors (those belong in RM once implemented) |
| **Reasoning Model (RM)** | State interpretation, regime/state outputs (deterministic then probabilistic), fingerprints, similarity retrieval, memory relevance, EV/risk-cost, reasoning-quality grading, learning promotion/rejection **semantics**, rubrics, exam logic, confidence calibration tied to evidence | Raw exchange connectivity (DATA); outcome labeling before reveal (Referee leak) |
| **Student** | Structured decision/thesis **from RM-provided causal context**: action, direction, confidence, thesis, supporting/conflicting evidence, invalidation, context interpretation | Bypassing RM governance; inventing bars or post-decision truth |
| **Referee** | Post-decision outcome truth: favorable move, stop/target, PnL, path, drawdown | Pre-decision Student packet content |
| **Execution (e.g. Billy)** | Acts **only** on validated, approved outputs | Intelligence or parsing raw LLM text |

### 2.3 Text diagram (data flow)

```
DATA (truth only)
    → Feature layer (observable facts, no final “brain”)
        → RM (intelligence: state, memory, similarity, EV, governance, rubric)
            → Student (express decision/thesis under RM context + contracts)
                → Referee (outcome truth, post-decision)
                    → Learning governance + persistence (governed episodes)
                        → RM-addressable memory (retrieval/fingerprint surfaces — must not bypass RM)
```

**Referee truth** must never leak into **pre-reveal** Student context (existing `validate_pre_reveal_bundle_v1` contract discipline continues).

---

## Section 3 — Crypto-perps intelligence requirements

The target domain is **crypto perpetual swaps**, not a generic equity assistant.

RM must eventually reason about (where DATA supports it): funding cycles, OI expansion/contraction, liquidation cascades, long/short crowding, basis/funding pressure, leverage risk, volatility spikes, fake vs real breakouts, trend continuation vs mean reversion, chop/no-trade regimes, late-entry risk, **cost of carry / holding**.

**Target analytical question (not yet implemented as a single module):**

> Given current features and prior **similar** setups, what is the probability that this market is in a specific **state**, and what is the expected value / risk of each action (long, short, no-trade)?

Today’s model remains closer to:

> OHLCV → RSI/EMA/ATR labels → fixed weighted score → threshold → action,

plus overlays and narrative LLM — until Phases B–D are implemented **inside RM**.

---

## Section 4 — Required future RM capabilities (phased map)

| Phase | Capability | Notes |
|-------|------------|--------|
| **A** | Data and math inventory | Prove inputs and formulas before state/EV |
| **B** | Perps state model | Deterministic labels first; probabilistic hooks later |
| **C** | Pattern fingerprint + similarity memory | Beyond exact signature-key retrieval |
| **D** | EV / risk-cost layer | Long / short / flat economics + perp costs |
| **E** | RM decision governance | Justify vs state, memory, EV; hallucination/conflict checks |
| **F** | Crypto-perps reasoning exam | After foundations; grades **reasoning**, not plumbing |

Sections 5–6 below map these to **Directive 1–6** with migration detail.

---

## Section 5 — Rules and constraints (engineering adherence)

- Do **not** implement isolated intelligence outside RM.
- Do **not** create a separate exam brain or separate memory brain.
- Do **not** let policy packs or UI infer undeclared reasoning quality.
- Do **not** use PnL alone as learning truth; do **not** promote wins with bad reasoning; do **not** punish sound no-trade for lack of PnL.
- Do **not** claim probabilistic modeling, EV, perps intelligence, or adaptive learning without the mechanisms actually computing and **using** those concepts under RM audit surfaces.

---

## Section 6 — Migration plan (Directives 1–6)

Each phase is a **future GT directive** (files to be created under `renaissance_v4/game_theory/directives/` unless architect places them elsewhere). **This document does not implement them.**

### Directive 1 — Data / math capability audit (maps to Phase A)

| Item | Detail |
|------|--------|
| **Goal** | Inventory OHLCV, funding, OI, liquidations, spread/liquidity, volume delta, order book **as available**; list all indicator/scoring/memory/promotion formulas and thresholds in use. |
| **Files likely touched** | Audit output may reference: `student_proctor/entry_reasoning_engine_v1.py`, `student_proctor/learning_memory_promotion_v1.py`, `student_context_builder_v1.py`, `pattern_game` / DB loaders, `run_memory`, scorecard builders — **read-first**, minimal edits unless fixing doc drift. |
| **Artifacts** | Written audit matrix (CSV or markdown appendix); gap list “available / stub / missing”. |
| **Acceptance proof** | Signed checklist + repo pointers (file:function); no state-model or EV code required. |
| **Dependencies** | None (foundation). |

### Directive 2 — RM state model v1 (maps to Phase B)

| Item | Detail |
|------|--------|
| **Goal** | RM-owned state outputs (deterministic first); interfaces allow later HMM/NH-HMM **without** duplicating brains elsewhere. |
| **Files likely touched** | New RM module package (path TBD); integration points from `run_entry_reasoning_pipeline_v1` or successor **single** RM façade; traces in `learning_trace_*`. |
| **Artifacts** | Schema for state outputs; unit tests; trace stages. |
| **Acceptance proof** | Tests + trace excerpt showing state fields per trade; explicit “prob placeholder” if not numeric yet. |
| **Dependencies** | Directive 1 complete. |

### Directive 3 — Pattern fingerprint + similarity memory v1 (maps to Phase C)

| Item | Detail |
|------|--------|
| **Goal** | Fingerprint vector + similarity retrieval; answer “have we seen this **type** of setup?” — not only exact `signature_key`. |
| **Files likely touched** | `cross_run_retrieval_v1.py` (evolve or wrap), `student_learning_store_v1.py`, RM fingerprint module; contracts in `contracts_v1.py`. |
| **Artifacts** | Fingerprint schema; retrieval metrics; tests with synthetic near-duplicates. |
| **Acceptance proof** | Tests proving similarity ranking; pre-reveal safety preserved. |
| **Dependencies** | Directives 1–2 (fingerprints lean on state/features). |

### Directive 4 — EV / risk-cost layer v1 (maps to Phase D)

| Item | Detail |
|------|--------|
| **Goal** | RM computes or approximates EV / risk-cost for long, short, no-trade using history + costs; auditable deterministic first version. |
| **Files likely touched** | New RM EV module; inputs from DATA/feature layer; optional links to scorecard/referee aggregates — **no** silent duplication of `entry_reasoning_engine_v1` scoring as “EV”. |
| **Artifacts** | EV schema; tests; trace fields. |
| **Acceptance proof** | Reproducible EV numbers on fixtures; documents formulas. |
| **Dependencies** | Directives 1–3 strongly recommended. |

### Directive 5 — RM reasoning governance v1 (maps to Phase E)

| Item | Detail |
|------|--------|
| **Goal** | Grade Student vs RM state + memory + EV; detect inconsistency, overconfidence, hallucinated evidence; accept/reject/escalate semantics. |
| **Files likely touched** | Consolidate governance currently spread across `learning_memory_promotion_v1`, `student_decision_authority_v1`, validation helpers — **toward** RM façade without breaking seals overnight (migration plan inside directive). |
| **Artifacts** | Governance record schema; integration tests; operator-visible proof. |
| **Acceptance proof** | Tests + sample traces showing governance decisions. |
| **Dependencies** | Directives 2–4 minimum for meaningful checks. |

### Directive 6 — Crypto-perps reasoning exam v1 (maps to Phase F)

| Item | Detail |
|------|--------|
| **Goal** | Scenario battery: trend, chop, fake breakout, funding/crowding, liquidation stress, conflicts, low-edge setups — grades **reasoning** against RM rubric. |
| **Files likely touched** | Exam pack builders, `web_app` or runner hooks, fixture repos — **no** duplicate brain outside RM. |
| **Artifacts** | Exam definitions; grading outputs; regression suite. |
| **Acceptance proof** | End-to-end exam run + architect-approved rubric mapping. |
| **Dependencies** | Directives 1–5 foundation wired. |

---

## Current gaps (explicit)

| Gap | Today | Target |
|-----|--------|--------|
| Unified RM module | Logic split across `entry_reasoning_engine_v1`, promotion, authority, router | Single RM façade + audit path |
| State model | Discrete RSI/EMA/ATR labels only | Regime/state layer + optional probabilities |
| EV for actions | Not in entry engine | RM-owned EV/risk-cost for long/short/flat |
| Pattern similarity | Signature-key retrieval, heuristic memory score | Fingerprint + similarity retrieval |
| Perps-specific features | Limited by DATA in packet | Funding/OI/liquidation/crowding **as DATA allows** |
| Reasoning rubric | Partial validation + promotion gates | Explicit RM grading vs state/memory/EV |
| Unified learning governance semantics | JSONL + promotion + eligibility | RM-governed “should this become memory?” |

---

## Non-goals (this refactor framing)

- **No PPO / RL** implementation in the initial RM refactor phases.
- **No HMM / NH-HMM** until Directive 1 proves inputs and Directive 2 establishes deterministic state interfaces (unless architect explicitly greenlights a spike tied to data proof).
- **No production trading behavior change** as the goal of this architecture phase.
- **No learning promotion semantics change** until governance is explicitly redesigned under Directive 5 (promotion code may stay as-is until then).
- **No full-run Student batch** required **for acceptance of this architecture document** — acceptance is this file + YES/NO confirmations.

---

## Disagreement protocol

If engineering disagrees with placing a specific behavior inside RM (e.g. legacy engine ownership), **stop** and document the conflict in a GT directive or amendment **before** implementing intelligence splits.

---

## YES / NO confirmations

| # | Statement | Answer |
|---|-----------|--------|
| 1 | Is this a Reasoning Model refactor (not a trading patch)? | **YES** |
| 2 | Is all brain logic **intended** to live inside RM over time? | **YES** |
| 3 | Are we avoiding duplicate intelligence paths (no scattered brains)? | **YES** (normative target; migration explicit in Directives 1–6) |
| 4 | Are we deferring HMM/RL until data and state foundations are proven? | **YES** |
| 5 | Are we preserving existing working Student plumbing (packets, annex, seal, authority, fingerprints)? | **YES** |
| 6 | Are we preserving DATA as truth-only (no reasoning in raw ingest)? | **YES** |
| 7 | Are we preserving Referee as post-decision truth (no leak into pre-reveal)? | **YES** |

---

## Document acceptance

This **Directive 0 documentation deliverable** is complete with:

- This file: **`docs/rm_refactor_architecture_v1.md`**
- All **YES / NO** confirmations answered above.

No code implementation was required for this directive beyond maintaining this repository document.
