# Layer 3 — Controlled Approval Interface (Design)

**Status:** Design complete — **UI not implemented** (no Layer 3 product surface in tree at design freeze).  
**Type:** Controlled operator surface — **decision only**, not visibility-only (Layer 2) and not execution (Layer 4).

**Depends on:** [`twig6_approval_model.md`](twig6_approval_model.md) (approval artifact, eligibility, lifecycle, boundaries). Sandbox persistence for approvals today: `approvals` table, [`learning_core/approval_model.py`](../../../scripts/runtime/learning_core/approval_model.py), [`approval_cli.py`](../../../scripts/runtime/approval_cli.py) — **CLI / data model**, not the Layer 3 UI described here.

**This document does not** add execution logic, runtime mutation, Slack/Telegram approval paths, coupling to an execution layer, or automatic approval.

---

## 1. Purpose

**What the Layer 3 approval interface is for**

- A **separate, authenticated** surface where **authorized principals** review **approval artifacts** and record **approve**, **reject**, or **defer**.
- **Read-only presentation** of linked evidence: remediation context, validation run, outcome analysis, pattern pointers, simulation policy snapshot.
- **Auditability**: every decision is attributable (who, when, what changed).

**What it is not for**

- **Not execution** — no “apply remediation,” live rollback, or execution-plane calls.
- **Not Layer 2** — not a read-only glass pane; it **changes approval state** only (bounded writes to the approval store / audit trail).
- **Not messaging** — Slack/Telegram are **not** the control plane for approve/reject/defer.
- **Not automatic approval** — pattern validated or simulation “success” does **not** imply approval; a **human (or explicitly delegated) decision** is required per policy.

---

## 2. Inputs (what it reads)

| Category | Content |
|----------|---------|
| **Approval artifacts** | Fields per Twig 6: e.g. `approval_id`, `source_remediation_id`, `pattern_id`, `validation_run_id`, `simulation_id`, `status`, `requested_by`, `approved_by`, `approval_timestamp`, `expiration_timestamp`, `confidence_score`, `risk_level`, `created_at`. |
| **Linked remediation / pattern / analysis context** | Read-only summaries and IDs: candidate/remediation line, validation result, outcome analysis excerpt, pattern status, simulation row + **policy JSON** — **display only**, no edits. |
| **Constraints** | Eligibility already satisfied when the artifact is **PENDING** (per Twig 6); **approval does not override** simulation policy `would_allow_real_execution` or introduce execution rights in current phase. |
| **Expiration** | For **APPROVED**: show **expiration_timestamp**; **EXPIRED** artifacts are invalid for execution handoff; **REJECTED** terminal for that `approval_id`. |
| **Audit fields** | History of transitions and actors for the artifact (and related scope if policy allows listing sibling requests). |

---

## 3. Allowed actions (only)

| Action | Description |
|--------|-------------|
| **Approve** | **PENDING → APPROVED**: record approver identity, decision timestamp, **TTL / expiration_timestamp** per policy. |
| **Reject** | **PENDING → REJECTED**: terminal for this `approval_id`; new positive path requires a **new** approval request if policy allows. |
| **Defer** | Explicit “not now” / hold: either a future **DEFERRED** status in schema **or** an **audited defer** on **PENDING** (e.g. deferral note + timestamp) **without** silent auto-approve. Implementation must not treat defer as approve. |

---

## 4. Forbidden actions

- **No execute** — no execution triggers, workers, or “run now” from this UI.
- **No rerun** — no re-invocation of pipeline, validation, or simulation from this surface.
- **No remediation mutation** — no INSERT/UPDATE/DELETE on remediation candidates, validations, analyses, patterns, or simulations from Layer 3.
- **No policy editing** — simulation and system policy blobs are **read-only** context.
- **No messaging-triggered approval** — approve/reject/defer are **not** accepted via Slack/Telegram as the authority path.

---

## 5. Safety model

| Topic | Rule |
|-------|------|
| **Who can approve** | Only **authenticated approver principals** (implementation: SSO, RBAC, or equivalent) — not public/unauthenticated links. |
| **How approval is constrained** | Decisions apply only to **eligible** artifacts; cannot override **Twig 6** non-override rules (e.g. `would_allow_real_execution` remains system-level; approval is **eligibility for future gates**, not “flip policy to execute”). |
| **Expiration / revocation** | **APPROVED** shows **expiration**; past expiry → **EXPIRED**; **REJECTED** and **EXPIRED** are clearly **invalid** for execution handoff. |
| **Separation from execution** | **Layer 4** execution (when it exists) must require **non-expired APPROVED**, matching **source_remediation_id**, environment/policy checks, and **separate** execution service — **Layer 3 does not call Layer 4** and does not embed execution hooks. |

---

## 6. Audit requirements

Every **approve**, **reject**, or **defer** must **record and display**:

- **approval_id**
- **Decision** (approve | reject | defer)
- **Actor** (approver identity)
- **Timestamp**
- **Status before → after**
- **Optional reason text** (required or strongly encouraged for reject/defer per policy)
- **expiration_timestamp** when approving

Audit must be **append-only / attributable** — no silent or anonymous state changes.

---

## 7. UI structure (panels / views)

| View | Purpose |
|------|---------|
| **Pending approvals** | Queue of **PENDING** (and deferred per policy); sort/filter by age, risk, remediation id. |
| **Approval detail** | Full artifact fields + risk/confidence + linked IDs. |
| **Linked evidence** | Read-only sections: validation outcome, outcome analysis snippet, pattern status, simulation highlights (including policy fields relevant to “why this is not execution permission”). |
| **Decision history** | Timeline for this **approval_id** (and optionally related remediation scope). |

**Controls:** Only **Approve**, **Reject**, **Defer** (with confirmation where required for approve/reject). **No** execution, pipeline, or messaging actions.

---

## 8. Relationship to Layer 2 and Layer 4

| Layer | Role |
|-------|------|
| **Layer 2 — Operator Dashboard** | **Read-only** visibility — **no** approval state changes. |
| **Layer 3 — Approval interface** | **Decision only** — bounded writes to **approval** (and audit) records. |
| **Layer 4 — Execution interface** | **Execution only** — consumes valid approval + policy + environment; **not** triggered from Layer 3 UI in current architecture. |

---

## Document control

- **Design freeze:** Layer 3 **UI** behavior and boundaries as above; implementation may add transport (e.g. web app) but must not violate forbidden actions or audit rules.
- **Plan/log:** Updates to [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md) and [`../directives/directive_execution_log.md`](../directives/directive_execution_log.md) accompany design acceptance per project sync rules.
