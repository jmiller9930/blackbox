# Foreman v2 (Mission-Control Pattern) Implementation Plan

## Status

Active execution artifact for the Foreman v2 broker + backend safety path.

### Execution snapshot (2026-03-27)

- Completed:
  - Foreman v2 runtime, state machine, proof gate, audit trail
  - operator command desk (`status`, `route`, `broadcast`, `terminate`)
  - strict actor-session lock (`foreman_v2_session_lock.json`)
  - remote terminate/close attempts (`PATCH` + `DELETE` session route)
  - backend dispatch idempotency contract wiring:
    - broker sends `X-Foreman-Dispatch-Key`
    - Mission Control session route dedupes repeated key in TTL window
  - local/clawbot env bootstrap script (`setup_env.sh`)
  - live proof harness script (`prove_live_session_safety.sh`)
- Remaining for closure:
  - live env values and active session IDs on clawbot
  - architect proof package from live run evidence table

## Objective

Build a lean Foreman v2 broker that automates the BLACK BOX development protocol between local agents (developer and architect roles) while using OpenClaw Gateway as backend session and routing fabric.

This plan intentionally excludes full Mission Control/Autensa product-autopilot scope. We reuse orchestration patterns only.

## Scope and Non-Goals

### In Scope

- Protocol brokerage for development flow:
  - directive intake
  - turn ownership gating
  - handoff dispatch
  - proof gate checks
  - architect validation handoff
- OpenClaw-backed message/session transport
- Lightweight audit trail for transitions and actions
- Mac-first runtime with lab (clawbot) backend compatibility

### Explicit Non-Goals

- Product autopilot features (research, ideation, swipe deck, convoy program management)
- Cost platform, growth experiments, SEO/social automation
- Rebuilding all of Mission Control UI
- Any execution/trading path changes

## Architecture Summary

### Control Model

- Foreman v2 is the policy/state broker.
- OpenClaw Gateway is the transport/runtime control plane (WebSocket sessions, routing).
- Agents are workers that follow Foreman v2 protocol prompts.

### Deployment Model (Target)

- Face/control UX can run on local Mac.
- Engine/backbone can run in lab (clawbot).
- Connectivity via `OPENCLAW_GATEWAY_URL` + token auth.

### Core Components

1. **State Engine**
   - canonical runtime state
   - strict transition table
   - idempotency keys per transition

2. **Protocol Guard**
   - talking-stick ownership checks
   - allowed action checks by role
   - handoff phrase validation

3. **Proof Gate**
   - checks required proof markers in shared docs
   - emits `developer_action_required` or `architect_action_required`

4. **OpenClaw Adapter**
   - send broker prompts to role channels/sessions
   - receive/parse role replies
   - do not delegate policy decisions to gateway

5. **Audit/Event Log**
   - append-only transition/action records
   - operator-visible trace for debugging and trust

## Prerequisites

## A. Protocol Prerequisites

- Canonical directive source in repo
- Canonical shared coordination log
- Turn ownership file (`talking_stick` semantics)
- Required handoff phrases defined and stable
- Closure proof requirements defined (minimum required markers)

## B. Runtime Prerequisites

- OpenClaw Gateway reachable from Foreman v2 runtime host
- Valid gateway token and pairing/auth configured
- Stable session naming convention for role routing (developer, architect)
- Environment config for local + lab modes

## C. Operational Prerequisites

- Single source of truth for next actor at runtime
- Retry/debounce policy for repeated transitions
- Explicit conflict mode when state files drift
- Kill switch / safe pause behavior

## D. Infrastructure Prerequisites (Mac + Clawbot)

- Local repo and server repo branch parity process
- Remote pull procedure on `~/blackbox` after push
- Optional launch agent/service wrapper for continuous broker loop
- Log path standards for runtime diagnostics

## Data Contracts (v2)

## Runtime State (canonical)

Minimum fields:

- `directive_title`
- `directive_status`
- `bridge_status`
- `next_actor`
- `talking_stick_holder`
- `required_phrase`
- `proof_status`
- `sync_status`
- `generation` (idempotency)
- `last_transition_reason`
- timestamps

## Transition States

- `idle`
- `developer_action_required`
- `developer_active`
- `architect_action_required`
- `architect_validating`
- `blocked`
- `closed`
- `sync_conflict`

## Allowed Transition Rules (initial)

- `idle -> developer_action_required` when active directive + no proof
- `developer_action_required -> developer_active` on valid handoff
- `developer_active -> architect_action_required` when proof + handoff phrase
- `architect_action_required -> architect_validating` on valid handoff
- `architect_validating -> closed` on proof pass
- `architect_validating -> developer_action_required` on amend/fail
- any state -> `sync_conflict` when files disagree with canonical runtime state

Disallow silent self-transitions that emit duplicate prompts.

## Implementation Layout (Repo)

Primary working location:

- `scripts/runtime/foreman_v2/`

Suggested modules:

- `__main__.py` (entrypoint)
- `app.py` (service loop / command mode)
- `state.py` (runtime state load/save)
- `transitions.py` (state machine rules)
- `protocol.py` (handoff phrase + role guard logic)
- `proof_gate.py` (shared-doc proof checks)
- `openclaw_adapter.py` (session send/receive)
- `audit.py` (events/log)
- `config.py` (env and paths)

