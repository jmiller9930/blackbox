# Work log — engineering responses to architect (Kitchen / policy)

Rolling log of dated entries for architect-facing answers and shipped work. Newest first.

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
