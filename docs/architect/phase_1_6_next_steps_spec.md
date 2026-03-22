# Architect Next Steps — Phase 1.6 Controlled Execution

**Date:** 2026-03-22

## Objective

Move from “agents defined” → “agents performing real, controlled work”.

This document defines the **first workloads** and **acceptance criteria** for:

- **DATA** (integrity / reliability operator)
- **Cody** (engineer / planner / builder)

---

# SECTION 1 — DATA: FIRST WORKLOAD

## Purpose

Prove DATA can:

- verify system state
- log results to SQLite
- raise alerts when something is wrong

---

## DATA Workload #1 — System Health Check (Minimum Viable)

### Checks to implement

1. **SQLite Health**
   - can connect to DB
   - simple query succeeds

2. **Gateway Health**
   - OpenClaw port reachable (e.g. **18789**)
   - process running

3. **Ollama Reachability**
   - Ollama HTTP base URL reachable (see `models` / gateway config on clawbot)
   - model list endpoint responds

> **Host-specific:** Use the live Ollama base URL from `~/.openclaw/openclaw.json` (e.g. `baseUrl` under models). Example from a lab gateway config: `http://172.20.2.230:11434` — **confirm** on your host before checks.

---

## DATA Expected Behavior

For each check:

### SUCCESS

- write row to `system_health_logs`
- include:
  - `target` (component)
  - `check_type`
  - `summary` = PASS
  - `evidence` = actual observation

### FAILURE

- write row to `system_health_logs`
- create alert in `alerts`
- include:
  - `source_agent` = DATA
  - `message` = failure description

---

## DATA Acceptance Criteria

DATA is considered **working** when:

- at least **3** health checks execute
- rows appear in `system_health_logs`
- at least **1** forced failure creates an alert
- no guessing (logs must reflect real checks)

---

# SECTION 2 — CODY: FIRST WORKLOAD

## Purpose

Prove Cody can:

- plan work
- structure output
- record engineering intent

---

## Cody Workload #1 — Patch Plan Record

### Input

Ask Cody:

> "Create a plan to add a new health check to DATA for disk usage"

---

## Cody Expected Output

Structured response containing:

- Objective
- Steps
- Files impacted
- Risks
- Validation steps

---

## Cody Persistence Requirement

Cody must write a record into task system:

Mapped fields:

- `title` → task summary
- `description` → plan details
- `state` → planned / proposed

---

## Cody Acceptance Criteria

Cody is considered **working** when:

- produces structured plan (not freeform)
- no hallucinated capabilities
- writes at least one task record
- stays within engineer/planner/builder role

---

# SECTION 3 — VALIDATION GATE

## Both agents must pass:

**DATA:**

- logs real checks
- creates alert on failure

**Cody:**

- produces structured plan
- records task

---

## If BOTH pass:

→ **Phase 1.6 COMPLETE**

---

# SECTION 4 — HARD CONSTRAINTS

Do **NOT**:

- add new agents
- change SQLite schema
- expand tool surface
- introduce secrets/vault
- allow autonomous execution

---

# SECTION 5 — NEXT PHASE (NOT NOW)

After validation:

- expand DATA checks
- expand Cody patch execution (controlled)
- begin learning loop design

---

# FINAL NOTE

This phase is about **proof of behavior**, not scale.

Small, correct, and observable > complex.

End of document.
