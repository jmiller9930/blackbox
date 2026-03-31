# Foreman v2 (Simple Broker)

Foreman v2 is the **development control plane** engine for brokered workflow: it sits between developer and architect roles and **governs** protocol routing, turn ownership sync, and coordination persistence (see [`../talking_stick/talking_stick_architecture.md`](../talking_stick/talking_stick_architecture.md)). It is **not** passive tooling.

Foreman v2 is a lean broker. It automates protocol routing:

- reads directive + shared log state
- determines next actor with a strict transition rule set
- dispatches role prompts through Mission Control/OpenClaw session endpoints
- writes canonical v2 runtime state + append-only audit

This is intentionally a simple control plane. It does not include Autensa product-autopilot features.

## What It Controls

Brokered development flow only:

1. Active directive with no proof -> route developer
2. Proof present but no architect handoff phrase -> keep developer lane
3. Proof + handoff phrase -> route architect for validation
4. Closed directive -> idle/closed state

## Runtime Files

Foreman v2 writes under `docs/working/`:

- `foreman_v2_runtime_state.json` (canonical state)
- `foreman_v2_audit.jsonl` (append-only events)

### Context packet routing gate (CANONICAL #013)

[`context_packet_gate.py`](context_packet_gate.py) provides `gate_foreman_context_packet(...)` — fail-closed validation of Foreman/orchestration **context packets** against `docs/working/current_directive.md`, the governance bus hash gate (`governance_bus.check_directive_hash_gate`), and lane metadata before treating a packet as routing authority. Contract: `docs/architect/development_plan.md` §5.9.10–5.9.11; implementation: [`modules/context_ledger/context_packet_validator.py`](../../../modules/context_ledger/context_packet_validator.py). Proof replay: `python3 -m pytest tests/test_context_packet_validator.py -q` and `python3 scripts/runtime/governance_bus.py --peek`.

## Dependencies

Python 3.10+ (stdlib only)

No extra pip dependencies are required.

## Configuration

Environment variables:

- `MISSION_CONTROL_URL` (default: `http://localhost:4000`)
- `MC_API_TOKEN` (optional bearer token for protected APIs)
- `FOREMAN_V2_DEVELOPER_SESSION` (required for live dispatch)
- `FOREMAN_V2_ARCHITECT_SESSION` (required for live dispatch)
- `FOREMAN_V2_POLL_SECONDS` (default: `3`)
- `FOREMAN_V2_DRY_RUN` (`1/true/yes` to disable outbound dispatch)
- `FOREMAN_V2_STRICT_SESSION_GUARD` (default `1`; verify/lock actor->session before live dispatch)
- `FOREMAN_V2_UNIFIED_LOG_PATH` (optional) — override path for **one JSON line per loop cycle** (hostname, PID, cycle, `next_actor`, `bridge_state`, stick holder, dispatch summary). Absolute path or path relative to repo root. If unset, defaults to `docs/working/foreman_v2_cycle_log.jsonl`. See [`../talking_stick/LOGGING_INVENTORY.md`](../talking_stick/LOGGING_INVENTORY.md).
- `FOREMAN_V2_LOOP_STDOUT` (default `1`) — set `0` to suppress per-cycle JSON lines on stdout (file append unchanged).
- `FOREMAN_V2_CYCLE_LOG_DISABLE` — set `1` to skip appending the cycle JSONL file (stdout unchanged unless `FOREMAN_V2_LOOP_STDOUT=0`).

Each **`talking_stick loop`** / **`foreman_v2 loop`** cycle prints one JSON line to stdout (**flushed**) so `> /tmp/talking_stick_debug.log` is non-empty without extra flags.

### Local + clawbot environment bootstrap

Use the included setup helper to create/update `.env.foreman_v2` with all required keys:

```bash
./scripts/runtime/foreman_v2/setup_env.sh ./.env.foreman_v2
source ./.env.foreman_v2
```

Run the same on clawbot:

```bash
ssh jmiller@clawbot.a51.corp 'cd ~/blackbox && ./scripts/runtime/foreman_v2/setup_env.sh ~/blackbox/.env.foreman_v2'
ssh jmiller@clawbot.a51.corp 'source ~/blackbox/.env.foreman_v2 && cd ~/blackbox/scripts/runtime && python3 -m foreman_v2 status'
```

Important:

- `FOREMAN_V2_DEVELOPER_SESSION` and `FOREMAN_V2_ARCHITECT_SESSION` must be set for live dispatch.
- Leave `FOREMAN_V2_DRY_RUN=0` for live runs.
- `MC_API_TOKEN` may be blank only if your Mission Control API is not protected.

## Launch (Mac Local)

From repo root:

```bash
cd scripts/runtime
python3 -m foreman_v2 once
```

Continuous loop:

