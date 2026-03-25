# Execution Eligibility Gate — Design & Acceptance Contract

**Directive ID:** 4.6.3.6  
**Status:** Design only — **no implementation** authorized by this document.  
**Phase:** 4.x — Execution **boundary** (gate), not execution mechanics.  
**Depends on:** Twig 6 approval model (sandbox implementation closed under **4.6.3.5**); simulation policy and validation pipeline (Twigs 4.x–5).  
**Blocks:** Any **execution implementation** until this design is reviewed, validated, and accepted.

---

## Purpose

Define the **canonical Execution Eligibility Gate**: the layer that answers **whether** an **APPROVED** remediation context may be considered **ready** for a **future** execution layer — **without** performing execution, **without** mutating infrastructure, and **without** overriding simulation policy or approval semantics.

This document establishes:

- **Eligibility artifact** fields and meaning  
- **Strict gating rules** (inputs from approval, validation, simulation)  
- **Separation:** eligibility ≠ execution  
- **Lifecycle** states and transitions  
- **Conceptual CLI** contract (no code)  
- **Safety boundaries**  
- **Future execution handoff** requirements  

**This document does not add code, schemas, Playground changes, approval logic changes, or messaging integration.**

---

## 1. Eligibility artifact definition

An **eligibility** record is a **durable evaluation outcome** that states whether **all strict conditions** are met for a **hypothetical** future execution step, **given** a specific **approval** and evidence pointers. It is **not** execution, **not** approval, and **not** infrastructure change.

### Conceptual structure (fields)

| Field | Description |
|--------|-------------|
| **eligibility_id** | Stable unique identifier for this evaluation record (UUID or equivalent). |
| **approval_id** | References the **APPROVED** (non-expired) approval artifact in the approval store; required anchor. |
| **source_remediation_id** | Same remediation lineage as the approval artifact; must remain consistent with **approval** and evidence rows. |
| **validation_run_id** | Sandbox validation run used in the evaluation (must be **PASS** when status → ELIGIBLE). |
| **simulation_id** | Twig 5 execution simulation row referenced in the evaluation (policy snapshot must be honored). |
| **eligibility_status** | **ELIGIBLE** \| **INELIGIBLE** \| **EXPIRED**. |
| **evaluated_at** | Timestamp when this eligibility outcome was computed or last re-evaluated. |
| **expires_at** | When this **ELIGIBLE** outcome ceases to be valid (mandatory for ELIGIBLE; policy-defined window). |
| **evaluated_by** | Actor or system principal that performed the evaluation (e.g. `eligibility_evaluator_v1`, operator id — format TBD at implementation). |
| **confidence_score** | Optional carry-forward from validation/analysis for **display and policy** only — **not** a substitute for gates. |
| **risk_level** | Informational category for operators; **does not** bypass any gate. |

**Notes:** Storage format (tables, JSON) is **out of scope** here. Multiple evaluations over time may produce new **eligibility_id** values; supersession rules are a **future implementation** detail.

---

## 2. Eligibility rules (strict)

An evaluation **may** yield **ELIGIBLE** only when **all** of the following hold simultaneously:

1. **Approval must be APPROVED**  
   The referenced **approval_id** exists and **status = APPROVED**.

2. **Approval must not be expired**  
   Approval **expiration** semantics (per approval model) must not have invalidated the approval at **evaluated_at** (and must remain valid through the intended **expires_at** window for ELIGIBLE, per policy).

3. **Validation must PASS**  
   The referenced **validation_run_id** must correspond to a sandbox validation result of **pass** for the same **source_remediation_id** chain.

4. **Simulation must exist**  
   **simulation_id** must reference a completed Twig 5 simulation row for that thread (synthetic execution + policy JSON).

5. **Simulation policy (current system phase)**  
   The stored simulation policy must still show **`would_allow_real_execution: False`**. The system remains in the **no-real-hooks** phase at the **eligibility** layer as well.

### Non-override rule (mandatory)

**Eligibility does NOT override simulation policy.**  
If policy states **`would_allow_real_execution: False`**, that remains true at the **system** level: **ELIGIBLE** means **“all preconditions for a future execution phase are satisfied at the gate layer,”** not **“policy now allows real execution.”** Any future phase that introduces real execution must **re-evaluate** policy, environment, and invocation rules; **eligibility alone** does not flip **`would_allow_real_execution`** to true.

### If any rule fails

The outcome **must** be **INELIGIBLE** (or **EXPIRED** if the record was previously ELIGIBLE and time/evidence invalidation applies — see §4).

---

## 3. Eligibility ≠ execution

