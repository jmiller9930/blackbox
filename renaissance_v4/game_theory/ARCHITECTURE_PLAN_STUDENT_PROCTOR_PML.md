# Architecture Plan — Student & Proctor (PML / BLACKBOX)

**Audience:** Principal / system architect, tech lead  
**Purpose:** Align on **high-level** structure, boundaries, and phased delivery before detailed design and implementation.  
**Companion docs:**
- `CONTEXT_LOG_PML_SYSTEM_AMENDMENT.md` — canonical product story + gap detail  
- `E2E_ROADMAP_STUDENT_PROCTOR_PML.md` — **binding** delivery bar **v2.1** (**SR-1–SR-5**, proof bundle, AC-1b)  
- **§11+** (this file) — **Directive Plan** — governing execution order (Directives 01–08), proof/acceptance/closeout  

**Version:** 1.1 — architecture plan + directive execution plan

---

## 1. Executive summary

BLACKBOX Pattern Machine Learning (PML) aims to implement a **training loop** with two **epistemically separated** roles on the same historic replay timeline:

| Role | Responsibility |
|------|----------------|
| **Student (Anna / agent)** | At each decision point *t*, reason from **causal market view**, **indicator + context** “cookbook,” and **retrieved memory** — **without** unrevealed outcomes or future bars. |
| **Referee (deterministic engine)** | **Immutable standard** for execution, PnL, WIN/LOSS, and **Referee-computed** quality scalars. Does **not** coach the Student during choice. |

After a graded unit, a **reveal** compares belief vs truth; **learning records** persist **matchable** experience so **later runs** can **change behavior** when similar contexts recur — otherwise “learning” is not demonstrated.

**Current state:** Replay, outcome metrics, harness comparison, engine-side memory (signatures, DCR, bundles) exist. The **Student causal loop** (blind decision → reveal → persisted student record → cross-run influence) is **not** fully implemented as a first-class pipeline in the pattern-game **Anna** path.

**Target:** Minimal incremental architecture: **reuse** Referee and existing stores where possible; **add** explicit **contracts** (schemas, boundaries) for Student output, reveal payloads, and student learning records; **prove** cross-run behavioral change with automated tests per phase.

---

## 2. Architectural principles (non-negotiable)

1. **Referee immutability** — No LLM path may **authorize** trades, **rewrite** ledger numbers, or redefine WIN/LOSS. All scores and graded quality derive from **replay + existing ledger types** (`OutcomeRecord`, etc.).

2. **Explicit contracts** — Student input/output, pre-reveal bundles, reveal payloads, and learning records are **versioned schemas** (JSON). Ad-hoc prose is not a source of truth for metrics.

3. **Minimal surface area** — New code **only** where the Student–Proctor story requires it; avoid refactors of unrelated replay, catalog, or ingest.

4. **Phased delivery** — **Shadow Student** (no execution impact) before any **execution-influencing** Student path, unless explicitly rescoped.

5. **Auditable leakage** — Automated guarantees that pre-reveal bundles **cannot** contain forbidden fields (future bars, full-session aggregates, unrevealed outcomes).

6. **Separation of concerns** — **Engine memory** (signature/DCR/bundle bias affecting fusion) remains distinct from **Student learning records** unless a future **explicit** merge policy is approved.

---

## 3. Logical architecture (conceptual)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Historic market data (SQLite / bars)               │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                                    │
                    │ forward replay                      │ optional slice for
                    ▼                                    │ Student “window” views
┌──────────────────────────────┐        ┌───────────────────────────────────┐
│         REFEREE LAYER          │        │      STUDENT CONTEXT BUILDER       │
│  (manifest, signals, fusion,   │        │  Causal OHLCV / indicators /       │
│   execution, ledger,           │        │  pattern_context, memory retrieval  │
│   OutcomeRecord, quality v1)   │        │  (NO outcomes pre-reveal)          │
└──────────────────────────────┘        └───────────────────────────────────┘
           │                                              │
           │  outcomes + trade list                         │  structured decision
           ▼                                              ▼