```bash
cd scripts/runtime
python3 -m foreman_v2 loop
```

Dry-run mode:

```bash
cd scripts/runtime
FOREMAN_V2_DRY_RUN=1 python3 -m foreman_v2 loop
```

## Launch (Mac Face + Lab Engine tie)

If Mission Control/OpenClaw backend is remote (lab/clawbot), point URL/token at that backend:

```bash
cd scripts/runtime
MISSION_CONTROL_URL="https://<your-mc-host>" \
MC_API_TOKEN="<token>" \
FOREMAN_V2_DEVELOPER_SESSION="<dev-session-id>" \
FOREMAN_V2_ARCHITECT_SESSION="<arch-session-id>" \
python3 -m foreman_v2
```

This keeps UI/control on Mac while broker routing goes through backend sessions.

## Operator Command Desk (Single Surface in Cursor)

Use Foreman v2 CLI subcommands as a lightweight command desk in one terminal/chat workflow.

Status:

```bash
cd scripts/runtime
python3 -m foreman_v2 status
```

Send operator message to one lane:

```bash
cd scripts/runtime
python3 -m foreman_v2 route --actor developer --message "pause and summarize current proof"
python3 -m foreman_v2 route --actor architect --message "validate phase 5.3c proof package"
```

Broadcast to both lanes:

```bash
cd scripts/runtime
python3 -m foreman_v2 broadcast --message "operator interrupt: hold work until further notice"
```

Terminate running loop:

```bash
cd scripts/runtime
python3 -m foreman_v2 terminate
```

Self-heal orchestration (canonical authority):

```bash
cd scripts/runtime
python3 -m foreman_v2 reconcile
python3 -m foreman_v2 stick-sync
python3 -m foreman_v2 reset --to-canonical
```

- `reconcile` recomputes canonical state from directive + shared log proof markers and syncs the stick holder.
- `stick-sync` force-aligns `talking_stick.json` holder with current runtime state.
- `reset --to-canonical` clears stale session lock, rebuilds canonical state, and resumes deterministic routing.
- Architect verdict gate: set `ARCHITECT_CANONICAL_VERDICT: met` or `ARCHITECT_CANONICAL_VERDICT: not_met` in shared coordination log; Foreman blocks canonical closure unless architect verdict is `met`.
- Three-strikes gate: after three `ARCHITECT_CANONICAL_VERDICT: not_met` entries, Foreman stops developer retries and forces architect closeout. Architect must write `ARCHITECT_DIRECTIVE_OUTCOME: accepted|rejected|blocked|deferred|closed_without_completion` before closure.

When running, the broker writes a PID file at `docs/working/foreman_v2.pid` and appends operator actions to `foreman_v2_audit.jsonl`.
Session lock safety is persisted in `docs/working/foreman_v2_session_lock.json`.
Role identity registry is persisted in `docs/working/foreman_v2_role_registry.json`.

## Session Safety Controls

Foreman v2 now applies live-dispatch guards:

- Preflight verification: `GET /api/openclaw/sessions/{sid}` must succeed before dispatch.
- Actor-session lock: first successful send pins each actor to one configured session ID in `foreman_v2_session_lock.json`.
- Lock conflict block: if an actor attempts to switch session IDs without explicit operator reconfiguration, dispatch is rejected with `session_lock_conflict`.
- Dedup evidence: repeated loop cycles with unchanged generation append `dispatch_skipped_dedup` audit events.

Operator `terminate` now attempts remote session shutdown (`PATCH` completed + `DELETE`) for configured developer/architect sessions before stopping local broker PID.

Foreman dispatch now includes backend idempotency headers:

- `X-Foreman-Actor`
- `X-Foreman-Dispatch-Key` (derived from `generation` + actor)

## Session Routing Notes

Foreman v2 dispatches prompts by calling:

- `POST /api/openclaw/sessions/{session_id}`

for developer and architect target sessions configured via env vars.

If session IDs are missing or `GET /api/openclaw/sessions/{sid}` fails (e.g. stale UUID / 404), Foreman v2 can still **record dispatch as successful** using **`dry_run_fallback:*`** when **`FOREMAN_V2_DISPATCH_FALLBACK_DRY_RUN=1`** (default). That keeps the bridge out of `sync_conflict` while Mission Control sessions are fixed or rebound. Set **`FOREMAN_V2_DISPATCH_FALLBACK_DRY_RUN=0`** to restore strict failure behavior. Lock conflicts (`session_lock_conflict`) never fall back.

## State Model

Primary states:

- `developer_action_required`
- `developer_active`
- `architect_action_required`
- `architect_validating`
- `closed`
- `sync_conflict`

Generation key:

- Built from directive title/status + bridge state + actor + proof status
- Used for idempotency so repeated loops do not spam duplicate dispatches