| Principle | Statement |
|------------|------------|
| **Eligibility does NOT trigger execution** | Creating or storing an **ELIGIBLE** record **must not** enqueue work, call services, or mutate systems. |
| **Eligibility does NOT mutate infrastructure** | No config writes, no SSH, no remediation actions. |
| **Eligibility only marks readiness** | It is a **gate artifact** for a **future** execution layer that **does not exist** in this design phase. |
| **Execution layer does not exist yet** | No worker, hook, or job may perform live remediation based solely on this document. |

---

## 4. Eligibility lifecycle

### States

- **ELIGIBLE** — All strict rules (§2) satisfied at **evaluated_at**; **expires_at** set; valid until expiry or invalidation.  
- **INELIGIBLE** — One or more rules failed; or **drift** after a prior ELIGIBLE (re-evaluation).  
- **EXPIRED** — Time-based end of validity for a previously **ELIGIBLE** record **or** explicit invalidation when **expires_at** &lt; now.

### Transitions (conceptual)

```
Evaluation with all rules PASS
         │
         ▼
     ELIGIBLE ──(time passes)──▶ EXPIRED
         │
         │   (re-eval: rule fails)
         ▼
INELIGIBLE ◀── (initial evaluation or drift)
```

- **APPROVED (approval) → ELIGIBLE (eligibility):** Not a direct DB transition on the **approval** row; means a **new eligibility evaluation** produced **ELIGIBLE** while **approval** remains **APPROVED** and non-expired.  
- **ELIGIBLE → EXPIRED:** When **now &gt; expires_at** or global invalidation.  
- **ELIGIBLE → INELIGIBLE:** Re-evaluation when validation/simulation/approval evidence **drifts** or **fails** re-check.

---

## 5. Interface contract (CLI — conceptual only)

**No implementation.** Future **read-only** tooling might expose:

### Evaluate

```text
eligibility --evaluate --approval-id <approval_id>
            [--evaluated-by <principal>]
```

**Inputs:** **approval_id** (required); optional **evaluated_by**.  
**Outputs:** **eligibility_id**, **eligibility_status**, **evaluated_at**, **expires_at**, **reason** if INELIGIBLE; **no** side effects on infrastructure.

### Status

```text
eligibility --status --eligibility-id <eligibility_id>
```

**Outputs:** Full structured view of the eligibility record + **whether** it is still **EXPIRED** by time.

---

## 6. Safety boundaries

| Boundary | Rule |
|----------|------|
| **Eligibility cannot trigger execution** | No code path may enqueue or perform live remediation from **ELIGIBLE** alone. |
| **Eligibility cannot bypass approval** | **ELIGIBLE** requires a valid **APPROVED** approval artifact. |
| **Eligibility cannot bypass validation** | **PASS** validation reference is mandatory for **ELIGIBLE**. |
| **Eligibility cannot originate from Playground** | Playground is **visibility** only; it **must not** create eligibility records. |
| **Eligibility cannot alter approval state** | Evaluations **read** approval/validation/simulation; they **do not** approve, reject, or re-open approvals. |

---

## 7. Execution handoff contract (future)

When an **execution layer** exists, it **must** require **all** of the following before any **real** remediation action:

| Requirement | Description |
|-------------|-------------|
| **valid eligibility_id** | Points to an **ELIGIBLE** record that is **not EXPIRED** at decision time. |
| **valid approval_id** | Matches the eligibility record; approval still **APPROVED** and not expired. |
| **non-expired eligibility** | **now ≤ expires_at** (and any **invalidation** rules satisfied). |
| **matching environment context** | Cluster / environment / policy version matches what was assumed — **no silent promotion** from sandbox to production. |
| **explicit execution invocation** | Execution is **not** automatic from eligibility; a **separate, explicit** invocation with **auditable** intent is required (exact shape TBD in execution design). |

**Additional gate:** Real execution remains **blocked** while **`would_allow_real_execution`** is **False** at the system policy level; **eligibility + approval** do **not** override that.

---

## Layer separation summary

| Layer | Role |
|-------|------|
| **Visibility (Playground, dashboards)** | Observe pipelines; **no** approval; **no** eligibility; **no** execution. |
| **Approval** | Human/eligible decision on a remediation context; **approval ≠ execution**. |
| **Eligibility gate** | **Read-only** evaluation: **ELIGIBLE / INELIGIBLE / EXPIRED**; **does not** execute. |
| **Execution (future)** | **Only** after explicit design + implementation; consumes **eligibility_id** + **approval_id** + **policy** + **explicit invocation**. |

---

## Review gate

**No execution implementation** until this design is **reviewed and accepted** by Chief Architect, Coordinator, and relevant reviewers.

**Enforcement:** Any implementation **must** conform to this document; **no authority creep** — **eligibility does not imply execution**.
