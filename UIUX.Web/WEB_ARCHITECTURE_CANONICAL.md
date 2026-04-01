# BLACK BOX Web Architecture Canonical

**Status:** Active `v1` web architecture contract for development  
**Location authority:** `UIUX.Web/` is the repo home for web-facing BLACK BOX work  
**Applies to:** landing page, login surface, internal portal, consumer portal shell, shared web assets, and the portal-to-engine integration boundary

## 1. Authority and precedence

This document is the canonical web architecture specification for files under `UIUX.Web/`.

It does **not** override project-wide governance. If there is a conflict, precedence remains:

1. `docs/architect/development_governance.md`
2. `docs/architect/development_plan.md`
3. `docs/working/current_directive.md`
4. this document for web architecture details inside `UIUX.Web/`

Interpretation rule:

- governance decides whether work is authorized, how proof is recorded, and who closes the slice
- this document decides what the web layer should be, how it should be structured, and how it should integrate with the BLACK BOX engine
- if a developer must choose between convenience and this contract, this contract wins unless the operator or architect updates it in writing

## 2. Purpose

The BLACK BOX web layer exists to provide a stable web front door and an operational portal over the engine core.

The web layer is **not** an independent product brain. It is a human-facing shell over:

- authentication and routing
- runtime visibility
- operator controls
- strategy visibility
- training visibility
- edge-bot visibility
- additive engine integration through the approved API boundary

## 3. `v1` product objective

The first useful BLACK BOX web release must provide:

- a public landing page
- a login surface
- a routed internal portal shell
- a routed consumer portal shell
- a stable shared visual language
- a non-brittle API client boundary to the engine core

The first useful BLACK BOX web release does **not** require:

- advanced analytics dashboards
- chart-heavy interfaces **except** the **internal default live operations surface** defined in **section 31** (primary SOL market chart as supervision, not decorative analytics)
- complex animation systems
- payment flows
- wallet custody
- storage of exchange secrets in the web app

## 4. Hosting and access contract

`v1` hosting assumptions:

- transport: HTTPS
- default public port: `443`
- external/front-door domain target: `blackbox.greyllc.net`
- internal host: `clawbot.a51.corp`
- internal host IP: `172.20.2.161`
- internal access target: `https://172.20.2.161:443/`
- canonical server repo path: `~/blackbox/UIUX.Web/`
- canonical local development path: `/Users/bigmac/Documents/code_projects/blackbox/UIUX.Web/`
- the web layer must be deployable without changing its core information architecture

Rules:

- the public domain is the human access point
- `clawbot.a51.corp` / `172.20.2.161` is the internal server target for web mounting and verification
- environment-specific values must be configurable rather than hard-coded into page content or scripts

### 4.1 Source-of-truth sync contract

BLACK BOX web development is local-first, git-synced, and clawbot-deployed.

Required workflow:

- author and edit web work in the local clone first
- commit locally
- push to the canonical git remote
- on `clawbot`, pull from git into `~/blackbox`
- verify and deploy from `~/blackbox`

Rules:

- the local clone is the authoring tree
- `clawbot` is the pulled execution / verification / deployment tree
- `clawbot` must not become an undocumented alternate authoring source of truth
- when local and `clawbot` differ, reconciliation must happen through git rather than through silent manual drift
- web work is not server-aligned until the relevant commit has been pulled into `~/blackbox`

## 5. Web server and mount contract

The `v1` web server standard is:

- reverse proxy / web server: `nginx`
- server host: `clawbot.a51.corp`
- listen port: `443`
- public server name: `blackbox.greyllc.net`
- internal verification target: `172.20.2.161:443`

Required mount behavior:

- the website root `/` must serve from the BLACK BOX web repo folder at `~/blackbox/UIUX.Web/`
- static assets must resolve from `~/blackbox/UIUX.Web/assets/`
- generated assets must resolve from `~/blackbox/UIUX.Web/assets/generated/`
- `index.html` is the landing-page entry file for `/`
- `/api/v1/` must be mounted as a reverse-proxy path to the BLACK BOX engine API upstream
- the authenticated live-update/event stream must be mounted under the same API namespace rather than as an unrelated side channel

Required deployment interpretation:

- the developer builds in `UIUX.Web/`
- the server serves the contents of `~/blackbox/UIUX.Web/`
- the web tier fronts the engine through `nginx` on `443`
- the web tier is not a separate mystery host or implied service

Rules:

- do not deploy the web files from an unspecified folder
- do not invent an alternate server root without updating this document
- do not mount the UI directly onto engine internals; use the reverse-proxied API boundary
- internal verification should use `https://172.20.2.161:443/` unless the operator later standardizes a different internal hostname

### 5.1 Engine upstream contract

The `v1` web tier must front one explicit BLACK BOX engine upstream.

Required `v1` upstream:

- upstream host: `127.0.0.1`
- upstream port: `8000`
- upstream base: `http://127.0.0.1:8000`
- public/proxied API base: `/api/v1/`
- proxied upstream API base: `http://127.0.0.1:8000/api/v1/`
- proxied live-update/event stream base: `http://127.0.0.1:8000/api/v1/stream/`
- engine healthcheck path: `/api/v1/health`

Rules:

- `nginx` on `443` is the approved web-facing entry point for browsers
- browsers should talk to `/api/v1/` on the same origin rather than directly to `127.0.0.1:8000`
- the upstream host/port must not be inferred from ad hoc container names or temporary shell commands
- if the engine service moves off `127.0.0.1:8000`, this document must be updated in the same change set

### 5.2 Auth and session contract

The `v1` portal must evolve from local bootstrap auth to engine-backed authentication through the same `/api/v1/` boundary.