┌──────────────────────────────┐        ┌───────────────────────────────────┐
│      GRADING & REVEAL         │◄───────│   STUDENT (Anna / LLM or stub)     │
│  Compare belief vs Referee;    │       │   Emit student_output_v1 (shadow)   │
│  build reveal payload          │       │   (later: optional influence path)  │
└──────────────────────────────┘        └───────────────────────────────────┘
           │
           ▼
┌──────────────────────────────┐        ┌───────────────────────────────────┐
│   STUDENT LEARNING STORE     │        │   ENGINE MEMORY (existing)        │
│   student_learning_record_*  │        │   context_signature_memory, DCR,  │
│   append-only, match keys    │        │   memory bundles, harness           │
└──────────────────────────────┘        └───────────────────────────────────┘
           │
           │ next run: retrieve + match
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  RUN N+1 — Student bundle may include retrieved student records; Referee      │
│  unchanged unless approved influence path merges into whitelisted manifest     │
│  keys (existing bundle/DCR patterns).                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key boundary:** **Referee** and **Student** do **not** share **pre-reveal** truth channels. **Reveal** is the **only** sanctioned merge point for Referee facts into the Student’s graded episode.

---

## 4. Component responsibilities

| Component | Owns | Does not own |
|-----------|------|----------------|
| **Replay runner** (`replay_runner` / manifest replay) | Deterministic path, `OutcomeRecord` stream, optional `pattern_context_v1`, DCR hooks | Student prose, LLM calls inside hot path (unless architect approves deferred batching strategy) |
| **Outcome / quality** (`pattern_outcome_quality_v1`, ledger) | Graded scalars from closed trades | Student interpretation |
| **Student context builder** (new or split module) | Assemble **legal** bundle at *t*: bars ≤ *t*, context, memory **without** leak | Referee outcomes pre-reveal |
| **Student agent interface** | Produce `student_output_v1` given bundle | Trades |
| **Reveal & grading** | Join Student output + Referee row + quality slice; emit `reveal_v1` | Changing Referee numbers |
| **Student learning store** | Persist `student_learning_record_v1`; retrieval API for next run | Fusion math |
| **Engine memory** (existing) | Signature match, bundle apply, harness winner persistence | Student narrative memory (unless merged by policy later) |
| **Operator UI / Barney** | Display, plain-English recap from **structured** facts | Computing primary metrics |

---

## 5. Data artifacts (contract layer)

All **versioned**; exact field lists belong in a separate **schema appendix** or OpenAPI-style document — architect to approve naming and storage layout.

| Artifact | Purpose |
|----------|---------|
| `student_output_v1` | Student decision at *t* or per graded unit (shadow phase). |
| `reveal_v1` | Referee truth + comparison + optional counterfactual hints **only** if Referee-grounded. |
| `student_learning_record_v1` | Persistent row for retrieval and cross-run proof tests. |
| Existing: `OutcomeRecord`, `pattern_outcome_quality_v1` output | **Source of truth** for numeric quality. |

**Pointer:** Detailed gap resolutions and checklist live in `CONTEXT_LOG_PML_SYSTEM_AMENDMENT.md` §12.

---

## 6. Phasing (delivery roadmap)

| Phase | Scope | Risk | Success signal |
|-------|--------|------|----------------|
| **0 — Contract freeze** | Schemas + leakage rules + test acceptance for “learning” | Low | Sign-off without coding |
| **A — Shadow Student** | Student produces `student_output_v1` **after** or **in offline pass**; Referee unchanged; alignment metrics computed | Low | Non-empty alignment report; no production behavior change |
| **B — Reveal UX / storage** | Persist `student_learning_record_v1`; UI or logs show reveal | Medium | Records append; queryable |
| **C — Cross-run proof** | Automated test: Run 2 differs per §12.5 fingerprint when records loaded | Medium | CI test green |
| **D — Execution influence (optional)** | Only via **existing** whitelisted paths (bundles/DCR); **no** raw LLM→orders | High | Requires separate ADR |

**Recommendation:** Ship **A → B → C** before **D** unless business mandates otherwise.

---

## 7. Dependencies and integration points

