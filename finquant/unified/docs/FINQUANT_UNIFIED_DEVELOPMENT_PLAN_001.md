# FinQuant Unified Development Plan 001

**Status:** Active working plan  
**Scope:** `finquant/unified/` isolated project only  
**Companion:** `FINQUANT_UNIFIED_LEARNING_ARCHITECTURE_001.md`

---

## 1. Intent

This plan exists to drive the isolated FinQuant project to a finished learning and test framework.

The project must not drift into vague experimentation. Each item must be completed through a strict closure loop:

1. Develop the item.
2. Test the item.
3. Generate proof.
4. Reflect on whether the proof is valid.
5. If the proof is weak or false, correct the item.
6. Re-test.
7. Re-prove.
8. Close the directive only when the proof is honest and sufficient.
9. Then move to the next directive.

No directive is considered complete because code exists alone.

---

## 2. The Three Questions This Project Must Solve

The finished framework must answer all three of these questions.

### Question 1 — Can FinQuant reason correctly inside the bounded baseline?

The system must prove that the model plus agent can:

- interpret market context,
- stay inside the baseline recipe and policy framework,
- choose action vs `NO_TRADE` correctly,
- and obey no-lookahead discipline.

### Question 2 — Can FinQuant actually learn and remember?

The system must prove that:

- eligible episodes are persisted,
- validated prior experience becomes retrievable,
- retrieved memory affects later decisions,
- and the behavior change is real rather than cosmetic.

### Question 3 — Can that learning be proven honestly?

The system must prove improvement through:

- repeatable tests,
- explicit artifact capture,
- before/after comparisons,
- and hard rejection of fake learning claims based only on lucky outcomes or execution completion.

If the framework cannot answer all three questions with artifacts, then the project is not complete.

---

## 3. Non-Negotiable Development Rule

This project follows a directive loop, not a loose coding loop.

Every work item must pass through:

- implementation,
- automated testing,
- proof artifact generation,
- proof review,
- correction if proof fails,
- and explicit closure.

This is the governing process for the isolated project.

---

## 4. Execution Commitment

This plan is intended to be executed end to end.

Once implementation begins, the default operating mode is:

- continue through the directive sequence without routine interruption,
- only pause for a real blocker, contradiction, or high-risk decision,
- finish each directive with code, tests, and proof before moving on,
- and keep going until the operator can see an observable training cycle happen.

This means the finish line is not:

- documentation exists,
- code compiles,
- or the runner starts.

The finish line is:

- the student can run a control path,
- governed learning can be persisted,
- a memory/context path can run after that,
- behavior can be compared honestly,
- and the referee artifact can say whether learning was proven.

---

## 5. Directive Sequence

The project will be executed in ordered directives.

### Directive A — Data Contract

Goal:

- define exactly what FinQuant reads from:
  - canonical market bars,
  - tick tape,
  - baseline reference context,
  - and evaluation rollups.

Deliverables:

- FinQuant-local data contract document
- structured input schema for the brain layer
- tests for loading and validating upstream data

Closure proof:

- fixture-based tests pass
- live-path mapping is documented
- no-lookahead boundary is explicit and test-covered

### Directive B — Decision Contract

Goal:

- define the authoritative FinQuant decision object for the isolated project.

Deliverables:

- structured decision schema
- parser/adapter from raw model output to governed decision
- action / abstention contract

Closure proof:

- invalid model output is rejected
- valid output becomes authoritative only after contract normalization
- decision contract tests pass

### Directive C — Brain Wiring

Goal:

- connect the chosen model as the FinQuant brain layer under governed lifecycle control.

Deliverables:

- stable model loading path
- prompt builder
- contract-normalized inference path
- raw output capture

Closure proof:

- runner can execute model-backed decisions
- artifacts capture `raw_model_output`
- source is `llm` or `hybrid`, never silently stub

### Directive D — Baseline-Constrained Judgment

Goal:

- make FinQuant reason relative to the baseline recipe and framework instead of improvising strategy.

Deliverables:

- baseline-aware prompt/context surface
- abstention-first rules for weak context
- bounded action criteria aligned to the framework

Closure proof:

- targeted no-trade cases pass
- weak-context entries are suppressed
- baseline surface is referenced, not bypassed

### Directive E — Memory Contract

Goal:

- define how the isolated project stores, filters, and retrieves prior experience.

Deliverables:

- memory record schema
- retrieval eligibility rules
- retrieval summary contract
- governance states for memory reuse

Closure proof:

- bad records are not returned
- eligible records are returned deterministically
- retrieval audit artifacts are produced

### Directive F — Learned Behavior Loop

