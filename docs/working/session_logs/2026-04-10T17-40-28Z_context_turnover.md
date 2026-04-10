# Context turnover log — BLACK BOX (engineering session archive)

| Field | Value |
|--------|--------|
| **UTC timestamp (filename)** | `2026-04-10T17-40-28Z` |
| **Amended (detail pass)** | Same calendar day — added **§12–17** (Jupiter policy semantics, data path, open questions). **Code-checked** against `modules/anna_training/dashboard_bundle.py` and related modules; **not** a substitute for live ops verification on `clawbot`. |
| **Repository** | `blackbox` (local path: workspace root) |
| **Git `HEAD` at original author time** | `3280424d1e5cdc747ca5a1a9a364b2d02de36550` (see `git log` for later commits) |
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
- **Runtime / product gaps** — see **§16** (ops topology, “live” semantics, tile schema).

---

## 11. Handoff checklist for the next engineer

1. Read `docs/working/current_directive.md` and Foreman bridge state — **do not** use this log as authorization to start work.  
2. `git fetch && git pull` on the host you will verify.  
3. For dashboard changes: confirm **`HEAD`**, then verify **live URL** (not only local file).  
4. If changing `api_server.py` or Python bundle builders: **restart `api`** after deploy per project rules.  
5. Update **`docs/working/shared_coordination_log.md`** or **`developer_handoff.md`** only when the triad expects those files to move — this session log is **additive**.

---

## 12. Jupiter “policy” vs Sean’s rules vs venue execution (terminology)

This section answers: *what does “Jupiter policy” mean in the UI bundle, and how is it different from “trading policy” and Jack?*

### 12.1 Trade policy (venue / registry posture)

- In repo language, **where settlement would bind** for the active posture is **Jupiter Perps** → executor hook **Jack** (see `AGENTS.md`, `docs/architect/ANNA_GOES_TO_SCHOOL.md`, `trading_core/README.md` and adapter/registry text).
- **Drift / Billy** is **deprecated**, not a live second path — do not treat it as parallel venue policy without an explicit, current directive.

### 12.2 Sean’s rules (mechanics — bar-derived evaluator)

- The **Jupiter_2** engine lives in **`modules/anna_training/jupiter_2_sean_policy.py`**: **SOL perp, 5m** bars, Supertrend (10, 3), EMA200, RSI 14, simple TR ATR, **ATR ratio vs a long lookback with a minimum (e.g. 1.35) to allow entries**, etc.
- Purpose: **paper / monitoring parity** with the TypeScript policy snapshot semantics — **no venue execution inside that Python module**.

### 12.3 What “Jupiter policy” means in the **dashboard bundle**

- **`jupiter_policy_snapshot`** (built by `build_jupiter_policy_snapshot()` in `modules/anna_training/dashboard_bundle.py`) is **this bar-derived evaluator**, wired through **`evaluate_sean_jupiter_baseline_v1`** → **`evaluate_jupiter_2_sean`** — **not** a separate mysterious layer and **not** Jack placing orders.
- The module docstring states explicitly: *“Jupiter policy snapshot: `evaluate_sean_jupiter_baseline_v1` → `evaluate_jupiter_2_sean` (bar-derived; paper).”*
- **Venue execution (Jack)** is a **different concern** and is **out of scope** for that evaluator; Phase 1 / registry text keeps execution **separate and gated**.

---

## 13. How we know “trade” vs “no trade” (backend computation)

Two different surfaces must not be conflated:

### 13.1 Jupiter policy snapshot (latest closed bars → `would_trade`)

`build_jupiter_policy_snapshot()` (same file) does roughly:

1. Resolve **market SQLite** path (`BLACKBOX_MARKET_DATA_PATH` / default via `_market_db_path()`).
2. If DB missing → **`error: market_db_missing`** (no fake signal).
3. Import **`fetch_recent_bars_asc`** (from `market_data.bar_lookup` after `_ensure_runtime_for_market_imports()`), read recent **closed** rows into **`market_bars_5m`**-backed structures.
4. If fewer than **`MIN_BARS`** → **`error: insufficient_history`** with hint text (no fake signal).
5. Run **`evaluate_sean_jupiter_baseline_v1(bars_asc=bars)`**, which uses **`jupiter_2_sean_policy`** internally.
6. Expose **`would_trade`**, **`side`**, **`reason_code`**, **`features`**, **`operator_tile_narrative`** (via **`format_jupiter_tile_narrative_v1`**, same family as tile formatting elsewhere).

So **“can we trade in the paper baseline sense on the latest bar history?”** = that evaluator on **canonical 5m bars**. If the DB or history is inadequate, you get **structured errors**, not invented trades.

### 13.2 Trade chain baseline row (ledger / display authority)

The **`dashboard_bundle.py` module docstring** (top of file) defines **baseline WIN/LOSS** binding:

- Tied to **`policy_evaluations`** (historic env label **`signal_mode=sean_jupiter_v1`** — compatibility name; **engine** is **Jupiter_2**) **plus** a matching execution row when **`trade=1`**.
- **`trade=0`** still means **NO TRADE** for **display authority** even if other artifacts exist — **non-authoritative** rows are not shown as outcomes.

