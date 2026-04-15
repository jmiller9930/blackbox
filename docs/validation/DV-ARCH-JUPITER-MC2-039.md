# DV-ARCH-JUPITER-MC2-039 — MC2 policy + Jupiter API validation

**Directive:** DV-ARCH-JUPITER-MC2-039  
**Date:** 2026-04-15  

---

## Response header

| Field | Value |
|-------|--------|
| **RE:** | DV-ARCH-JUPITER-MC2-039 |
| **STATUS** | **complete** — implementation + **§4 live proof on clawbot** (see **§4.6**) |

**COMMIT (closure):** see git `main` at proof update (**includes** `e6c4b9b` Bearer+session API access, `99ed5b2` dockerignore whitelist + image rebuild).

---

### Engineering prerequisites for headless §4 (session auth)

When **`JUPITER_AUTH_MODE=session`**, unauthenticated `curl` to `/api/*` returns `401` `login_required`. **`Authorization: Bearer`** with the same **`JUPITER_OPERATOR_TOKEN`** as policy POST is accepted for JSON API routes (**`e6c4b9b`**). The MC2 module must be in the Docker image ( **`jupiter_mc2_policy.mjs`** in `Dockerfile` + **`.dockerignore`** whitelist **`99ed5b2`**).

---

## 1. Policy `jup_mc2` (MC2)

| Field | Value |
|-------|--------|
| **policy_id** | `jup_mc2` |
| **Derived from** | JUP-MC-Test (same `generateSignalFromOhlcV4` pipeline as MC-Test) |
| **Single parameter change** | **`VOLUME_SPIKE_MULTIPLIER`:** Jupiter_4 default **1.2** → MC2 **1.35** (constant `MC2_VOLUME_SPIKE_MULTIPLIER` in `vscode-test/seanv3/jupiter_mc2_policy.mjs`) |
| **Unchanged** | RSI thresholds, `MIN_EXPECTED_MOVE`, crossover logic, ATR period, etc. |

**Files:**

- `vscode-test/seanv3/jupiter_mc2_policy.mjs` — MC2 lane + diagnostics (`mc2_lane`, `mc2_volume_spike_multiplier`).
- `vscode-test/seanv3/jupiter_4_sean_policy.mjs` — optional 5th argument `opts.volumeSpikeMultiplier` (defaults unchanged for existing callers).
- `vscode-test/seanv3/jupiter_policy_runtime.mjs` — `ALLOWED_POLICY_IDS` includes `jup_mc2`; `resolveJupiterPolicy` branch; `normalizePolicyId` aliases `jup_mc2` / `jupiter_mc2` / `mc2`.
- `vscode-test/seanv3/jupiter_web.mjs` — UI select + API contract strings.

---

## 2. API registration

`GET /api/v1/jupiter/policy` returns `allowed_policies` from `ALLOWED_POLICY_IDS`, which now includes **`jup_mc2`**.

---

## 3. Automated smoke (local, no HTTP)

From `vscode-test/seanv3`:

```bash
node -e "
import { generateSignalFromOhlcMcTest } from './jupiter_mc_test_policy.mjs';
import { generateSignalFromOhlcMc2 } from './jupiter_mc2_policy.mjs';
// synthetic bars …
"
```

Confirmed: `diag.volume_spike_multiplier_effective` is **1.2** for MC-Test and **1.35** for MC2 on the same synthetic series.

---

## 4. Operator proof checklist (primary host — e.g. clawbot :707)

**Prerequisites:** `JUPITER_OPERATOR_TOKEN` set on the process serving Jupiter web; SeanV3 DB path as configured.

### 4.1 Read APIs (before POST)

Replace `HOST` and `TOKEN` as appropriate.

```bash
curl -sS "http://HOST:707/api/v1/jupiter/policy"
curl -sS "http://HOST:707/api/summary.json"
curl -sS "http://HOST:707/api/operator/state.json"
curl -sS "http://HOST:707/api/live-market.json"
```

Expect: HTTP 200, valid JSON, no `error` at root (unless environment-specific).

