# Work log — engineering responses to architect (Kitchen / policy)

Rolling log of dated entries for architect-facing answers and shipped work. Newest first.

---

## 2026-04-17T18:20:00Z — Architect — RE: CURRENT OPEN POLICY ARTIFACT BINDING DIRECTIVE — LIVE HOST PROOF ON CLAWBOT (BLOCKING)

**Directive / tag:** **Architect — RE: CURRENT OPEN POLICY ARTIFACT BINDING DIRECTIVE — LIVE HOST PROOF ON CLAWBOT** (BLOCKING — no new feature work until proven)

**Host:** `clawbot` · **`~/blackbox`** · **`git rev-parse HEAD` = `07c3d9219548361f7464b412a0616b3090e2ab45`** (after `git pull origin main`; `UIUX.Web` **`docker compose restart api`** executed).

**Policy under test (non-mechanical):** `tests/fixtures/policy_intake/fixture_minimal_direction_policy.ts` → **`candidate_policy_id` = `fixture_minimal_direction_v1`** (not `kitchen_mechanical_always_long_v1`).

| Step | Requirement | Result |
|------|-------------|--------|
| 1 | Intake PASS; capture `submission_id`, `content_sha256` | **`pass: true`** · **`submission_id` = `69933ea3a779444a959bc5fa`** · **`content_sha256` = `dd210033e295b71110efcefa212f12a2d9687223400816112bf716aeee9a06e3`** |
| 2 | Manifest row: `execution_target`, `submission_id`, `content_sha256`, `deployed_runtime_policy_id` | Registered via `register_kitchen_deployment_manifest_entry.py` → **`jupiter` / same `submission_id` / same sha / `jup_mc_test`** (file: `renaissance_v4/config/kitchen_policy_deployment_manifest_v1.json` on **clawbot host** — **lab mutation; not in `origin/main` unless committed**). |
| 3 | Assign via API; assignment record matches | **`POST /api/v1/renaissance/kitchen-runtime-assignment`** → **`ok: true`** · **`active_runtime_policy_id`: `jup_mc_test`** · **`content_sha256`** matches · **`runtime_http_post_ok`: true** |
| 4 | **`GET /api/v1/jupiter/policy`** (Bearer) full payload | **`active_policy`: `jup_mc_test`** · **`submission_id` / `content_sha256`** match intake · **`artifact_binding`: `manifest_v1`** |
| 5 | Engine execution proof (deterministic / controlled) | **`docker exec jupiter-web node`** loads **`jupiter_mc_test_policy.mjs`** · **`generateSignalFromOhlcMcTest`** with 80 ascending closes → JSON with **`engine_id` = `jupiter_mc_test_policy_mjs_v1`**, **`diag.policy_engine` = `jupiter_mc_test`**. **`seanv3` container was in `Restarting` state** during check — **`jupiter-web` used for module load.** |
| 6 | Negative assign without manifest artifact | Second intake **`submission_id` = `31d3e750151d48bf82f6235e`** (no manifest row) → **`POST` assignment** → **`ok: false`** · **`error`: `policy_not_deployed_as_runtime_artifact`** (no legacy fallback) |
| 7 | UI parity Kitchen vs Jupiter | **API parity verified:** **`GET .../kitchen-runtime-assignment?execution_target=jupiter`** shows **`authoritative_active_policy` = `jup_mc_test`**, assignment row matches manifest submission+sha; runtime GET echo matches. **Browser screenshots:** MCP browser from this environment did not load external Jupiter URL (stayed `about:blank`) — **operator should attach** Kitchen `#/renaissance` + Jupiter `707` screenshots if formal UI proof is required. |

**Honest limit on “exact bytes” vs slot:** Jupiter still **executes** the deployed module for slot **`jup_mc_test`** (`jupiter_mc_test_policy.mjs`). The manifest binds **which Kitchen submission+hash** is associated with that slot for observability; **byte-identity** between the uploaded TS and the shipped `.mjs` is **not** claimed here (that would require the build pipeline that compiles this submission into the Sean module).

---

## 2026-04-14T18:30:00Z — DV-078 + Architect directive (Kitchen policy inventory model)

**Directive / tag:** **DV-078** (unified Kitchen policy inventory); **Architect — RE: Fix Kitchen Policy Inventory Model and Eliminate Cross-Source UI Confusion** (BLOCKING — operator inventory view)

**Summary for architect**

| Topic | Response |
|-------|----------|
| First paint vs refresh mismatch | **Root cause:** overlapping async fetches (`intake-candidates` + `kitchen-runtime-assignment` in parallel paths; duplicate `rv4LoadCandidates` on Renaissance load). **Fix:** single GET **`/api/v1/renaissance/kitchen-policy-inventory`**, request **sequence guard** (`rv4InventorySeq`), removed duplicate init fetch. |
| One stable inventory | Payload aggregates **registry allowlist**, **manifest entries**, **intake candidates**, **`kitchen_runtime`** (same as prior assignment GET), **`legacy_registry_only`**, **`assignable_submission_ids`**. |
| UI | **`#rv4-inventory-summary`** line documents four layers in one place; candidate table driven from same JSON. |
| Git | **`4020b61`** on `main` — pushed `origin/main`. |

**Proof still required on host (operator):** `git pull` on lab host, **`docker compose restart api`**, hard-refresh Kitchen — confirm first paint and poll show **same** inventory counts/rows when data unchanged.

---

## 2026-04-14T17:00:00Z — Clarification (registry vs intake vs Jupiter dropdown)

**Directive / tag:** Clarification thread (no new DV); relates **DV-070** / registry allowlist / Jupiter **`GET /api/v1/jupiter/policy`**

**Summary for architect**

- **`kitchen_policy_registry_v1.json`** = shared **allowlist** of runtime policy ids (Jupiter reads via `BLACKBOX_REPO_ROOT` / `jupiter_registry_allowlist.mjs` where configured).
- **Policy Intake** = **local** submission/evaluation history (`policy_intake_submissions/`, gitignored) — not the master list of runtime ids.
- **No contradiction:** Jupiter dropdown can be full while Intake is empty; different stores, same **allowlist** for what ids exist.

---

*Format: ISO-8601 UTC timestamps; directive IDs use project tags (DV-*) or architect RE subject lines.*
