# Quant Research Kitchen V1 — workbench product spec (v1)

This document is the **version 1** product spec for **Quant Research Kitchen V1**: the governed, web-facing strategy research and validation surface built on the Renaissance validation backend. It also serves as a short **SME usage** guide and lists **what remains manual** in v1.

**Architecture thesis (permanent layer):** [`docs/architect/quant_research_kitchen_v1.md`](../docs/architect/quant_research_kitchen_v1.md).

## Product identity

- **What it is:** A workbench for reviewing the **locked baseline**, **Monte Carlo** reference, **approved experiments**, and **exports** — without mutating baseline code from the browser.
- **What it is not:** A strategy builder, promotion console, or live trading UI.

The first validated recipe remains **`RenaissanceV4_baseline_v1`**. The harness (`robustness_runner`, replay, Monte Carlo) is the single validation path.

## SME usage (operator browser)

1. Open the BlackBox dashboard and go to **Quant Research Kitchen V1** (`/dashboard.html#/renaissance`).
2. **Baseline card:** Read tag, commit, deterministic metrics, Monte Carlo reference status.
3. **Report links:** Open baseline markdown and Monte Carlo baseline markdown via API-served files (same artifacts on disk as validation).
4. **CSV exports (baseline):** Download trades / deterministic metrics / Monte Carlo summary as CSV from saved JSON — no recompute at click time.
5. **Approved launchers:** Start only listed jobs (baseline Monte Carlo reference, example pipeline check, candidate compare — compare still needs a trades JSON path under `renaissance_v4/reports/experiments/`).
6. **Experiment queue:** Select a row to load detail, recommendation, **vs baseline** deltas (when artifacts exist), markdown links, and per-experiment CSV exports.

## API additions (v1)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/renaissance/workbench` | Approved job actions + roadmap hints (non-executable metadata). |
| `GET /api/v1/renaissance/file?rel=<repo-relative>` | Read-only download for files under `renaissance_v4/reports/` or `renaissance_v4/state/`. |
| `GET /api/v1/renaissance/baseline/export?kind=trades\|metrics\|monte_carlo` | Baseline CSV from saved artifacts. |
| `GET /api/v1/renaissance/experiments/<id>/export?kind=...` | Experiment CSV from saved artifacts (`trades` uses `candidate_trades` from summary JSON or index `extra`). |
| `GET /api/v1/renaissance/baseline` | Extended payload: `report_links`, `export_urls`, `strategy_id`. |
| `GET /api/v1/renaissance/experiments/<id>` | Extended payload: `report_links`, `comparison_vs_baseline`, `export_urls`. |

JSON schemas are versioned in payloads (`*_v2` where extended).

## Experiment metadata (direction)

Index records should carry (and the UI surfaces where present):

- `experiment_id`, `experiment_type` (in `extra` for new runs), `baseline_tag` / strategy reference, `status`, `recommendation`, `created_at`, `completed_at`, report paths, export paths (via API), optional `date_range` / `symbol` when the harness provides them (not required for v1 minimum).

## Version 1 scope delivered

- Baseline visibility, report links, CSV exports for baseline and experiments.
- Experiment queue columns: type, completed, created.
- Detail: recommendation, deterministic / Monte Carlo summary line, **vs baseline** deterministic deltas, markdown links, CSV exports.
- Approved launcher buttons aligned with `POST /api/v1/renaissance/jobs` (`baseline_mc`, `example_flow`, `compare`).
- **XLSX:** Not implemented in v1 (CSV is the required minimum).

## What remains manual or out of scope in v1

- **Harness types** not yet wired as jobs: date-range replay slice, stop/target sensitivity, regime gating sweep, risk-threshold sweep (listed as roadmap in `/workbench` JSON).
- **Compare** still requires a **candidate trades JSON** on the API host under `renaissance_v4/reports/experiments/` (path entered in the prompt or produced by `export-trades`).
- **Architect approval** for any production promotion — unchanged; not exposed in UI.
- **Baseline immutability** — unchanged; UI cannot edit locked logic.
- **XLSX exports** — optional follow-up if dependencies and SME demand justify it.

## Related

- Operator deploy: after changing `dashboard.html` or `api_server.py`, restart the **api** service on the lab host so Python routes reload; `dashboard.html` is served via the API route on many deployments.
