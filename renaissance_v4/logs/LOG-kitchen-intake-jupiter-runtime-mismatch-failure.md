# Failure analysis: Kitchen intake vs Jupiter runtime policy deployment

**Status:** Open architectural gap (not a one-off bug).  
**Audience:** Architect, operator, runtime engineering.  
**Related:** `renaissance_v4/QUANT_KITCHEN_COMPLETED_CHECKLIST.md`, `renaissance_v4/config/kitchen_policy_registry_v1.json`, `renaissance_v4/POLICY_ASSIGNMENT_SYSTEMS_MAP.md`, `renaissance_v4/kitchen_policy_registry.py`.

---

## 1. Executive summary

Quant Research Kitchen (Renaissance) can **accept**, **validate**, and **persist** a partner-uploaded TypeScript policy and show it as a **passing candidate**. Jupiter (SeanV3), however, **does not execute** arbitrary policy blobs from that path. It only switches among **pre-shipped** policy modules identified by stable strings (`jup_v4`, `jup_mc_test`, `jup_kitchen_mechanical_v1`, …).

When pressure mounted to make the **Assign to runtime** control “work” for lab or ad hoc candidates, the relief valve became **registry mapping**: associate a `candidate_policy_id` with an **approved** `runtime_policy_id` in `kitchen_policy_registry_v1.json`. That is **not** the same as deploying the uploaded policy to Jupiter. It is **label alignment** for the control plane and UI eligibility.

**Systematic failure:** a handful of **hardcoded** runtime policies became the **de facto** backplane for “anything we want to assign,” because mapping onto them was the only way to get a green assign path—without building a true **intake artifact → runtime execution** bridge.

**User-visible outcome:** operators see **PASS** on intake and **Assign disabled** (or, if mapped, a misleading sense that something “real” was assigned when Jupiter still runs the **shipped** module, not the upload).

---

## 2. Intended behavior (what the product should mean)

| Layer | Intended meaning |
|--------|-------------------|
| **Kitchen intake** | Validate contract, deterministic harness, persist canonical spec + submission; **truth** = “this artifact passed our gates.” |
| **Runtime assignment** | **Either** select a runtime policy that **is** the built/deployed form of that artifact, **or** explicitly document that assignment is **only** switching among pre-registered engine modules **until** dynamic loading exists. |
| **Registry** | Authoritative list of **real** deployable runtime IDs and **explicit** mechanical/lab pairings—not a generic alias table from arbitrary uploads to unrelated modules. |

---

## 3. Actual behavior (ground truth)

- **Jupiter policy selection** persists `analog_meta.jupiter_active_policy` (or equivalent) to a **string id** resolved by `resolveJupiterPolicy()` in SeanV3 to **bundled** `.mjs` modules. See checklist: live Jupiter does **not** load arbitrary policy packages from the Kitchen UI without merge + image rebuild + registration.
- **`infer_runtime_policy_id_for_candidate`** maps `candidate_policy_id` → `runtime_policy_id` for UI and assignment eligibility. Sources: `runtime_policies` list, `mechanical_slot`, `intake_candidate_runtime_map`.
- **Mechanical slot** (`kitchen_mechanical_always_long_v1` → `jup_kitchen_mechanical_v1`) is an **intentional**, documented pairing for the mechanical proof path.
- **`intake_candidate_runtime_map`** was documented as mapping **lab fixture** ids to a deployable id for **testing** the control plane—**not** as “this upload is now that policy’s logic on Jupiter.”

---

## 4. Failure mode: registry as substitute for deployment

| Anti-pattern | Why it fails |
|--------------|--------------|
| Mapping arbitrary `candidate_policy_id` values (e.g. lab uploads) to `jup_mc_test` or similar so **Assign** enables | Assign then means “set active runtime id to **pre-shipped** `jup_mc_test`,” **not** “run this submission’s TS.” |
| Treating **PASS** intake as sufficient for “deployable” | Intake proves **BlackBox evaluation contract**; Jupiter execution is a **different** system with different artifacts. |
| Letting a handful of **hardcoded** policies become the **only** assignable targets | **De facto** standard: every new candidate is “mapped to something we already have” instead of a real pipeline from artifact to runtime. |

**Symptom:** Operators think they are **shipping their policy**; engineering knows Jupiter is still running **whatever module** that id always pointed to.

---

## 5. Symptoms observed

- Candidate **passes** intake; **Assign to runtime** remains **disabled** when `runtime_policy_id` cannot be inferred (honest: no mapping).
- **Temporary** fix: add rows to `intake_candidate_runtime_map` → Assign **enables** but **semantic lie** unless the runtime is extended to load that submission.
- Confusion between **candidate id** (`import_test_v1`) and **runtime** behavior (`jup_mc_test` signal logic).
- Tension: **Archive** exists; **no hard delete**—stale rows remain visible in audit trails, increasing the need for clear **meaning** of each row.

---

## 6. Root cause (concise)

- **Two pipelines** (Kitchen intake vs Jupiter module deployment) were **not** unified under a single **deployable artifact id** that both sides agree on.
- **Registry mapping** was used to **simulate** integration at the **control-plane** layer without **execution** parity.

---

## 7. What “fixed” actually requires (non-exhaustive)

1. **Explicit product decision:**  
   - **A)** Assignment is **only** “switch among shipped Jupiter policies” until further notice; UI must **state** that uploads are **not** executed on Jupiter.  
   - **B)** Build a **real** path: submission revision → build step → registered runtime id → assign selects **that** id (or dynamic load from a known store).

2. **Stop using** `intake_candidate_runtime_map` (or similar) to **pretend** unrelated candidates map to `jup_mc_test` **unless** the purpose is **narrowly** scoped and **labeled** as control-plane / lab only.

3. **UI copy:** When `runtime_policy_id` is missing, **explain** that the candidate is not bound to a **deployable** Jupiter module—not only “registry mismatch.”

4. **Exit criteria for closing this gap:**  
   - Documented **single** story for “upload → what runs on Jupiter” with **proof** (hash, id, or module name), **or**  
   - Explicit **waiver** that Jupiter assignment is **orthogonal** to upload content, with **no** misleading Assign semantics.

---

## 8. References (repo)

- `renaissance_v4/QUANT_KITCHEN_COMPLETED_CHECKLIST.md` — Jupiter does not load arbitrary uploads; manual deploy steps.
- `renaissance_v4/config/kitchen_policy_registry_v1.json` — registry + `description` field (keep aligned with this analysis).
- `renaissance_v4/kitchen_policy_registry.py` — `infer_runtime_policy_id_for_candidate`.
- `renaissance_v4/policy_intake/README.md` — intake API and stages.

---

## 9. Revision history

| Date | Note |
|------|------|
| 2026-04-17 | Initial failure log from triage (Kitchen PASS vs Assign disabled; registry mapping anti-pattern). |