So **ledger/trade-chain semantics** are **separate** from **Jupiter tile narrative alone**; the UI must not treat **`operator_tile_narrative`** as the sole authority for the chain row outcome.

---

## 14. “Live” data — how information reaches the backend and the browser

### 14.1 Canonical inputs for the policy view (not a raw tick tape in the bundle)

- **Canonical state** for the policy snapshot is **closed bars in SQLite** (`market_bars_5m`), not a browser WebSocket of every tick.
- Population path includes runtime upsert logic (e.g. `scripts/runtime/market_data/store.py` **`upsert_market_bar_5m`**), schema in **`data/sqlite/schema_phase5_canonical_bars.sql`**; bars carry **`price_source`** (e.g. Pyth-related naming where applicable).

### 14.2 Pyth “liveness” as probe artifact

- **`dashboard_bundle.py`** defines **`_pyth_probe_snapshot(repo)`**, reading **`docs/working/artifacts/pyth_stream_status.json`** under the repo root — a **filesystem artifact** produced by whatever stream/probe process operators run.
- **Code paths exist** in repo; **exact production wiring** (systemd units, compose service names, cron) is **not** proven by reading Python alone — needs **ops map** or live host inspection.

### 14.3 Sequential learning staleness

- The bundle includes **backend-computed** sequential / queue / tick signals (e.g. **`_sequential_tick_staleness`**, surfaced under **`liveness` / `operator_signals`** in the payload). These are **server-derived**, not inferred in static HTML.

### 14.4 UI transport

- **`dashboard.html`** uses **`fetch('/api/v1/dashboard/bundle?...')`** on a **poll interval** — **REST JSON snapshots**, not a WebSocket firehose for the full bundle.
- **“Live” in the UI** means **fresh polls + backend freshness fields** (and whatever the operator defines as acceptable staleness), **not** necessarily a literal browser SSE for every underlying tick.

---

## 15. Web UI scope — disciplined boundaries

- Treat **`jupiter_policy_snapshot`** and **`trade_chain`** as **whatever `build_dashboard_bundle` returns** — do not invent fields in the HTML layer.
- **`UIUX.Web/jupiter_tile_rule_colors_mockup.html`** states the **intent** (green/red per rule line); **production** still uses largely **one formatted narrative blob** plus **`features`** — **per-line classification** (`ok` / `stop` / `gate` / `neutral`) would require **structured fields** or an **agreed parser** on `operator_tile_narrative` (mockup file acknowledges this).
- **Do not** conflate **paper `would_trade`** on **DB bars** with **Jack placing live orders**; registry and governance text keep execution **separate, gated**.

---

## 16. Not runtime-certain without ops / product decisions (explicit gaps)

| # | Topic | Repo has | Still need for **runtime certainty** |
|---|--------|-----------|--------------------------------------|
| 1 | **Pyth + bar writers on clawbot** | Writers/upsert paths, `_pyth_probe_snapshot` reader | Which **processes/services** keep **`pyth_stream_status.json`** and **bar closure** current (daemon names, systemd, compose) — **ops map** or live inspection. |
| 2 | **“Live” UI semantics** | Age fields, poll-based UI | Product choice: show **“live”** only when Pyth age &lt; *N* s, vs always surfacing **last closed bar** time regardless — **not** fully specified in code alone. |
| 3 | **Per-line tile coloring API** | `features`, `operator_tile_narrative` | Optional **schema extension** to emit **`ok` / `stop` / `gate` / `neutral`** per narrative line — today coloring in UI beyond basic styling may need **bundle contract** change. |

If the triad fixes **(2)** and **(3)**, web work can align **without** guessing execution or trading policy beyond the bundle.

---

## 17. Alignment summary (reader checklist)

**Yes — after reading the repo, these statements are aligned:**

- **Jupiter Perps** is the **active trade policy (venue posture)** → executor hook **Jack** in registry language; **Drift/Billy** deprecated as a live path.
- **Sean / Jupiter_2** rules are the **bar-derived paper evaluator** in Python — **not** venue execution in that module.
- **Trade vs no trade** in the **policy snapshot** flows from **`would_trade` / `reason_code` / `features`** via **`evaluate_sean_jupiter_baseline_v1`** on **`market_bars_5m`** history; missing DB/history → **errors**, not fake signals.
- **Trade chain** baseline display authority follows **ledger + policy_evaluations + `trade` flag** semantics documented in **`dashboard_bundle.py`** — **`trade=0`** → **NO TRADE** for display even if other rows exist.
- **Data** = **ingested/stored closed bars + status artifacts + bundle-computed liveness**; **dashboard** = **polling `/api/v1/dashboard/bundle`**.

**Intentionally light until ops confirms:** exact **live topology** for Pyth stream and bar writers on the lab host.

---

*End of turnover log. Original filename timestamp is UTC at first document creation; §12–17 amended same calendar day. Adjust if re-exporting from another timezone.*