Required `v1` auth endpoints:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/complete`
- `POST /api/v1/auth/email/verify`
- `POST /api/v1/auth/email/resend-verification`
- `GET /api/v1/account/me`
- `POST /api/v1/account/password`

Required `v1` session behavior:

- server-issued session or token becomes the source of truth for authenticated API access
- role enforcement must be performed server-side as well as in the UI
- UI bootstrap credentials are development-only and must not be treated as production auth
- login success must return enough data to determine `user_id`, `username`, `role`, `account_state`, and session validity
- logout must invalidate the active session on the server side
- protected pages must fail closed when session validation fails

Required `v1` auth response envelope:

- `trace_id`
- `requested_at`
- `result_state`
- `reason_code` when not successful
- `session` object when successful

Required `session` object fields:

- `user_id`
- `username`
- `role`
- `account_state`
- `issued_at`
- `expires_at`

Rules:

- passwords must be verified by the engine once engine auth is wired
- the client may cache session metadata for navigation convenience, but server truth controls authorization
- auth transitions must leave audit records

## 6. Web architecture shape

The BLACK BOX web layer must follow this shape:

- static-first shell where possible
- semantic HTML for structure
- standard CSS for styling
- minimal JavaScript only where interaction or engine communication requires it
- shared tokens and reusable primitives rather than page-specific visual inventions

`v1` implementation rule:

- do not make a framework mandatory unless a later directive explicitly chooses one
- if a framework is introduced later, it must preserve the route structure, component contracts, token system, and API boundary defined here
- the default assumption for `v1` is standards-based web delivery: HTML, CSS, and JavaScript

## 7. Information architecture

The required `v1` route set is:

| Route | Purpose | Access |
|-------|---------|--------|
| `/` | Public landing page / under-construction or product front door | Public |
| `/login` | Login entry point | Public |
| `/internal` | Internal operator portal | `internal_admin`, `internal_member` (staff); admin-only tools gated in UI and must be enforced server-side |
| `/consumer` | Consumer portal shell | `consumer_user` only |
| `/guide` | Structured system guide for how BLACK BOX works and how to work with Anna | Any authenticated user |
| `/404` | Not-found screen | Public |

Rules:

- route naming should remain simple and stable
- internal and consumer experiences must be separated by route and role
- unauthorized access must fail closed to login or an access-denied state
- a page must not rely on hidden DOM sections as the only access-control mechanism

## 8. Landing page contract

The landing page is the public face of BLACK BOX.

Required `v1` landing content:

- BLACK BOX name
- original BLACK BOX box-mark
- concise portal status or mission statement
- login path
- under-construction or current-status messaging until the full portal is active

Landing-page mark rule:

- the BLACK BOX box-mark must sit dead center in the landing-page hero area
- the mark should occupy roughly one quarter of the visual focus area in `v1`
- the mark must be a BLACK BOX original asset
- the mark may take inspiration from the feel of a geometric boxed icon, but must not copy Cursor branding
- the mark must use a black/dark treatment rather than a white-box clone

Layout rule:

- the landing page should remain visually centered, sparse, and premium
- do not crowd the hero with excessive copy, links, or panels
- if temporary status cards are used, they must remain subordinate to the hero mark

## 9. Visual system contract

The portal must maintain one design language during development.

Required visual characteristics:

- Apple-like restraint
- premium but simple presentation
- soft-radius controls
- clean spacing
- subtle shadows and depth
- low visual noise
- neutral, light-first background palette unless a later directive changes theme

Forbidden `v1` visual behavior:

- neon dashboard styling
- noisy gradients
- mismatched card styles between screens
- novelty skeuomorphism
- inconsistent button systems
- random spacing or radius choices per page

## 10. Styling methodology contract

The styling system must use:

- CSS custom properties for design tokens
- semantic class names
- reusable component classes
- shared layout primitives

Minimum token categories:

- colors
- typography
- spacing
- radii
- shadows
- breakpoints
- transition timing

Rules:

- inline style attributes should be avoided except where a later directive explicitly justifies them
- one-off page CSS should be avoided when a shared primitive can be used instead
- styling should be additive through shared tokens/classes rather than repeated ad hoc declarations
- page layout must not depend on fragile absolute positioning for core content

## 11. Typography and control language

Default `v1` typography rule:

- use a system sans-serif stack aligned to Apple-like presentation
- prioritize legibility and calm hierarchy over decorative type

Button and control rule:

- all buttons must share one visual language
- all inputs must share one visual language
- all cards must share one visual language
- primary, secondary, disabled, loading, and destructive states must be visually distinct

Minimum button states:

- default
- hover
- active
- focus-visible
- disabled
- loading

Rules:

- no clickable control may look disabled when active
- no disabled control may look active
- hover/active states must be subtle and consistent
- focus-visible state is required for keyboard navigation

## 12. Accessibility contract

The `v1` web layer must meet practical baseline accessibility requirements.

Required rules:

- use semantic HTML landmarks
- all interactive controls require accessible labels
- keyboard navigation must work for primary flows
- visible focus state is mandatory
- color alone must not be the only status indicator
- images that communicate brand or meaning require `alt` text

`v1` accessibility floor:

- landing page
- login page
- internal portal navigation
- major control buttons

## 13. Portal roles and routing contract

The required `v1` web roles are:

- `internal_admin` — full operator portal including user directory / admin API surfaces
- `internal_member` — same internal portal route; **no** user-admin tools (client hides links; engine must deny `/admin/*` without admin role)
- `consumer_user` — consumer portal only

Required routing behavior:

- unauthenticated users go to `/login` when protected pages are requested
- authenticated internal staff (`internal_admin`, `internal_member`) route to `/internal`
- authenticated `consumer_user` users route to `/consumer`
- unknown or invalid roles fail closed

Development bootstrap credential rule:

- local/dev: `admin`/`admin` (admin), `team`/`team` (member), `consumer`/`consumer` (consumer); login page exposes quick sign-in by level
- bootstrap passwords must still be stored through the normal password-hash path in production
- these bootstrap credentials are development-only and not a production contract

## 14. Internal portal contract

The internal portal is the first priority portal surface.

### 14.1 Default post-login experience

The **default route** after internal login (`/internal`) must present the **BLACK BOX-owned live operations surface** described in **section 31**, not a Drift wrapper, not a docs-first layout, and not a generic grid of undifferentiated placeholders.

The operator must be able to **immediately** (above the fold, without reading documentation) orient to market motion, data health, Anna activity, and runtime state. Deeper panels (training, strategies, edge bots, full exchange detail, system guide) remain reachable from navigation but are **secondary** to that default supervision composition.

### 14.2 Required `v1` panels or views (full portal)

In addition to the **section 31** default landing composition, the internal portal continues to reserve or expose:

- runtime controls (also summarized on the default landing **control strip** per section 31)
- Anna status (also summarized on the default **Anna at work** surface per section 31)
- Billy / Drift exchange status
- winning / losing state
- Anna training / learning window
- strategy inventory with drill-down
- training participation input/review
- edge-bot status
- recent event feed

Rules:

- the training window must be first-class, not buried deep in navigation
- the internal portal must be useful without Slack for the covered `v1` actions
- each visible panel must map to a defined data or control contract
- panels may be hidden by role, but must not silently disappear due to data-loading errors

## 15. Consumer portal contract

The consumer portal is intentionally smaller than the internal portal.

Required `v1` consumer surface:

- account status
- bot connection status
- connect / disconnect status visibility
- strategy-selection placeholder or current selected strategy visibility when enabled
- readable system status relevant to the consumer's scope

Rules:

- the consumer portal must not expose internal-only controls
- the consumer portal must not expose sensitive internal runtime detail unless later authorized
- the consumer portal must remain understandable to a non-operator

## 16. PiBot placeholder contract (`v1`)

PiBot connection, pairing, recovery, and edge enrollment are contracted future surfaces, but they are not required to be implemented in the first web-integrated slice.

Required `v1` interpretation:

- PiBot is part of the product/system model
- PiBot-related surfaces may appear in the portal as placeholders
- placeholder PiBot surfaces must be labeled honestly as `not complete`, `not wired`, or equivalent fail-closed language
- PiBot controls must not appear active until the engine/API path exists

Rules:

- the UI must not imply that PiBot pairing or recovery is live when it is not
- a placeholder is acceptable; a fake active workflow is not
- the future implementation must remain easy to add because the route, panel, and API namespace are already reserved by contract

## 17. System guide contract

The web layer must include one structured guide page that explains the system in plain language for logged-in users.

Required guide coverage:

- what BLACK BOX is
- how the portal, engine, Anna, Billy, and PiBot fit together
- how to talk to Anna
- how curriculum/training staging works
- how paper trades differ from real trades
- how PiBot connection and recovery work
- what the major portal statuses mean
- links to deeper governed docs when needed

Rules:

- the guide is not an architecture-spec replacement; it is a human-readable operational/system explanation
- the guide must be readable by both internal and consumer users
- the guide must stay consistent with the canonical architecture and behavior contracts
- the guide should be reachable after login from the portal navigation

## 18. State handling contract

Every page or panel that reads from the engine must support explicit UI states.

Minimum required states:

- loading
- success
- empty
- degraded
- error
- unauthorized where applicable

Rules:

- no panel may remain blank without explanation when data is unavailable
- failures must be visible and readable
- degraded engine/API conditions must fail closed and inform the user rather than faking healthy state

## 19. Portal-to-engine integration contract

The web layer must integrate with the BLACK BOX engine through an explicit API boundary.

Required `v1` integration surfaces:

- authenticated HTTPS JSON query API
- authenticated HTTPS JSON control API
- authenticated live status/event stream

The web layer must **not**:

- write directly to engine-owned database tables
- mutate runtime state through local-only hacks
- scrape logs as the primary source of truth
- infer success when the engine did not explicitly acknowledge success

The engine remains:

- the canonical source of truth
- the owner of runtime state
- the owner of artifact generation
- the owner of command acceptance or rejection

### 19.1 Query endpoint matrix (`v1`)

The UI-to-engine read contract must use these canonical `GET` paths:

| Path | Purpose | Minimum response body |
|------|---------|-----------------------|
| `/api/v1/health` | Engine healthcheck | `status`, `requested_at`, `trace_id` |
| `/api/v1/runtime/status` | Runtime state summary | `runtime_state`, `reason_code` (nullable), `requested_at`, `trace_id` |
| `/api/v1/anna/status` | Anna state / thesis / confidence summary | `anna_state`, `edge_thesis`, `confidence_or_uncertainty`, `guardrail_status`, `requested_at`, `trace_id` |
| `/api/v1/anna/training/status` | Training / learning state | `training_state`, `degree_lane`, `review_status`, `requested_at`, `trace_id` |
| `/api/v1/exchange/status` | Billy-owned exchange connectivity truth | `exchange_name`, `connection_state`, `wallet_state`, `public_key_match`, `drift_user_state`, `rpc_state`, `market_data_state`, `last_checked_at`, `reason_code`, `trace_id` |
| `/api/v1/pnl/summary` | Winning / losing summary | `winning_or_losing`, `performance_summary`, `requested_at`, `trace_id` |
| `/api/v1/strategies` | Strategy inventory and counts | `items`, `active_count`, `considering_count`, `on_deck_count`, `requested_at`, `trace_id` |
| `/api/v1/edge-bots` | Edge / PiBot status list | `items`, `requested_at`, `trace_id` |
| `/api/v1/events/recent` | Recent event feed | `items`, `requested_at`, `trace_id` |
| `/api/v1/account/me` | Account profile for current user | `account`, `requested_at`, `trace_id` |

Rules:

- each path must return JSON
- every response must include `trace_id`
- every response must include `requested_at`
- paths may grow additively, but the minimum fields above are required

### 19.2 Control endpoint matrix (`v1`)

The UI-to-engine write contract must use these canonical `POST` paths:

| Path | Purpose | Minimum request body | Minimum response body |
|------|---------|----------------------|-----------------------|
| `/api/v1/runtime/start` | Start runtime participation | `actor_id` | `trace_id`, `requested_at`, `result_state`, `reason_code` (nullable) |
| `/api/v1/runtime/pause` | Pause runtime participation | `actor_id` | `trace_id`, `requested_at`, `result_state`, `reason_code` (nullable) |
| `/api/v1/runtime/stop` | Stop runtime participation | `actor_id` | `trace_id`, `requested_at`, `result_state`, `reason_code` (nullable) |
| `/api/v1/runtime/restart` | Restart runtime participation | `actor_id` | `trace_id`, `requested_at`, `result_state`, `reason_code` (nullable) |
| `/api/v1/training/review/submit` | Submit training participation or review action | `actor_id`, `training_item_id`, `action` | `trace_id`, `requested_at`, `result_state`, `reason_code` (nullable) |

PiBot-reserved future control paths:

- `/api/v1/edge-bots/enroll`
- `/api/v1/edge-bots/recover`
- `/api/v1/edge-bots/disconnect`

Rules:

- PiBot-reserved future control paths may exist in docs before they are implemented
- until implemented, the UI must label them as not wired
- every control action must fail closed when rejected or unavailable

### 19.3 Common API envelope rule (`v1`)

Successful query/control responses must remain machine-readable and additive.

Minimum common response fields:

- `trace_id`
- `requested_at`
- `result_state`
- `message`

Error/negative responses must also include:

- `reason_code`

Rules:

- `result_state` should be bounded to `success`, `accepted`, `rejected`, or `error`
- `reason_code` must be stable enough for UI handling and audit
- UI copy may be human-friendly, but machine-readable fields are required

### 19.4 Event stream contract (`v1`)

The authenticated live-update stream must live under the `/api/v1/stream/` namespace.

Required `v1` stream path:

- `/api/v1/stream/status`

Required event envelope:

- `event_type`
- `emitted_at`
- `trace_id`
- `payload`

Recommended initial `event_type` set:

- `runtime_status_changed`
- `anna_status_changed`
- `exchange_status_changed`
- `training_status_changed`
- `strategy_inventory_changed`
- `edge_bot_status_changed`
- `recent_event_added`

Rules:

- clients must tolerate new event types additively
- stream disconnects must fail closed in the UI with readable degraded status
- the stream is not a substitute for the query API; it is a near-real-time update surface layered on top

### 19.5 Detailed payload schema contract (`v1`)

The endpoint list above is not sufficient by itself.

The following field-level schemas are the binding `v1` response contracts for the web UI and engine.

#### 19.5.1 Common field-shape rules

Rules:

- every API response body is JSON object root, never a bare array
- every response includes `trace_id`, `requested_at`, and `result_state`
- all timestamps use strict ISO-8601 UTC with required `Z` suffix
- ids and opaque references are non-empty ASCII strings
- integer counts are JSON integers
- decimal/monetary/ratio values may be returned as JSON numbers or decimal strings, but one endpoint must stay internally consistent across all calls
- fields marked nullable must be present with `null` when no value exists rather than omitted, unless otherwise stated
- additive fields are allowed, but required fields may not be removed or renamed without governed contract update

#### 19.5.2 Common response envelope

Required on every successful query/control response:

| Field | Type | Required rule |
|-------|------|---------------|
| `trace_id` | string | Required stable request correlation id. |
| `requested_at` | string | Required response generation timestamp. |
| `result_state` | string | Required bounded value: `success`, `accepted`, `rejected`, `error`. |
| `message` | string or null | Required nullable human-readable summary. |

Required on every rejected/error response:

| Field | Type | Required rule |
|-------|------|---------------|
| `reason_code` | string | Required stable machine-readable reason. |
| `message` | string | Required human-readable explanation. |

#### 19.5.3 `GET /api/v1/health`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `status` | string | Required bounded value: `healthy`, `degraded`, `unhealthy`. |
| `service_name` | string | Required stable engine service identifier. |
| `version` | string or null | Required nullable deployed version/build identifier. |

#### 19.5.4 `GET /api/v1/runtime/status`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `runtime_state` | string | Required bounded value: `starting`, `running`, `pausing`, `paused`, `stopping`, `stopped`, `restarting`, `unknown`. |
| `last_transition_at` | string or null | Required nullable timestamp for last runtime-state transition. |
| `reason_code` | string or null | Required nullable runtime reason when not cleanly running. |
| `current_mode` | string or null | Required nullable bounded value: `idle`, `analysis`, `training`, `paper_trade`, `live_trade`, `maintenance`. |

#### 19.5.5 `GET /api/v1/anna/status`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `anna_state` | string | Required bounded value: `analyzing`, `waiting`, `paused`, `stopped`, `error`, `abstaining`. |
| `current_strategy` | string, array, or null | Required nullable current strategy id or ordered list of ids. |
| `edge_thesis` | string or null | Required nullable concise current working thesis. |
| `confidence_or_uncertainty` | string | Required bounded value: `confident`, `uncertain`, `abstaining`. |
| `guardrail_status` | string | Required bounded value: `clear`, `blocked`, `restricted`. |
| `winning_or_losing` | string | Required bounded value: `winning`, `losing`, `flat`. |
| `degree_lane` | string | Required bounded value: `bachelor`, `master`, `phd`. |
| `training_execution_state` | string | Required bounded value: `conversation`, `candidate_training`, `staged_training`, `validated_learning`, `review_only`, `simulation_only`, `simulation_then_micro_live`. |

#### 19.5.6 `GET /api/v1/anna/training/status`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `state_label` | string | Required bounded value: `conversation`, `candidate_training`, `staged_training`, `validated_learning`. |
| `degree_lane` | string | Required bounded value: `bachelor`, `master`, `phd`. |
| `review_status` | string | Required bounded value: `not_reviewed`, `under_review`, `review_complete`, `escalated`. |
| `execution_mode` | string | Required bounded value: `review_only`, `simulation_only`, `simulation_then_micro_live`. |
| `execution_status` | string | Required bounded value: `not_started`, `in_review`, `running`, `completed`, `rejected`. |
| `promotion_outcome` | string | Required bounded value: `not_promoted`, `validated`, `rejected`, `deferred`. |
| `latest_training_item_id` | string or null | Required nullable latest active training item reference. |

#### 19.5.7 `GET /api/v1/exchange/status`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `exchange_name` | string | Required stable venue identifier. |
| `connection_state` | string | Required bounded value: `connected`, `degraded`, `disconnected`, `unknown`. |
| `wallet_state` | string | Required bounded value: `loaded`, `not_loaded`, `mismatch`. |
| `public_key_match` | boolean | Required boolean. |
| `drift_user_state` | string | Required bounded value: `ready`, `missing_user_account`, `margin_not_enabled`, `not_checked`. |
| `rpc_state` | string | Required bounded value: `reachable`, `unreachable`, `degraded`. |
| `market_data_state` | string | Required bounded value: `healthy`, `stale`, `down`, `unknown`. |
| `last_checked_at` | string | Required last exchange-health evaluation timestamp. |
| `reason_code` | string or null | Required nullable stable failure/degraded reason. |

#### 19.5.8 `GET /api/v1/pnl/summary`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `winning_or_losing` | string | Required bounded value: `winning`, `losing`, `flat`. |
| `current_balance` | number or string | Required current balance value. |
| `comparison_balance` | number or string | Required comparison-point balance value. |
| `performance_summary` | object | Required object. |

Required `performance_summary` fields:

- `win_rate`
- `expected_value`
- `average_win`
- `average_loss`
- `drawdown`
- `fee_drag`

#### 19.5.9 `GET /api/v1/strategies`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `items` | array | Required list of strategy records. |
| `active_count` | integer | Required count. |
| `considering_count` | integer | Required count. |
| `on_deck_count` | integer | Required count. |

Required per-item fields:

- `strategy_id`
- `title`
- `status`
- `summary`
- `last_updated_at`

Required `status` enum:

- `active`
- `considering`
- `on_deck`
- `inactive`
- `archived`

#### 19.5.10 `GET /api/v1/edge-bots`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `feature_state` | string | Required bounded value: `not_complete`, `not_wired`, `live`. |
| `items` | array | Required list; may be empty. |

Required per-item fields when implemented:

- `bot_id`
- `bot_label`
- `device_type`
- `connection_state`
- `owner_binding_state`
- `last_seen_at`

Required `connection_state` enum:

- `connected`
- `disconnected`
- `recovering`
- `unknown`

Required `owner_binding_state` enum:

- `bound`
- `unbound`
- `recovery_pending`
- `unknown`

#### 19.5.11 `GET /api/v1/events/recent`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `items` | array | Required list; may be empty. |

Required per-item fields:

- `event_id`
- `event_type`
- `severity`
- `occurred_at`
- `title`
- `summary`
- `trace_id`
- `related_ref` (nullable)

Required `severity` enum:

- `info`
- `warning`
- `error`

#### 19.5.12 `GET /api/v1/account/me`

Required response fields:

| Field | Type | Required rule |
|-------|------|---------------|
| `account` | object | Required object. |

Required `account` fields:

- `user_id`
- `username`
- `email`
- `role`
- `account_state`
- `email_verified`
- `accepted_risk_terms_at` (nullable)
- `created_at`
- `last_login_at` (nullable)

#### 19.5.13 Control request body contract

Required on every control request body:

- `actor_id`
- `requested_at`
- `command_source`

Required `command_source` enum:

- `portal_internal`
- `portal_consumer`
- `slack`
- `system_internal`

Additional required fields by endpoint:

- `/api/v1/training/review/submit`: `training_item_id`, `action`

Required `action` enum for `/api/v1/training/review/submit`:

- `stage_it`
- `revise_it`
- `leave_it`
- `review_complete`
- `escalate`

#### 19.5.14 Event-stream payload mapping

Required `payload` object minimums by `event_type`:

- `runtime_status_changed` -> same field minimums as `GET /api/v1/runtime/status`
- `anna_status_changed` -> same field minimums as `GET /api/v1/anna/status`
- `exchange_status_changed` -> same field minimums as `GET /api/v1/exchange/status`
- `training_status_changed` -> same field minimums as `GET /api/v1/anna/training/status`
- `strategy_inventory_changed` -> same field minimums as `GET /api/v1/strategies`
- `edge_bot_status_changed` -> same field minimums as `GET /api/v1/edge-bots`
- `recent_event_added` -> one event item using the `GET /api/v1/events/recent` item schema

## 20. API client contract

The web client must be built to accommodate engine growth without brittle rewrites.

Required client behavior:

- tolerate additive JSON response fields
- tolerate new event types on the live stream
- treat unknown optional fields as non-breaking
- keep parsing logic localized rather than scattered through every page

Required request behavior:

- send only documented inputs
- preserve `trace_id` and other returned correlation identifiers where relevant
- surface readable acknowledgement or failure state back into the UI

Rules:

- the client must not assume the engine payload shape will never expand
- the client must not break because one new status field or event type appears
- additive compatibility is the default expectation

## 21. Component contract

The web layer must be composed from reusable primitives.

Minimum primitive set:

- page shell
- header
- hero
- card
- button
- input
- badge
- status row
- panel shell
- event feed item

Rules:

- new pages should compose from existing primitives first
- new primitives should be added only when the existing set cannot express the need cleanly
- duplicated near-identical components are a contract violation unless explicitly approved

## 22. Asset contract

All web assets must live under `UIUX.Web/`.

Required asset rules:

- shared visual assets go in `UIUX.Web/assets/`
- generated web art studies and approved generated logo variants go in `UIUX.Web/assets/generated/`
- landing and portal pages must use repo-local assets, not random hotlinked internet assets
- logo assets must remain original BLACK BOX assets
- asset names should be stable and descriptive

## 23. File organization contract

The web layer must stay organized and easy to hand off.

Current required base structure:

```text
UIUX.Web/
  index.html
  styles.css
  assets/
    generated/
  WEB_ARCHITECTURE_CANONICAL.md
```

If the portal expands, the preferred direction is:

```text
UIUX.Web/
  index.html
  login.html
  internal.html
  consumer.html
  404.html
  styles.css
  app.js
  assets/
    generated/
  WEB_ARCHITECTURE_CANONICAL.md
```

**As-delivered static shell (Phases 1–4 foundation):** the repo includes the tree above with `404.html`, shared `app.js` (sessionStorage dev bootstrap `admin`/`admin` and `consumer`/`consumer`, `BlackboxPortal.api` for `/api/v1/` + optional SSE), and nginx should map clean paths `/login` → `login.html`, `/internal` → `internal.html`, `/consumer` → `consumer.html` when configured. **Local / scalable static serve:** `UIUX.Web/docker-compose.yml` + `Dockerfile` + `nginx/default.conf` run **nginx** in Docker with **TLS on container port 443** (compose maps **`443:443`** and **`80:80`**; HTTP redirects to HTTPS). Use **`https://127.0.0.1/`** or **`https://172.20.2.161/`** (default port 443). The image bakes a **dev self-signed** cert (browser warning until replaced for production). Scale with multiple replicas behind a load balancer (same image, stateless).

**Proof artifacts:** `UIUX.Web/artifacts/PROOF_INDEX.txt` maps automated tests to deliverables; `UIUX.Web/artifacts/pytest_uiux_web_latest.txt` is the checked-in transcript of the latest `pytest tests/test_uiux_web.py` run for that change set. Regenerate both when the web shell changes materially.

**Unified portal document:** `UIUX.Web/content/UNIFIED_PLAN.md` is a **generated** splice of `docs/architect/development_plan.md` and this file (`WEB_ARCHITECTURE_CANONICAL.md`), built by `python3 scripts/build_unified_portal_plan.py`. Run that script after editing either source, then commit the updated `UNIFIED_PLAN.md`. Internal operators open it in-browser via **`internal-plan.html`** (auth-gated).

Rules:

- do not scatter web files across unrelated repo folders
- do not create throwaway naming schemes that force later cleanup
- keep route/page names aligned with the information architecture in this document

## 24. Implementation sequence (`v1`)

This section is the canonical economical build order for the `v1` web UI.

The developer must use this sequence unless a later governed directive explicitly changes it.

Sequence rule:

- do not jump ahead to later portal surfaces while an earlier required foundation is still missing
- do not replace a missing earlier phase with mock complexity in a later phase
- each phase should leave a usable, testable increment
- the internal portal path is the first priority portal surface

### Phase 1 — Static public shell

Required deliverables:

- `index.html`
- shared `styles.css`
- repo-local asset loading from `UIUX.Web/assets/`
- public landing page following the locked visual system
- `404` page or equivalent not-found surface

Phase goal:

- prove the web root is mounted correctly and the shared visual system is real

Phase exit criteria:

- `/` loads successfully
- the landing page uses the BLACK BOX mark package
- styles and assets resolve from the documented folder structure
- there are no fake engine interactions on the landing page

### Phase 2 — Login surface

Required deliverables:

- `/login`
- username/password form
- development bootstrap support for `admin` / `admin`
- role-based routing behavior after successful login

Phase goal:

- prove the web layer can authenticate and route users without inventing hidden page states

Phase exit criteria:

- `/login` renders correctly
- invalid auth fails visibly
- valid auth routes `internal_admin` to `/internal`
- valid auth routes `consumer_user` to `/consumer`

### Phase 3 — Internal portal shell

Required deliverables:

- `/internal`
- shared page shell and navigation
- panel shells for the required internal surfaces
- honest placeholders or disabled states where engine data is not yet wired

Phase goal:

- establish the internal portal frame before wiring real engine data

Phase exit criteria:

- the internal shell loads behind auth
- visible panels match the internal portal contract
- no control appears active unless it is wired or explicitly disabled

### Phase 4 — Minimal API client and session layer

Required deliverables:

- shared request helper for `/api/v1/`
- shared error-handling path
- shared auth/session handling
- shared live-update/event-stream client

Phase goal:

- centralize engine communication before wiring many panels

Phase exit criteria:

- API calls are not scattered as one-off page logic
- auth/session state is reusable
- event-stream connection path exists in one shared client layer

### Phase 5 — First real engine-backed panel

Required deliverables:

- one real internal panel backed by the engine API
- recommended first panel: runtime status or Billy / exchange status
- readable loading, success, degraded, and error states

Phase goal:

- prove end-to-end UI -> API -> engine -> UI acknowledgement

Phase exit criteria:

- the selected panel reads live engine-backed data
- UI state handling is explicit
- no log scraping or fake status is used

### Phase 6 — Runtime controls

Required deliverables:

- internal runtime-control buttons for `start`, `pause`, `stop`, and `restart`
- readable control acknowledgements
- fail-closed error handling for rejected or failed actions

Phase goal:

- prove the internal portal can safely send real control actions through the approved boundary

Phase exit criteria:

- each runtime-control action uses the control API
- each result returns readable acknowledgement
- no control silently appears successful when the engine rejects it

### Phase 7 — Internal operational surfaces

Required deliverables:

- Anna status panel
- training / learning window
- strategy inventory with drill-down
- recent event feed
- edge-bot status panel

Phase goal:

- fill out the internal operator portal after the first real engine-backed control/read loop is proven

Phase exit criteria:

- each panel maps to a documented data contract
- missing data states are explicit
- the training window remains first-class and visible

### Phase 8 — Consumer portal shell

Required deliverables:

- `/consumer`
- consumer-safe status surfaces only
- connection status visibility
- limited strategy/status visibility consistent with the consumer contract

Phase goal:

- add the smaller consumer experience after the internal portal is already useful

Phase exit criteria:

- the consumer shell is role-routed correctly
- internal-only controls are not exposed
- consumer views remain simpler than internal views

### Phase 9 — Deployment and mount proof

Required deliverables:

- `nginx` mount on `443`
- root mount from `~/blackbox/UIUX.Web/`
- `/api/v1/` reverse proxy path
- internal verification against `https://172.20.2.161:443/`

Phase goal:

- prove the locked server and mount contract is real

Phase exit criteria:

- the mounted site is reachable on the documented internal target
- the site serves from the documented server folder
- API requests traverse the documented proxy path

Implementation-order rule:

- this sequence is binding for economical `v1` delivery
- the developer may refine internals within a phase, but should not reorder the major phases without an updated governed contract
- the first acceptable web slice is Phase 1 through Phase 3
- the first acceptable engine-integrated web slice is Phase 1 through Phase 6
- the first acceptable broader `v1` portal slice is Phase 1 through Phase 9

## 25. Web build directive packet (`v1`)

This section is the canonical directive-style execution packet for building the `v1` web UI.

Objective:

- build the BLACK BOX web layer in the locked sequence above
- keep the internal portal as the first priority portal surface
- maintain the locked visual system, routing model, and engine-boundary rules

Required implementation:

1. Build in `UIUX.Web/` only for the web layer unless a later governed change extends the structure.
2. Follow the `v1` implementation sequence in this document.
3. Use repo-local assets only.
4. Use the locked CSS-first methodology and shared primitives.
5. Use the locked API boundary under `/api/v1/`.
6. Keep the client additive and non-brittle.
7. Fail closed on missing auth, missing data, rejected controls, and engine/API errors.

Out of scope:

- introducing a different design language
- bypassing `/api/v1/` with direct DB/runtime access
- building consumer complexity ahead of internal portal usefulness
- advanced dashboards or analytics outside the contracted `v1` surfaces
- hidden fake controls that imply implementation where none exists

Required proof:

- page/route proof for the phase being delivered
- control proof for any engine-facing action
- explicit note that visible buttons either work, navigate, or are honestly disabled
- internal mount/proxy proof when deployment work is in scope

Acceptance rule:

- a web slice is not accepted merely because it "looks close"
- it must satisfy the phase exit criteria it claims to complete
- architect validation is still required under project governance

## 26. Security and data-boundary contract

The web layer must respect the BLACK BOX data boundary.

The web layer may hold:

- account identity fields already authorized for portal use
- session state
- role/routing state
- non-secret operational and status data

The web layer must not hold:

- wallet private keys
- seed phrases
- exchange secrets
- payment data
- unnecessary PII

Rules:

- secrets stay outside the web app per the platform's non-custodial model
- the web layer may display public or consented status data, but must not become a secret vault

### Transport and nginx baseline (standard practice, not “Fort Knox”)

This is **baseline hygiene** for a static portal shell. It is **not** a WAF, bot defense, or application auth (those come with the engine API and hosting perimeter).

**In scope today:**

- **HTTPS only for users:** port **80** responds with **301** to **https://** on the same host; TLS **1.2+** on **443**.
- **No nginx version banner:** `server_tokens off` so the Server header does not advertise a precise nginx build.
- **Standard response headers** on HTML and API-proxied routes (when added): `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`, `Permissions-Policy` neutering camera/mic/geo/payment by default.
- **Docker image:** static files are **explicitly** copied into the docroot so `nginx/` config is **not** accidentally published under `/nginx/`.

**Explicitly not “trusted production” yet:**

- The **baked-in self-signed certificate** in the Docker image is for **lab / bring-up only**. Browsers will warn; **MITM is possible** if you train users to click through. For any shared or external exposure, replace with **real certificates** (internal PKI or public CA) and normal renewal.
- **Do not** add **`Strict-Transport-Security` (HSTS)** until a **valid, stable** certificate and hostname are in use. HSTS + bad/stale certs bricks clients.
- **Dev bootstrap login** (`admin`/`admin`, `consumer`/`consumer`) is **client-side demo state** in `sessionStorage` until the engine owns auth. **Do not** treat it as security; replace with server-verified sessions/tokens per portal contract.
- **Firewall / network ACL:** restrict **443** (and **80** if kept) to **operator/VPN** or approved ranges; do not leave the portal world-open unless intentionally public with real auth.

**When `/api/v1/` is proxied:** enforce **authentication and TLS** on the engine upstream; nginx must forward **`X-Forwarded-Proto`** (and related headers) so the API can enforce HTTPS-aware policies.

**Self-service account (standard process):** The portal ships **UI shells** (`register.html`, `forgot-password.html`, `reset-password.html?token=`, `verify-email.html?token=`, `account-settings.html`) aligned with common practice: **no email enumeration** on forgot-password messaging, **time-limited single-use tokens** for reset and verify (enforced server-side), **password hashing** and **rate limits** on the engine only. Client paths are declared in `app.js` as `ACCOUNT_API` (`/auth/register`, `/auth/password-reset/request`, `/auth/password-reset/complete`, `/auth/email/verify`, `/auth/email/resend-verification`, `/account/me`, `/account/password`, `/admin/users`, `/admin/users/invite`). **`internal-users.html`** is the operator directory/invite shell. Until the engine implements these routes and outbound email, forms show configuration hints and fail closed.

## 27. Testing and acceptance contract for web work

Governance applies to web work exactly as it applies to engine work.

No web slice is complete without developer proof and architect validation.

**Automated artifact (this repo):** run `python3 -m pytest tests/test_uiux_web.py -v --tb=short` from the repository root and retain the output in `UIUX.Web/artifacts/pytest_uiux_web_latest.txt` (see `UIUX.Web/artifacts/PROOF_INDEX.txt` for the test-to-deliverable matrix). Commit the transcript in the **same change set** as material web or test updates.

Minimum `v1` web proof expectations:

- page loads successfully
- no blocking console/runtime errors for the tested flow
- all visible buttons either:
  - perform a real action
  - navigate correctly
  - are visibly disabled with an honest explanation
- layout remains usable at desktop and common laptop widths
- focus states exist for interactive controls
- engine-facing actions return readable success or failure state

Acceptance rule:

- no fake active controls
- no dead buttons presented as working controls
- no silent failures on engine interactions
- no acceptance without proof recorded under governance

## 28. Non-goals for `v1`

The following are explicitly out of scope unless later directed:

- advanced consumer analytics suites
- real-time charting as a **consumer** portal focus or as **exchange-clone** UI; **exception:** the **internal** default **live SOL market surface** (section 31) is **in scope** as a BLACK BOX supervision chart backed by the engine market-data path
- visual experimentation beyond the locked system language
- multi-brand theme packs
- complex CMS behavior
- client-side storage of critical secrets

## 29. Developer handoff summary

If a developer reads only one web-specific document before building, this should be enough to start.

The developer must understand:

- where web work lives: `UIUX.Web/`
- what routes exist
- what the landing page must look like
- what the internal and consumer portals are for
- the **internal default landing** is the **live operations surface** (section 31), not a Drift wrapper or docs-first screen
- what the system guide page must explain
- what visual system to use
- how CSS should be organized
- how the UI must talk to the engine
- which exact API paths and envelopes the UI should target
- how to avoid brittle client/API coupling
- what cannot be stored in the web layer
- how web work will be tested and accepted under governance

## 30. Change rule

This document is intended to reduce ambiguity during development.

Rules for change:

- update this document when a web-facing contract changes materially
- do not silently drift from this document during implementation
- if a future directive changes the web stack, route shape, or design system, update this file in the same change set that establishes the new contract

## 31. Internal post-login live operations surface (architect recommendation)

This section is the **canonical contract** for the **default internal experience** after login. It does **not** replace engine or API ownership; the web layer **displays** engine-backed truth and **fails closed** when unavailable.

### 31.1 Developer recommendation (summary)

Build the default post-login internal experience as a **BLACK BOX-owned live operations surface**, not as a Drift wrapper and not as a docs-first portal.

The goal is that when an internal user logs in, they can **immediately** answer:

- what is the market doing right now
- is live market data flowing
- is Anna working
- what mode is Anna in
- is the runtime healthy
- do I need to intervene

Do **not** make the default screen a wrapped external Drift interface. The operator goal is **system visibility and trust in BLACK BOX itself**, not venue immersion.

### 31.2 Default internal landing view — four primary surfaces

The first screen after internal login is a live **operations overview** composed of **four** primary surfaces, in this **visual hierarchy**:

1. Live SOL market surface (dominant, center)
2. Pyth ingestion and storage surface (near the chart)
3. Anna at work surface
4. Runtime control strip  
   **Secondary:** recent events / supporting state below or beside, without crowding the four primaries.

#### Surface 1 — Live SOL market surface

This is the **dominant** visual in the center of the screen.

**Required behavior**

- Show a live **SOL** candlestick chart.
- Updates must come from the **same market-data path** BLACK BOX ingests and validates (engine-backed; not a decorative third-party widget).
- When live and valid, **label the source as Pyth** explicitly.
- Show **stale / degraded** state honestly when data is old or missing.

**Required data around the chart**

- current SOL price
- recent percentage move
- selected timeframe (e.g. `1m`, `5m`, `15m`, `1h`)
- last update timestamp
- freshness status
- volatility state badge (e.g. `calm`, `elevated`, `high`)

**Optional (preferred)**

- spread
- recent high / low
- candle count in the current window

**Design rule**

- This is a **BLACK BOX** chart, not a cloned exchange UI.
- Restrained, premium, readable: **candlesticks first**, controls second.

#### Surface 2 — Pyth ingestion and storage surface

Placed **near** the chart. Purpose: prove the chart is backed by a **living ingestion system**, not a decorative number.

**Required items**

- Pyth ingestion state: `healthy`, `degraded`, `stale`, or `down`
- processed data count
- retained / stored data count
- current storage usage
- configured retention / limit status
- trim status if trimming is active
- alert state if thresholds are crossed

**Required policy behavior (product/engine; UI must reflect it)**

- Staged storage policy: **alert first** at threshold; **trim** old data after configured size limit; reserve **automatic storage expansion** as later optional work, not required in this slice.
- The UI must show the **configured storage limit** and **current utilization**.
- The UI must **not** hide storage pressure.

#### Surface 3 — Anna at work surface

The operator must see that Anna is **functioning**, not merely “online.”

**Required items**

- Anna state (examples): `analyzing`, `waiting`, `paused`, `stopped`, `error`, `abstaining` — bounded set as contracted by engine/API
- current working thesis or decision summary
- confidence / uncertainty state
- guardrail state
- current mode: `analysis`, `training`, `paper_trade`, `maintenance`, or other **bounded** runtime mode already contracted
- last meaningful action timestamp
- recent event or recent decision trace summary

**Preferred additions**

- latest candidate or latest reviewed item id
- latest training / review state
- visible abstain reason when Anna is not taking action

**Design intent**

- Anna is **visible and inspectable**; show **work and state**, not human-like theatrics.
- Concise **evidence of operation** matters more than decorative personality.

#### Surface 4 — Runtime control strip

Controls are **visible** but must **not** dominate the page.

**Required controls**

- `Start`, `Pause`, `Stop`, `Restart` (as already contracted for runtime; see section 19 control matrix).

**Required state near controls**

- current runtime state
- last transition time
- whether controls are enabled or blocked
- reason code / message when blocked or unavailable

**Design rule**

- Controls are **clearly separated** from telemetry.
- Disabled controls must **state why** they are disabled.
- **Fail closed** when the engine/API does not acknowledge availability.

### 31.3 What the default screen must not be

The default internal landing must **not** be:

- the system guide or a document page
- a generic list of panels with placeholder text and no supervision story
- a wrapped full Drift exchange page
- a consumer-safe simplified shell presented as the internal default

The internal default must be a **live supervision surface**.

### 31.4 Drift (secondary only)

- **Do not** make Drift embedding part of the **required** default implementation for this slice.
- If desired later: provide a secondary **View on Drift** link or optional Drift panel/tab.
- Do **not** make the portal depend on external site embedding.
- Do **not** treat Drift UI as BLACK BOX source of truth.

The **native BLACK BOX candlestick chart** (engine-backed) is the preferred solution for default market visibility.

### 31.5 User experience goal

After login, the internal operator should immediately understand:

| Lens | Question answered |
|------|-------------------|
| Market | SOL is moving like this |
| Data | Pyth is ingesting and storage is healthy |
| Anna | Anna is doing this right now |
| System | Runtime is in this state and these controls are available |

### 31.6 Implementation direction

Wire the landing page around **engine-backed** surfaces, not static placeholders.

**Target data paths (conceptual; exact paths remain section 19 and engine contracts)**

- Live chart data from the BLACK BOX **market-data** path (proxied via `/api/v1/` or additive documented read endpoints as approved).
- Ingestion / storage telemetry from the BLACK BOX engine (counts, limits, utilization, trim/alert — as implemented per slice).
- Anna state from **`/api/v1/anna/status`** (and related training endpoints where applicable).
- Runtime from **`/api/v1/runtime/status`** and **control** endpoints in section 19.

**Visual hierarchy (implementation order)**

1. SOL live chart  
2. Pyth ingestion / storage health  
3. Anna working state  
4. Runtime controls  
5. Recent events as secondary support  

### 31.7 Acceptance standard

This work is **successful** when an internal user can log in and, **without reading documentation**, understand:

- whether live trade / market data is flowing
- whether Anna is actively working
- what mode the system is in
- whether the system is healthy enough to proceed

**Operational proof** (live Pyth, live Drift, live control side effects) is validated in a **separate acceptance pass** per governance; the **layout and honest states** can ship before full operational proof.

### 31.8 Safe to build now vs must be proven later

**Safe to build now (no blocker)**

- Default internal dashboard **composition** and **visual hierarchy**
- SOL live market **panel shell** (chart area, timeframes, labels, stale/degraded UX)
- Pyth ingestion / storage **telemetry panel** shell
- Anna at work **panel** shell
- Runtime **control strip** with separation from telemetry
- Recent events / supporting state region
- Explicit UI states: `loading`, `healthy`, `degraded`, `stale`, `not wired`, `error`
- **API-bound** component hooks using the **endpoint schema** already defined in **section 19** (and additive market-data read contracts as approved)

**Must not be assumed proven until validation**

- Chart fed by **real** live Pyth through the engine path
- Processed / stored counts **accurate**
- Storage trimming / alerts **actually** functioning
- Anna status reflecting **real** runtime behavior
- Runtime controls **actually** affecting the engine
- Exchange (Drift) connectivity **operationally** live

**Instruction to the developer (canonical wording)**

Proceed with the **internal post-login operations dashboard layout** now. Build the BLACK BOX-owned **live operations surface** with panel shells, visual hierarchy, **honest fail-closed** states, and **API-bound** hooks. Do **not** assume live Pyth, live Drift, or live Anna control wiring are already proven; treat those as **runtime-backed** states to be validated in the acceptance pass. **Layout and UI composition** may advance in parallel with **operational truth** validation.
