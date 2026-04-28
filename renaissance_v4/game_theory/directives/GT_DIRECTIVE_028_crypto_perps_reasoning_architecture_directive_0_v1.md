# GT_DIRECTIVE_028 — Crypto Perps Reasoning Architecture (Directive 0 — Alignment Memo)

**Date:** 2026-04-27  
**From:** Architect  
**To:** Engineering  
**CC:** Operator  
**Scope:** Pattern Machine / Student reasoning / crypto-perps intelligence architecture (`renaissance_v4/game_theory/` and related contracts; lab deploy per governance when execution paths change)

**Kind:** Architecture update and phased roadmap — **not** an implementation ticket by itself.

---

## 1. Purpose

Define the **target intelligence architecture** for crypto perpetuals reasoning so engineering implements **coherent layers** instead of ad hoc patches (threshold tweaks, duplicate indicators, LLM prompts without measurable inputs).

This memo is **Directive 0**: it states **why** the next phases exist and **what** “done” looks like at the system level. Concrete data audits, schemas, and exams follow as **Directive 1–6** (separate records).

**Why not earlier:** Advanced math (HMM, RL-style loops, EV layers) is unsafe on unproven plumbing. Baseline proof is now in place: decision packets, entry reasoning, seal/authority alignment, traces, and fingerprints are understood (see internal inventory and `docs/student_reasoning_wiring_report_v1.md`). **Now** the intelligence stack can be designed deliberately.

---

## 2. Target architecture (four pillars)

Crypto-perps intelligence in this program is defined as the composition of:

| Pillar | Role | Outcome |
|--------|------|---------|
| **State detection** | Describe the **market regime** at decision time | Deterministic or probabilistic **state labels** (and later posteriors) that downstream layers consume |
| **Pattern memory** | Answer **“have we seen this setup before?”** | **Pattern vectors** + **similarity retrieval** over historical setups (not raw RSI thresholds alone) |
| **Expected value / risk cost** | Quantify **trade vs flat** under uncertainty and carrying costs | **EV estimates** for long, short, and no-trade paths using history, volatility, funding, and explicit risk — decisions stop being pure indicator reactions |
| **RM governance** | **Grade** whether the Student’s decision is **reasonable** given state + memory + EV | Referee / RM does not need to predict every tick; it verifies **coherence** and policy compliance |

The **Student** consumes these layers (and explanations) within contracts already governing packets, annex, seal, and authority. The **engine** remains the numerical backbone until a directive explicitly moves authority; overlaps with existing `entry_reasoning_engine_v1` and `student_decision_authority_v1` must be **named** in later directives to avoid duplicate sources of truth.

---

## 3. Logical flow (reference)

Conceptual order at decision time:

1. **Inputs** — Normalized perps-capable feature set (Directive 1 defines what exists vs missing).
2. **State model** — Regime/state output (Directive 2); optional upgrade path to HMM / NH-HMM **without** rewriting consumers if interfaces are stable.
3. **Pattern fingerprint + retrieval** — Vectorize setup; retrieve similar past rows (Directive 3).
4. **EV / risk-cost layer** — Compare actions using historical outcomes and cost terms (Directive 4).
5. **Student decision** — Still bounded by governance: structured output, seal, authority rules.
6. **RM grading** — Reasoning grade vs state + memory + EV (Directive 5).
7. **Exam** — Scenario battery only after the stack exists (Directive 6).

This is the **intended dependency chain**. Skipping earlier phases produces unrunnable exams or misleading grades.

---

## 4. Phased directives (index)

| Phase | Title | Intent |
|-------|--------|--------|
| **0** | **Architecture alignment (this memo)** | Shared mental model; prevents random patches |
| **1** | Quant / perps **data capability audit** | Inventory OHLCV, funding, OI, liquidations, spread, volume delta, order book, etc. — **no** heavy math without knowing inputs |
| **2** | **Perps state model v1** | Deterministic/probabilistic **regime output** first (trend bull/bear, chop, high-vol breakout, exhaustion, squeeze risk, …); **hook** for later HMM/NH-HMM |
| **3** | **Pattern fingerprint + similarity memory v1** | Setup → pattern vector; retrieve similar historical setups |
| **4** | **EV / risk-cost layer v1** | EV for long, short, no-trade from outcomes + volatility + funding + risk |
| **5** | **RM governance / reasoning grade v1** | Grade Student vs state + memory + EV (reasonableness, not omniscience) |
| **6** | **Crypto perps reasoning exam v1** | Cases across long, short, chop, squeeze, funding, exhaustion, conflict — **after** the above |

Each subsequent directive should be filed as its own GT record with proof bars appropriate to that layer.

---

## 5. Principles (non-negotiable for implementation)

1. **Contracts first** — New intelligence surfaces extend **versioned schemas** and tracing; no silent parallel JSON.
2. **One authority story** — Any new “decision” field must declare whether it **advises**, **constrains**, or **overrides** relative to existing engine and Student seal paths.
3. **Deterministic baselines** — Probabilistic models must ship with **deterministic fallbacks** or fixed seeds where exams require reproducibility.
4. **ProofPack mindset** — Each phase ships tests or operator-visible checks; Directive 6 is not the first time we discover missing data.

---

## 6. Explicit non-goals (Directive 0)

- This memo does **not** authorize Large refactors of unrelated modules.
- It does **not** replace existing closure on plumbing directives; it **builds on** them.
- It does **not** mandate a specific vendor API — Directive 1 decides what data is real vs stubbed.

---

## 7. Directive 0 — acceptance criteria

Directive 0 is **satisfied** when:

- Engineering and Operator acknowledge this memo as the **reference architecture** for crypto-perps reasoning work.
- New work in this area is **labeled** with its phase (1–6) or explicitly marked **out of scope**.
- No feature work claims “state” or “EV” without pointing at the **directive and code** that implements that phase.

Engineer response (when closing Directive 0): short acknowledgment appended below (template section), plus link to where phased directives will live (files or tickets).

---

## Canonical workflow record

This file is the canonical record for **Directive 0** (architecture alignment).

Workflow:

1. Architect issues Directive 0 (this document).
2. Engineering aligns implementation plans and upcoming GT directives to sections 2–4.
3. Operator tracks phased rollout; Architect reviews phase closures per governance.

---

## Engineer update

**Status:** pending engineer acknowledgment

Engineer should append:

- Confirmation that phased directives **1–6** will be drafted/filed as separate GT artifacts before implementation begins.
- Any **boundary questions** (single vs split authority) raised early.

---

## Architect review

**Status:** pending architect review

Architect will append acceptance when Directive 0 acknowledgment is complete.
