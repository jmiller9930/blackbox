# Architect Response — SQLite Deviation Review

**Date:** 2026-03-22

## Verdict

The current implementation is **acceptable as a bridge**, but it is **not the final architect target schema**.

This means:

- **Conceptually aligned:** YES
- **Operationally usable right now:** YES
- **Schema-complete vs architect spec:** NO

Cursor's assessment is correct.

---

## Architect Decision

### 1. Accept current schema as Phase 1.6 bridge

Do **not** stop progress over this.

The current SQLite implementation is sufficient to begin:

- DATA health logging
- alert recording
- Cody task bookkeeping

This is enough to support controlled execution work.

---

### 2. Do NOT pretend this is final parity

The bridge schema must be explicitly treated as:

**Phase 1.6 bridge schema**

not:

**final architect schema**

That distinction must remain documented.

---

### 3. Freeze behavior expectations now

Even though DDL differs, agent behavior must still follow the architect rules:

#### DATA

- only writes verified health checks
- only raises real alerts
- no guessing
- no silent deletes or rewrites

#### Cody

- writes structured task/work records
- does not write health logs
- does not generate alerts

Behavior matters more than column naming at this stage.

---

## Accepted Deviations (For Now)

### system_health_logs

Current shape is acceptable temporarily even though it differs from the target.

Accepted for now:

- `id TEXT PRIMARY KEY`
- `checked_at + created_at`
- `target`
- `summary + evidence`

Missing but deferred:

- `latency_ms`
- `metadata`
- final target naming

### alerts

Current shape is acceptable temporarily.

Accepted for now:

- `status + acknowledged_at`
- `source_agent`
- `channel`

Missing but deferred:

- strict `resolved / resolved_at`
- direct FK/traceability to health log rows

### agent_tasks

The current `VIEW agent_tasks` over `tasks` is acceptable temporarily.

Accepted for now:

- using existing task model
- mapping `title/description/state`

Missing but deferred:

- dedicated `task_type`
- dedicated `result_summary`

---

## Required Next Action

This must be documented explicitly as:

**Architect-approved temporary bridge mapping**

and kept visible in repo docs.

See also: [`phase_1_6_agent_activation.md`](phase_1_6_agent_activation.md) — section *Architect `sqlite_spec_phase` — match vs deviation*.

---

## What To Do Next

### A. Continue implementation on bridge schema

Proceed with:

- DATA health checks
- DATA alerting
- Cody task logging

Do not wait for final schema migration.

---

### B. Add a future migration task to the plan

Tracked future work: **SQLite schema normalization** (see [`phase_1_6_agent_activation.md`](phase_1_6_agent_activation.md) — *Future: SQLite schema normalization*).

---

### C. Keep writes architect-compatible

Even with temporary columns, agent writes should conceptually map to the architect model.

Example:

- `target` behaves like `component`
- `summary/evidence` behave like `message/details`
- `status + acknowledged_at` behave like alert lifecycle

---

## What Not To Do

- Do not rebuild SQLite from scratch right now
- Do not introduce schema churn mid-implementation
- Do not block DATA/Cody activation waiting for perfect DDL
- Do not claim final parity has been reached

---

## Phase Guidance

### Current phase

Proceed with:

- DATA real health checks
- DATA logging
- DATA alert path
- Cody structured task output

### Later phase

Normalize schema after agent behavior is proven.

This is the correct sequencing.

---

## Final Architect Call

The repo implementation is:

- **good enough to proceed**
- **not final**
- **must remain explicitly labeled as a bridge**

Continue work on behavior now, and schedule schema normalization as a later tracked task.

End of response.
