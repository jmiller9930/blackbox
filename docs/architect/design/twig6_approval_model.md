# Twig 6 — Approval Model Design & Acceptance Contract

**Status:** Design only — **no implementation** authorized by this document.  
**Phase:** 4.x — Approval layer (future); **DATA Twig 6** in master plan terms (“Controlled Remediation Execution” remains **stub**; **this** document defines the **approval artifact and gates** that must exist **before** any execution-layer work).  
**Depends on:** Playground output contract and sandbox remediation pipeline (Twigs 4.x–5) as **visibility/diagnostic** inputs only — **not** approval sources.

---

## Purpose

Define the **canonical approval model** for BlackBox **before** any persistence, runtime integration, or execution hooks. This establishes:

- what an **approval artifact** is and what fields it carries;
- **eligibility** for entering the approval process;
- strict **boundary** between **simulation**, **approval**, and **execution**;
- **lifecycle** and **invalidation** rules;
- a **conceptual CLI contract** for human/system decisions;
- **safety boundaries** and a **future execution handoff** contract.

**This document does not modify code, schemas, Playground, Slack, Telegram, Anna, or Cody.**

---

## 1. Approval artifact definition

An **approval** is a **durable, auditable record** that a **human or designated approver** has reviewed a specific **remediation context** and **granted or denied eligibility** for a **future** execution phase. It is **not** execution and **not** infrastructure mutation.

### Conceptual structure (fields)

| Field | Description |
|--------|-------------|
| **approval_id** | Stable unique identifier for this approval record (UUID or equivalent). |
| **source_remediation_id** | Remediation candidate ID in the **sandbox / learning** lineage that was reviewed (must match the chain under review). |
| **pattern_id** | Optional. Pattern row associated with the proposed remediation path, if applicable; **absence** allowed when approval is tied only to validation/simulation evidence. |
| **validation_run_id** | Sandbox validation run that was part of the evidence package (must reference a **PASS** run when status → APPROVED; see eligibility). |
| **simulation_id** | **Execution simulation** row ID (`remediation_execution_simulations` / Twig 5 semantics) proving a policy-evaluated simulation exists for this thread. |
| **requested_by** | Actor who requested approval (e.g. operator id, system principal — format TBD at implementation time). |
| **approved_by** | Actor who approved or rejected (human or delegated approver id); empty while **PENDING**. |
| **approval_timestamp** | When the decision was recorded (or null until decision). |
| **expiration_timestamp** | When this approval ceases to be valid if **APPROVED** (mandatory for APPROVED state; see lifecycle). |
| **status** | **PENDING** \| **APPROVED** \| **REJECTED** \| **EXPIRED**. |
| **confidence_score** | Optional aggregate confidence carried forward from validation/analysis for **display and policy** only — **not** a substitute for human judgment. |
| **risk_level** | Categorical risk (e.g. low / medium / high / blocked) derived from policy + context — **informational** for approvers. |

**Notes (non-normative for implementation phase):**

- Storage format (table names, JSON blobs) is **out of scope** here.
- **pattern_id** optional preserves cases where approval is anchored on validation + simulation without a promoted pattern row.

---

## 2. Approval eligibility rules

Approval **may be requested** only when **all** of the following hold:

1. **Validation must PASS**  
   The referenced **validation_run_id** must correspond to a sandbox validation result of **pass** for the same **source_remediation_id** chain under review.

2. **Simulation must exist**  
   A **simulation_id** must reference a completed **Twig 5** simulation record for the same remediation/pattern thread (synthetic execution record + policy snapshot).

3. **Simulation policy (current phase)**  
   The stored simulation policy must show **`would_allow_real_execution: False`** — i.e. the system remains in the **no-real-hooks** phase; simulation is **explicitly not** granting execution rights.

### Non-override rule (mandatory)

**Approval does NOT override simulation policy in this phase.**  
If policy states **`would_allow_real_execution: False`**, that remains true at the **system** level: approval means **“eligible for future execution subject to future gates,”** not **“policy now allows real execution.”** Any future phase that introduces real execution must **re-evaluate** policy and environment; approval alone does not flip **`would_allow_real_execution`** to true.

### What eligibility does not require (clarification)

- Eligibility does **not** require Playground to have been used; Playground is **never** an approval origin (see §6).
- Eligibility does **not** imply Slack/Telegram/Anna approval; those channels remain **out of scope** for this design’s approval issuance unless a later directive explicitly scopes them.

---

## 3. Approval does not mean execution

| Principle | Statement |
|-----------|------------|
| **approval ≠ execution** | An **APPROVED** artifact is a **gate artifact** only. No remediation action is performed by creating or storing it. |
| **Approval grants eligibility only** | It signals that a **named approver** accepted risk and scope for a **specific** remediation id / evidence bundle **until expiration** or **invalidation**. |
| **Execution layer does not exist yet** | No worker, hook, or job may perform live remediation based on this design document. Twig 6 **live execution** remains **stub** in the master plan until a separate implementation directive. |
| **No component may act on approval yet** | Runtime dispatch, DATA response generation, Telegram/Slack bots, and Playground **must not** interpret approval as a command to execute. |

---

## 4. Approval lifecycle

### States

- **PENDING** — Request created; awaiting **approved_by** / decision timestamp.
- **APPROVED** — Decision positive; **expiration_timestamp** set; artifact valid until expiry or invalidation.
- **REJECTED** — Decision negative; terminal for this **approval_id** (new request needs a new **approval_id** if policy allows retry).
- **EXPIRED** — Time-based end of validity for **APPROVED**; or system-marked when superseded (see below).

