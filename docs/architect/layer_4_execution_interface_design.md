# Layer 4 — Execution Interface (Canonical Design)

**Status:** **Design complete** — **no** Layer 4 production execution interface implemented in tree at design freeze. **Safety mitigation contract** (execution grant, audit-before-effect, single entry point, context match, kill switch) is **section 13** — **normative** for implementation.  
**Related:** [`layer_3_approval_interface_design.md`](layer_3_approval_interface_design.md) (decision only); [`twig6_approval_model.md`](design/twig6_approval_model.md) (future execution handoff); optional read: [`execution_eligibility_gate.md`](design/execution_eligibility_gate.md) (sandbox eligibility evaluation — **not** execution).

**Separation:** Existing [`scripts/runtime/execution_plane/`](../../scripts/runtime/execution_plane/) (Anna / mock proposal path) — **relationship to Layer 4** is **fixed in section 13.3** (single entry point; no parallel remediation path). **Layer 4** here means the **controlled remediation execution** boundary described in Phase 4.x — **distinct** namespace and gates.

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
- **Execution context still valid** — validation run / simulation / environment **match** what the approval assumed per the **context match contract** (**section 13.4**); otherwise **fail closed** (no execution).

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
- **Success grant per approval:** **Section 13.1** — default **one** successful execution per **`approval_id`**.

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

**Audit-before-effect (normative):** **Section 13.2** — a **durable intent record** **must** precede irreversible effects.

**Execution record (minimum):**

- **execution_id**, **approval_id**, **source_remediation_id** (echo), **triggered_by** (principal), **request_timestamp**, **start_timestamp**, **end_timestamp**, **outcome** (success | failed | aborted), **failure_class**, **idempotency_key**, **policy_snapshot_ref** (version/hash).

**Traceability:** **approval → execution** is **queryable** in one direction; **execution** row **must** reference **approval_id**.

**Actor / trigger:** **Who** submitted the execution request (human id or service account) — **mandatory**.

---

## 10. Kill switch / abort

- **Boundary:** **Execution dispatcher / worker** — **not** Layer 2 or Layer 3; **not** messaging or approval UI.
- **Normative contract:** **Section 13.5** (pre-execution block, in-flight cancel, abort/timeout, observability).

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
- **No implementation** in this directive — **design artifact only** (implementation **must** satisfy **section 13** before production execution).
- **No messaging integration** as execution trigger.
- **No hidden execution path** — all execution **must** be **auditable** and tied to **approval_id**.

---

## 13. Safety mitigation contract (pre-implementation)

**Purpose:** Lock a **fixed safety contract** before Layer 4 implementation. Rules below are **normative** for **production** controlled remediation execution unless a future architect directive **explicitly** supersedes them.

### 13.1 Execution grant limit

| Rule | Definition |
|------|------------|
| **Default** | Each **`approval_id`** allows **at most one** execution with **`outcome = success`** (committed success). |
| **After one success** | Any new execution request for the same **`approval_id`** (including a **different** idempotency key) **must** be **rejected** with **`execution_denied`** / **grant_exhausted** (or equivalent), unless **bounded repeat** below applies. |
| **Failed / aborted** | Do **not** consume the **success grant** unless policy explicitly defines partial success as success (default: **they do not**). Retries remain subject to **expiration**, **revocation**, and **context match** (sections 3, 13.4). |
| **Bounded repeat (opt-in only)** | **`max_successes_per_approval_id = N`** where **N > 1** is allowed **only** when the **approval artifact** (or attached policy) **explicitly** records **`allows_multiple_executions: true`** and **`N`**. Default remains **1**. |
| **Idempotency interaction** | Same idempotency key → same outcome (section 6). **Grant** governs **count of successful completions**; idempotency governs **deduplication within** attempts. |

### 13.2 Audit-before-effect rule

