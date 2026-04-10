# Context turnover log — BLACK BOX (engineering session archive)

| Field | Value |
|--------|--------|
| **UTC timestamp (filename)** | `2026-04-10T17-40-28Z` |
| **Repository** | `blackbox` (local path: workspace root) |
| **Git `HEAD` at author time** | `3280424d1e5cdc747ca5a1a9a364b2d02de36550` |
| **Document type** | Session / turnover — **not** a governance directive; **not** a substitute for `docs/working/current_directive.md` |

---

## 1. Where this file lives (validated structure)

- **Canonical working area:** `docs/working/` — already contains `developer_handoff.md`, `shared_coordination_log.md`, `current_directive.md`, `team_sync.md`, audits, etc.
- **This folder:** `docs/working/session_logs/` — **created for time-stamped engineering turnover and context logs** so long narrative does not bloat the coordination log.
- **Related pattern elsewhere:** `docs/working/proof_webui_control_verify/_archive/proof_verify_run_<ISO-timestamp>/` stores proof run artifacts; this file is **prose + pointers**, not proof JSON.

**Rule:** Do not treat this document as contracted scope; binding work remains per `docs/architect/development_governance.md` and the project contract in `.cursor/rules/architect-developer-directive-contract.mdc`.

---

## 2. Project identity (repository level)

- **Name:** BLACK BOX — phased agentic platform (see root `README.md`).
- **Phase 1 (stated in README):** Bootstrap **Cody** (engineering agent skeleton); explicit exclusions include production trading logic, full DB schema, and mandatory ClawBot integration.
- **Agents registry:** `AGENTS.md` — Cody active; Billy/Jack/Robbie/Bobby are registry/planned per phase, not arbitrary implementation targets.
- **Major doc anchors:** `docs/blackbox_master_plan.md`, `docs/architect/development_plan.md`, `docs/architect/ANNA_GOES_TO_SCHOOL.md` (Anna / training / governance), `docs/runtime/execution_context.md` (primary host / proof).

---

## 3. Governance, proof, and lab host (operational truth)

- **Contracted vs implied:** Binding requirements are **written** in governance and directives — see `.cursor/rules/binding-work-contracted-not-implied.mdc`.
- **Architect proof format:** When reporting completion to the architect, use evidence tables and explicit met/not met — `.cursor/rules/architect-proof-response.mdc`.
- **Lab host:** Canonical runtime work is often validated on **`clawbot`** with repo path `~/blackbox` — see `docs/architect/local_remote_development_workflow.md`.
- **Git delivery:** Substantive changes are **not** “delivered” until **committed and pushed** to `origin` (see `.cursor/rules/git-complete-push-origin.mdc`).

---

## 4. UI / operator surface — deployment facts (critical)

These facts resolved repeated “I see old UI” confusion:

| URL / asset | Served by | Notes |
|-------------|-----------|--------|
| `/dashboard`, `/dashboard/`, `/dashboard.html` | **API (`api_server.py`)** via nginx `proxy_pass` to `api:8080` | HTML is read from **`_REPO_ROOT/UIUX.Web/dashboard.html`** inside the **api** container mount (e.g. `/repo/...`). |
| Rebuilding **only** the `web` Docker image | **Does not** update `/dashboard.html` behavior for proxied routes | Stale `web` image `COPY` of `dashboard.html` can **mislead** grep-based proof; verify **api** mount or `curl` the live URL. |
| `styles.css`, `text-scale.js`, other static files | Often **nginx** from `web` image | Changing those may require **`docker compose build web`** per project rules. |

Reference: `UIUX.Web/nginx/default.conf` comments; `.cursor/rules/clawbot-ui-deployment-complete.mdc`.

**Operator verification habit:** After `git pull` on the lab host, **hard refresh** the browser; API serves HTML with `no_cache` for dashboard routes in `api_server.py`, but intermediaries and mental models still confuse **image** vs **mount**.

---

## 5. `UIUX.Web/dashboard.html` — chronology of changes (this engineering arc)

The following is a **sequential narrative** of dashboard work discussed and implemented across iterations (merge with `git log UIUX.Web/dashboard.html` for exact ordering).

### 5.1 Trade chain / baseline / “no trade”

- **Problem:** “No trade” in baseline cells appeared **green** or green-adjacent.
- **Root causes addressed in code:**
  - Baseline **column background** used a **mint** gradient in `tcColumnBgOnly`, washing the whole cell green even when the label was neutral.
  - Baseline **verdict** strip used **teal** (`#0f766e`), which reads as green-ish beside neutral copy.
- **Mitigations:**
  - Baseline column tint moved to **slate** (`rgba(226,232,240,…)`), not mint.
  - Baseline verdict strip recolored to **slate navy** (`#1e293b`) with a slate border tone.
  - Baseline **chip** and **Jupiter narrative** block got explicit **baseline lane** styling (`tc-tile-narr-baseline`, chip border) for “color coded baseline” without implying pass/fail green.

### 5.2 Bottom-of-page “little windows” / accordions

