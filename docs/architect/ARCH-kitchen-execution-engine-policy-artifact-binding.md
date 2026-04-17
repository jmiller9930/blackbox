# Architecture: separate execution engine from policy artifact (Kitchen ↔ runtime binding)

**TO:** Architect, Engineering  
**FROM:** Engineering (architecture response)  
**RE:** Architecture Reset — Separate Execution Engine from Policy Artifact  
**STATUS:** BLOCKING — design baseline for implementation  
**Date:** 2026-04-17  

**One-line summary:** We formally separate a **generic execution engine** per target from a **policy artifact** Kitchen creates; **assignment** must bind **that artifact** to execution — not **alias-only** switches to unrelated prebuilt modules.

**Related:** `renaissance_v4/logs/LOG-kitchen-intake-jupiter-runtime-mismatch-failure.md`, `renaissance_v4/logs/RESP-ARCH-policy-runtime-binding-engineering.md`, `renaissance_v4/QUANT_KITCHEN_COMPLETED_CHECKLIST.md`.

**SeanV3 Node (current implementation):** The normative **engine vs policy** boundary, file map, and forbidden patterns are **`docs/architect/engine_policy_demarcation_v1.md`**. Section 3 below still describes historical alias-driven behavior; **the Jupiter “module switchboard” row is superseded** for the Node hot path by manifest + `evaluator.mjs` artifact load (`vscode-test/seanv3/jupiter_policy_runtime.mjs`, `engine/artifact_policy_loader.mjs`).

---

## 1. Executive summary

**Problem:** Kitchen can **intake, validate, store, and list** policy artifacts, but **runtime assignment** today ultimately selects **pre-registered string ids** that resolve to **baked-in strategy modules** on Jupiter (and analogous allowlists on BlackBox). That does **not** guarantee the **exact** Kitchen-stored artifact is what executes.

**Target:** One **execution engine** per target (generic: feeds, bars, schedule, risk, orders, state). One **policy artifact** type (decision package: logic + metadata + hash + compatibility). **Assignment** = bind **this** artifact to **this** target; **runtime** = execute **that** binding with **provable** identity.

**This document:** (1) current state and reuse, (2) alias-driven paths, (3) target architecture, (4) Path A vs B, (5) recommendation, (6) proof of closure, (7) migration outline.

---

## 2. Current state — what remains valid and reusable

These are **already aligned** with “policy as artifact” on the **BlackBox / Renaissance** side and should **not** be thrown away:

| Component | Location / role | Reuse |
|-----------|------------------|--------|
| **Canonical policy spec** | `renaissance_v4/policy_spec/policy_spec_v1.py`, normalized `policy_spec_v1.json` under intake | Yes — metadata, identity, indicators section |
| **Indicator vocabulary** | `renaissance_v4/policy_spec/indicators_v1.py`, `indicator_mechanics.py`, `indicator_engine.mjs` (harness) | Yes — declarations + mechanical support |
| **Intake pipeline** | `renaissance_v4/policy_intake/pipeline.py`, `run_ts_intake_eval.mjs`, `ts_validate.py` | Yes — bundle, harness, viability |
| **Storage layout** | `renaissance_v4/state/policy_intake_submissions/<submission_id>/` — raw, canonical, report | Yes — **artifact store**; binding must reference **submission_id + content_sha256** |
| **Candidate registry** | `renaissance_v4/policy_intake/candidates_registry.py`, API `intake-candidates` | Yes — listing; **must** gain **binding fields** (artifact ref, deployed id, or hash) |
| **Lifecycle** | `renaissance_v4/kitchen_policy_lifecycle.py` | Yes — extend with lifecycle for **deployed** / **active** artifact |
| **Execution target model** | `renaissance_v4/execution_targets.py`, Kitchen UI target selector | Yes |
| **Assignment HTTP orchestration** | `renaissance_v4/kitchen_runtime_assignment.py` — POST/GET verify, ledger, drift | **Reuse flow**; **change payload** from “policy id only” to **binding** |

**What is *not* sufficient as the end state:** `kitchen_policy_registry_v1.json` **`intake_candidate_runtime_map`** mapping arbitrary `candidate_policy_id` → `jup_mc_test` (or any id) **without** a **build or hash** that makes that id **identical** to the Kitchen artifact.

---

## 3. Current state — alias-driven runtime paths (exact)

### Jupiter (SeanV3)

| Mechanism | Files / behavior |
|------------|------------------|
| **Active policy persistence** | SQLite `analog_meta.jupiter_active_policy` — string id only |
| **Resolution** | `vscode-test/seanv3/jupiter_policy_runtime.mjs` — `resolveJupiterPolicy(db)` → **`policyId`** + in-process **module** from `jupiter_*_policy.mjs` |
| **Allowlist** | `ALLOWED_POLICY_IDS` — fixed set of ids |
| **Sole write** | `POST /api/v1/jupiter/active-policy` — body `{"policy":"<id>"}`; `jupiter_web.mjs` |
| **Kitchen → Jupiter** | `kitchen_runtime_assignment.py` — `jupiter_post_active_policy(..., policy_id)` — **only** id string |

