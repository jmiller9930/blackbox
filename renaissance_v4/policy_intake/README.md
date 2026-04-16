# Kitchen policy intake (DV-ARCH-KITCHEN-POLICY-INTAKE-048)

## Operator API

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/v1/renaissance/policy-intake` | `multipart/form-data` field **`policy_file`** (max 8 MiB) |
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

## YAML / JSON

Specs parse and normalize to **PolicySpecV1**. Deterministic signal/trade/PnL proof **requires** a TypeScript evaluator; YAML/JSON-only uploads stop after static checks with an explicit message.

## Storage layout

`renaissance_v4/state/policy_intake_submissions/<submission_id>/`

- `raw/original_<filename>` — immutable upload
- `canonical/policy_spec_v1.json` — normalized
- `report/intake_report.json` — full staged report

## STATUS

**Partial / incremental:** Structural validation uses `tsc` and `npx` (`typescript`, `esbuild`) on the API host. Primary-host proof (operator upload end-to-end) is required for directive closure.
