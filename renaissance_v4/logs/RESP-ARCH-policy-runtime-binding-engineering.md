# Engineering response: Kitchen policy must bind to exact runtime execution

**TO:** Architect  
**FROM:** Engineering  
**RE:** Policy Assignment Must Bind the Exact Kitchen Policy to Runtime Execution  
**STATUS:** Acknowledged — **BLOCKING** until operational proof per directive  
**Date:** 2026-04-17  

---

## 1. Receipt of directive

We acknowledge the requirement:

- **One binding model:** the policy assigned in Kitchen must be **the exact policy** executed by the selected trade target’s runtime.
- **No acceptable substitute:** alias-only mapping to pre-baked modules (`jup_mc_test`, `jup_v4`, …) unless that module **is** the built/deployed form of **that** Kitchen artifact.
- **Closure is operational:** assign in Kitchen → trade service shows **that** policy active → engine executes **that** policy — Jupiter and BlackBox when in scope.

The current control plane **does** switch `active_policy` via `POST …/active-policy` using a **string id**; it **does not** today guarantee that id’s **implementation** is byte-for-byte or semantically identical to a given Kitchen submission. **That gap is the defect** described in `LOG-kitchen-intake-jupiter-runtime-mismatch-failure.md`.

---

## 2. Explicit answers (no registry/UI theory — runtime binding only)

### Q1: What exact mechanism will make a Kitchen policy become the exact runtime-executed policy for **Jupiter**?

**Today (as shipped):**  
Jupiter resolves execution only through **`resolveJupiterPolicy(db)`** in `vscode-test/seanv3/jupiter_policy_runtime.mjs`, which maps **`analog_meta.jupiter_active_policy`** → **in-process modules** (`jupiter_*_policy.mjs`). New behavior requires **one of**:

| Mechanism | What it is |
|-----------|------------|
| **Option A — Per-policy deployment** | After Kitchen intake PASS: **build** the submission’s TS (or canonical artifact) into a **versioned** `jupiter_*_policy.mjs` (or bundled chunk), register a **new** `jup_<slug>_<content_hash_short>` (or similar) in **`ALLOWED_POLICY_IDS`** + **`resolveJupiterPolicy`**, ship in the **SeanV3 image**, deploy. Assignment POST uses **that** id. **Runtime id = deployed identity of that Kitchen artifact.** |
| **Option B — Dynamic artifact loading** | SeanV3 stores **`submission_id`** + **content_sha256** (or path) in SQLite / meta; **`resolveJupiterPolicy`** (or a loader it calls) **reads** the artifact from BlackBox/Kitchen store, **esbuild/import** or precompiled module per revision, with cache invalidation on hash change. **GET /policy** returns **that** binding (id + hash), not a generic alias. |

**Not sufficient alone:** extending `kitchen_policy_registry_v1.json` **`intake_candidate_runtime_map`** to point candidates at `jup_mc_test` — that only satisfies **control-plane eligibility**, not **execution parity**.

**Canonical reference:** `renaissance_v4/QUANT_KITCHEN_COMPLETED_CHECKLIST.md` §1 — states there is **no** dynamic upload without merge + deploy; **this directive supersedes “manual today” as the product bar.**

---

### Q2: What exact mechanism will make a Kitchen policy become the exact runtime-executed policy for **BlackBox**?

**Today:** `kitchen_runtime_assignment.py` can **`POST /api/v1/blackbox/active-policy`** with a **policy id** (`blackbox_post_active_policy`), subject to the **same** class of problem: the BlackBox trade surface must **resolve** that id to **the same** artifact Kitchen assigned.

**Required:** Mirror **A or B** on the BlackBox side: either **deployed module id per Kitchen revision** or **dynamic load** from **submission_id / hash** stored in assignment record + BlackBox resolver. **`renaissance_v4/blackbox_policy_control_plane.py`** and runtime adapter paths must **load** that artifact, not only accept a string id from registry.

---

### Q3: If per-policy deployment — what is the build and registration path?

**Proposed path (outline — to be detailed in a design PR):**