Working docs:

- `docs/working/foreman_v2_runtime_state.json`
- `docs/working/foreman_v2_bridge.json`
- `docs/working/foreman_v2_audit.jsonl`

## Phased Build Plan

## Phase 0 - Spec Lock

- Freeze state schema and transition rules
- Freeze role channel/session naming
- Freeze handoff phrase parsing rules

Exit: review-approved protocol spec with test fixtures.

## Phase 1 - Runtime State Core

- Implement canonical state file manager
- Implement generation/idempotency handling
- Implement conflict detection checks

Exit: deterministic state reads/writes and conflict signaling.

## Phase 2 - Transition Engine

- Implement strict transition table
- Reject invalid transitions with explicit reason
- Add dedupe/debounce for repeated handoffs

Exit: no loop spam, no illegal transition writes.

## Phase 3 - Proof Gate

- Parse shared docs for required proof markers
- Emit developer/architect required actions
- Enforce closure gate only on valid proof

Exit: directive cannot close without proof markers.

## Phase 4 - OpenClaw Adapter

- Implement send prompt to role session/channel
- Add backend idempotency contract (`X-Foreman-Dispatch-Key`)
- Add remote preflight + session existence checks before send
- Implement inbound message listener/parsing (remaining)
- Tie inbound events to transition engine (remaining)

Exit: end-to-end brokered handoff between roles via gateway with duplicate-dispatch suppression.

## Phase 5 - Audit + Operator Visibility

- Append-only audit log
- compact status view for operator
- conflict diagnostics output

Exit: operator can inspect full transition chain quickly.

## Phase 6 - Local Soak

- Run broker locally on Mac with lab gateway
- validate repeated directive cycles
- verify no duplicate handoff storms

Exit: stable 3-cycle soak with expected transitions.

## Phase 7 - Lab Rollout

- run in clawbot backend service mode
- keep local UI/controls if preferred
- confirm local agent to lab broker path

Exit: production-like operation in lab with rollback path.

## Testing Strategy

### Unit Tests

- transition validity tests
- proof parser tests
- handoff phrase parser tests
- idempotency/dedupe tests

### Integration Tests

- directive -> developer handoff -> proof -> architect handoff -> close
- failure/amend route
- sync conflict detection route

### Operational Checks

- service restarts recover state safely
- duplicate inbound messages do not duplicate transitions
- stale/invalid stick state blocks action
- repeated dispatch key does not produce duplicate session send at backend route
- terminate triggers remote close attempts and local PID stop

## End-to-End Backend Inclusion (Required Gate)

### Required runtime topology

1. Foreman v2 process (local or clawbot runtime)
2. Mission Control API route `/api/openclaw/sessions/[id]`
3. OpenClaw gateway sessions
4. Shared docs + audit files in repo

### Backend safety guarantees in scope

- Session preflight verification before send
- Actor->session lock persistence and conflict block
- Dispatch-key dedupe at broker + backend route
- Remote terminate/close attempt path

### Proof package required for architect acceptance

| Where | What you ran / captured | Result |
|---|---|---|
| clawbot `~/blackbox` | `source .env.foreman_v2 && ./scripts/runtime/foreman_v2/prove_live_session_safety.sh` | pass/fail with artifacts |
| docs/working | `foreman_v2_session_lock.json` | stable actor->session mapping |
| docs/working | `foreman_v2_audit.jsonl` tail | dispatch + dedupe + terminate evidence |
| clawbot git | `git rev-parse HEAD` | proof commit SHA |

The directive is not considered operationally closed until this proof table is populated from a live (non-dry) run.

## Risk Register and Mitigations

1. **State drift**
   - Mitigation: canonical runtime state plus derived views; drift detector

2. **Prompt duplication/looping**
   - Mitigation: generation keys + cooldown + same-side block

3. **Host split confusion (Mac vs clawbot)**
   - Mitigation: explicit runtime mode in config and startup logs

4. **Protocol bypass**
   - Mitigation: all action handlers guarded by ownership + phrase validation

5. **Gateway dependency issues**
   - Mitigation: adapter retries, offline fail-safe, queue pending transitions

## Cutover Plan (Foreman Legacy -> v2)

1. Build v2 alongside legacy (no destructive replacement)
2. Shadow mode: v2 observes and simulates transitions
3. Compare outputs for 1 to 2 directive cycles
4. Enable v2 as authoritative writer
5. Keep legacy rollback switch for short window
6. Remove legacy active loop once stable

## Definition of Done (v2 Broker)

- Brokered chat flow obeys v2 protocol as authority
- Turn ownership enforced on every action
- Proof gate blocks invalid closure
- OpenClaw transport integrated and stable
- No duplicate-loop behavior in soak test
- Lab deployment validated after server sync

## References

- Mission Control repository: `https://github.com/crshdn/mission-control`
- OpenClaw docs (Control UI / Gateway): `https://docs.openclaw.ai/web/control-ui`
- OpenClaw dashboard reference: `https://docs.openclaw.ai/web/dashboard`