- **Database:** `market_bars_5m`, existing replay DB assumptions.
- **Anna stack:** Ollama / `agent_context_bundle` patterns for **optional** narration of **structured** reveal — **not** the authority layer.
- **PML UI / harness:** Operator batches, scorecard, memory modes — **surface** Student alignment when ready; **no** coupling to Student schema until contracts exist.
- **CI:** New tests for leakage and cross-run proof **must** run without GPU/LLM where possible (stub Student).

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Latency if LLM per bar | Batch / post-pass Student in v1; architect decides hot vs cold path |
| Leakage via prompt engineering | Schema validation + automated bundle tests |
| Conflating engine memory with Student memory | Separate stores until explicit merge ADR |
| Scope creep into “LLM trader” | Phase gates; Referee immutability principle |

---

## 9. Open decisions for architect (to drive)

1. **Hot path vs post-pass** for Student inference (latency, audit, reproducibility).
2. **Storage** for `student_learning_record_v1` (path, retention, GDPR/export if any).
3. **Identity** of graded unit v1 — **per trade** vs finer granularity.
4. **Whether** Student learning retrieval ever **feeds** engine memory or stays **analytic-only** until Phase D.
5. **SLOs** for batch duration when Student runs over full history.

---

## 10. Handoff

| Role | Responsibility |
|------|----------------|
| **Architect** | Owns ADRs on boundaries, schemas approval, phase gates, non-functional requirements, integration with broader BLACKBOX roadmap. |
| **Engineering** | Implements approved contracts **within** minimal-diff rules; tests; no Referee mutation. |

This plan is **intentionally** high-level. Detailed sequence diagrams, schema JSON, and file-level edit lists follow **after** architect sign-off on §3–§6 and §9.

---

## 11. Directive Plan (governing execution)

Engineering work is decomposed into **directives** (01–08). Each directive defines objective, implementation, forbidden scope, tests, proof, acceptance, and closeout (commit / push / remote pull / Flask restart). A directive **closes** only after **architect accepts** the proof — see full text below.

---

## 1. Governing Model

The architecture plan is the parent control document.

Engineering work is not executed from the architecture plan directly. Instead, the architecture plan is divided into bounded directives. Each directive instructs engineering to implement a specific portion of the approved architecture, run specific tests, and return specific proof artifacts for review.

A directive is not considered complete because engineering says it is complete.

A directive is complete only when:

- the requested implementation exists
- the requested tests were run
- the requested proof was returned
- the architect reviews that proof and accepts it

Only after acceptance does the directive close and the next directive begin.

This creates a closed verification loop:

Architect issues directive  
Engineering implements and returns proof  
Architect reviews proof  
Directive accepted or rejected  
Accepted artifact returns to engineering  
Next directive begins

This loop is mandatory.

---

## 2. Directive Standard

Each directive must be small enough to be reviewed clearly and proved cleanly.

Each directive must contain:

- directive identifier
- title
- objective
- required implementation
- forbidden scope
- required tests
- required proof
- acceptance standard
- closeout instructions

Directives must not combine unrelated goals. If a directive is too broad to prove cleanly, it must be split.

---

## 3. Proof Standard

Engineering proof must be specific and reproducible.

Accepted proof may include:

- git diff or commit references
- file paths changed
- schema samples
- test output
- screenshots
- curl output
- API responses
- database evidence
- log excerpts
- before/after behavioral comparisons

Claims without evidence are not proof.

If a directive required a behavior change, proof must show the behavior change.

If a directive required a no-leak boundary, proof must show the boundary was tested.

If a directive required persistence, proof must show the artifact exists after the run ends and can be read back.

---

## 4. Acceptance Rule

A directive is accepted only when the returned proof demonstrates that the directive was implemented as requested.

If proof is partial, unclear, missing, or does not actually establish the required behavior, the directive remains open.

No downstream directive should be considered complete by assumption from an earlier unproven directive.

---

## 5. Recommended Directive Breakdown

The Student–Proctor architecture should be divided into a sequence of directives. The sequence below is the recommended order.

---

## Directive 01 — Contract Freeze

### Objective

Freeze the core contract layer for the Student–Proctor system before behavior work begins.

### Required implementation

Engineering must define and submit the initial versioned schemas for:

- `student_output_v1`
- `reveal_v1`
- `student_learning_record_v1`