1. **Trigger:** Successful intake (`pass`, `candidate_policy_id`, `canonical/policy_spec_v1.json`, raw TS under `policy_intake_submissions/<id>/`).
2. **Build:** CI or dedicated job: **esbuild** TS → single bundle; run **harness** / contract tests; emit **artifact manifest** (`submission_id`, `content_sha256`, `runtime_target: jupiter|blackbox`).
3. **Register Jupiter:** Add generated module to SeanV3 tree; extend **`jupiter_policy_runtime.mjs`**; extend **`ALLOWED_POLICY_IDS`**; image **Dockerfile** COPY + rebuild; **`allowed_policies`** in `GET /policy` includes new id.
4. **Register BlackBox:** Same artifact rules for BB adapter (path TBD per BB layout).
5. **Assignment:** Kitchen assignment store persists **`submission_id`** + **`deployed_runtime_policy_id`** (the **new** id). POST active-policy sets **that** id only after deploy succeeded.

**Proof:** `GET` trade service shows **`active_policy == deployed_runtime_policy_id`** and manifest hash matches Kitchen row.

---

### Q4: If dynamic load — what is the artifact resolution path?

**Proposed path (outline):**

1. **Persist:** Assignment row + runtime meta store **`kitchen_submission_id`**, **`policy_content_sha256`**, optional **`artifact_uri`** (internal).
2. **Resolve:** On engine cycle, **`resolveJupiterPolicy`** (or loader): if meta points to Kitchen artifact → **fetch** from `renaissance_v4/state/policy_intake_submissions/...` (or API) → verify hash → **load** (esbuild in process or precompiled). **Fail closed** if hash mismatch.
3. **Expose:** `GET /api/v1/jupiter/policy` returns **submission_id** + **hash** + **active** so operator can compare to Kitchen UI.

**Constraints:** determinism, startup cost, sandboxing — **design review required.**

---

### Q5: How will the runtime prove active policy is the exact Kitchen-assigned policy, not an alias slot?

**Required signals (all of):**

| Proof | Mechanism |
|-------|-----------|
| **Identity** | **`active_policy` id** equals **Kitchen-recorded** `deployed_runtime_policy_id` (deployment model) **or** **`submission_id` + `content_sha256`** match (dynamic model). |
| **Integrity** | Hash of loaded module / artifact **equals** hash in **`intake_report.json`** / canonical spec for that assignment. |
| **Observability** | Trade service GET returns **those fields**; dashboard compares Kitchen row vs GET (existing drift machinery extended, not replaced by “sync feels ok”). |

**Not sufficient:** “GET returns `jup_mc_test`” when Kitchen assigned a **different** submission — **that is the bug class** this directive forbids.

---

### Q6: What current code paths must change because assignment today only switches among already-deployed runtime ids?

| Area | Current behavior | Required change |
|------|------------------|-----------------|
| **`kitchen_policy_registry.py`** / **`infer_runtime_policy_id_for_candidate`** | Maps candidate → **pre-listed** `jup_*` for UI eligibility | Either **derive** id from **deployed artifact** record **or** **remove** alias semantics for “assign”; registry lists **real** deployable ids tied to builds. |
| **`kitchen_runtime_assignment.py`** | POST **`policy_id`** to Jupiter/BB | Persist **`submission_id`** + **binding proof** (deployed id **or** hash); POST must use **binding** that implies **exact** artifact. |
| **`vscode-test/seanv3/jupiter_policy_runtime.mjs`** | Static `resolveJupiterPolicy` | Add **branch** for per-submission or per-build id **or** dynamic loader. |
| **`jupiter_web.mjs` (or equivalent)** | POST sets SQLite **`jupiter_active_policy`** | Accept **only** ids that **resolve** to bound artifact **or** extend payload with **submission/hash**. |
| **BlackBox adapter** | Same id-switch pattern | Same binding rules. |
| **Dashboard** | Assign enabled when `runtime_policy_id` inferred | Must reflect **bound** policy **or** disable until deploy/load completes — **no** green assign on alias alone. |

---

## 3. Decision required from product/architecture

Engineering **cannot** implement both A and B fully in parallel without scope explosion. **Select one primary binding model** (per-policy deployment vs dynamic load) for Jupiter first; BlackBox follows the same pattern.

---

