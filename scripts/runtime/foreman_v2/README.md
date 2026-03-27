# Foreman v2 (Simple Broker)

Foreman v2 is a lean development-process broker. It sits between developer and architect roles and automates protocol routing:

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

When running, the broker writes a PID file at `docs/working/foreman_v2.pid` and appends operator actions to `foreman_v2_audit.jsonl`.
Session lock safety is persisted in `docs/working/foreman_v2_session_lock.json`.

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

If session IDs are missing, Foreman v2 records dispatch failure and moves into `sync_conflict` until fixed.

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

