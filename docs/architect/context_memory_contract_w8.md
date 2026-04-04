# W8 — Context & Memory Contract (memory-driven agent)

**Status:** **Contract defined (Advisor); implementation = gap** — see §8.  
**Related:** [`context_engine_as_built.md`](context_engine_as_built.md) (current behavior).  
**Authority:** Training Architect must approve scope, risk, and phased delivery.

---

## 1. Purpose

Define **required** behavior for a **memory-driven** analyst path: **similarity-based retrieval** of **structured lessons** that **influence** current reasoning — distinct from **history-only** (raw ledger) and from **bounded carryforward** alone.

This document is the **contract** the Agentic Training Advisor requested. **§8** states compliance honestly.

---

## 2. Required behavior (contract text)

When Anna is presented with a **trade or problem**, the system **must** support:

1. **Situation recognition** — represent the current situation in a form comparable to stored experience.  
2. **Similarity-based memory retrieval** — retrieve **relevant** prior lessons when **exact** match is not required (near-match / edge cases).  
3. **Structured lesson recovery** — lessons are **not** raw log dumps; they are **distilled, reusable** objects (patterns, constraints, validated insights).  
4. **Application to reasoning** — retrieved memory **influences** analysis (FACT or controlled narrative layer per policy).  
5. **Edge cases** — defined behavior when match is **partial**, **ambiguous**, or **missing** (no hallucinated memory).

---

## 3. Required distinctions (must be explicit in implementation)

| Layer | Definition | Must not |
|-------|------------|----------|
| **History** | Raw trades, JSONL rows, append-only logs | Be the only “memory” |
| **Memory** | Distilled lessons / patterns with metadata (scope, validity, source) | Be implicitly merged with history without schema |
| **Operational context** | Market, policy, tick, **selected** memory injections for **this** decision | Include unbounded full ledger |

Implementation **must** keep these **separate in code paths** (distinct stores or namespaces + injection pipeline), not only in prose.

---

## 4. Documentation requirements (this file + annexes)

| Topic | Location |
|-------|----------|
| What qualifies as memory | §2, §6 |
| How memory is created | §6 (RCA, validation, promotion, human sign-off — **TBD** by Architect) |
| How similarity is defined | §6 (metric / embeddings / rules — **implementation choice**) |
| Retrieval API | §6 |
| Influence on reasoning | §6 (FACT vs advisory layer) |
| Post-training persistence | §6 |
| Exclusions | Full ledger injection; unvalidated noise as authoritative FACT |

---

## 5. Validation & test requirements (contract must be provable)

Scenarios **required** by the Advisor (summarized):

| # | Scenario | Pass criterion |
|---|----------|----------------|
| T1 | Known pattern reuse | Same class of setup → lesson retrieved → visible influence on output |
| T2 | Near-match | No exact key → closest relevant memory → influence traceable |
| T3 | No memory | No prior → no fabricated prior; safe fallback |
| T4 | Persistence | Memory survives cycles/sessions until reset |
| T5 | Noise control | Irrelevant history **not** injected; **bounded** context |

**Artifacts per run (for audit):** inputs, **retrieved memory objects**, **context snapshot** (prompt slice), **output**, **short explanation** of influence (automated or human-annotated).

---

## 6. Target architecture (engineering — not yet built)

*This section describes **intended** behavior once implemented. It is **not** a claim of current code.*

### 6.1 Memory objects (conceptual schema)

- **id**, **created_at**, **source** (e.g. RCA, gate event, human), **situation_fingerprint** or **embedding id**, **lesson_text** (structured fields TBD), **validity** (scope: symbol, regime, tier), **confidence / validation state**.

### 6.2 Similarity

- Options: embedding + nearest-neighbor; rule-based **tags** (symbol, regime, outcome class); hybrid. **Architect + Engineering** choose per risk and cost.

### 6.3 Injection pipeline

- **After** authoritative FACTs from math/rules; **memory layer** as **FACT** or **advisory** per governance (fail-closed if unvalidated).

### 6.4 Creation path

- From **structured RCA**, **promotion events**, **operator-approved** bullets — **not** automatic “every row becomes memory” without validation.

### 6.5 Exclusions

- **No** default injection of **full** `paper_trades.jsonl`.  
- **No** treating raw log lines as **validated** memory without policy.

---

## 7. Implementation plan (phased — timeline = Architect approval)

| Phase | Deliverable | Est. complexity |
|-------|-------------|-----------------|
| **P0** | This contract + compliance matrix (§8) | Done (this doc) |
| **P1** | Memory store schema + CRUD + migration; separate from raw ledger | High |
| **P2** | Similarity / retrieval service (configurable) | High |
| **P3** | Integration into `build_analysis` / injection layer + flags | High |
| **P4** | Tests T1–T5 + artifact exporter for proof package | Medium–High |
| **P5** | RCA → memory pipeline (structured) | Medium (depends on RCA schema) |

**Timeline:** Not committed in-repo — requires **Architect** resourcing and **risk** review (hallucination, overfitting, governance).

**Update (Advisor direction):** W9 is **in-scope now**. The **executable MVP slice** (ordered PRs, code touch list, tests, safety) is **`docs/architect/w9_implementation_plan.md`**.

---

## 8. Compliance assessment — **as-built vs this contract**

| Requirement | As-built (`context_engine_as_built.md`) | Compliant? |
|-------------|----------------------------------------|------------|
| Similarity-based retrieval (non-exact) | Not implemented | **No** |
| Structured lesson objects (not raw logs) | Carryforward bullets only; no lesson DB | **No** |
| Explicit history / memory / operational split | Merged in one prompt stack | **No** |
| Influence of memory on reasoning beyond carryforward | Partial (short FACT bullets) | **Partial** |
| Near-match / edge case handling | N/A | **No** |
| Provable test artifacts T1–T5 | Not present | **No** |

**Verdict:** **Gap identified.** The system is **rule-driven** and **history-aware**; it is **not** **memory-driven** in the sense of this contract until **P1–P4** (minimum) ship.

**Response to Advisor:** **Not** “Compliant (as-built).” **“Gap identified — implementation plan §7; contract documented §1–6; proof pending implementation.”**

---

## 9. Acceptance criteria (Advisor §7)

Satisfied **only** when:

1. **Documentation** — this contract + as-built delta updated each release.  
2. **Code** — retrieval + injection + separation of concerns **landed** and **flagged**.  
3. **Validation** — tests T1–T5 **green** + artifacts **checked in** or generated in CI.

---

## 10. Sign-off (external)

| Role | Name | Date | Notes |
|------|------|------|-------|
| Training Architect | | | Approve scope / risk / phase order |
| Agentic Training Advisor | | | Acknowledge gap vs contract |
| Engineering lead | | | Commit delivery plan |

---

*Engineering — W8 draft. **Do not** mark contract “satisfied” until §9 and §8 compliance row is all green.*
