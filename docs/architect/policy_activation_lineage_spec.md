# Policy activation and lineage specification (team consensus + gaps)

**Status:** Target architecture and product requirements — **not** fully implemented in code today.  
**Purpose:** Capture the distinction between **policy authoring** and **policy assignment**, and define what “load + apply” must mean so the dashboard does not mis-attribute trades or tiles to the wrong policy.

**Related:** Current engine behavior (as-is) — [`DV-ARCH-INTAKE-021_blackbox_engine_policy_kitchen_alignment.md`](DV-ARCH-INTAKE-021_blackbox_engine_policy_kitchen_alignment.md). Package layout for new baselines — [`policy_package_standard.md`](policy_package_standard.md). **Kitchen-first before live assignment** — [`DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md`](DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md).

---

## 0. Gating: Kitchen evaluation before activation (DV-ARCH-POLICY-LOAD-028)

**Activation** (assigning a policy to the live trading slot) is **downstream** of **Quant Research Kitchen**: validation, replay, Monte Carlo, baseline comparison, and an **approved / eligible** state. The **`approved_for_activation`** milestone (see [`DV-ARCH-POLICY-LOAD-028`](DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md) §5) is part of that product rule: a policy must not be assignable until Kitchen (and any human approval step) clears it. **One** backend submission path serves dashboard and Kitchen.

---

## 1. Two separate subsystems

| Subsystem | Question it answers |
|-----------|---------------------|
| **Policy authoring** | How a policy is **created** from a template (fill → validate → artifact). |
| **Policy assignment** | How that policy is **attached** to the live engine **going forward**. |

Both are required. A perfect generator without explicit **activation semantics** will still produce confusing or misleading dashboard behavior.

---

## 2. Intended end-to-end workflow (target)

When the platform supports template-driven policies end-to-end:

```text
template
  → filled policy
  → validated policy artifact
  → loaded into the system
  → applied prospectively only
```

**Requirements on the system:**

1. **Policy generation** — A structured way to fill the template and produce a **valid** policy (and pass validation gates).
2. **Policy activation semantics** — A **deterministic** rule for **when** that policy becomes live.

Without (2), operators cannot trust which policy produced which evaluation or trade.

---

## 3. Recommended activation model: next closed evaluation boundary

**Apply on next closed evaluation boundary** (safest default for bar-based engines):

- User **selects** or **loads** a policy now.
- System records the policy as **pending** (not yet driving evaluation).
- The **first** evaluation that uses the new policy is the **next closed bar** (or next **eligible** event, if the engine defines a different boundary).
- The **first** trade/no-trade tile (and downstream ledger rows) after that boundary is attributed to the **new** policy.

**Why:** Applying “instantly” in the middle of an active bar or active holding state mixes lineage and makes it unclear which policy authorized the signal.

This model must be **explicit**, **forward-only**, and **lineage-aware**, or the dashboard will keep misrepresenting what produced what.

---

## 4. Template fields (beyond strategy logic)

A policy template should carry enough structure to **generate** the policy correctly and to **activate** it correctly. Suggested minimum metadata:

| Area | Examples |
|------|----------|
| Identity | Policy name; policy id; version |
| Placement | Slot target (e.g. baseline Jupiter slot) |
| Activation | Activation rule (see §3); effective-from boundary type |
| Execution | Evaluator type (which engine / module family) |
| Strategy | Signals, thresholds, gates |
| Sizing | Sizing / hint model |
| Provenance | Notes, source (Kitchen run id, git ref, etc.) |

The **loaded result** should be stored as a **durable artifact** (versioned, auditable), not ephemeral chat text.

---

## 5. Lineage and display rules (to be specified in implementation)

When this spec is implemented, engineering should define **concretely**:

1. **How** a policy is loaded (storage, schema, integrity).
2. **When** it becomes effective (pending → active transition; boundary timestamp or `market_event_id`).
3. **How** old vs new policy attribution is **stored** on `policy_evaluations`, execution rows, and open-position state.
4. **How** the dashboard shows the transition **without rewriting history** (no retroactive relabeling of prior bars/trades).

Until then, treat this section as the **acceptance bar** for “policy activation v1.”

---

## 6. Gap vs current BlackBox (honest snapshot)

Today, baseline Jupiter selection is roughly:

- **SQLite** `baseline_operator_kv` key `baseline_jupiter_policy_slot` (+ env fallback) — see `modules/anna_training/execution_ledger.py` (`get_baseline_jupiter_policy_slot`).

There is **no** first-class **pending → next boundary** state machine in that path as of this writing. Slot changes apply as soon as the next code path reads KV; evaluation is already **closed-bar**-oriented, but **lineage of “switch moment”** vs **historical tiles** is not modeled as a separate activation spec.

**Policy implementations** remain **reviewed Python** (and optional mirrors), per governance — not arbitrary runtime strings.

---

## 7. Next engineering deliverables (suggested order)

1. **Policy activation and lineage** — Data model + API + UI rules for pending/active, boundary id, and immutable attribution.
2. **Template + validator** — Already partially aligned with `POLICY_SPEC.yaml` / `validate_policy_package.py`; extend with **activation metadata** when ready.
3. **Dashboard truth** — Explicit “effective policy for this `market_event_id`” display rules and migration from “current slot only” where needed.

---

## 8. Revision

| Version | Change |
|---------|--------|
| 1 | Ingested team conversation: authoring vs assignment, next-boundary activation, template metadata, lineage requirements, gap note. |
| 2 | §0 **Kitchen-first** gate (**DV-ARCH-POLICY-LOAD-028**); link from related. |
