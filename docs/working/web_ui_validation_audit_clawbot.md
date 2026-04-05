# Web UI validation audit — primary host (clawbot)

**Purpose:** System-truth inventory for operator and Engineering Architect.  
**Host:** `https://clawbot.a51.corp`  
**Generated:** automated HTTP layer from `scripts/ui/verify_clawbot_ui_http.sh` + code-derived expectations.  
**Restriction:** Interactive behavior (every click, indicator truth vs runtime) is **not** fully proven by automation alone; manual rows are marked **not tested (manual)** unless noted.

---

## 1. Automated proof — page load + GET API (clawbot)

**Command (re-run on clawbot):**

```bash
cd ~/blackbox && BASE_URL=https://clawbot.a51.corp CURL_INSECURE=-k bash scripts/ui/verify_clawbot_ui_http.sh
```

**Last run result (embedded):** all listed paths returned **HTTP 200** (see script output when run).  
**Interpretation:** Nginx → static or API wiring responds; **not** proof that buttons mutate correct state or indicators match live processes.

---

## 2. `/dashboard.html` — interactive inventory

| Element | Location | Expected | Actual (audit) | Status |
|--------|----------|------------|----------------|--------|
| Nav: Dashboard | left nav | Stay / load dashboard | Route 200 | **working** (load) |
| Nav: Operator Panel | left nav | `GET /internal.html` | 200 | **working** (load) |
| Nav: Learning Engine | left nav | `GET /anna/sequential-learning` | 200 | **working** (load) |
| Nav: Training Dashboard | left nav | `GET /anna/training` | 200 | **working** (load) |
| Banner strip | row 1 | Reflects `GET /api/v1/dashboard/bundle` (`banner`, `wallet`) | Polls every 15s | **working** (if API truth matches runtime — **indicator truth not independently proven**) |
| Start | row 2 | `POST /api/v1/sequential-learning/control/start` with body from Run configuration | **not tested (manual)** | **unverified** |
| Resume | row 2 | same | **not tested (manual)** | **unverified** |
| Pause / Stop / Reset | row 2 | `POST …/pause|stop|reset` | **not tested (manual)** | **unverified** |
| Tick | row 2 | Shown only when `tick_required`; `POST …/tick` | **not tested (manual)** | **unverified** |
| Run configuration fields | collapsible | localStorage + POST body | **not tested (manual)** | **unverified** |
| Operator panel links | collapsible | Same-origin navigation | 200 on targets | **working** (load) |
| Learning / Training / Boundary / Raw JSON | collapsible | Display / JSON | Raw uses bundle | **partial** (raw = API truth at fetch time) |
| Trade chain table | row 4 | Data from `trade_chain` in bundle | Renders from ledger | **working** (if ledger correct — **data truth not independently proven**) |

**Misleading-risk callouts:**

- Indicators (state, mode, wallet) **follow the bundle API**, not direct process inspection. If API or env is wrong, UI shows wrong.
- **Tick** hidden when not `tick_required` — by design; operator must know why it disappears (queue empty / not running).

---

## 3. Other major surfaces (load-only verification)

| Surface | Path | HTTP (clawbot) | Interactive audit |
|---------|------|----------------|-------------------|
| Landing | `/`, `/index.html` | 200 | **not tested (manual)** |
| Login | `/login.html` | 200 | **not tested (manual)** — dev bootstrap / future engine auth |
| Internal portal | `/internal.html` | 200 | **not tested (manual)** — many pills/modals |
| Anna hub | `/anna.html` | 200 | **not tested (manual)** |
| Sequential learning | `/anna/sequential-learning` | 200 | **not tested (manual)** |
| Training JSON page | `/anna/training` | 200 | **not tested (manual)** |
| Event / operator chart | `/anna/event-view`, `/anna/event-dashboard` | 200 | **not tested (manual)** |
| QEL | `/anna/evaluation` | 200 | **not tested (manual)** |
| Docs / guide / consumer | various | 200 | **not tested (manual)** |

---

## 4. GET `/api/v1/*` (clawbot automated)

All endpoints enumerated in `scripts/ui/verify_clawbot_ui_http.sh` returned **200** on last run. Individual JSON correctness vs production DB/runtime is **not** proven here.

**Note:** `evaluation-summary?strategy_id=test` returned 200; response body may be an error object — **inspect JSON** before trusting.

---

## 5. Acceptance vs directive §6–7

| Directive requirement | Met? |
|----------------------|------|
| Every **link** load-tested on clawbot for enumerated routes | **Yes** (automated) |
| Every **button** clicked and outcome observed | **No** — **not met** without manual pass |
| Every **indicator** validated against ground truth | **No** — API-backed only |
| Screenshots of each major surface | **Not attached** — operator must capture |
| One report with item / location / expected / actual / status | **This document** — interactive rows **actual = not tested (manual)** where applicable |

**Verdict:** **REJECTED** for full acceptance per strict §7 (“any visible UI element untested → rejected”) for **interactive** elements. **PASS** for **enumerated HTTP reachability** on clawbot at time of script run.

---

## 6. Operator next steps (to close the directive)

1. Re-run `scripts/ui/verify_clawbot_ui_http.sh` after each deploy.
2. Manual session: for each button on dashboard and sequential page, record HTTP response / UI change (screenshot optional).
3. Compare indicator fields to `curl -sS https://clawbot.a51.corp/api/v1/dashboard/bundle` and to sequential control file / ledger on host.
4. Attach screenshots to this doc or a ticket archive.

---

## 7. Proof artifact reference

- Script: `scripts/ui/verify_clawbot_ui_http.sh`
- Commit: includes `5906386` (script add); re-run after pull on clawbot.
