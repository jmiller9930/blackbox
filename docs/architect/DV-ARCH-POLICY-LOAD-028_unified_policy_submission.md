# DV-ARCH-POLICY-LOAD-028 — Unified policy submission flow (Kitchen-first)

**To:** Engineering  
**Cc:** Dashboard Engineering / Research / Runtime Ops  
**Re:** Unified Policy Submission Flow — All Policies Must Pass Kitchen Evaluation Before Live Assignment  
**Status:** Rule **documented** in-repo; **implementation** (unified pipeline, state machine, UI) is **required product direction** — track separately with proof when shipped.

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

**Documentation status:** captured in this file and cross-links.  

**Implementation status:** open until unified pipeline + states + UI match §3–§6.  

```
STATUS: documentation complete (implementation pending)
COMMIT: (record git rev-parse HEAD on branch that merged this doc)
```

---

## 12. Revision

| Version | Change |
|---------|--------|
| 1 | Architect memo ingested; permanent architecture record. |
