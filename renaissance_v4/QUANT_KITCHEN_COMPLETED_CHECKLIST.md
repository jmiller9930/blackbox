# Quant Research Kitchen — completed checklist (Renaissance)

**Location:** This file lives under `renaissance_v4/` so the checklist stays next to the validation engine.  
**Update when:** A directive closes, a major harness feature ships, or LOAD-028 inventory changes.

---

## Operational truth — DV-ARCH-FLOW-CORRECTION-043 (flow control)

| Field | Value |
|-------|--------|
| **RE:** | DV-ARCH-FLOW-CORRECTION-043 |
| **STATUS** | **complete** (documentation + checklist alignment; **not** claiming E2E operational proof) |

**Closure commit:** use `git log -1 --oneline -- renaissance_v4/QUANT_KITCHEN_COMPLETED_CHECKLIST.md` on `main` (avoid embedding a stale hash in this table).

**Implemented capability ≠ operationally proven outcome.** Do not collapse those into one statement.

**Correct current wording:** The Kitchen and policy infrastructure are **implemented**, but the **first fully proven end-to-end operational cycle** remains **blocked on obtaining a valid closed-trade series from Jupiter** (native Sean/Jupiter ledger).

**Active operational blocker (unchanged):**

- No **reliable closed-trade series** in **`sean_paper_trades`** (Jupiter/Sean SQLite) → in practice **Monte Carlo** and **stabilization** remain blocked downstream; we are **not** in strategy-learning / candidate-comparison mode until that exists.

**Immediate engineering priority (043):** Shortest path to **policy available in Jupiter → active → signals → open → close → PnL → then MC**. MC stays **downstream** of closed-trade proof.

**What not to do now (043):** Do not integrate Sean divergence candidates into the active pipeline, drift into strategy-quality debates, add abstraction layers, or use broad “ready / feature complete” language that hides the blocker.

---

## Jupiter policy — how it becomes available, selected, and verified

Answers below describe the **shipped SeanV3 / Jupiter** path (`vscode-test/seanv3/`). This is **not** the BlackBox Kitchen **policy-package** ingest path (`robustness_runner ingest-policy`); Kitchen evaluates **packages** in Renaissance; Jupiter runs **merged policy modules** in Node. Live Jupiter does **not** load arbitrary policy blobs from the UI at runtime.

### 1. How a new policy becomes available to Jupiter

| Step | What happens |
|------|----------------|
| **Code** | Add a policy module (e.g. `jupiter_*_policy.mjs`) with `generateSignalFromOhlc*` and entry resolver. |
| **Register** | Extend `ALLOWED_POLICY_IDS` and `resolveJupiterPolicy()` in `jupiter_policy_runtime.mjs` so the id maps to that module’s signal functions. |
| **Surface** | Update `jupiter_web.mjs` (API contract / operator UI copy) if the policy should appear in `GET /api/v1/jupiter/policy` and the sole-write POST. |
| **Deploy** | Add the new `.mjs` to the **Dockerfile** `COPY` list (and **`.dockerignore`** allowlist if the image build excludes it). Rebuild the **seanv3** / Jupiter image and restart the container. |

**Manual today:** There is **no** dynamic “upload policy into Jupiter” without a merge + image rebuild. Selecting among **already shipped** policies is what the API does.

### 2. How the policy is selected (API / runtime path)

| Layer | Mechanism |
|-------|-----------|
| **Persistence** | SQLite key **`analog_meta.jupiter_active_policy`** (string id: `jup_v4`, `jup_v3`, `jup_mc_test`, `jup_mc2`, …). |
| **Write** | **Sole write** from HTTP: **`POST /api/v1/jupiter/active-policy`** (alias **`/set-policy`**) with JSON `{"policy":"<id>"}` and **`Authorization: Bearer`** = `JUPITER_OPERATOR_TOKEN` (see `jupiter_web.mjs`). |
| **Read order** | **`resolveJupiterPolicy(db)`** in `jupiter_policy_runtime.mjs`: **`analog_meta.jupiter_active_policy`** → else **`SEAN_JUPITER_POLICY`** env → else default **`jup_v4`**. Evaluated **each engine cycle** (no stale module cache). |
| **Read-only** | **`GET /api/v1/jupiter/policy`** returns `active_policy`, `allowed_policies`, contract metadata. |

### 3. How we confirm the engine is trading under that policy

| Evidence | Where |
|----------|--------|
| **Runtime config** | `GET /api/v1/jupiter/policy` → `active_policy` matches intended id. |
| **DB** | `SELECT v FROM analog_meta WHERE k='jupiter_active_policy'` on the Sean parity DB (same value). |
| **Diagnostics** | Policy-specific tags / engine ids from `resolveJupiterPolicy` (e.g. `policyEngineTag`, `engineId`) appear in engine / tile output when instrumented (see Sean dashboard / Jupiter web diagnostics). |

**Important:** Policy **selected** ≠ policy **produced trades**. Selection only proves the resolver chose that lane.

### 4. Minimum evidence for trade generation and close behavior