Engineering must also define:

- the legal pre-reveal decision packet boundary
- the forbidden pre-reveal fields
- the initial graded-unit choice for v1

### Forbidden scope

- no execution influence
- no LLM authority changes
- no replay math changes
- no UI behavior changes beyond inspection tooling if needed

### Required tests

Engineering must validate:

- schema validity
- sample artifact generation
- leakage test cases for forbidden fields
- contract examples for each artifact

### Required proof

Engineering must return:

- changed file list
- schema file contents or references
- at least one legal example per artifact
- at least one illegal pre-reveal bundle example rejected by test
- explicit statement of the chosen graded unit for v1

### Acceptance standard

Directive 01 is accepted only when the contracts are explicit, versioned, testable, and the no-leak boundary is proven by example.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## Directive 02 — Student Context Builder

### Objective

Implement the legal Student decision packet builder for the chosen graded unit.

### Required implementation

Engineering must create the Student context builder that assembles a legal decision packet at time `t` using only approved pre-reveal information.

The packet must be built from causal state only and must exclude:

- future bars
- current graded-unit outcomes
- current graded-unit entries or exits
- current graded-unit PnL
- current graded-unit WIN/LOSS
- any other forbidden Referee flashcard field

### Forbidden scope

- no execution influence
- no reveal logic yet
- no changes to Referee authority
- no substitution of post-hoc summary objects for legal decision packets

### Required tests

Engineering must validate:

- packet generation at multiple timesteps
- packet correctness using causal boundaries
- no-leak tests for all forbidden field categories

### Required proof

Engineering must return:

- changed file list
- examples of generated decision packets
- proof that packets contain legal fields only
- proof that no-leak tests pass
- explanation of how the builder obtains causal state

### Acceptance standard

Directive 02 is accepted only when legal decision packets exist, are causally bounded, and leakage is explicitly disproven by tests.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## Directive 03 — Shadow Student Output

### Objective

Introduce `student_output_v1` generation in shadow mode.

### Required implementation

Engineering must wire a Student interface that consumes the legal decision packet and emits `student_output_v1` in machine-checkable form.

This phase is shadow-only. The Student output must not alter Referee execution, trade selection, or ledger math.

A stub Student is acceptable for initial proof as long as the schema and data flow are real.

### Forbidden scope

- no execution influence
- no override of Referee fields
- no use of Student output as order authority

### Required tests

Engineering must validate:

- Student output generation for multiple graded units
- schema compliance of outputs
- proof that execution remains unchanged with Student enabled

### Required proof

Engineering must return:

- changed file list
- examples of `student_output_v1`
- test evidence that Student output is produced
- before/after evidence that Referee behavior is unchanged

### Acceptance standard

Directive 03 is accepted only when shadow Student output exists, is valid, and has zero execution authority.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## Directive 04 — Reveal Layer

### Objective

Create the structured reveal join between Student output and Referee truth.

### Required implementation

Engineering must implement `reveal_v1` as the only sanctioned point where Student output and Referee truth for the graded unit are joined.

The reveal artifact must contain:

- Student decision
- Referee truth
- approved comparison fields
- only Referee-grounded explanatory content

### Forbidden scope

- no rewrite of Referee truth
- no narrative-only reveal objects without structured fields
- no future-state leakage into pre-reveal objects

### Required tests

Engineering must validate:

- reveal artifact creation
- schema compliance
- correct joining of Student and Referee fields
- separation between pre-reveal and post-reveal objects

### Required proof

Engineering must return:

- changed file list
- examples of `reveal_v1`
- tests showing reveal is generated only after decision
- proof that pre-reveal and post-reveal fields remain separated

### Acceptance standard

Directive 04 is accepted only when reveal exists as a structured post-decision truth join and preserves the Student–Proctor boundary.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## Directive 05 — Student Learning Store

### Objective

Persist Student learning records in a retrievable, versioned store.

### Required implementation

Engineering must implement append and retrieval support for `student_learning_record_v1`.

The store must be:

- append-only
- versioned
- queryable without requiring an LLM
- usable in later runs for matching

### Forbidden scope

