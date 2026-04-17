# Policy assignment systems map (Kitchen → runtime → reverse truth)

**Audience:** Architect, runtime ops, dashboard engineering  
**Scope:** How Quant Research Kitchen policy assignment is **designed** to work — **forward assignment** and **reverse assignment** together — which **Legos** (files, stores, APIs, env) connect, and **where friction shows up today**.  
**Status:** Living document — asks for a consolidated overview at the end.

---

## 1. What you are mapping

The assignment mechanism is **not** only “Kitchen pushes to the target.” It is **two coupled halves**:

| Half | Direction | What happens |
|------|-----------|----------------|
| **Forward assignment** | Kitchen → execution target | Operator runs the Kitchen assign path; BlackBox **POST**s `active-policy` to the target and **only then** persists assignment + ledger + lifecycle after **GET** read-back matches. |
| **Reverse assignment** | Trade surface / runtime → Kitchen | There is **no** inbound webhook from Jupiter to BlackBox. “Reverse” is implemented as **pull**: the same **GET …/policy** used for truth drives **reconcile** (collapse Kitchen row to runtime when approved), **external** ledger entries, **drift** state, and **lifecycle** updates when runtime diverged from what Kitchen last recorded. |

Both halves are required for a coherent story: forward establishes intent and proof; reverse keeps Kitchen from lying when the world changes outside Kitchen.

Two different “truths” exist in the system:

| Truth | Meaning |
|-------|---------|
| **Kitchen record** | What BlackBox persisted after an operator action from the Kitchen flow (`kitchen_runtime_assignment.json`). |
| **Runtime truth** | What the **execution target** reports as `active_policy` over HTTP (`GET …/policy`). |

**Design rule (DV-074 / DV-070):** Runtime GET is **authoritative** for “what is live.” Kitchen may **push** intent to the target, but if someone changes policy on the trade surface (Jupiter operator UI, another control plane, or misconfigured base URL), the next Kitchen read **reconciles** the local row toward runtime or records **drift**.

---

## 2. Glossary (Lego names)

- **Candidate** — A policy submission that passed intake (`intake_report.json` with `pass: true`, `candidate_policy_id`, etc.). Listed via candidates registry (DV-061).
- **Mechanical candidate** — The proof policy id `kitchen_mechanical_always_long_v1` mapped in `kitchen_policy_registry_v1.json` under `mechanical_slot.{jupiter|blackbox}` to a fixed **runtime policy id** (e.g. `jup_kitchen_mechanical_v1`). This is the path `assign_mechanical_candidate` implements.
- **Execution target** — `jupiter` (Sean Jupiter stack) or `blackbox` (reserved BlackBox control plane). Normalized by `renaissance_v4/execution_targets.py`.
- **Kitchen policy registry** — `renaissance_v4/config/kitchen_policy_registry_v1.json`: allowed runtime policy ids per target + mechanical slot mapping (DV-074).
- **Assignment store** — `renaissance_v4/state/kitchen_runtime_assignment.json` (`kitchen_runtime_assignment_store_v1`).
- **Lifecycle store** — `renaissance_v4/state/kitchen_policy_lifecycle_v1.json` per `(submission_id, execution_target)` (DV-069).
- **Ledger** — Append-only history in `kitchen_policy_ledger` (Kitchen assigns + external drift).
- **Trade surface** — Operator-facing place where active policy can change **without** going through Kitchen (e.g. Jupiter web UI calling Sean’s `POST /api/v1/jupiter/active-policy`). That change is **reverse assignment** material: Kitchen learns it on the next read, not via a separate “assign back” API.
- **Reverse assignment** — Not a POST from target to Kitchen; it is the **reconciliation pipeline** on `GET …/renaissance/kitchen-runtime-assignment` (runtime GET → `maybe_record_external_runtime_change` → `reconcile_assignment_store_to_runtime_truth` → `drift_status` → `reconcile_with_drift`). Same endpoint family as forward truth, opposite causal direction.

---

## 3. Intended forward flow (candidate → Kitchen → target inherits)

This is the **happy path** when everything goes through Kitchen.

```mermaid
flowchart LR
  subgraph intake["Policy intake"]
    A[Policy package upload] --> B[intake_report.json pass]
    B --> C[candidate_policy_id + execution_target]
  end
  subgraph kitchen["Kitchen decision"]
    C --> D{Mechanical proof candidate?}
    D -->|kitchen_mechanical_always_long_v1| E[Registry mechanical_slot → active_runtime_policy_id]
  end
  subgraph push["Push to target"]
    E --> F[POST .../active-policy Bearer]
    F --> G[GET .../policy read-back]
    G -->|active_policy matches| H[Write assignment store + ledger + lifecycle confirmed]
  end
  subgraph target["Execution target"]
    H --> I[Jupiter or BlackBox runs active_policy]
  end
```

