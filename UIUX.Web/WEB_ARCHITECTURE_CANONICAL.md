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
- chart-heavy interfaces
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
| `/internal` | Internal operator portal | `internal_admin` only |
| `/consumer` | Consumer portal shell | `consumer_user` only |
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

- `internal_admin`
- `consumer_user`

Required routing behavior:

- unauthenticated users go to `/login` when protected pages are requested
- authenticated `internal_admin` users route to `/internal`
- authenticated `consumer_user` users route to `/consumer`
- unknown or invalid roles fail closed

Development bootstrap credential rule:

- local/dev bootstrap username: `admin`
- local/dev bootstrap password: `admin`
- bootstrap password must still be stored through the normal password-hash path
- this bootstrap credential is development-only and not a production contract

## 14. Internal portal contract

The internal portal is the first priority portal surface.

Required `v1` panels or views:

- runtime controls
- Anna status
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

## 16. State handling contract

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

## 17. Portal-to-engine integration contract

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

## 18. API client contract

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

## 19. Component contract

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

## 20. Asset contract

All web assets must live under `UIUX.Web/`.

Required asset rules:

- shared visual assets go in `UIUX.Web/assets/`
- generated web art studies and approved generated logo variants go in `UIUX.Web/assets/generated/`
- landing and portal pages must use repo-local assets, not random hotlinked internet assets
- logo assets must remain original BLACK BOX assets
- asset names should be stable and descriptive

## 21. File organization contract

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

Rules:

- do not scatter web files across unrelated repo folders
- do not create throwaway naming schemes that force later cleanup
- keep route/page names aligned with the information architecture in this document

## 22. Implementation sequence (`v1`)

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

## 23. Web build directive packet (`v1`)

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

## 24. Security and data-boundary contract

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

## 25. Testing and acceptance contract for web work

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

## 26. Non-goals for `v1`

The following are explicitly out of scope unless later directed:

- advanced consumer analytics suites
- real-time charting as a primary portal focus
- visual experimentation beyond the locked system language
- multi-brand theme packs
- complex CMS behavior
- client-side storage of critical secrets

## 27. Developer handoff summary

If a developer reads only one web-specific document before building, this should be enough to start.

The developer must understand:

- where web work lives: `UIUX.Web/`
- what routes exist
- what the landing page must look like
- what the internal and consumer portals are for
- what visual system to use
- how CSS should be organized
- how the UI must talk to the engine
- how to avoid brittle client/API coupling
- what cannot be stored in the web layer
- how web work will be tested and accepted under governance

## 28. Change rule

This document is intended to reduce ambiguity during development.

Rules for change:

- update this document when a web-facing contract changes materially
- do not silently drift from this document during implementation
- if a future directive changes the web stack, route shape, or design system, update this file in the same change set that establishes the new contract
