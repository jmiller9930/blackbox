# Layer 4 — Execution Interface (Canonical Design)

**Status:** **Design complete** — **no** Layer 4 production execution interface implemented in tree at design freeze.  
**Related:** [`layer_3_approval_interface_design.md`](layer_3_approval_interface_design.md) (decision only); [`twig6_approval_model.md`](design/twig6_approval_model.md) (future execution handoff); optional read: [`execution_eligibility_gate.md`](design/execution_eligibility_gate.md) (sandbox eligibility evaluation — **not** execution).

**Separation:** Existing [`scripts/runtime/execution_plane/`](../../scripts/runtime/execution_plane/) (Anna / mock proposal path) is **out of scope** for this document unless a future directive explicitly merges paths. **Layer 4** here means the **controlled remediation execution** boundary described in Phase 4.x — **distinct** namespace and gates.

---

## 1. Purpose

**What Layer 4 execution is**  
The **action layer**: the only authorized place to **perform** a **bounded real-world or system operation** that was **explicitly approved** under a valid **`approval_id`**, subject to **policy**, **environment**, and **audit**.

**What it does**

- Accepts an **explicit execution request** (human or explicitly delegated service principal) referencing **`approval_id`** and **validated execution context**.
- **Re-validates** approval and gates **immediately before** side effects.
- **Runs** the permitted operation (sync or async per section 6 mental model).
- **Records** immutable **execution audit** linking **approval_id → execution_id → outcome**.

**What it is not**

- **Not** detection, learning, pattern promotion, or simulation (Layers / Twigs upstream).
- **Not** approval (Layer 3) or read-only visibility (Layer 2).
- **Not** messaging — Slack/Telegram do **not** trigger execution.
- **Not** “auto-run because green dashboard / validated pattern / successful simulation.”

---

## 2. Inputs

Execution **must** require all of the following:

| Input | Requirement |
|--------|-------------|
| **`approval_id`** | Must resolve to an **APPROVED** artifact (or production equivalent) **eligible** for execution under policy. |
| **Linked remediation / context** | **source_remediation_id**, validation/simulation pointers **consistent** with the approval row (or explicit policy for re-baselining). |
| **Validity checks** | System **policy** (e.g. `would_allow_real_execution` and successors), **environment** (cluster/env id), **maintenance window**, **policy version** — **all** must pass per phase rules. |
| **Expiration / revocation checks** | **now ≤ expiration_timestamp**; status **APPROVED**; **not** superseded/revoked per policy. |

---

## 3. Preconditions

- **Approval status** = **APPROVED** (not PENDING, REJECTED, DEFERRED, EXPIRED).
- **Not expired** — compare wall-clock to **expiration_timestamp** (and any shorter **execution token** window if introduced later).
- **Not revoked** — if revocation or supersession exists, **approval_id** must still be **active**.
- **Execution context still valid** — validation run / simulation / environment **match** what the approval assumed, within defined tolerance; otherwise **fail closed** (no execution).

---

## 4. Allowed actions

**Exactly:** **execution trigger** — submit **one** bounded operation **authorized** by the **approval_id** and **context** (e.g. “apply remediation step X,” “invoke connector Y with args Z” — **concrete operation types** to be fixed at implementation time).

**Does not include:** mutating **upstream** sandbox tables (remediation candidates, validation runs, outcome analyses, patterns, simulations) **as part of** execution — those remain **read** for proof; **execution** writes go to **execution audit** and **external effect** targets only, per operation contract.

---

## 5. Forbidden actions

- **Execution without** a **valid** **approval_id** path (no bypass of Layer 3).
- **Slack/Telegram-triggered execution** as the **control plane** (notifications may exist; they **must not** carry execution authority).
- **Simulation-triggered** or **pattern-triggered** execution.
- **Policy editing** during execution request handling (policy is **read** + **evaluate** only).
- **Mutation of upstream learning/pipeline artifacts** (insert/update/delete on detection/validation/analysis/pattern/simulation tables) **from** the execution interface — **forbidden**; only **execution audit** and **authorized external effects**.

---

## 6. Idempotency / replay protection

- Every execution request carries a **client-supplied idempotency key** (or server-generated dedupe hash of **approval_id + operation fingerprint + context version**).
- **Duplicate** requests with the same key while a run is **completed** → return **same outcome reference** (no double effect).
- **Duplicate** while **in progress** → **single** underlying work (coalesce or reject duplicate with **reference** to active **execution_id**).
- **Replay** after failure: **new** idempotency key or explicit **retry policy** — **never** silent double-apply.

---

## 7. Concurrency / race conditions

| Scenario | Behavior |
|----------|----------|
| **Concurrent execution attempts** (same **approval_id**) | **At most one** **mutating** execution in flight per **approval_id** + **operation class** unless policy explicitly allows parallel disjoint operations (default: **serialize** or **reject** second with **409**-style semantics). |
| **Approval state changes during execution** | **Pre-check** at enqueue and **re-check** at **worker start**; if approval **no longer APPROVED** or **expired**, **abort** before side effects; if effects already started, **compensate** per section 8. |

---

## 8. Partial failure / rollback model

| Topic | Design |
|--------|--------|
| **Failure classes** | e.g. **precheck_failed**, **infra_unavailable**, **partial_apply**, **compensation_failed** — **typed** for audit and operator response. |
| **Rollback expectations** | Operations declare **compensating action** or **manual recovery**; **best-effort** rollback when safe; **never** claim success if compensation incomplete. |
| **Abort** | **Kill** or **timeout** → transition to **aborted** / **failed** with **reason**; **no** “success” unless invariants hold. |

---

## 9. Audit requirements

**Execution record (minimum):**

- **execution_id**, **approval_id**, **source_remediation_id** (echo), **triggered_by** (principal), **request_timestamp**, **start_timestamp**, **end_timestamp**, **outcome** (success | failed | aborted), **failure_class**, **idempotency_key**, **policy_snapshot_ref** (version/hash).

**Traceability:** **approval → execution** is **queryable** in one direction; **execution** row **must** reference **approval_id**.

**Actor / trigger:** **Who** submitted the execution request (human id or service account) — **mandatory**.

---

## 10. Kill switch / abort

- **Kill switch:** A **global** or **per-environment** flag that **blocks all new execution** and may **signal cancel** to in-flight work (exact mechanics implementation-defined). Boundary: **execution dispatcher / worker** — **not** Layer 2 or Layer 3.
- **Emergency stop:** Operator action to **drain** or **abort** queue; **audited**.
- **Where it lives:** **Outside** messaging and **outside** approval UI — **execution control plane** only (future module).

---

## 11. Layer separation (no bypass)

| Layer | Role |
|-------|------|
| **Layer 2** | **Visibility** — read-only; **no** execution. |
| **Layer 3** | **Decision** — approve/reject/defer; **no** execution. |
| **Layer 4** | **Action** — execute **only** with valid **approval** + gates. |

**No bypass:** L2 cannot approve or execute. L3 cannot execute. L4 cannot approve. Messaging cannot substitute for L3/L4.

---

## 12. Non-goals

- **No automation** of execution in this design phase (no schedulers, no “auto-heal” without a future directive).
- **No implementation** in this directive — **design artifact only**.
- **No messaging integration** as execution trigger.
- **No hidden execution path** — all execution **must** be **auditable** and tied to **approval_id**.

---

## Document control

- **Canonical path:** `docs/architect/layer_4_execution_interface_design.md` (this file).
- **Master plan / directive log** updated in the same change set per project sync rules.