### Transitions

```
                    ┌─────────────┐
                    │   PENDING   │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
     REJECTED         APPROVED      (withdraw/cancel
     (terminal)           │          → TBD policy)
                          │
                          ▼
                      EXPIRED
                    (time-based or
                     supersession)
```

- **PENDING → APPROVED:** Approver records **approved_by**, **approval_timestamp**, **expiration_timestamp**, **status = APPROVED**.
- **PENDING → REJECTED:** Approver records rejection; **approval_timestamp** may still be set; **expiration_timestamp** N/A or null.
- **APPROVED → EXPIRED:** Automatic when **now > expiration_timestamp**, or when explicitly invalidated (see below).

### Expiration rules (conceptual)

- Every **APPROVED** record **must** have **expiration_timestamp** (max validity window defined by policy, e.g. 24h / 7d — exact duration is a **future policy** decision).
- After expiry, status becomes **EXPIRED**; the artifact **must not** be used for execution handoff.

### Re-approval conditions

- A **new** **approval_id** is required after **REJECTED**, **EXPIRED**, or **invalidation** if the operator wants a fresh **APPROVED** state.
- Re-approval **must** re-validate that eligibility rules (§2) still hold with **current** validation_run_id / simulation_id references (or updated references if the chain was re-run).

### Invalidation triggers (non-exhaustive)

- **Supersession:** A newer approval for the same **source_remediation_id** + scope may mark the previous **APPROVED** as **EXPIRED** or **invalidated** per policy.
- **Evidence drift:** If validation or simulation records are **superseded** or **deleted** in a future schema, existing approvals referencing them become **invalid** (implementation must define detection).
- **Policy change:** Global policy version bump may invalidate all open **PENDING** or shorten **APPROVED** windows — **exact mechanics** deferred to implementation.

---

## 5. Interface contract (CLI level — conceptual only)

**No implementation.** The following defines **inputs/outputs** for a **future** approval tool (not Playground).

### Approve

```text
approve --remediation-id <source_remediation_id>
        [--validation-run-id <id>]
        [--simulation-id <id>]
        [--pattern-id <id>]
        [--approver <approved_by>]
        [--ttl <duration>]
```

**Required inputs (conceptual):**

- **source_remediation_id** — ties to the remediation chain.
- Evidence pointers: **validation_run_id** and **simulation_id** must be supplied or **resolvable** by the tool from context; both must satisfy §2.

**Outputs:**

- **approval_id**, **status** (= APPROVED or error), **expiration_timestamp**, echo of linked ids; **no** side effects on infrastructure.

### Reject

```text
reject --remediation-id <source_remediation_id>
       [--approver <approved_by>]
       [--reason <text>]
```

**Outputs:**

- **approval_id** (or request id), **status** = REJECTED; **no** execution or infra changes.

### List / show (optional future)

- Query by **remediation_id**, **status**, **approver** — **read-only** relative to execution.

---

## 6. Safety boundaries

| Boundary | Rule |
|----------|------|
| **Approval cannot trigger execution** | No code path may enqueue, call, or imply live remediation from **APPROVED** alone. |
| **Approval cannot modify infrastructure** | No APIs, SSH, or config writes as part of approval recording. |
| **Approval cannot bypass validation** | **APPROVED** requires a **PASS** validation reference per §2; forging or omitting validation references is invalid. |
| **Approval cannot originate from Playground** | Playground is **sandbox-only visibility**; it **must not** create, approve, or imply **approval_id**. Operators use **future** dedicated approval surfaces (CLI/UI), not the Playground pipeline. |

---

## 7. Future execution handoff contract

When an **execution layer** exists (post–Twig 6 stub), it **must** require **all** of the following before any **real** remediation action:

| Requirement | Description |
|-------------|-------------|
| **valid approval_id** | Exists in the approval store; cryptographically or administratively integrity-protected (implementation detail). |
| **non-expired state** | **status == APPROVED** and **now ≤ expiration_timestamp** (and not invalidated). |
| **matching source_remediation_id** | Execution target matches the approval’s **source_remediation_id**. |
| **matching environment context** | **Environment** / cluster / maintenance window / policy version matches what approval assumed (exact matching rules TBD; must include **no silent promotion** from sandbox DB to production). |

**Additional gate:** Execution must still respect **simulation policy evolution**: if **`would_allow_real_execution`** remains **False** at the system level, **no** real hook may run regardless of approval — until a **future directive** explicitly enables hooks and aligns policy. **Approval + policy + environment** must **all** pass.

---

## Separation summary

| Layer | Role |
|-------|------|
| **Visibility (Playground, dashboards)** | Observe pipeline stages; **no** approval; **no** execution. |
| **Approval** | Human/eligible decision; **eligibility only**; **no** execution. |
| **Execution (future)** | **Only** after explicit implementation; consumes **approval_id** + **policy** + **context**; **not** defined here. |

---

## Acceptance checklist (design)

- [x] Approval artifact fields defined (§1).
- [x] Eligibility rules + simulation policy non-override (§2).
- [x] Approval ≠ execution (§3).
- [x] Lifecycle and expiration (§4).
- [x] Conceptual CLI (§5).
- [x] Safety boundaries (§6).
- [x] Future execution handoff (§7).
- [x] No code, no DB schema, no runtime integration in this document.

---

## Review gate (before any Twig 6 implementation directive)

Design review required from:

- **Chief Architect**
- **Chris (Coordinator)**
- Relevant sub-agents (e.g. policy, security, data)

**No implementation directive for Twig 6** until this design is **reviewed and accepted** per project governance.