- no implicit merge with engine memory
- no execution influence yet
- no replacing existing Referee truth artifacts

### Required tests

Engineering must validate:

- append behavior
- persistence after run completion
- retrieval by key or signature
- schema compliance of stored artifacts

### Required proof

Engineering must return:

- changed file list
- examples of stored records
- evidence the records persist after the run ends
- evidence the records can be read back on demand

### Acceptance standard

Directive 05 is accepted only when Student learning records are durably stored, retrievable, and structurally valid.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## Directive 06 — Cross-Run Retrieval

### Objective

Load prior Student learning records into later Student decision packets under approved matching rules.

### Required implementation

Engineering must implement retrieval and matching of prior Student learning records for later runs.

Retrieved records must enter the Student path only through the approved legal-decision-packet contract.

### Forbidden scope

- no silent relabeling of engine memory as Student learning
- no execution influence unless separately approved
- no future leakage through retrieval

### Required tests

Engineering must validate:

- records are loaded on later runs
- matching logic selects appropriate prior records
- retrieved records appear in legal Student packets only where allowed

### Required proof

Engineering must return:

- changed file list
- evidence of prior records being loaded
- evidence of matching behavior
- examples of later Student packets containing retrieved prior experience legally

### Acceptance standard

Directive 06 is accepted only when prior Student learning records are read back and legally reintroduced into later Student decision packets.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## Directive 07 — Cross-Run Proof

### Objective

Prove that prior Student learning records can change later Student behavior.

### Required implementation

Engineering must provide an automated proof scenario where:

- Run 1 produces Student learning records
- Run 2 loads those records
- Run 2 changes at least one observable decision-relevant Student field because of those records

Observable decision-relevant differences may include:

- act versus abstain
- direction change
- confidence change if confidence is part of the contract
- recipe or pattern choice change
- another architect-approved field

### Forbidden scope

- no fake proof using internal state changes that do not alter observable Student output
- no manual-only proof without repeatable test coverage
- no claims based solely on “memory loaded” metrics

### Required tests

Engineering must validate:

- Run 1 baseline
- Run 2 with records loaded
- reset condition showing behavior returns to baseline when the learning store is cleared or bypassed

### Required proof

Engineering must return:

- changed file list
- before/after Student outputs
- evidence that the relevant learning records were produced, persisted, loaded, and matched
- automated test output proving the behavior delta
- reset proof showing the behavior delta disappears when learning state is removed

### Acceptance standard

Directive 07 is accepted only when prior Student learning records are shown to cause an observable decision-relevant difference in a later run and that difference disappears when the learning state is removed.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## Directive 08 — UI Truth Separation

### Objective

Ensure the application distinguishes score visibility from learning-state visibility.

### Required implementation

Engineering must update the application to clearly separate:

- run score or scorecard artifacts
- Student learning state or memory state

The operator must not be misled into thinking that clearing visible score history also resets learning state.

### Forbidden scope

- no fake UI wording without true backend distinction
- no hidden learning resets triggered by unrelated score clearing

### Required tests

Engineering must validate:

- score clearing does not erase learning state unless explicitly intended
- learning reset is a distinct action if implemented
- UI text reflects the actual backend behavior

### Required proof

Engineering must return:

- changed file list
- screenshots or API proof
- backend proof of distinct state handling
- explanation of the operator-facing semantics

### Acceptance standard

Directive 08 is accepted only when application behavior truthfully distinguishes visible run history from persistent learning state.

### Closeout instructions

At the end of this directive, engineering must:

- fully commit the code locally with a clear commit message
- push the committed code to the authoritative remote repository
- SSH to the remote server and perform a `git pull`
- restart the Flask web services so the current application reflects the latest directive state

Engineering must include proof that these closeout steps were completed.

---

## 6. Closure Rule

No directive closes on intent alone.

No directive closes on engineering explanation alone.

No directive closes because code exists somewhere in the repository.

A directive closes only when proof demonstrates that the requested behavior or boundary has actually been implemented and tested.

---

## 7. Final Operational Rule

The architecture plan governs the direction.

The directives govern the work.

Proof governs acceptance.

That loop remains in force for the full Student–Proctor buildout.