## Proof Gate Logic (Simple)

Proof is considered present when shared coordination log includes markers:

- `implementation proof`
- `tests`
- `commands`

Architect handoff is considered returned when shared log contains:

- `have the architect validate shared-docs`

This is intentionally strict and explicit for deterministic automation.

## Operating Procedure (How to Use v2)

1. Start Foreman v2 loop.
2. Work from `docs/working/current_directive.md`.
3. Developer writes proof markers in shared log.
4. Developer includes handoff phrase in shared log.
5. Foreman v2 routes architect validation prompt.
6. Architect validates/updates directive state.
7. Foreman v2 detects closure and moves state to `closed`.

## Architect Kickoff (Exact Runbook)

Use this sequence when starting a real development cycle.

1) Confirm synced code on clawbot:

```bash
cd ~/blackbox
git pull origin main
git rev-parse HEAD
```

2) Ensure Mission Control API is up (current lab baseline uses `:4010`):

```bash
cd ~/mission-control
PORT=4010 npm run dev
```

3) Ensure Foreman env is loaded on clawbot:

```bash
cd ~/blackbox
./scripts/runtime/foreman_v2/setup_env.sh ~/blackbox/.env.foreman_v2
set -a
source ~/blackbox/.env.foreman_v2
set +a
```

4) Start the broker loop:

```bash
cd ~/blackbox/scripts/runtime
python3 -m foreman_v2 loop
```

5) Drive the cycle from the operator desk:

```bash
python3 -m foreman_v2 status
python3 -m foreman_v2 route --actor developer --message "begin implementation for active directive"
python3 -m foreman_v2 route --actor architect --message "stand by for validation handoff"
```

Architect should run preflight first on the execution host:

```bash
python3 -m foreman_v2 doctor
python3 -m foreman_v2 bind-sessions
set -a
source ~/blackbox/.env.foreman_v2
set +a
python3 -m foreman_v2 doctor
```

If `doctor` shows `ok: true`, kickoff is ready.
`bind-sessions` writes both `.env.foreman_v2` and `foreman_v2_role_registry.json`, so role identity stays explicit and inspectable.

6) Developer writes proof in shared docs and hands back with:
- `have the architect validate shared-docs`

7) Architect validates and closes/amends directive in shared docs.

8) Capture proof package:

```bash
./foreman_v2/prove_live_session_safety.sh
```

## Live-Ready Checklist

Foreman v2 is live-ready when all are true:

- `python3 -m foreman_v2 status` returns valid state JSON.
- `route` to developer and architect both return `sent=True`.
- `docs/working/foreman_v2_session_lock.json` exists with both actor locks.
- `docs/working/foreman_v2_audit.jsonl` shows operator route and state events.
- `python3 -m foreman_v2 terminate` returns success detail with remote close status.
- `python3 -m foreman_v2 doctor` returns `ok: true`.
- `python3 -m foreman_v2 bind-sessions` can auto-bind non-main sessions when IDs are missing.

## Visual Queue (How You Know It Is In Development)

You can monitor development visually from one terminal/chat surface in Cursor:

- **State line:** `python3 -m foreman_v2 status`
  - watch `bridge_state`, `next_actor`, `proof_status`, `reason`.
- **Audit timeline:** tail the audit log

```bash
tail -f ~/blackbox/docs/working/foreman_v2_audit.jsonl
```

- **Session lock card:** open `docs/working/foreman_v2_session_lock.json`
  - confirms active actor→session mapping.
- **Shared-doc progress:** open
  - `docs/working/current_directive.md`
  - `docs/working/shared_coordination_log.md`

Interpretation guide:
- `next_actor=developer` + `proof_status=missing` => implementation lane active.
- `next_actor=architect` + `proof_status=present` => validation lane active.
- `bridge_state=sync_conflict` => session/config/proof mismatch needs operator action.

## Testing

Run targeted tests:

```bash
python3 -m pytest -q tests/test_foreman_v2.py
```

Run live session safety proof (no dry-run):

```bash
./scripts/runtime/foreman_v2/prove_live_session_safety.sh
```

The proof script requires `.env.foreman_v2` to contain live session values.

Run one cycle smoke test:

```bash
cd scripts/runtime
FOREMAN_V2_DRY_RUN=1 python3 -m foreman_v2 once
```

## Current Constraints

- Inbound message parsing is not yet implemented in v2 runtime; state progression is driven by canonical shared docs.
- OpenClaw dispatch remains prompt routing; Foreman v2 adds preflight/lock safety but does not parse inbound agent messages yet.
- This is by design for a low-complexity first implementation.

## Next Iteration (Planned)

- Add inbound role reply parsing (session stream hooks)
- Add explicit stick ownership parser integration
- Add richer proof schema validation
- Optional lightweight operator status page

