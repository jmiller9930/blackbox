# GT_DIRECTIVE_028 — Reasoning Model Refactor: Centralize the Brain (Directive 0 — Alignment Memo)

**Date:** 2026-04-27  
**From:** Architect  
**To:** Engineering  
**CC:** Operator  
**Scope:** Pattern Machine / Student reasoning / crypto-perps intelligence architecture (`renaissance_v4/game_theory/` and related contracts; lab deploy per governance when execution paths change)

**Kind:** Architecture update and phased roadmap — **not** a bundle of trading patches or unrelated feature tickets.

**One-line intent:** We are **not** adding features; we are **moving all intelligence into one governed Reasoning Model (RM) box**.

---

## Executive framing

This program is undertaking a **Reasoning Model refactor**. The goal is a **single, auditable place** where anything that **decides, reasons, scores intelligence, evaluates memory, estimates state, computes EV, or governs learning** lives. Deterministic market math **feeds** that box; it does **not** scatter “brain” logic across modules.

---

## 1. Purpose

Define the **target architecture** so engineering builds **coherent layers** instead of ad hoc patches (threshold tweaks, duplicate indicators, LLM prompts without measurable inputs, hidden heuristics).

This memo is **Directive 0**: it states **why** phased work exists and **what** “done” looks like at the system level. Concrete data audits, schemas, and exams follow as **Directive 1–6** (separate records).

**Why not earlier:** Advanced structures (state models, EV layers, similarity memory) are unsafe on unproven plumbing. Baseline proof is now in place: packets, entry reasoning plumbing, seal/authority alignment, traces, and fingerprints are understood (see internal inventory and `docs/student_reasoning_wiring_report_v1.md`). **Now** intelligence can be **centralized** deliberately.

---

## 2. Hard boundary — no brain logic outside RM

**Rule:** Anything that **decides**, **reasons**, **scores intelligence**, **evaluates memory**, **estimates state**, **computes EV**, or **governs learning** belongs **inside the Reasoning Model (RM) box**.

**Corollary:** Deterministic **market math** (bars-derived features) may live in a **signal/feature layer** and **feed** RM; RM owns **interpretation**, **aggregation**, **memory**, **EV**, **governance**, and **learning promotion** semantics. There must be **one** governed surface through which audits run.

**Directive language for implementation:** **No brain logic outside RM.**

**Forbidden patterns:**

- Hidden scoring in arbitrary modules (duplicate “final scores” that bypass RM).
- A **separate exam brain** that encodes intelligence RM cannot see.
- **Isolated memory heuristics** that bypass RM (retrieval without RM-visible scoring paths).
- **Policy-specific intelligence** that cannot be audited **through** RM (no unauditable side channels).

Later phased directives **migrate** scattered logic toward RM; they do not add parallel brains.

---

## 3. Layered architecture (reference)

| Layer | Responsibility | Examples |
|--------|----------------|----------|
| **DATA** | Provides **truth**: canonical inputs and outcomes | Market bars; funding; open interest; liquidation-related feeds where available; fills; outcomes; logs; ledgers |
| **Signal / feature layer** | Computes **raw features** only (deterministic transforms, no proprietary “decision”) | RSI, EMA, ATR, Z-score, volume state, funding state, liquidation-risk proxies, spread features — **inputs to RM** |
| **RM box** | Owns **intelligence** | State model; pattern memory; similarity; EV; decision-quality scoring; reasoning governance; **learning promotion logic** as applicable |
| **Student** | Produces **decision / thesis** using **RM-provided context** (and contracts for seal/authority as today) |
| **Referee** | Grades **outcome** after the fact (PnL / rules), distinct from RM’s **reasoning** governance |
| **Billy / execution** | Acts **only** on **validated, approved** outputs — **no** intelligence here |

**Logical order at decision time:** DATA → features → **RM** → Student → (later) outcome → Referee. Execution is downstream of validation.

---

## 4. Capabilities inside the RM box (maps to phased work)

These are **not** separate silos in random modules; they are **RM-owned capabilities** (implemented across Directive 1–6):

| Capability | Role |
|-------------|------|
| **State model** | Regime / state output (deterministic first; probabilistic hooks later) |
| **Pattern memory + similarity** | “Have we seen this setup before?” — vectors + retrieval |
| **EV / risk-cost** | Long / short / no-trade economics using history, volatility, funding, risk |
| **Reasoning governance + learning promotion** | What counts as coherent reasoning; what gets promoted — **auditable through RM** |

Directives **2–5** land **inside** this box; Directive **1** feeds DATA/feature clarity; Directive **6** validates the **whole** stack under exam scenarios.

---

