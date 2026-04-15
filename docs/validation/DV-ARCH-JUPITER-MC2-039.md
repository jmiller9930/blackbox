# DV-ARCH-JUPITER-MC2-039 — MC2 policy + Jupiter API validation

**Directive:** DV-ARCH-JUPITER-MC2-039  
**Date:** 2026-04-15  

---

## Response header

| Field | Value |
|-------|--------|
| **RE:** | DV-ARCH-JUPITER-MC2-039 |
| **STATUS (code + registration)** | **complete** — `jup_mc2` implemented and listed in `GET /api/v1/jupiter/policy` → `allowed_policies` |
| **STATUS (live operator proof on host)** | **pending** — run **§4** on clawbot after deploy (Bearer token, engine cycle) |

**COMMIT:** `26ef379` (MC2 implementation + proof doc; re-verify after `git pull` on primary host).

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

---

## 5. Failure conditions (directive §9)

If any read returns non-JSON, POST returns non-200, `active_policy` does not update, or engine ignores selection: **stop**, capture response bodies and logs, file a defect — do not proceed with further cycles.

---

## 6. Non-goals

No lifecycle changes, no extra policy variants beyond this single MC2 lane, no bypass of `POST /api/v1/jupiter/active-policy` for selection.