| Rule | Definition |
|------|------------|
| **Order** | A **durable execution intent record** **must** be persisted to the **execution audit / intent store** **before** any **irreversible external effect** or **commit** to a protected target system. |
| **Intent minimum** | **`execution_id`**, **`approval_id`**, **`intent_timestamp`**, **`triggered_by`**, **`policy_snapshot_ref`**, **`context_hash`** (or bundled **context_version** fields), **`idempotency_key`**, **`operation_fingerprint`**. |
| **Intent failure** | If intent **cannot** be written → **no** execution; **no** side effects. |
| **Crash window** | If the process **crashes** after intent but before effect: **reconciliation** resumes or marks **`failed`** using the same **`execution_id`** per idempotency; **never** a **second** success for the same **`approval_id`** when grant is exhausted (section 13.1). |
| **WORM / equivalence** | Intent rows are **append-only** (no silent delete). **Equivalent:** append-only intent log plus **reconciliation** against external effect state. |

### 13.3 Single execution entry point

| Rule | Definition |
|------|------------|
| **Layer 4 is sole remediation gate** | **Controlled remediation execution** tied to **sandbox `approval_id`** and production policy **must** go **only** through the **Layer 4** implementation (this specification). **No** parallel “execute approved work” path. |
| **`execution_plane` (Phase 4.3)** | [`scripts/runtime/execution_plane/`](../../scripts/runtime/execution_plane/) is **not** Layer 4 for **remediation**. It **must not** consume **execution grants**, write **Layer 4 intent records**, or perform **approved remediation** against **production** targets. It remains **mock / lab / Anna proposal** unless a directive **replaces** it with an adapter that **only** invokes the **Layer 4** API. |
| **CLI / jobs** | Any operator **CLI**, **cron**, or **job** that performs **approved remediation** **must** be the **Layer 4** entry point (or a documented wrapper that **only** calls it). **No** bypass. |

### 13.4 Context match contract

| Field / rule | Definition |
|--------------|------------|
| **`approval_context_hash`** | Request **must** include a hash (or server-verified equivalent) fixed at **approval commit** time from: **`source_remediation_id`**, linked **validation_run_id(s)** (or explicit none), **simulation_run_id** (or none), **`policy_version`**, **`environment_id`**, and **`operation_fingerprint`** if the approval is operation-specific. Exact composition is **implementation-defined** but **must** be **documented** and **stable** per approval version. |
| **Match** | At **enqueue** and **worker start**, recompute from **current** DB state; **must equal** the request’s **`approval_context_hash`** (**fail closed**). **No drift** unless a **new** approval artifact is issued (new **`approval_id`** or architect-defined **re-baseline**). |
| **Policy snapshot** | **`policy_snapshot_ref`** at execution **must** match an **eligible** policy for that approval (**fail closed**). |
| **Invalidates execution** | Change to approval row, **expiration**, **revocation**, linked **remediation** / **validation** / **simulation** pointers, **environment**, or **policy version** that changes the hash — **unless** superseded by a **new** approval. |
| **Clock** | Expiration uses **server UTC**; execution workers **must** use **NTP-aligned** time; **no** client-trusted clock for gate decisions. |

### 13.5 Kill switch / abort contract

| Phase | Behavior |
|-------|----------|
| **Pre-execution (kill ON)** | **Reject** new requests immediately (**`execution_blocked`** or **503**); **no** new intent records; dispatcher **does not** admit work that would create effects. |
| **In-flight** | **Cooperative cancel** to workers; **no new effects** after cancel is observed; **hard timeout** if the worker does not finish (timeout value **bounded** and **configurable**). |
| **Abort (operator)** | Transition to **`aborted`** with **reason**; **no** success; **compensate** per section 8 if needed. |
| **Timeout** | **`failed`** or **`aborted`** with **`failure_class`**; **never** silent success. |
| **Observability (minimum)** | Observable **`kill_switch`**: **enabled \| disabled**, **scope** (global \| `environment_id`), **`updated_at`**, **`updated_by`**. **Emergency stop** and **kill** changes **audited**. **Queue depth** and **in-flight execution count** exposed for operations. |

---

## Document control

- **Canonical path:** `docs/architect/layer_4_execution_interface_design.md` (this file).
- **Master plan / directive log** updated in the same change set per project sync rules.
- **Safety mitigation addendum:** section **13** (execution grant, audit-before-effect, single entry point, context match, kill switch contract).