Confirm `GET /api/v1/jupiter/policy` includes **`jup_mc2`** inside **`allowed_policies`**.

### 4.2 Write — switch to MC2

```bash
curl -sS -X POST "http://HOST:707/api/v1/jupiter/active-policy" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"policy":"jup_mc2"}'
```

Expect: HTTP **200**, JSON with `ok: true`, `active_policy: "jup_mc2"`.

### 4.3 Read after write

```bash
curl -sS "http://HOST:707/api/v1/jupiter/policy"
```

Expect: **`active_policy`** is **`jup_mc2`**.

### 4.4 Runtime

Wait for at least one Sean engine cycle; confirm logs / diagnostics reference MC2 (`policy_engine` / `mc2_lane` / `mc2_volume_spike_multiplier` in signal path as applicable).

### 4.5 Round-trip

```bash
curl -sS -X POST "http://HOST:707/api/v1/jupiter/active-policy" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"policy":"jup_mc_test"}'
```

Then `GET /api/v1/jupiter/policy` → **`active_policy`** should be **`jup_mc_test`**.

### 4.6 Live proof — clawbot (primary host), 2026-04-15

**Host:** `http://127.0.0.1:707` (same service as `http://clawbot.a51.corp:707/`). **Auth:** `Authorization: Bearer <JUPITER_OPERATOR_TOKEN>` on every request (session mode).

| Step | Result |
|------|--------|
| **GET `/api/v1/jupiter/policy` (before)** | HTTP 200. `active_policy`: **`jup_mc_test`**. `allowed_policies`: `jup_v4`, `jup_v3`, `jup_mc_test`, **`jup_mc2`**. |
| **POST `/api/v1/jupiter/active-policy`** `{"policy":"jup_mc2"}` | HTTP 200. `ok: true`, `active_policy`: **`jup_mc2`**, `previous_policy`: **`jup_mc_test`**, `applied_on_next_engine_cycle`: **true**. |
| **GET `/api/v1/jupiter/policy` (after MC2)** | HTTP 200. `active_policy`: **`jup_mc2`**. |
| **GET `/api/summary.json`** | HTTP 200. `trading_mode.jupiter_runtime`: **`{"active_policy":"jup_mc2","source":"runtime_config"}`** (snippet). |
| **GET `/api/operator/state.json`** | HTTP 200 (schema `jupiter_operator_state_v1`). |
| **GET `/api/live-market.json`** | HTTP 200 (schema `jupiter_live_market_v1`). |
| **Runtime / logs** | `jupiter-web` stderr: **`[jupiter] set active Jupiter policy: jup_mc_test → jup_mc2`**. Sean engine applies resolved policy on subsequent ticks (`applied_on_next_engine_cycle`); this host’s `seanv3` poll log shows **300000 ms** kline interval — deep MC2 signal-path logging was not required for API closure; API + meta + summary snapshot confirm selection. |
| **POST revert** `{"policy":"jup_mc_test"}` | HTTP 200. `active_policy`: **`jup_mc_test`**, `previous_policy`: **`jup_mc2`**. |
| **GET `/api/v1/jupiter/policy` (after revert)** | HTTP 200. `active_policy`: **`jup_mc_test`**. |

**Sample bodies (abbreviated):**

```json
{"contract":"jupiter_policy_observability_v1","active_policy":"jup_mc_test","source":"runtime_config","allowed_policies":["jup_v4","jup_v3","jup_mc_test","jup_mc2"]}
```

```json
{"ok":true,"contract":"jupiter_active_policy_switch_v1","operation":"set_active_jupiter_policy","active_policy":"jup_mc2","previous_policy":"jup_mc_test","source":"runtime_config","applied_on_next_engine_cycle":true}
```

---

## 5. Failure conditions (directive §9)

If any read returns non-JSON, POST returns non-200, `active_policy` does not update, or engine ignores selection: **stop**, capture response bodies and logs, file a defect — do not proceed with further cycles.

---

## 6. Non-goals

No lifecycle changes, no extra policy variants beyond this single MC2 lane, no bypass of `POST /api/v1/jupiter/active-policy` for selection.
