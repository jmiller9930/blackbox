# Phase 1.6 — Activate Agents + System Prerequisites

## Objective

Move from “agents on paper” to **agents doing controlled, real work**.

---

## Core Decisions

- SQLite will run **on the clawbot server (local file DB)**
- No additional VM at this stage
- Agents will be given **narrow, controlled responsibilities only**

---

## Immediate Build Tasks

### 1. SQLite Setup

- Install SQLite on clawbot
- Create database file (e.g. `blackbox.db`)
- Define initial tables:
  - `system_health_logs`
  - `agent_tasks`
  - `alerts`
- Ensure read/write access from agent runtime

### 2. DATA Agent — First Responsibilities

DATA must be able to:

- Check gateway health
- Check Ollama connectivity (LLM server)
- Verify SQLite availability
- Validate key endpoints / services
- Log results into SQLite
- Raise alerts on failure conditions

DATA should:

- never guess
- only report verified status
- classify failures clearly

### 3. Cody Agent — First Responsibilities

Cody must be able to:

- Read repository structure
- Analyze files and dependencies
- Generate patch plans (not blind execution)
- Propose new agent configs / updates
- Output structured changes for approval

Cody should:

- not execute uncontrolled system changes
- operate as planner + builder

### 4. System Prerequisites (Document + Enforce)

Define and document:

- clawbot role (gateway + runtime)
- LLM server role (Ollama host)
- SQLite location (local path)
- required ports (gateway, Ollama, etc.)
- required services (gateway, websocket feeds)
- external endpoints (price feeds, APIs)
- alert surface (logs, Telegram, etc.)
- backup strategy for SQLite

---

## Constraints

- No new agents until Cody + DATA are validated
- No broad autonomy
- No secrets in repo or chat
- All actions must be logged or traceable

---

## Success Criteria

- SQLite running and writable
- DATA successfully logs system health checks
- Cody produces structured repo analysis or patch plan
- At least one alert scenario tested and logged

---

## Next Phase (After Validation)

- Expand DATA monitoring coverage
- Introduce Anna (analysis layer)
- Introduce Billy (execution layer)
- Implement vault-based secrets management

---

## BLACK BOX repo alignment

| Phase 1.6 intent | In-repo today (Phase 1.5 persistence) |
|------------------|-----------------------------------|
| `alerts` | `alerts` table in [`data/sqlite/schema_phase1_5.sql`](../../data/sqlite/schema_phase1_5.sql) |
| `agent_tasks` | `tasks` table (agent-scoped via `agent_id`) |
| `system_health_logs` | `system_events` (structured events + payloads); extend or add `system_health_logs` in a follow-up migration if needed |

**Init script:** [`scripts/init_phase1_5_sqlite.sh`](../../scripts/init_phase1_5_sqlite.sh) — run on clawbot after choosing DB path.

**Agent definitions:** [`agents/agent_registry.json`](../../agents/agent_registry.json) — Cody + DATA policy, [`DATA_ONLINE_SETUP.md`](DATA_ONLINE_SETUP.md) for OpenClaw wiring.

**Registry / secrets rules:** [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) — vault-first policy; no secrets in git or chat.