**Alias character:** `policyId` **always** means “which **shipped** module,” not “which Kitchen submission.”

### BlackBox

| Mechanism | Files / behavior |
|------------|------------------|
| **Registry allowlist** | `renaissance_v4/config/kitchen_policy_registry_v1.json` — `runtime_policies.blackbox` |
| **Inference** | `infer_runtime_policy_id_for_candidate` — maps candidate → id **from** registry / mechanical_slot |
| **Persisted “active”** | `renaissance_v4/blackbox_policy_control_plane.py` — `blackbox_kitchen_runtime_policy_v1.json` — **`active_policy`** string |
| **Approval** | `runtime_policy_approved(repo, "blackbox", pid)` — same id list |

**Alias character:** active policy is a **string id** approved against **pre-listed** ids, not a **hash-addressed** artifact load.

### Kitchen control plane (shared)

| Mechanism | Alias risk |
|------------|------------|
| `infer_runtime_policy_id_for_candidate` | Enables UI when **inferred** id non-empty; **does not** deploy artifact |
| Assignment store | Records `submission_id` + `active_runtime_policy_id` — **must** tie **artifact** to id under new model |

---

## 4. Target-state architecture (concepts)

```
┌─────────────────────────────────────────────────────────────┐
│  EXECUTION ENGINE (per target: Jupiter, BlackBox)          │
│  • Feeds, bar construction, evaluation schedule              │
│  • Risk gates, order placement, positions, state             │
│  • Calls: policy.evaluate(inputs) or loads artifact bundle   │
│  • Does NOT embed strategy-specific code for each partner    │
└──────────────────────────┬──────────────────────────────────┘
                           │ binding: submission_id + hash
                           │    OR deployed policy id = hash of package
┌──────────────────────────▼──────────────────────────────────┐
│  POLICY ARTIFACT (Kitchen)                                  │
│  • Raw TS (or bundle) + canonical policy_spec_v1.json       │
│  • content_sha256, candidate_policy_id, submission_id       │
│  • Declared indicators, metadata, version                   │
└─────────────────────────────────────────────────────────────┘
```

**Assignment record (conceptual):** must store enough to **reconstruct** “what is running” = **artifact identity**, not only `jup_v4`.

**Runtime proof:** GET / observability returns **artifact hash** and/or **submission_id** + **engine version** matching **Kitchen** row.

---

## 5. Path A vs Path B — comparison

| Dimension | Path A — Per-policy deployment (package + id) | Path B — Dynamic load |
|-----------|-----------------------------------------------|------------------------|
| **What executes** | **Built** module/package registered under a **unique** `runtime_policy_id` (or `jup_<hash>`) that **is** the built output of **that** submission | **Same** bytes Kitchen validated, loaded **by reference** (submission id + hash from store) |
| **Build/deploy** | CI or pipeline: intake PASS → esbuild → tests → **register** id + **ship** in image or sidecar registry | **No** per-policy image build; **loader** in engine pulls artifact |
| **Determinism** | Strong — **immutable** package per id | Requires **pinned hash**, **no** drift, **cache** invalidation on change |
| **Operator workflow** | “Promote” → build → deploy → assign **new** id | “Assign” → runtime loads **latest** approved hash (or pinned revision) |
| **Security** | **Only** approved packages in allowlist; signature possible | **Must** verify hash against Kitchen DB; **sandbox** (no `fs` escape) |
| **Rollback** | Switch id to previous **deployed** package | Switch pointer to previous **hash** |
| **Debugging** | Id + version in logs; **matches** Docker image | submission_id + hash in logs |
| **Traceability** | **Id → build manifest → submission_id** | **Hash → submission** directly |
| **Jupiter first** | Extend `resolveJupiterPolicy` to resolve **either** legacy ids **or** new **package** ids; **or** dynamic branch | **Loader** in `jupiter_policy_runtime.mjs` (or subprocess) **imports** bundle from path/HTTP |
| **BlackBox** | Same: **new** id in `runtime_policies` **after** package exists **or** loader reads from `policy_intake_submissions/` | Same loader pattern with BB store |

---

## 6. Recommendation (explicit)

**Primary recommendation: Path A (per-policy deployment) for first production-grade closure**, with **staged** delivery:

