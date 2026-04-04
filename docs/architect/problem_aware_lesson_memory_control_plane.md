# Problem-aware lesson memory control plane — design note

**Source directive:** Training Architect — *Control-plane memory engagement (gap closure)* (`memory_engagement_directive.pdf`, 2026-04).  
**Status:** Gap definition + implementation directions — **new required layer**; **does not modify** accepted W9 semantics (validated-only injection, bounded FACT merge, deterministic `behavior_effect` rules).  
**Audience:** Training Architect, Engineering, Advisor  
**Date:** 2026-04

---

## Directive objective (verbatim intent)

- **Achieved:** lesson memory retrieval, validated-only injection, bounded similarity scoring, deterministic behavioral effects → **memory influences behavior**.
- **Gap to close:** the system does not yet define **when** memory should be engaged, intensified, or constrained based on **problem conditions**.
- **Objective:** **memory engagement responsive to problem state**, not only environment flags.

---

## Context (as-built, accepted)

Lesson memory is **memory-capable** and can **influence behavior** when engaged. Engagement today is **environment + main analysis path** (context complete, `ANNA_LESSON_MEMORY_ENABLED`, SQLite `conn`). It is **not** modulated by problem state (risk, confidence, conflict, semantic ambiguity beyond the early clarification gate).

This note records the **control-plane** work: **when** memory should engage, **intensify**, be **constrained**, or **bypassed** based on **detected problem conditions**.

---

## Required capabilities (directive)

### 1. Detect problem-state signals

Each signal below must be **explicitly defined**, **implemented**, and **inspectable** in `anna_analysis_v1` (not only internal variables).

| Signal | Directive requirement | Notes |
|--------|------------------------|--------|
| **Ambiguity** | **Semantic**, not only missing fields | Beyond `assess_context_completeness()` early gate; requires additional heuristics or layer output — scope for MVP must be named. |
| **Low confidence** | Explicit or **derived** | Pipeline/LLM/playbook metadata must converge on testable fields. |
| **Conflicting signals** | Defined | e.g. disagreeing authoritative layers — needs explicit detection rules. |
| **Elevated risk** | Defined | Can build on existing `risk_assessment` + guardrail context. |

### 2. Engagement modes (directive)

| Mode | Meaning |
|------|--------|
| **Baseline** | Current W9 retrieval/injection behavior (when memory is env-enabled). |
| **Intensified** | Broader retrieval (e.g. higher effective cap or lower min score within **hard** bounds). |
| **Constrained** | Stricter filtering (tighter match, fewer lessons, or stricter score floor). |
| **Bypass** | Memory disabled for this run (FACT + behavioral merge off), regardless of base env, unless directive allows env-only override — **must be explicit in implementation**. |

### 3. Bind signals → engagement behavior

Mapping must be **explicit in code**, **configurable where needed**, and **visible** in output. Example patterns from the directive (final matrix is an **engineering + architect** decision):

| Situation (example) | Example mode direction |
|---------------------|-------------------------|
| High risk | **Constrained** *or* **Intensified** — **pick one policy**; contradictory example in directive implies tradeoffs need a written choice. |
| Low confidence | **Intensified** |
| Conflicting signals | **Intensified** |
| Clear / routine | **Baseline** |

### 4. Control-plane ownership

- **Where logic lives:** a dedicated module or clear functions invoked from `build_analysis` **before** `build_lesson_memory_fact_lines` / merge (so retrieval parameters can be adjusted).
- **Invocation:** single pass per analysis run; deterministic order documented.
- **Interaction:** reads problem signals → selects mode → sets retrieval parameters (`top_k`, `min_score` effective values) and gates `behavior_effect` if policy says so; **does not** relax validated-only or global caps.

### 5. Output visibility (`anna_analysis_v1`)

Payload must include (directive):

- **Detected signals** (structured).
- **Engagement mode** (enum/string).
- **Retrieval parameters** used for that run (effective inject cap, min score, any mode-specific overrides).

Suggested shape (illustrative): extend `lesson_memory` or add `memory_control_plane: { "signals": {...}, "mode": "...", "retrieval": {...} }`.

---

## Detailed signal hooks (repository, pre-implementation)

| Signal | Role | Existing / candidate hooks (repo) |
|--------|------|-----------------------------------|
| **Ambiguity** | User intent or market situation underspecified | **Partial:** `assess_context_completeness()` (`context_requirements.py`) — early gate only. **Extensions:** second-pass ambiguity (e.g. hedge language, mixed timeframe) would need explicit rules or model output — **not** in W9. |
| **Low confidence** | Model or layer unsure | **Candidate:** `resolve_answer_layers` / LLM path metadata if exposed (e.g. playbook miss + weak template). **Not** unified today as a single field for lesson gating. |
| **Conflicting signals** | Facts or layers disagree | **Candidate:** compare authoritative layers (math vs playbook vs strategy facts), or explicit “conflict” flags from a future reconciler. **Not** wired to lesson memory. |
| **Elevated risk** | Guardrail / context / text-driven risk | **Exists:** `determine_risk_level()` + `risk_assessment` in `anna_analysis_v1` (`risk.py`, `analysis.py`). **Not** passed into `lesson_memory` retrieval today. |

