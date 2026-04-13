# Directive BBX-SLACK-001 — Slack operator program — governance lock

**Governance:** [`../development_governance.md`](../development_governance.md); template alignment: [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md).

**Program umbrella:** [`../slack_conversational_operator/canonical_development_plan.md`](../slack_conversational_operator/canonical_development_plan.md) (Phase 0).  
**Technical LDD:** [`../slack_conversational_operator/slack_conversational_operator_system_ldd.md`](../slack_conversational_operator/slack_conversational_operator_system_ldd.md).

---

## Scope & objectives

**Requirement:** Lock the **architectural contract** before implementation of the Slack → OpenClaw / BlackBox conversational operator system.

**In scope:**

- Record and commit the fixed model below so Engineering works against one contract.
- Ensure MVP boundary and **Jupiter V2 policy untouched** constraint are explicit.

**Fixed model (non-negotiable for this program):**

- Slack is the communication surface.
- OpenClaw / BlackBox is the default interpreter and router.
- Specialists are hidden implementation modules.
- Context assists interpretation and continuity; it does **not** replace truth sources.
- All factual answers come from grounded tools and APIs.
- Named agents are optional routing hints only (presentation overlays), not parallel truth.
- **V2 trading policy behavior remains untouched** unless separately authorized.

**Out of scope for this directive:** Transport wiring, intent extraction, tool implementation — later BBX-SLACK directives.

**Why:** Prevents parallel interpretations and scope drift before code lands.

---

## Documentation / Status Synchronization (Mandatory)

This directive is not considered complete unless:

- `docs/blackbox_master_plan.md` reflects this program where applicable
- `docs/architect/directives/directive_execution_log.md` records BBX-SLACK-001 status
- `docs/architect/development_plan.md` Slack operator subsection remains aligned
- **both** master plan and execution log updates occur in the **same change set** when status changes

---

## Closeout / return summary (Mandatory)

*(Complete when architect accepts closure.)*

`Plan/log status sync: PASS`

---

## Developer verification checklist (before return) (Mandatory)

Before return, verify:

- [ ] `docs/blackbox_master_plan.md` matches current state for BBX-SLACK program reference
- [ ] `docs/architect/directives/directive_execution_log.md` matches
- [ ] status granularity matches in both documents
- [ ] completion summary includes `Plan/log status sync: PASS`
- [ ] **Git:** change set committed and pushed when docs changed

---

## Git commit and remote sync (Mandatory for implementation closes)

This directive is **documentation / governance closure** for the governance lock slice. Record **Git proof: N/A** only if truly docs-only with no repo file changes; otherwise record SHA and push.

---

## Documentation mismatch failure rule (Mandatory)

Per [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md) — no closure if master plan and execution log disagree.

---

## Proof & evidence (Mandatory for closure)

**Acceptance criteria (from program plan):**

- Committed canonical text states the fixed model **without ambiguity** and includes MVP scope boundary (LDD + canonical plan).
- Operator can read committed text and confirm it matches intent.

**Evidence to attach on closeout:**

- Paths: `docs/architect/slack_conversational_operator/canonical_development_plan.md`, `slack_conversational_operator_system_ldd.md`, `development_governance.md`, `development_plan.md` (subsection).
- Operator sign-off note (channel/date) or architect attestation line in execution log.

Closeouts must end with **`Plan/log status sync: PASS`** when applicable.

---

## Notes

- **001** is intentionally **docs-first**; no production Slack path is required to close governance lock if the committed artifacts satisfy the contract.
- Subsequent directives (002+) address implementation slices.
