# Kitchen policy intake (DV-ARCH-KITCHEN-POLICY-INTAKE-048)

## Operator API

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/v1/renaissance/policy-intake` | `multipart/form-data`: **`policy_file`** (max 8 MiB) and **`execution_target`** (`jupiter` or `blackbox`; default `jupiter` if omitted). Evaluation and baseline scope use this target only (DV-055). |
| `GET` | `/api/v1/renaissance/policy-intake/<submission_id>` | Read persisted `intake_report.json` |
| `POST` | `/api/v1/renaissance/policy-intake/<submission_id>/archive` | JSON body `{"is_active": false}` soft-archives; `{"is_active": true}` restores. (DV-066) |
| `GET` | `/api/v1/renaissance/intake-candidates` | Query: `execution_target`, `include_archived` (0/1), `collapse_duplicates` (default 1: one row per `candidate_policy_id`, newest first). (DV-061 / DV-066) |
| `POST` | `/api/v1/renaissance/kitchen-runtime-assignment` | Body `{"submission_id":"...","execution_target":"jupiter"|"blackbox"}`. Governed mechanical candidate only; approved ids come from `renaissance_v4/config/kitchen_policy_registry_v1.json`. **DV-074:** Jupiter persists only after SeanV3 POST **and** GET verify; no fake success without runtime. GET includes `runtime` + `drift`. BlackBox assign fails until runtime API is wired. |
| `GET` | `/api/v1/renaissance/kitchen-runtime-assignment` | Query `execution_target` for one row, or omit for full store. |
| `POST` | `/api/v1/renaissance/kitchen-assign-jupiter` | **Deprecated alias** — same as runtime-assignment with `execution_target: jupiter`. |
| `GET` | `/api/v1/renaissance/kitchen-jupiter-assignment` | **Deprecated** — use `kitchen-runtime-assignment?execution_target=jupiter`. |

## UI

**Quant Research Kitchen** (`/dashboard.html#/renaissance`) — **Submit Policy for Evaluation** card: file picker + staged status.

## TypeScript contract (executable path)

Uploaded `.ts` files must **bundle** with `esbuild` (no missing modules). Export:

```ts
export function generateSignalFromOhlc(
  closes: number[],
  highs: number[],
  lows: number[],
  volumes: number[],
  ctx?: { schemaVersion?: string; indicators?: Record<string, number | object | null> },
): { longSignal: boolean; shortSignal: boolean; signalPrice: number; diag?: object };
```

Optional: `export const MIN_BARS: number`.

**Canonical indicators (DV-064):** optional embed for the same `indicators` object as `policy_spec_v1.json`:

```ts
/* RV4_POLICY_INDICATORS
{"schema_version":"policy_indicators_v1","declarations":[{"id":"rsi_main","kind":"rsi","params":{"period":14}}],"gates":[]}
*/
```

Declaring a **non–mechanically-supported** kind fails intake with `indicator_declared_but_not_mechanically_supported: <kind>` (see `indicator_mechanics.py`).

Sean-style multi-file policies that import local modules may fail bundling until those paths exist in-repo; self-contained uploads are the reliable v1 path.

## Deterministic harness (DV-056)

The intake eval harness (`policy_intake/run_ts_intake_eval.mjs`) generates synthetic bars with **strictly increasing integer closes** so policies that compare consecutive closes see stable strict inequality on every host (Linux/macOS, Docker, etc.). A prior sin-based series could produce consecutive closes equal within floating-point noise on some platforms, yielding **no signals** and a misleading live FAIL while local runs passed.

Successful harness JSON includes **`harness_revision`** (e.g. `int_ohlc_v4`), **`signal_contract`** (DV-065), and **`indicator_evaluation_context`** (DV-064). Stage 1 **`content_sha256`** matches **`signal_contract.content_sha256`** on the same TS bytes.

### Signal contract (DV-065)

The harness invokes **`generateSignalFromOhlc`** (or **`default`**) with **`(closes, highs, lows, volumes)`** and optionally a **5th `ctx`** when the policy function accepts ≥5 parameters.

**Counting signals** uses **`normalizeIntakeSignalOutput`** in **`intake_signal_normalize.mjs`**, which maps:

- **Primary:** `longSignal`, `shortSignal` (booleans)
- **Aliases:** `long`, `short` booleans
- **Nested:** `signal.longSignal` / `signal.short` / `signal.direction` / `signal.side`
- **Top-level:** `direction` / `side` (string or number)

**Browser upload** and **`POST /api/v1/renaissance/policy-intake`** both call **`run_intake_pipeline`** with the same bytes — identical harness output for the same file.

Persisted proof: **`stages.stage_5_deterministic.signal_contract`** in **`report/intake_report.json`** (`first_five_bar_returns`, `last_five_bar_returns`, `viability_inputs`, `content_sha256`).

**Optional deep debug (DV-060):** set environment variable **`RV4_INTAKE_HARNESS_DEBUG=1`** on the API process; the harness adds an **`intake_debug`** object (file SHA-256, first/last closes, sample policy output). The Python runner also scans stdout for the last valid JSON object with an `ok` key so stray Node warnings on stdout cannot corrupt parsing.

## YAML / JSON

Specs parse and normalize to **PolicySpecV1**. Deterministic signal/trade/PnL proof **requires** a TypeScript evaluator; YAML/JSON-only uploads stop after static checks with an explicit message.

## Storage layout

`renaissance_v4/state/policy_intake_submissions/<submission_id>/`

- `raw/original_<filename>` — immutable upload
- `canonical/policy_spec_v1.json` — normalized
- `report/intake_report.json` — full staged report

## API container runtime (required)

Policy intake calls **`npx`** (esbuild) and **`node`** (deterministic harness). The **`api`** Docker image is built from **`UIUX.Web/Dockerfile.api`**, which extends `python:3.11-alpine` and installs **`nodejs`** + **`npm`** (provides **`npx`**). This is an explicit image dependency — not an undocumented host-only tool.

After changing the API image definition, rebuild and restart (example):

`cd UIUX.Web && docker compose build api && docker compose up -d api`

Verify inside the running container: `node -v` and `npx -v`.

## STATUS

Structural validation uses `npx` (`esbuild`) and `node` on the API host as above. Primary-host proof (operator upload end-to-end) is required for directive closure.