| Claim | Minimum proof |
|-------|----------------|
| **Signals fire** | Engine logs / diagnostics showing non-flat signal evaluation when bars qualify (policy-dependent). |
| **Trades open** | Rows in **`sean_paper_position`** with non-flat side **or** lifecycle events in **`paper_trade_log`** consistent with entries (see Sean schema). |
| **Trades close + PnL** | **`sean_paper_trades`** non-empty with **`gross_pnl_usd`** (or equivalent) per row; **`GET /api/v1/sean/trades.csv`** export non-empty. |

**Kitchen / MC:** `renaissance_v4` Monte Carlo consumes **closed-trade PnL series** (`robustness_runner`, `trade_export.py`). That series must come from **real** closed trades — not inferred from candles alone.

---

## Completed (product / engine)

The items below are **implemented capability** in-repo. They are **not** a substitute for the operational proof row in §“Operational truth” unless separately verified on the lab host with ledger evidence.

- [x] **Architecture & naming** — `docs/architect/quant_research_kitchen_v1.md`, `quant_research_kitchen_modularity_v1.md`, SRA role `strategy_research_agent_v1.md`.
- [x] **Workbench v1 (dashboard)** — Route `/dashboard.html#/renaissance`, baseline + experiments + exports + approved jobs — see `renaissance_v4/WORKBENCH_V1.md` (“Version 1 scope delivered”).
- [x] **Workbench APIs** — Documented in `WORKBENCH_V1.md` (`/api/v1/renaissance/*`).
- [x] **Harness** — `research/robustness_runner.py`: `export-trades`, `baseline-mc`, `compare`, `compare-manifest`, `ingest-policy` (full pipeline per DV-ARCH-POLICY-INGESTION-024-C; see `docs/architect/DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md` §13).
- [x] **Manifest-driven replay (v7.2)** — `research/replay_runner.py` + `configs/manifests/baseline_v1_recipe.json`; `game_theory/MANIFEST_REPLAY_INTEGRATION.md`.
- [x] **Policy package replay (024-A)** — `research/policy_package_ingest.py`.
- [x] **SRA plumbing** — `research/sra_foundation.py`, variants/runs, experiment index — see `state/` artifacts and tests under repo `tests/`.
- [x] **Governance docs** — LOAD-028 (rule documented), INTAKE-021, `blackbox_policy_kitchen_integration_writeup.md`, `policy_package_standard.md`.
- [x] **Policy wiring map (029)** — `docs/architect/policy_wiring_surface_map_v1.md` (complete per that doc).
- [x] **Jupiter MC2 + API (039)** — `docs/validation/DV-ARCH-JUPITER-MC2-039.md` (complete).
- [x] **Automated regression (target suites)** — See `docs/validation/stabilization_035_report.md` §1 for pytest bundles run against this stack (not a substitute for full operational cycles).

---

## Validation directives (explicit outcomes)

| Directive | Outcome | Evidence |
|-----------|---------|----------|
| DV-ARCH-FLOW-CORRECTION-043 | **Complete** (status language + Jupiter policy path documented here) | This file, §“Operational truth” + §“Jupiter policy” |
| DV-ARCH-CANONICAL-POLICY-SPEC-046 | **Partial** — PolicySpecV1 + `normalize_policy` + `jup_pipeline_proof_v1` in Sean; full parity + lab trade/MC proof open | `renaissance_v4/policy_spec/README.md` |
| DV-ARCH-KITCHEN-POLICY-INTAKE-048 | **Partial** — intake API + staged pipeline + Kitchen UI upload; primary-host operator proof + `npx` availability | `renaissance_v4/policy_intake/README.md` |
| DV-ARCH-JUPITER-MC2-039 | **Complete** | `docs/validation/DV-ARCH-JUPITER-MC2-039.md` |
| DV-ARCH-STABILIZATION-035 (full 5 cycles) | **Not met** | `docs/validation/stabilization_035_report.md` |
| DV-ARCH-JUPITER-MC-UNBLOCK-040 | **Not met** | Same report, §9 |

---

## Open / not done (tracked elsewhere)

- [ ] **LOAD-028 implementation** — Persisted submission → `approved_for_activation`, unified package submit, MC/compare tied to submission id — see LOAD-028 §13 “still open”.
- [ ] **Stabilization / MC unblock** — Non-empty native closed-trade PnL where required (`baseline-mc` / Sean ledger); see `stabilization_035_report.md` and §9 (040).
- [ ] **Priority (043)** — Prove **injected / merged** Jupiter policy → active → **signals → open → close → PnL** on the lab host; MC remains **after** that proof.

---

## Related paths

| Path | Role |
|------|------|
| `renaissance_v4/ACTIVE_DOCKET.md` | BLACKBOX / Jupiter / Kitchen phased priorities (047–053) |
| `renaissance_v4/WORKBENCH_V1.md` | Product spec + API list |
| `renaissance_v4/ROBUSTNESS.md` | Robustness runner usage |
| `docs/validation/` | Directive closure and smoke evidence |
| `policies/generated/renaissance_baseline_v1_stack/` | Generated baseline stack artifacts |
