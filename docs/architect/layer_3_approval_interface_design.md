# Layer 3 — Approval Interface (Canonical Design)

**Status:** **Design complete**; **decision surface implemented** in [`scripts/runtime/approval_interface/`](../scripts/runtime/approval_interface/) (WSGI + token-guarded POST). This document remains the **canonical** design record.  
**Related:** Approval **artifact** model — [`design/twig6_approval_model.md`](design/twig6_approval_model.md); persistence — `learning_core/approval_model.py`, `approval_cli.py`.

---

## 1. Purpose

**What Layer 3 is**  
The **controlled approval interface**: an authenticated operator surface that sits **between** Layer 2 (read-only visibility) and Layer 4 (execution). It exists to record **human (or policy-delegated) decisions** on **approval artifacts** — **approve**, **reject**, or **defer** — with **audit**.

**What it does**

- Presents **approval artifacts** and **read-only** linked context (remediation, validation, analysis, pattern pointers, simulation/policy snapshot).
- Performs **only** the allowed state transitions on **approval** (and audit) records per policy.
- Makes **expiration**, **rejection**, and **audit** visible so operators and downstream systems know what is valid.

**What it does NOT do**

- **Does not execute** remediation or touch live systems.
- **Does not** replace Layer 2 (no general monitoring; no read-only-only mandate — Layer 3 **writes approval decisions only**).
- **Does not** use Slack/Telegram as the authority path for approve/reject/defer.
- **Does not** auto-approve because a pattern is “validated” or a simulation “succeeded.”

---

## 2. Inputs

The approval interface **reads** (displays; **no mutation** of these rows except via explicit forbidden-scope rules below):

| Input | Description |
|--------|-------------|
| **Approval artifacts** | e.g. `approval_id`, `source_remediation_id`, `pattern_id`, `validation_run_id`, `simulation_id`, `status`, `requested_by`, `approved_by`, timestamps, `confidence_score`, `risk_level` (per Twig 6). |
| **Linked remediation / pattern / analysis** | Read-only views: candidate/remediation summary, validation outcome, outcome analysis excerpt, pattern row **as context** (not as approval substitute). |
| **Expiration state** | For **APPROVED**: `expiration_timestamp`; **EXPIRED** / **REJECTED** clearly indicated. |
| **Audit fields** | Prior decisions, actors, times — for traceability and history panels. |
| **Constraints** | Eligibility for **PENDING** already enforced at request creation; system simulation policy (e.g. `would_allow_real_execution`) is **not** overridden by approval in current phase. |

---

## 3. Allowed actions (ONLY)

| Action | Meaning |
|--------|---------|
| **Approve** | **PENDING → APPROVED** — record approver, time, **expiration** per policy. |
| **Reject** | **PENDING → REJECTED** — terminal for this `approval_id`. |
| **Defer** | Hold / “not now” — **audited** deferral (schema may add **DEFERRED** or defer-on-PENDING with note) — **must not** auto-approve. |

No other primary actions.

---

## 4. Forbidden actions

- **No execution** — no triggers to execution plane, workers, or “apply now.”
- **No rerun** — no re-run of pipeline, validation, or simulation from this interface.
- **No mutation of pipeline artifacts** — no INSERT/UPDATE/DELETE on remediation candidates, validation runs, outcome analyses, **remediation_patterns** / pattern registry rows, or execution simulations **from Layer 3**.
- **No policy editing** — policy JSON and system gates are **read-only** context.
- **No messaging-triggered approval** — Slack/Telegram (or any messenger) **must not** be the control plane for approve/reject/defer decisions.

---

## 5. Safety model

| Topic | Definition |
|--------|------------|
| **Separation from execution** | Layer 3 **never** calls Layer 4. Execution is a **different** service boundary and requires its own gates (approval id, non-expiry, environment, policy version). |
| **Separation from pattern registry** | **Promoting/changing** pattern lifecycle (candidate → validated, etc.) is **not** Layer 3. Layer 3 may **display** pattern id/status as **evidence** only; it does **not** mutate `remediation_patterns` or registry rules. |
| **Approval ≠ execution** | An **APPROVED** artifact is **eligibility for future execution subject to other gates**, not permission to execute now. Simulation policy **does not** flip to “allow real execution” from this UI alone (per Twig 6). |
| **Expiration / revocation visibility** | Operators always see whether an artifact is **valid for handoff** (approved + not expired) vs **EXPIRED** / **REJECTED**. |
| **Human decision boundary** | Approve/reject/defer are **explicit human (or explicitly delegated) decisions** — not silent automation from telemetry or chat. |

---

## 6. Audit requirements

**Recorded** (append-only / attributable, implementation detail):

- **approval_id**, **decision** (approve \| reject \| defer), **actor**, **timestamp**, **status before → after**, **expiration_timestamp** when approving, **reason** where policy requires (reject/defer).

**Visible** in UI:

- Same fields in **decision history**; linked ids for traceability to validation/simulation/remediation.

**Traceability**

- Every decision links to **approval_id**; history must support “who approved what, when, under which artifact.”

---

## 7. UI structure

| View | Role |
|------|------|
| **Pending approvals** | Queue of items awaiting decision (PENDING / deferred per policy); sort/filter. |
| **Approval detail panel** | Full artifact fields, risk/confidence, linked ids. |
| **Evidence context panel** | Read-only: validation outcome, analysis snippet, pattern status, simulation highlights (policy fields explaining non-execution). |
| **Decision history** | Timeline of transitions for the artifact (and related scope if allowed). |

**Controls:** only **Approve**, **Reject**, **Defer** (+ confirmations as required). **No** execution, pipeline, or messaging actions.

---

## 8. Layer relationship (no bypass)

| Layer | Responsibility |
|-------|----------------|
| **Layer 2** | **Visibility only** — read-only dashboard; **no** approval state changes. |
| **Layer 3** | **Decision only** — approval artifact transitions + audit. |
| **Layer 4** | **Execution only** — runs only under execution policy and gates. |

**No cross-layer bypass:** Visibility (L2) cannot substitute for approval (L3). Approval (L3) cannot trigger execution (L4) directly. Execution (L4) must not skip approval/eligibility checks defined for the phase. Messaging channels are **not** shortcuts into L3 or L4.

---

## Document control

- **Canonical path:** `docs/architect/layer_3_approval_interface_design.md` (this file).
- Supersedes informal discussion; older duplicate path [`design/layer3_approval_interface.md`](design/layer3_approval_interface.md) points here.
