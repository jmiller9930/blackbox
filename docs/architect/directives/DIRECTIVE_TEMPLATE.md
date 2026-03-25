# Architect directive — canonical template

**Purpose:** Copy this scaffold when authoring a new directive file (`directive_<id>_<slug>.md`). Sections marked **(Mandatory)** are non-negotiable for every new directive, twig, sub-step, or closure-bearing work package.

**Related:** Registry [`README.md`](README.md); execution trail [`directive_execution_log.md`](directive_execution_log.md); roadmap [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md). Closeout-only artifacts may use [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md).

---

# Directive &lt;ID&gt; — &lt;Short title&gt;

## Scope & objectives

&lt;Directive-specific content.&gt;

---

## Documentation / Status Synchronization (Mandatory)

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

Broader umbrella wording is not sufficient when the log records a more specific twig or sub-step status.

---

## Closeout / return summary (Mandatory)

Every completion, gate packet, closeout, or return summary must include:

`Plan/log status sync: PASS`

If this line is missing, the work is not considered complete.

---

## Developer verification checklist (before return)

Before return, verify:

- [ ] `docs/blackbox_master_plan.md` matches current implemented state
- [ ] `docs/architect/directives/directive_execution_log.md` matches current implemented state
- [ ] status granularity matches in both documents
- [ ] no stale wording remains for prior twigs/sub-steps
- [ ] completion summary includes `Plan/log status sync: PASS`

---

## Documentation mismatch failure rule (Mandatory)

If documentation status mismatch is discovered after return:

- the work is considered **incomplete**
- documentation must be corrected **before any next directive begins**
- **no** subsequent twig or phase may proceed until sync is restored

---

## Proof & evidence

&lt;Directive-specific acceptance criteria, commands, clawbot proof, etc.&gt;

---

## Notes

&lt;Optional.&gt;