- **User intent:** Remove redundant **collapsible stacks** at the foot of the main column; move navigation destinations to the **left nav** where appropriate; avoid duplicate link rows.
- **Evolution:**
  - Operational boundary content was moved between **Operator panel** and **bottom** sections multiple times; user feedback rejected **accordion affordance** that resembled the old bottom stack.
  - **Static panels** (`dash-panel`) were tried; user still perceived **boxed regions** at the bottom as failures.
  - **Final direction (as of later commits):** **Run configuration** and **Operational boundary** moved into **`<dialog>`** modals opened by **Paths…** / **Ops boundary** (and additional **nav-adjacent controls** in `HEAD` — see `navDashPaths` / `navDashOb` in current file).

### 5.3 Left navigation

- Nav expanded to include routes that were previously only inline links: **QEL evaluation**, **Event view**, **Anna hub**, **System guide** (alongside Dashboard, Operator Panel, Learning Engine, Training Dashboard, Intelligence METHOD).
- Latest `HEAD` adds **Run configuration** and **Operational boundary** as **button** controls styled like nav links — validate in `dashboard.html` around `.dash-nav-linklike`.

### 5.4 Anna intelligence strip

- Remains a **`<details>`** block (distinct styling: `dash-intel-details`) — **not** the same component as removed `dash-below` stacks; operators may still collapse/expand it.

---

## 6. Browser verification (what was actually done in automation)

- A **local static** server (`python3 -m http.server` in `UIUX.Web`) was used to load `dashboard.html` in the IDE browser MCP.
- **Limitation:** Static serving returns **404** for `/api/v1/dashboard/bundle` — the UI shows **FETCH ERR**, placeholder dashes, and JSON parse errors; this is **expected** without the API stack.
- **What static verification is good for:** Layout, presence of **Paths…** / **Ops boundary**, **Trade chain** region, **no boxed panels after trade chain** in the main column, nav structure.
- **What requires full stack:** Liveness tier, bundle-driven fields, trade table population, operational boundary text from `renderOB`.

---

## 7. Git references (dashboard-related, recent)

Recent `git log` entries observed during turnover authoring (newest first):

- `3280424` — Dashboard: add Run configuration and Operational boundary to left nav  
- `f18c4e3` — Dashboard: fix baseline green wash; baseline tile styling; paths/OB in dialogs  
- `66dec8d` — Dashboard: replace dash-below accordions with static panels  
- `be5e3cc` — Dashboard: nav adds QEL/event/hub/guide; remove redundant bottom link stack  
- `2d6c42b` — Dashboard: move operational boundary into operator links panel  
- (Earlier) `8200ba1` — baseline “no trade” teal override removed; `edc8016` — baseline narrative rendering (per prior session notes)

Use `git log -- UIUX.Web/dashboard.html` for the authoritative line-by-line history.

---

## 8. Key source files (dashboard thread)

| Path | Role |
|------|------|
| `UIUX.Web/dashboard.html` | Operator dashboard markup, CSS, client JS (`render`, `renderTC`, `renderOB`, `cellMini`, `tcColumnBgOnly`, dialogs). |
| `UIUX.Web/api_server.py` | Serves `/dashboard.html` from repo-rooted path; sets `no_cache` for HTML. |
| `UIUX.Web/nginx/default.conf` | Proxies dashboard routes to API; documents mount vs image. |
| `UIUX.Web/jupiter_tile_rule_colors_mockup.html` | **Mockup only** — intent for rule-line coloring (OK / stop / gate / neutral); not wired to live API. |

---

## 9. Failure modes and how to avoid them

| Symptom | Likely cause | Check |
|---------|----------------|-------|
| Old bottom accordions | Browser cache **or** server not on latest commit | `git pull` on host; hard refresh; `curl` live URL and grep for `dash-below` / `dialog id=`. |
| “No trade” still looks green | Mint column wash **or** stale CSS | Confirm `tcColumnBgOnly` uses slate for baseline; confirm no `.tc-tr-baseline .tc-no-trade { teal }` override. |
| Dashboard HTML grep in **web** container shows X, operator sees Y | `/dashboard.html` is **not** from **web** image for proxied route | Grep **`api`** container `/repo/UIUX.Web/dashboard.html` or curl HTTPS endpoint. |
| JSON error / FETCH ERR on static file open | No API | Run full stack or accept static layout-only proof. |

---

## 10. Follow-ups (explicit non-contract list)

- **Full-stack browser proof** on `clawbot` (or equivalent): bundle fetch OK, trade chain populated, baseline cells match intended colors under real data.
- **Anna intelligence `<details>`:** Product decision whether to flatten or move to dialog like paths/OB.
- **Liveness strip** showing green pulse under FETCH ERR on static preview — separate UX question (error vs live styling).
- **Page size widget** (`text-scale.js`) — third-party control chrome; not removed in dashboard thread.

---

## 11. Handoff checklist for the next engineer

1. Read `docs/working/current_directive.md` and Foreman bridge state — **do not** use this log as authorization to start work.  
2. `git fetch && git pull` on the host you will verify.  
3. For dashboard changes: confirm **`HEAD`**, then verify **live URL** (not only local file).  
4. If changing `api_server.py` or Python bundle builders: **restart `api`** after deploy per project rules.  
5. Update **`docs/working/shared_coordination_log.md`** or **`developer_handoff.md`** only when the triad expects those files to move — this session log is **additive**.

---

*End of turnover log. Filename timestamp is UTC at document creation; adjust if re-exporting from another timezone.*
