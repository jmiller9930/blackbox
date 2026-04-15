# DV-ARCH-POLICY-LOAD-028 — Unified policy submission flow (Kitchen-first)

**To:** Engineering  
**Cc:** Dashboard Engineering / Research / Runtime Ops  
**Re:** Unified Policy Submission Flow — All Policies Must Pass Kitchen Evaluation Before Live Assignment  
**Status:** Rule **documented** in-repo. **Partial backend** exists (see §13); **full** unified state machine, Kitchen-routed dashboard **package** submit, and enforcement gates remain **tracked** with proof when shipped.

---

## 1. Purpose

Lock in the policy-handling rule for the platform.

From this point forward:

**No policy may be assigned to the live BlackBox trading slot unless it has first passed through Quant Research Kitchen evaluation.**

This applies regardless of where the operator initiates the action (main dashboard, Kitchen, human, or future AI operator).

---

## 2. Core rule

A policy may be:

- selected from the main dashboard  
- selected from Quant Research Kitchen  
- provided by a human operator  
- provided later by an AI operator  

But **every** policy must follow the same backend path:

```text
policy package
  → validation
  → replay
  → Monte Carlo
  → baseline comparison
  → artifact generation
  → approval state
  → only then eligible for activation
```

There will be **no direct-load shortcut** into live trading.

---

## 3. Required product behavior

### 3.1 Main dashboard

If the main dashboard includes a selector, picker, upload, or attachment-based policy submission control, that control must mean:

**Submit policy for Kitchen evaluation**

It must **not** mean: **Activate policy immediately.**

### 3.2 Quant Research Kitchen

Kitchen remains the **canonical evaluation surface** for:

- policy validation  
- deterministic replay  
- Monte Carlo  
- baseline comparison  
- recommendation state  

### 3.3 Activation boundary

Only policies that already have a **successful Kitchen evaluation** and are marked **eligible** may enter the activation flow handled by the BlackBox assignment mechanism.

### 3.4 Built-in baseline version selector vs policy package submission

Do **not** conflate these:

| Surface | What it is | Kitchen-first rule |
|--------|------------|---------------------|
| **Main dashboard — Jupiter baseline dropdown** (`jup_v2` / `jup_v3` / `jup_v4`) | Chooses among **already merged, integrated** evaluator binaries in-repo. | Changing the slot **schedules activation** at the next closed-bar boundary ([DV-ARCH-POLICY-ACTIVATION-023](policy_activation_lineage_spec.md)); it is **not** uploading a new policy package. These engines were merged under governance before the operator could select them. |
| **Policy package** (folder with `POLICY_SPEC.yaml`, new/custom recipe) | New or candidate policy **content** destined for the live slot. | Must go through the **full** path in §2 (validation → … → `approved_for_activation`) on the **canonical** pipeline; **no** direct “load into live” from upload or a dashboard shortcut. |

Future **dashboard** controls that **submit a package file or path** must route into the **same** Kitchen evaluation pipeline as Research Kitchen — not a separate “quick load” API.

---

## 4. Unified backend requirement

Main dashboard and Kitchen must use the **same** backend ingestion / evaluation pipeline.

**Do not build:**

- one “quick load” path in the dashboard  
- another “research load” path in the Kitchen  

There must be **one canonical** policy submission and evaluation process.

---

## 5. Required states

A submitted policy must move through explicit states such as:

| State (example names) | Meaning |
|------------------------|--------|
| `submitted` | Received for processing |
| `validation_failed` | Package/structural or rule checks failed |
| `validated` | Passes validation gates |
| `replay_complete` | Deterministic replay finished |
| `monte_carlo_complete` | MC stage finished |
| `compared_to_baseline` | Baseline comparison done |
| `approved_for_activation` | Cleared for assignment |
| `activated` | Live assignment applied per BlackBox mechanism |

A policy that has **not** reached **`approved_for_activation`** (or equivalent) **must not** be assignable to the live slot.

---

## 6. UI language requirement

