# Directive 4.6.3.2 Part B — DATA Twig 4 (Design Only)

## Title

Remediation Validation Pipeline (Design Phase)

## Purpose

Define a safety-first pipeline for infrastructure remediations so fixes are proposed, tested, validated, and promoted without granting DATA live execution authority.

This design is a prerequisite for any future remediation capability.

## Scope

Design only.

- No runtime implementation
- No execution logic
- No system mutation

## 1) Remediation lifecycle model

Lifecycle states for remediation candidates:

- `candidate`
- `under_test`
- `validated`
- `rejected`

State rules:

- `candidate -> under_test` is required before any validation decision.
- `candidate -> validated` direct transition is forbidden.
- `rejected` is terminal in this phase.
- `validated` requires evidence-backed pass criteria.

## 2) Candidate generation sources

Allowed proposal sources:

- deterministic rule-based suggestions (Twig 3 diagnostics)
- optional LLM-generated suggestions (explicitly labeled)
- future human-provided remediations

Source requirements:

- every remediation candidate is tagged with `source`
- no source is authoritative pre-validation
- LLM-origin candidates cannot override deterministic validation outcomes

## 3) Test environment model

Validation must run in non-live contexts only:

- sandbox environment
- isolated runtime process/container
- replay/simulated system conditions

Environment constraints:

- zero impact to live execution/trading surfaces
- deterministic setup inputs where possible
- reset/teardown capability between validation runs

## 4) Validation criteria

A remediation candidate is valid only when measurable criteria pass:

- target error condition is resolved
- no regression is introduced in baseline checks
- relevant system metrics improve or remain within bounds
- stability is maintained across the defined test window

Criteria characteristics:

- measurable signals (logs, counters, status snapshots, health checks)
- deterministic evaluation preferred over subjective judgment
- explicit thresholds per remediation type

## 5) Evaluation process

Evaluation flow (design target):

1. capture pre-test baseline artifacts
2. apply candidate inside sandbox only
3. run deterministic validation checks
4. capture post-test artifacts
5. classify result (`pass`/`fail`) with failure category and evidence

Required evaluation outputs:

- before/after comparison
- failure classification (`functional`, `stability`, `regression`, `safety`)
- optional confidence score (bounded and explainable)

## 6) Promotion rules

Promotion eligibility:

- candidate must be in `validated`
- evidence record must be present and complete
- promotion is registry/storage only, not execution authorization

Promotion outcome:

- stored as a validated remediation pattern
- eligible for future controlled-use workflows only
- not automatically executed in live systems

## 7) Storage model

Persistence model (SQLite or equivalent) for remediation records:

Required fields:

- `remediation_id`
- `source`
- `lifecycle_state`
- `evidence`
- `created_at`, `updated_at`, `validated_at` (where applicable)
- `version`

Recommended companion records:

- transition audit table (`from_state`, `to_state`, `reason`, `changed_at`)
- test-run artifact table (baseline refs, post-run refs, verdict, metrics summary)

## 8) Safety boundaries

Non-negotiable boundaries for Twig 4 design phase:

- no live execution of fixes
- no automatic remediation
- no DATA authority expansion
- no interaction with trading/execution systems

## 9) Separation from DATA runtime

Architecture separation requirement:

- remediation validation pipeline is not part of DATA response generation
- remediation validation pipeline is not part of execution system control paths
- remediation validation pipeline is an isolated subsystem with explicit interfaces

Boundary consequence:

- DATA may report diagnostics/suggestions only
- validation/promotion artifacts are diagnostic-governance objects, not chat outputs

## 10) Future integration notes (no implementation)

Future controlled integration can allow validated patterns to be considered only when:

- execution-aware gating passes (`safe`/`controlled`/`blocked`)
- maintenance window policy is open and explicitly approved
- rollback, audit, and approval controls are present

Future use must remain human-governed and policy-gated; no autonomous remediation.

## Hard-rule compliance for this directive

This document introduces no runtime behavior and no code-path changes. It does not modify DATA/Anna behavior, routing/persona behavior, or execution capabilities.