Goal:

- prove that prior validated experience can change a later decision.

Deliverables:

- before/after comparison harness
- behavior-delta test cases
- memory-influenced decision path

Closure proof:

- one controlled scenario without memory
- same or near-same scenario with memory
- explicit behavior delta
- explicit reason for the delta

### Directive G — Training Export

Goal:

- turn governed episodes into training-ready FinQuant examples.

Deliverables:

- isolated training export builder
- curated JSONL contract
- filtering rules for usable episodes

Closure proof:

- export is deterministic
- only eligible records are included
- exported data reflects the decision contract

### Directive H — Exam Framework

Goal:

- deliver a repeatable test framework that distinguishes wiring success from judgment success from learning success.

Deliverables:

- case packs
- runner
- grader
- artifact bundle
- result summary

Closure proof:

- framework can detect:
  - stub-only success,
  - model-backed failure,
  - learned-behavior success,
  - false-learning claims

### Directive I — Final Unified Proof

Goal:

- demonstrate the three questions are answered by the isolated project.

Deliverables:

- final report
- run artifacts
- comparison artifacts
- closure checklist

Closure proof:

- Question 1 answered with artifacts
- Question 2 answered with artifacts
- Question 3 answered with artifacts

---

## 6. Observable Completion Standard

The project is not complete until the operator can observe a full FinQuant training cycle in the isolated environment.

Minimum required visible cycle:

1. A control run executes with no memory and no prior-context influence.
2. Eligible learning is written or promoted into the governed store.
3. A candidate run executes with memory/context enabled.
4. The candidate run shows whether prior learning changed judgment.
5. A referee artifact states whether the behavior change was real, attributable, and better.

Minimum expected artifact bundle:

- control run artifacts
- candidate run artifacts
- persisted learning rows or governed rejection evidence
- retrieval trace
- before/after behavior delta
- operator-facing referee report

If the operator cannot see that cycle happen with artifacts, the project is not done.

## 5. Test Framework Requirements

The finished test framework must contain four testing lanes.

### Lane 1 — Structural correctness

Tests:

- data load
- schema validation
- contract validation
- model output parsing
- artifact writing

Purpose:

- prove the system is wired correctly

### Lane 2 — Judgment correctness

Tests:

- entry vs `NO_TRADE`
- hold vs exit
- weak-context abstention
- conflicting-evidence handling
- no-lookahead integrity

Purpose:

- prove the model/agent can make bounded decisions correctly

### Lane 3 — Memory and learning correctness

Tests:

- memory record persistence
- retrieval eligibility filtering
- retrieval application
- behavior delta from prior experience
- negative tests where memory should not affect decisions

Purpose:

- prove the system can learn and remember in a governed way

### Lane 4 — Proof integrity

Tests:

- reject runs with no durable learning but misleading performance
- reject runs with good execution but no memory effect
- reject runs with incomplete artifacts
- reject runs where claimed learning is not demonstrable

Purpose:

- prove the proof is honest

---

## 6. Artifact Contract

Every directive should emit a proof bundle when applicable.

Minimum artifact expectations:

- input case or dataset reference
- resulting decision artifacts
- evaluation artifact
- memory/retrieval artifact when relevant
- run summary
- directive-specific proof summary

No directive should close with “trust me.”

---

## 7. Closure Standard

A directive closes only when all of the following are true:

- implementation exists
- relevant tests pass
- proof artifacts exist
- the proof actually supports the claim
- known inconsistencies are documented
- no critical contradiction remains between code, outputs, and stated behavior

If proof and claim disagree, the proof wins.

---

## 8. Immediate Next Actions

The next execution order should be:

1. Write the FinQuant-local data contract.
2. Stabilize and formalize the FinQuant decision contract.
3. Build targeted abstention and weak-context judgment tests.
4. Formalize the isolated memory contract.
5. Build a learned-behavior proof harness.
6. Build the training export path.
7. Build the finished exam framework.

This order matters because the exam framework is meaningless if the data, decision, and memory contracts are still fuzzy.

---

## 9. Expert Execution Rule

Any expert or sub-agent working this plan must:

- work only inside the isolated FinQuant project unless explicitly told otherwise,
- treat the main application stack as read-only reference,
- follow directive order unless a blocker forces re-sequencing,
- produce tests and proof for each item,
- and never call a directive complete without an artifact-backed closure.

---

## 10. End State

The project is complete only when the isolated FinQuant system can honestly demonstrate:

- bounded baseline-aware reasoning,
- governed memory and retrieval,
- measurable learned behavior,
- and a finished test framework that proves all of the above.