## 4. Closure criteria (operational — matches directive)

| # | Criterion |
|---|-----------|
| 1 | Policy **created and passing** in Kitchen (specific `submission_id`). |
| 2 | **Assigned** to Jupiter for that target. |
| 3 | Jupiter **`GET /api/v1/jupiter/policy`** (or documented equivalent) shows **active** = **that** binding (id + hash / submission ref per model). |
| 4 | Engine cycle uses **that** artifact’s logic (verified by signal/trace or controlled test). |
| 5 | Repeat for BlackBox when that path is in scope. |

Until **1–4** are demonstrated on **primary_host** with captured proof, **assignment model remains incomplete** per this directive.

---

## 5. One-line summary (engineering)

We will implement **either** per-policy deployment **or** dynamic artifact loading so **`active_policy` and execution both trace to the exact Kitchen submission**; the current **alias-only id switch** is **not** the final model and will be **replaced** in the assignment and resolution path, not patched with more registry rows.

---

## Appendix A — Architect directive (verbatim)

```
TO: Engineering
FROM: Architect
RE: Policy Assignment Must Bind the Exact Kitchen Policy to Runtime Execution
STATUS: BLOCKING

The current behavior is not acceptable.

From this point forward, the rule is simple:

The policy assigned in Kitchen for a selected trade target must be the exact policy executed by that target's runtime. There is no second path. There is no acceptable alias-only substitute. There is no "close enough" mapping to an already-baked policy module unless that module is in fact the exact Kitchen policy artifact that was assigned.

Right now the system is still treating assignment as "switch to an existing runtime policy id." That is not the requirement. The requirement is "run this policy." If the operator assigns a policy in Kitchen, then Jupiter or BlackBox must execute that specific policy for that target.

This means the current alias-slot model is not sufficient as the final solution. A candidate policy cannot simply be funneled into jup_mc_test, jup_v4, or any other preexisting runtime id unless that runtime id is a real build of the exact Kitchen policy artifact being assigned.

So the defect is this:

The current control plane can switch runtime ids, but it cannot yet guarantee that the exact Kitchen-created policy is what the runtime is actually executing. That breaks the product requirement.

The required end state is:

A policy is created and validated in Kitchen.
That exact policy becomes runtime-bindable for the selected target.
When the operator assigns it, the trade service executes that exact policy.
When the operator looks at the trade service, the active policy shown there is the same policy that was assigned in Kitchen.
No alternate path exists.

Engineering must implement one real binding model to achieve this.

Option one is per-policy deployment. A Kitchen policy that passes intake is built into a target-specific runtime artifact or module with its own runtime id. That id is registered for the selected target, deployed, and then assignment sets that exact id active. In that model, the runtime id is not a generic alias. It is the deployed identity of that exact Kitchen policy.

Option two is dynamic artifact loading. The runtime resolves the active policy from a Kitchen submission id, artifact hash, or canonical artifact reference and loads that exact policy at runtime. If this is chosen, it must still preserve determinism, validation, and safety.

One of those two must be selected. The current model of "assign to an already-existing runtime alias" is not enough.

Do not answer this with more registry theory, more reconciliation theory, or more UI theory. This is a runtime binding problem.

Engineering must answer these questions explicitly:

What exact mechanism will make a Kitchen policy become the exact runtime-executed policy for Jupiter?
What exact mechanism will make a Kitchen policy become the exact runtime-executed policy for BlackBox?
If the answer is per-policy deployment, what is the build and registration path?
If the answer is dynamic load, what is the artifact resolution path?
How will the runtime prove that the active policy is the exact Kitchen-assigned policy and not merely an alias slot?
What current code paths must change because assignment today only switches among already-deployed runtime ids?

Required proof for closure is not conceptual. It is operational.

A policy created in Kitchen must be assigned to Jupiter.
Jupiter must show that exact policy as the active runtime policy.
That same policy must be what the engine executes.
The same must be true for BlackBox when that path is implemented.

Until that is true, the assignment model is incomplete.

One-line summary:

The policy assigned in Kitchen must be the exact policy executed by the selected runtime target. Alias switching is not the final product and is no longer acceptable as the assignment model.
```
