# Directive BBX-SLACK-002 — Slack operator — end-to-end transport path

**Governance:** [`../development_governance.md`](../development_governance.md); template: [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md).

**Program expectations:** [`../slack_conversational_operator/canonical_development_plan.md`](../slack_conversational_operator/canonical_development_plan.md) (Phase 1 / Directive BBX-SLACK-002).

---

## Scope & objectives

**Requirement:** Create Slack → OpenClaw → **one** operator router package → Slack as the **single default ingress**; transport-only proof (health/ack), trace ID, context payload into Python.

**Out of scope:** Rich intent/tools (003+).

---

## Documentation / Status Synchronization (Mandatory)

Per template — master plan + `directive_execution_log.md` in same change set on status change.

---

## Closeout / return summary (Mandatory)

`Plan/log status sync: PASS` *(when closing)*

---

## Developer verification checklist (before return) (Mandatory)

Per [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md).

---

## Git commit and remote sync (Mandatory for implementation closes)

Required when this directive ships code — SHA, branch, push, primary-host SHA if applicable.

---

## Documentation mismatch failure rule (Mandatory)

Per template.

---

## Proof & evidence (Mandatory for closure)

**Authoritative criteria:** See canonical plan § Directive BBX-SLACK-002 (live Slack thread, trace ID, OpenClaw → Python context).

---

## Notes

**Status:** Activate when architect issues implementation start after **001** acceptance.