**Step-by-step (mechanical path, as implemented):**

1. **Intake succeeds** — `assign_mechanical_candidate` reads `renaissance_v4/policy_intake/submissions/{id}/report/intake_report.json` and requires `pass`, correct `candidate_policy_id`, and matching `execution_target`.
2. **Registry resolves slot** — `mechanical_slot_safe` + `runtime_policy_approved` ensure the target runtime policy id is listed in the registry.
3. **Outbound HTTP (Kitchen API host → target)** — For Jupiter: `POST {KITCHEN_JUPITER_CONTROL_BASE}/api/v1/jupiter/active-policy` with `{"policy": "<active_runtime_policy_id>"}` and Bearer token; then `GET …/jupiter/policy` to verify. BlackBox path mirrors with `KITCHEN_BLACKBOX_*` env vars.
4. **Persistence only after verify** — Local `assignments_by_target[et]` is written **only** if POST succeeds and GET read-back matches (DV-074). Ledger gets a `kitchen` entry; lifecycle moves toward `assigned_runtime_confirmed` via `mark_assigned_runtime_confirmed`.

**API surface (BlackBox `api_server.py`):**

- `GET /api/v1/renaissance/kitchen-runtime-assignment?execution_target=jupiter|blackbox` — Full read payload (assignment, runtime, drift, lifecycle summary, ledger tail, `authoritative_active_policy`).
- `POST /api/v1/renaissance/kitchen-runtime-assignment` — Body: `submission_id`, `execution_target`; runs `assign_mechanical_candidate`.
- Legacy: `GET …/kitchen-jupiter-assignment` returns **410 Gone**; `POST …/kitchen-assign-jupiter` remains a deprecated alias; prefer `kitchen-runtime-assignment`.

**UI thread:** Dashboard Renaissance / Kitchen blocks fetch the GET endpoint and render **Active trade policy** from `authoritative_active_policy` (runtime) and per-row **`runtime_policy_id`** (from `infer_runtime_policy_id_for_candidate` in DV-077) for the green-dot match.

---

## 4. Reverse assignment (trade surface → Kitchen) and backwards compatibility

If the operator (or automation) changes active policy **on the trade surface**, Kitchen does **not** receive a webhook. Instead, **the next GET** from the dashboard/API runs a **pull-and-reconcile** pipeline:

```mermaid
flowchart TD
  R[Runtime GET active_policy] --> M{maybe_record_external_runtime_change}
  M --> L[Ledger external entry if drift / unknown]
  R --> REC[reconcile_assignment_store_to_runtime_truth DV-070]
  REC --> K[kitchen row active_runtime_policy_id collapsed to runtime if approved]
  R --> D[drift_status: match / runtime_diverged / ...]
  D --> LC[reconcile_with_drift → lifecycle: external_override / runtime_diverged / confirmed]
```

**Behaviors to remember:**

- **`authoritative_active_policy`** in the GET payload is the runtime’s `active_policy` string when the GET succeeded — use this for “what is live.”
- **`reconcile_assignment_store_to_runtime_truth`** overwrites persisted `active_runtime_policy_id` when it disagreed with runtime but the runtime policy is still **registry-approved** (DV-070).
- **`unknown_runtime_policy`** — Runtime reports a policy id **not** in `kitchen_policy_registry_v1.json` (manual change or skew); UI and drift logic treat this distinctly.
- **External ledger** — `maybe_record_external_runtime_change` dedupes ledger lines when runtime diverged from last Kitchen assignment without a new Kitchen POST.

This is the **backwards compatibility** story: legacy or side-channel policy changes **eventually** show up in Kitchen state **on read**, not by Kitchen initiating a second POST.

---

## 5. Data and control-plane threads (how things connect)