These are **candidates** for a **ProblemTier** or **ProblemProfile** input to policy — not commitments to implement all at once.

---

## Policy options (maps to engagement modes)

| Option | Maps to modes | Tradeoff |
|--------|----------------|----------|
| **A — Always-on baseline** | Baseline only when memory env on | Simple; may use memory on routine turns. |
| **B — Problem-triggered intensification** | Intensified on signal | Needs reliable signals + tests. |
| **C — Selective widening/narrowing** | Intensified vs Constrained | Needs tuning + forensics. |
| **D — Behavior-effect gating** | Often **Constrained** for stance changes | Separates FACT context from `behavior_effect`. |

---

## Recommended MVP approach (smallest safe)

**Goal:** Introduce **problem-aware orchestration** without destabilizing W9 invariants (validated-only, bounded injection, no ledger flooding, no silent promotion of candidates).

1. **Define a single internal `ProblemTier`** (or boolean `problem_context`) computed **only from fields already produced in `build_analysis` before lesson merge** — e.g. start with **`risk_assessment.level`** + **`guardrail_mode`** + optional **`context_assessment`** flags. **Do not** block shipping on full semantic ambiguity or LLM confidence in v1 of this control plane.

2. **Default behavior = current W9** when a new env gate is off, e.g. `ANNA_LESSON_MEMORY_PROBLEM_AWARE=0` (default **0**): no change to retrieval math.

3. **When `ANNA_LESSON_MEMORY_PROBLEM_AWARE=1`:** apply **one** bounded knob only, for example:
   - **Intensification:** if `ProblemTier` is `medium` or `high`, increase effective inject cap by **at most +1** vs `ANNA_LESSON_MAX_INJECT`, still capped by a **new absolute ceiling** (e.g. max 4); **or**
   - **Neutral / narrow:** if `risk_level == high` and `guardrail_mode == FROZEN`, **skip** `behavior_effect` application while still allowing read-only FACT lines (policy choice — document explicitly).

4. **Telemetry:** add `lesson_memory.control_plane` (or extend `lesson_memory` payload) with `{ "problem_tier": "...", "knob": "baseline|intensify|..." }` so Foreman/architect can verify behavior without guessing.

5. **Tests:** pytest for tier boundaries; prove **no** change when problem-aware flag is off.

Early slices may **stub** semantic ambiguity and conflicting signals as `unknown` or `false` with explicit TODO, only if the directive allows phased delivery — **architect sign-off** on stubbed vs blocking.

---

## Constraints (directive — must not break)

- Validated / promoted-only lesson injection.
- Bounded memory (hard caps remain).
- Deterministic behavior paths for any `behavior_effect` rules that remain in scope.

---

## Deliverables (directive)

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | **Design note** | This document (living; update as matrix is fixed). |
| 2 | **Implementation slice (MVP)** | Code + config hooks per sections above. |
| 3 | **Validation artifacts** | Tests + proof that engagement **adapts** to problem conditions; before/after `anna_analysis_v1` excerpts. |

---

## Acceptance criteria (directive)

The gap is **closed** when:

- Memory engagement is **adaptive to problem conditions** (not only `ANNA_LESSON_MEMORY_ENABLED` on/off for every qualifying run).
- Signals, mode, and retrieval parameters are **visible** on `anna_analysis_v1`.

---

## Closing

| Layer | State |
|-------|--------|
| W9 | **Accepted unchanged in meaning** — memory-capable, behaviorally influenced under current engagement rules. |
| New layer | **Problem-aware control plane** — this note + MVP + validation. |

**Framing:** *We have memory → behavior; we now require memory → engagement that responds to problem state.*

Further work references this file and W9 proof artifacts; implementation is a **separate phase** with its own proof package.

---

## Implementation (MVP, runtime)

| Area | Location |
|------|----------|
| Signals, modes, retrieval math | `scripts/runtime/anna_modules/memory_control_plane.py` |
| `build_analysis` integration, `anna_analysis_v1.memory_control_plane` | `scripts/runtime/anna_modules/analysis.py` |
| Lesson retrieval overrides (`top_k`, `min_score`) | `scripts/runtime/anna_modules/lesson_memory.py` — `build_lesson_memory_fact_lines(..., top_k=, min_score=)` |
| `behavior_effect` gated by mode | `scripts/runtime/anna_modules/policy.py` — `apply_lesson_memory_to_suggested_action(..., allow_behavior_effect=)` |
| Tests | `tests/test_memory_control_plane.py` |

**Env:** `ANNA_LESSON_MEMORY_CONTROL_PLANE` — unset defaults to **on**; set to `0` to disable dynamic modes (W9-compatible baseline retrieval). `ANNA_LESSON_MEMORY_HIGH_RISK_MODE=constrained\|intensified` (default `constrained`).
