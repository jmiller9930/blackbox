# Phase 1.6 — Activate Agents + System Prerequisites

## Controlled execution phase (architect — active)

**Status:** Architect **concurrence** received. Implementation of Cody + DATA definitions is **approved**. The system is in **controlled execution** — **no expansion** (no new agents, no vault integration, no broad tool surface) until validation completes.

**Focus:** stability, validation, controlled execution — not premature scaling.

A separate `phase_1_7.md` is **not required** while this document remains the single execution-scope reference.

---

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
- operate as **engineer + planner + builder**

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

## Constraints (remain enforced)

- **No new agents** (Anna, Billy, Mia expansion, etc.) until architect sign-off
- **No vault / secrets integration** in this phase
- **No expansion of tool surface** beyond defined scope
- **No autonomous execution** beyond defined scope (no uncontrolled mutation)
- No broad autonomy; no secrets in repo or chat
- All actions must be logged or traceable

---

## Approved next actions (operational)

### 1. SQLite (clawbot)

- Deploy **locally** on clawbot (no separate VM)
- Apply schema: **`system_health_logs`**, **`alerts`** (Phase 1.5), **`agent_tasks`** (view over `tasks` + use `tasks` for writes)
- Run [`scripts/init_phase1_6_sqlite.sh`](../../scripts/init_phase1_6_sqlite.sh) (applies 1.5 + 1.6)

### 2. DATA — first workload

- Check **gateway** health, **Ollama** connectivity, **SQLite** availability, **key endpoints**
- **Log results** to SQLite; **detect and report** at least one failure condition
- Report **only verified truth**; **classify** failures; **never speculate**

### 3. Cody — first workload

- **Analyze** repository structure; produce **structured patch plan(s)**; **propose** agent config improvements
- **Do not** execute uncontrolled changes or mutate system state without approval

### 4. Validation gate

Demonstrate:

- DATA produces **reliable health logs** in SQLite
- DATA **detects** a failure condition
- Cody produces a **usable patch plan**
- SQLite **stores** results as expected

---

## Success Criteria

- SQLite running and writable (`init_phase1_6_sqlite.sh` applied on clawbot)
- DATA logs system health checks into **`system_health_logs`** / **`alerts`** as designed
- Cody produces structured repo analysis or patch plan (no blind execution)
- At least one **failure** scenario detected and logged

---

## Next Phase (After Validation)

- Expand DATA monitoring coverage
- Introduce Anna (analysis layer)
- Introduce Billy (execution layer)
- Implement vault-based secrets management

---

## BLACK BOX repo alignment

| Phase 1.6 intent | In-repo |
|------------------|--------|
| `alerts` | [`data/sqlite/schema_phase1_5.sql`](../../data/sqlite/schema_phase1_5.sql) |
| `agent_tasks` | View `agent_tasks` → `tasks` in [`data/sqlite/schema_phase1_6.sql`](../../data/sqlite/schema_phase1_6.sql) |
| `system_health_logs` | Table in [`data/sqlite/schema_phase1_6.sql`](../../data/sqlite/schema_phase1_6.sql) |

**Init script (recommended):** [`scripts/init_phase1_6_sqlite.sh`](../../scripts/init_phase1_6_sqlite.sh) — applies **1.5 + 1.6** to `BLACKBOX_SQLITE_PATH` (default `data/sqlite/blackbox.db`).  
Legacy: [`scripts/init_phase1_5_sqlite.sh`](../../scripts/init_phase1_5_sqlite.sh) alone does **not** add `system_health_logs` / `agent_tasks` view.

**Agent definitions:** [`agents/agent_registry.json`](../../agents/agent_registry.json) — Cody + DATA policy, [`DATA_ONLINE_SETUP.md`](DATA_ONLINE_SETUP.md) for OpenClaw wiring.

**Registry / secrets rules:** [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) — vault-first policy; no secrets in git or chat.

**Verification audit (pass/fail record):** [`agent_verification.md`](agent_verification.md) — do not duplicate full agent prose there.

**Workspace drift:** [`workspace_sync.md`](workspace_sync.md) — mandatory repo → OpenClaw workspace steps after updates.