Any dashboard button or control that currently implies **direct loading** must be renamed or described so the operator understands the real behavior.

**Acceptable wording examples:**

- Submit Policy for Evaluation  
- Evaluate Policy Package  
- Send to Kitchen  

**Unacceptable wording** (unless the policy is already approved and the action is specifically the activation step):

- Load Policy  
- Activate Policy  
- Apply Policy  

---

## 7. Documentation placement (this repo)

This rule is recorded here and cross-linked from:

- [`blackbox_policy_kitchen_integration_writeup.md`](blackbox_policy_kitchen_integration_writeup.md)  
- [`policy_package_standard.md`](policy_package_standard.md)  
- [`development_governance.md`](development_governance.md)  
- [`policy_activation_lineage_spec.md`](policy_activation_lineage_spec.md)  

**Dashboard engineering:** treat §3–§6 as **required product behavior** for any policy submission or activation UX.

---

## 8. Implementation direction

Engineering must define and/or implement the submission flow so that:

- policy package selection from the **main dashboard** routes into the **Kitchen evaluation pipeline**  
- Kitchen continues to evaluate policies through the same governed process  
- **no** direct assignment path remains for untested policies  

---

## 9. Non-goals (this pass)

Do **not** in this pass:

- create a bypass around Kitchen  
- allow immediate live activation from upload  
- introduce alternate policy loaders  
- change evaluator logic  
- change lifecycle logic  

This directive is a **control-flow and product-behavior** rule.

---

## 10. Success criteria

Successful when:

- every policy enters through **one shared evaluation path**  
- the operator **cannot accidentally** activate an untested policy  
- dashboard and Kitchen stay **behaviorally aligned**  
- the rule is **documented and enforced** (enforcement = code + API + UI, when implemented)  

---

## 11. Response header (for closure packets)

**RE:** DV-ARCH-POLICY-LOAD-028  

**Documentation status:** captured in this file and cross-links (see §7).  

**Implementation status:** **partial** — see §13 (inventory). **Not** closed until explicit policy states, Kitchen-routed package submit from dashboard (if product adds one), and **`approved_for_activation`** gating are implemented and proven.  

```
STATUS: documentation complete; implementation partial (see §13)
COMMIT: (record git rev-parse HEAD on branch that merged this doc)
```

---

## 13. Related implementation inventory (avoid duplicating work)

Use this list to **avoid** re-specifying the same flow in multiple places. Other directives may add code; this section only **maps** them to LOAD-028.

| Item | Directive / module | Role relative to §2 |
|------|---------------------|------------------------|
| Policy package **validation** → deterministic replay artifact | **DV-ARCH-POLICY-INGESTION-024-A** — `renaissance_v4/research/policy_package_ingest.py` (`run_policy_package_replay`) | **First slices** of validation + replay; **not** yet Monte Carlo / baseline compare / approval state machine. |
| Activation **scheduling** + lineage on eval/trades | **DV-ARCH-POLICY-ACTIVATION-023** — `modules/anna_training/execution_ledger.py` (`policy_activation_log`); see [`policy_activation_lineage_spec.md`](policy_activation_lineage_spec.md) | **Not** a Kitchen bypass; applies to **which integrated slot** runs at the bar boundary. |
| Baseline dashboard **POST** `/api/v1/dashboard/baseline-jupiter-policy` | `UIUX.Web/api_server.py` | Enqueues **pending** activation for **built-in** slots only; see §3.4. **Custom packages** must not use this endpoint as a substitute for Kitchen evaluation. |

**Still open for LOAD-028 alignment:** persisted **state machine** (`submitted` … `approved_for_activation`), Monte Carlo + baseline comparison wired to the **same** submission id, dashboard/Kitchen **single** submit API for **packages**, and UI copy audit (§6) on any future upload control.

---

## 12. Revision

| Version | Change |
|---------|--------|
| 1 | Architect memo ingested; permanent architecture record. |
| 2 | §3.4 built-in vs package; §13 implementation inventory; §11 partial status. |
