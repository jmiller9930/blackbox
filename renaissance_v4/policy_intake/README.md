# Kitchen policy intake (DV-ARCH-KITCHEN-POLICY-INTAKE-048)

## Operator API

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/v1/renaissance/policy-intake` | `multipart/form-data`: **`policy_file`** (max 8 MiB) and **`execution_target`** (`jupiter` or `blackbox`; default `jupiter` if omitted). Evaluation and baseline scope use this target only (DV-055). |
| `GET` | `/api/v1/renaissance/policy-intake/<submission_id>` | Read persisted `intake_report.json` |

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
): { longSignal: boolean; shortSignal: boolean; signalPrice: number; diag?: object };
```

Optional: `export const MIN_BARS: number`.

Sean-style multi-file policies that import local modules may fail bundling until those paths exist in-repo; self-contained uploads are the reliable v1 path.

## Deterministic harness (DV-056)

The intake eval harness (`policy_intake/run_ts_intake_eval.mjs`) generates synthetic bars with **strictly increasing integer closes** so policies that compare consecutive closes see stable strict inequality on every host (Linux/macOS, Docker, etc.). A prior sin-based series could produce consecutive closes equal within floating-point noise on some platforms, yielding **no signals** and a misleading live FAIL while local runs passed.

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