| Lego | Path / endpoint | Role |
|------|------------------|------|
| Registry | `renaissance_v4/config/kitchen_policy_registry_v1.json` | Allow-list + mechanical mapping; must stay aligned with Sean `ALLOWED_POLICY_IDS` (see registry `description`). |
| Assignment store | `renaissance_v4/state/kitchen_runtime_assignment.json` | Last successful Kitchen-driven assignment per target. |
| Lifecycle | `renaissance_v4/state/kitchen_policy_lifecycle_v1.json` | Per-submission state machine vs runtime drift. |
| Candidates API | `GET …/renaissance/ui/intake-candidates` (see `api_server`) | Rows enriched with `runtime_policy_id` for UI. |
| Jupiter control | Env: `KITCHEN_JUPITER_CONTROL_BASE`, `KITCHEN_JUPITER_OPERATOR_TOKEN` | Must point at **Sean Jupiter** origin, not BlackBox `:8080` (see `jupiter_control_plane_warnings`). |
| BlackBox control | `KITCHEN_BLACKBOX_CONTROL_BASE`, `KITCHEN_BLACKBOX_OPERATOR_TOKEN` | Parallel path for `blackbox` target. |

**Thread separation:** The **browser** talks to BlackBox (nginx → `api` :8080). **Kitchen assignment** code in `api` makes **outbound** HTTP to the **Jupiter** host/port where Sean’s policy API lives. Pointing `KITCHEN_JUPITER_CONTROL_BASE` at the wrong process is a common failure mode (documented in code).

---

## 6. Problems observed in practice (current pain)

These are **symptoms** seen when wiring the dashboard and lab; they are not an exhaustive root-cause analysis.

1. **Split semantics** — “Assigned” in the UI can mean “operator requested assignment / lifecycle state” while the **green dot** is defined as **`runtime.active_policy === row.runtime_policy_id`** (DV-077). If those two notions are not read from the same payload fields, the UI can look contradictory until clarified in code (e.g. `authoritative_active_policy` for the headline line).

2. **Drift is normal** — Any change on the Jupiter trade surface creates **runtime_diverged** until the next successful reconcile or a new Kitchen assign. Operators may interpret drift as a bug rather than expected behavior.

3. **Registry vs runtime allow-list** — Assignment fails with `jupiter_runtime_policy_set_mismatch` if Sean’s `allowed_policies` does not include the mechanical slot id even when the repo registry lists it (DV-077). Deploy skew between Sean and BlackBox repo is a **hard** gate.

4. **Configuration sensitivity** — Wrong `KITCHEN_JUPITER_CONTROL_BASE` (e.g. localhost:8080) blocks or mis-assigns; warnings exist but depend on env being set correctly on the **API** host.

5. **Stale deploy** — Dashboard HTML and API code are served from the repo mount; static assets are baked in **web**. Partial updates (pull without rebuild/restart) can make the UI look “wrong” even when `main` is correct.

6. **Mechanical-only assign path** — `assign_mechanical_candidate` is tightly scoped to the mechanical proof policy. Broader “any approved candidate” assignment is a **future** unified flow (see `DV-ARCH-POLICY-LOAD-028` in docs) — the map above is accurate for what is **implemented**, not the full product vision.

---

## 7. Request for architect overview

We need a **single top-level narrative** that answers:

- How **forward assignment** and **reverse assignment** are jointly specified (not “push-only” semantics), including whether any future **push** from target to Kitchen is desired or pull-only is final.
- Where is the **activation boundary** between “evaluated in Kitchen” and “live on a target,” and how does that interact with **DV-028** (Kitchen-first, no direct load)?
- For **non-mechanical** policies, what is the **intended** end-state of this same assignment store vs a future unified state machine?
- Should **trade-surface** changes ever **push** identity back into Kitchen beyond reconcile + ledger (e.g. operator attribution), or is **runtime GET + audit** sufficient?
- What is the **canonical** operator story when `drift` is `runtime_diverged`: always fix from Kitchen, always fix from Jupiter, or either with ledger as source of history?

Please provide a short **architect overview** tied to this map so engineering can align UI copy, lifecycle names, and runbooks with one story.

---

## 8. Primary code references

| Topic | Module |
|-------|--------|
| Assignment + runtime query + drift + read payload | `renaissance_v4/kitchen_runtime_assignment.py` |
| Lifecycle states + drift reconciliation | `renaissance_v4/kitchen_policy_lifecycle.py` |
| Registry + `infer_runtime_policy_id_for_candidate` | `renaissance_v4/kitchen_policy_registry.py` |
| Candidate list + `runtime_policy_id` enrichment | `renaissance_v4/policy_intake/candidates_registry.py` |
| HTTP routes | `UIUX.Web/api_server.py` (`kitchen-runtime-assignment`, candidates, ledger) |

---

## 9. Related documents (repo)

- `docs/architect/DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md` — product rule for Kitchen-first activation (full implementation still tracked).
- `renaissance_v4/kitchen_runtime_assignment.py` module docstring — DV-068 / DV-074 summary.