## 5. Logical flow (reference)

1. **Inputs** — Normalized perps-capable feature set (Directive 1 defines what exists vs missing).
2. **State model** — Regime/state output (Directive 2); stable interfaces for later HMM / NH-HMM **inside RM**.
3. **Pattern fingerprint + retrieval** — Setup → vector; similar historical setups (Directive 3); **RM-visible**.
4. **EV / risk-cost layer** — Compare actions (Directive 4); **RM-owned**.
5. **Student decision** — Thesis/decision using RM context; existing seal/authority contracts apply until refactors say otherwise.
6. **RM reasoning grade** — Coherence vs state + memory + EV (Directive 5).
7. **Exam** — Scenario battery after the stack exists (Directive 6).

Skipping earlier phases produces exams or grades that **cannot** trace back to **one brain**.

---

## 6. Phased directives (index)

| Phase | Title | Intent |
|-------|--------|--------|
| **0** | **Architecture alignment (this memo)** | Reasoning Model refactor — **centralize the brain**; no duplicate intelligence surfaces |
| **1** | Quant / perps **data & math capability audit** | **`GT_DIRECTIVE_029`** — inventory DATA, math, decision path, memory usability; deliverable `docs/rm_directive_1_quant_perps_data_math_capability_audit_v1.md` |
| **2** | **Perps state model v1** | Regime output inside **RM** (hook for HMM/NH-HMM later) |
| **3** | **Pattern fingerprint + similarity memory v1** | RM-owned pattern vectors + retrieval |
| **4** | **EV / risk-cost layer v1** | RM-owned EV for long, short, no-trade |
| **5** | **RM governance / reasoning grade v1** | Grade Student vs RM outputs (reasonableness, not omniscience) |
| **6** | **Crypto perps reasoning exam v1** | Cases across regimes and conflicts — **after** RM stack exists |

Each subsequent directive should be filed as its own GT record with proof bars appropriate to that layer.

---

## 7. Principles (non-negotiable)

1. **Central RM audit surface** — Intelligence must be inspectable **through** RM contracts and traces.
2. **Contracts first** — Versioned schemas; no silent parallel JSON.
3. **One authority story** — Any field that looks like a “decision” or “score” declares its relationship to RM and to Student seal paths (migrate legacy duplicates explicitly).
4. **Deterministic baselines** — Probabilistic models ship with reproducible fallbacks or fixed seeds where exams require it.
5. **ProofPack mindset** — Each phase ships tests or operator-visible checks; Directive 6 is not the first discovery of missing data.

---

## 8. Explicit non-goals (Directive 0)

- This memo does **not** authorize unrelated trading patches disguised as “intelligence.”
- It does **not** replace closure on existing plumbing directives; it **builds on** them.
- It does **not** mandate a specific vendor API — Directive 1 decides what data is real vs stubbed.

---

## 9. Directive 0 — acceptance criteria

Directive 0 is **satisfied** when:

- Engineering and Operator acknowledge this memo as the **reference architecture** for the Reasoning Model refactor.
- New work is **labeled** with phase (1–6) or marked **out of scope**.
- No work introduces **brain logic** outside RM without an explicit migration plan and GT record.

Engineer response (when closing Directive 0): short acknowledgment appended below, plus confirmation that phased directives **1–6** will be filed before implementation and that **boundary migration** (legacy engine vs RM) is tracked.

---

## Canonical workflow record

This file is the canonical record for **Directive 0** (architecture alignment).

Workflow:

1. Architect issues Directive 0 (this document).
2. Engineering aligns implementation plans and phased directives to sections 3–6.
3. Operator tracks phased rollout; Architect reviews phase closures per governance.

---

## Engineer update

**Status:** pending engineer acknowledgment

Engineer should append:

- Confirmation that phased directives **1–6** will be drafted/filed before implementation.
- **Migration notes**: which existing modules (`entry_reasoning_engine_v1`, promotion paths, authority) consolidate toward RM and in what order.

---

## Architect review

**Status:** pending architect review

Architect will append acceptance when Directive 0 acknowledgment is complete.

---

## Directive closures (trace-validated)

**Directive 2 — CLOSED:** trace-validated deterministic perps state model with completed acceptance bundle.

Closure evidence (per job folder under `runtime/student_test/<job_id>/`): `learning_trace_events_v1.jsonl` (including ten `perps_state_model_evaluated_v1` rows with ordering vs indicators and synthesis), `student_test_acceptance_v1.json`, `decision_fingerprint_report.md`; `python3 scripts/run_student_test_mode_v1.py --recipe-id pattern_learning` exits **0** with `"ok": true` when the harness completes.
