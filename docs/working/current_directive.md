# Current directive

**Status:** Active - architect-owned intake-cycle refresh and publication-readiness slice.
**Pillar 1 lock:** ACTIVE NOW (hard lock). Beyond-Pillar authorization remains forbidden unless an explicit lock-lift decision packet is authorized and published under the #036/#037 gate contract.

**Last updated:** 2026-03-31 - **Architect:** CANONICAL #040 accepted/closed; CANONICAL #041 issued (architect-owned intake-cycle refresh and publication-readiness gate).

## Title

**CANONICAL #041 - Pillar 1 Intake-Cycle Refresh and Publication-Readiness Gate (Architect)**

## Objective

Require a fresh, hash-aligned, replay-safe intake cycle after #040 so any future lock-state publication review is grounded in current operator-authority evidence with complete #036 contract coverage.

## Required implementation (architect)

1. Require fresh intake authority evidence package for the next intake cycle:
   - operator identity and decision timestamp
   - architect identity for reconciliation ownership
   - explicit packet identifier for the new cycle
2. Enforce complete packet coverage mapping to #036 contracts:
   - `LDP-REQ-*` requirements
   - `LDP-PUB-*` publication gate references
   - explicit handling for missing or stale fields
3. Enforce active directive-hash alignment at intake capture time:
   - reject stale or mismatched `directive_hash_at_decision`
   - preserve deterministic, replay-safe hash pinning
4. Enforce freshness and replay-safety checks for publication event intent:
   - monotonic timestamps
   - non-replayed packet identity
   - fail-closed verdict if freshness or replay safety fails
5. Produce deterministic canonical intake verdict packet:
   - one of `accepted_for_follow_on_gate`, `blocked`, `deferred`, `closed_without_completion`
   - include explicit rationale and gate references for any failed checks
6. Preserve deterministic lane ownership and atomic governance discipline:
   - keep `next_actor=architect` unless a governed follow-on directive explicitly changes ownership
   - use hash-pinned atomic bus operations for directive issuance/re-issuance/publication

## Out of scope

- No developer implementation directive issuance unless a governed follow-on directive explicitly sets `next_actor=developer`.
- No lock-lift publication decision itself in this slice; this slice validates intake-cycle refresh and publication-readiness only.
- No implied lock-lift or beyond-Pillar authorization by narrative text, stale evidence, or chat-only signals.
- No live exchange execution.

## Required proof (architect)

- Shared-log Phase A evidence in `docs/working/shared_coordination_log.md` stating:
  - intake-cycle evidence package fields and source artifacts
  - per-check outcomes for authority, completeness, hash alignment, and freshness/replay safety
  - canonical verdict and deterministic lane outcome
  - bus signal commands and resulting lane state
- `python3 scripts/runtime/governance_bus.py --peek` output showing expected `effective_next_actor`.
- Matching status synchronization updates where scope/status changed.

## Acceptance criteria

- Intake-cycle refresh evidence is explicit, fresh, hash-aligned, and mapped to #036 contracts.
- Canonical intake verdict output is deterministic and fail-closed.
- Lane ownership remains deterministic with no implied transitions.
- Atomic bus signaling and hash-gate lane state are recorded and reproducible.

## Turn ownership and coordination

- `next_actor`: `architect`
- Architect owns this directive until an explicit governed handoff changes turn ownership.