1. **Phase 0 (now):** Document-only; **stop** expanding alias maps as “fixes.”  
2. **Phase 1 — Jupiter:** Build pipeline: **passing** submission → **bundled** `jupiter_kitchen_<submission_id_or_hash>_<short>.mjs` (or single package dir) → **one** new id per **promoted** policy → **register** in `ALLOWED_POLICY_IDS` + image → **assignment** POSTs **that** id only. **GET** returns id + **manifest hash** matching Kitchen.  
3. **Phase 2 — BlackBox:** Same artifact package pattern; **persist** `active_policy` as **that** id **or** extend state file with **submission_id + hash** if BB engine stays file-based.  
4. **Path B (dynamic load):** **Defer** as **Phase 3** or **parallel R&D** if operator need for **instant** assign without deploy **outweighs** image discipline — **not** required for first **architectural proof**.

**Reasoning:** Path A matches **existing** Jupiter operational model (allowlist + shipped modules), **minimizes** runtime risk, gives **clear** rollback (previous package id), and **proves** “this id **is** that build.” Path B is **valid** but **higher** risk for determinism and security without a **long** loader design.

---

## 7. Proof of closure (operational)

| # | Criterion |
|---|-----------|
| 1 | Policy **PASS** in Kitchen; **submission_id** + **content_sha256** recorded. |
| 2 | **Build** produces **deployable** package; **runtime_policy_id** is **unique** to that package (or manifest ties id → hash). |
| 3 | **Assign** sets **that** id (Path A) **or** **hash pointer** (Path B) on **target**. |
| 4 | **GET** runtime API returns **active** identity **+** hash **or** submission ref **matching** Kitchen. |
| 5 | **Engine cycle** uses **that** package (verified by **signal** or **contract test** against known bars). |
| 6 | Repeat for **BlackBox** when target is **in scope**. |

**Not closure:** “GET returns `jup_mc_test`” while Kitchen assigned a **different** submission.

---

## 8. Migration from alias model

1. **Freeze** new `intake_candidate_runtime_map` entries except **documented** lab exceptions.  
2. **Implement** build pipeline + **new** ids for **promoted** policies only.  
3. **Extend** `kitchen_runtime_assignment` persistence: `submission_id`, `content_sha256`, `deployed_runtime_policy_id` (Path A).  
4. **Change** `resolveJupiterPolicy` (and BB resolver) to **resolve** new id → **module** built from **that** package.  
5. **Deprecate** “assign = pick any old `jup_*`” for **Kitchen** flows; **legacy** selector may remain for **non-Kitchen** ops until retired.  
6. **Dashboard:** show **artifact hash** + **runtime id** side by side; **drift** if mismatch.

---

## 9. Explicit answers (checklist)

| Question | Answer |
|----------|--------|
| **What parts remain valid?** | §2 table — intake, spec, indicators, storage, candidates, lifecycle, targets; assignment **orchestration** reused with **new** payload. |
| **What paths are alias-driven?** | §3 — Jupiter `resolveJupiterPolicy` + SQLite id; **POST** `policy` string; BB `active_policy` + registry allowlist; `infer_runtime_policy_id_for_candidate` for UI. |
| **What artifact is executed?** | Path A: **deployed package** (built from Kitchen raw TS). Path B: **bytes** from `policy_intake_submissions/.../raw/` or canonical bundle. |
| **Unique identification?** | **submission_id** + **content_sha256** (canonical); Path A adds **deployed_runtime_policy_id** tied to manifest. |
| **How Kitchen binds?** | Assignment stores **submission_id** + **hash** + **deployed id** (A) or **hash-only** pointer (B). |
| **How runtime proves?** | GET returns **hash** + **id**; engine logs **manifest**; drift detector compares to Kitchen. |
| **Recommended path first?** | **Path A** (per-policy deployment); Path B **later** if needed. |
| **Same for BlackBox?** | **Same** binding model; **different** HTTP adapter + state file; **shared** artifact store and manifest. |
| **Migration work?** | §8 |

---

## 10. Behavioral parity with “pre-Kitchen” operation

**Preserved:** Trade service still runs **one** active policy at a time; **POST** selects active policy; engine loop unchanged in **shape**.

**Changed:** **What** “policy id” **means** for **Kitchen-origin** flows: it must **denote** (Path A) **this** built package **or** (Path B) **this** hash — **not** an arbitrary slot. **Legacy** `jup_v4` / `jup_mc_test` remain **valid** as **pre–Kitchen-era** bundled strategies until retired; **new** Kitchen-assigned policies **do not** reuse those ids as **aliases**.

---

## 11. Next deliverables (engineering)

1. **Design PR:** One **package** format (manifest schema), **build** job contract, **Jupiter** registration steps, **one** E2E proof path.  
2. **Spike:** Minimal **Path A** — one fixture submission → build → **new** id → assign → GET proves hash.  
3. **BlackBox** alignment doc — same binding fields, BB-specific POST/state.

---

*End of architecture document.*
