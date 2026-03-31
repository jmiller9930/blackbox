# Architect directive — canonical template

**Governance (non-negotiable):** [`../development_governance.md`](../development_governance.md) — **You cannot canonically close a directive** unless every **(Mandatory)** section in this template (or the equivalent blocks in [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md)) is **fully** completed. Architect, developer, or **both** in one person must satisfy **all** role-owned fields per that document (**Directive templates — mandatory for closure**). This template and the governance doc are **bidirectionally coupled**; closure is invalid if either is ignored.

**Purpose:** Copy this scaffold when authoring a new directive file (`directive_<id>_<slug>.md`). Sections marked **(Mandatory)** are non-negotiable for every new directive, twig, sub-step, or closure-bearing work package.

**What this document is:** An architect-issued **directive** *is* the authorized **development item** (numbered ID + title, scoped in `development_plan.md`). This file (or a [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md) packet that embeds the same mandatory blocks) must contain **all** mandatory sections for **canonical closure** of that item. Missing a mandatory section blocks closure.

**Related:** Registry [`README.md`](README.md); execution trail [`directive_execution_log.md`](directive_execution_log.md); roadmap [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md). Closeout-only artifacts may use [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md).

---

# Directive &lt;ID&gt; — &lt;Short title&gt;

## Scope & objectives

**Requirement:** State **what** the developer must implement (boundaries, in-scope / out-of-scope, links to specs). This is authored when the directive is **issued**, not at closeout.

**Why:** Developers implement from written spec, not from chat. Scope prevents silent expansion.

**Non-negotiable for directive issuance:** Yes — a directive without clear scope is not safely executable. *(This section is the “open” of the work package; closeout still requires the mandatory sections below when you return.)*

&lt;Directive-specific content.&gt;

---

## Documentation / Status Synchronization (Mandatory)

**Requirement:** Same as closeout template: **master plan** + **directive_execution_log** updated in the **same change set** with **matching** status text.

**Why:** Single source of truth across roadmap and log; required for audit and for `Plan/log status sync: PASS` to mean something.

**Non-negotiable for closure:** Yes — without this, the directive cannot be marked closed in the canonical record.

This directive is not considered complete, closed, advanced, or canonically valid unless:

- `docs/blackbox_master_plan.md` is updated to **matching status granularity**
- `docs/architect/directives/directive_execution_log.md` is updated to the **same status/scope**
- **both updates occur in the same change set**

If a twig/sub-step is recorded in the execution log as:

- active  
- complete  
- closed  
- implemented  
- corrected  

then the master plan must reflect the same status **explicitly**.

Broader umbrella wording is not sufficient when the execution log records a more specific twig or sub-step status.

---

## Closeout / return summary (Mandatory)

**Requirement:** Include the literal line `Plan/log status sync: PASS` in the return that closes the directive (or the closeout packet attached to it).

**Why:** Explicit attestation that documentation sync rules were satisfied.

**Non-negotiable for closure:** Yes.

Every completion, gate packet, closeout, or return summary must include:

`Plan/log status sync: PASS`

If this line is missing, the work is not considered complete.

---

## Developer verification checklist (before return) (Mandatory)

**Requirement:** Every checklist item must be satisfied before architect acceptance; Git row applies when the directive changed the repo.

**Why:** Prevents returning with stale or contradictory canonical docs.

**Non-negotiable for closure:** Yes.

Before return, verify:

- [ ] `docs/blackbox_master_plan.md` matches current implemented state
- [ ] `docs/architect/directives/directive_execution_log.md` matches current implemented state
- [ ] status granularity matches in both documents
- [ ] no stale wording remains for prior twigs/sub-steps
- [ ] completion summary includes `Plan/log status sync: PASS`
- [ ] **Git:** change set committed and pushed to canonical remote (or `N/A` documented for docs-only); see **Git commit and remote sync** below

---

## Git commit and remote sync (Mandatory for implementation closes)

**Requirement:** For directives that shipped **code or material repo changes**, fill SHA, branch, push confirmation, and primary-host SHA when required. Docs-only: **Git proof: N/A** with justification.

**Why:** Immutable revision pointer for audit and re-initiation.

**Non-negotiable for closure:** Yes for implementation; **N/A** only with stated docs-only rationale.

Same rule as [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md): if this directive shipped **code** or **material repo changes**, record **full commit SHA**, **branch**, **remote push confirmation**, and **primary-host SHA** when [`docs/runtime/execution_context.md`](../../runtime/execution_context.md) requires clawbot proof. **Docs-only** work may state **Git proof: N/A** with one line why.

---

## Documentation mismatch failure rule (Mandatory)

**Requirement:** Do not treat closure as valid if master plan and execution log disagree; fix docs before the next directive.

**Why:** Hard stop on documentation debt that would invalidate future work.

**Non-negotiable:** The rule is binding; closeouts must not assert completion while leaving known mismatches.

If documentation status mismatch is discovered after return:

- the work is considered **incomplete**
- documentation must be corrected **before any next directive begins**
- **no** subsequent twig or phase may proceed until sync is restored

---

## Proof & evidence (Mandatory for closure)

**Requirement:** Concrete commands, outcomes, and artifact paths proving the directive’s acceptance criteria are met (per [`../global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md) where applicable).

**Why:** Architect validation and future audits rely on repeatable evidence, not summaries alone.

**Non-negotiable for closure:** Yes — empty or hand-wavy proof blocks closure.

&lt;Directive-specific acceptance criteria, commands, clawbot proof, etc.&gt;

Closeouts and returns must end with **Git commit and remote sync** (filled) + **`Plan/log status sync: PASS`** when applicable — see [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md).

---

## Notes

**Requirement:** Optional; use for non-binding context.

**Why:** Keeps optional chatter out of mandatory sections.

**Non-negotiable for closure:** No — this section may be omitted.

&lt;Optional.&gt;
