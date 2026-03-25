# Closeout / gate packet — canonical template

**Purpose:** Copy this scaffold for **closure-only** artifacts, gate packets, proof summaries, or returns when a full [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md) file is not used. Normative rules are the same; this file is a short path for copy-paste.

---

## Documentation / Status Synchronization (Mandatory)

This work is not considered complete, closed, advanced, or canonically valid unless:

- `docs/blackbox_master_plan.md` is updated to **matching status granularity**
- `docs/architect/directives/directive_execution_log.md` is updated to the **same status/scope**
- **both updates occur in the same change set**

If a twig/sub-step is recorded in the execution log as **active**, **complete**, **closed**, **implemented**, or **corrected**, then the master plan must reflect the same status **explicitly**. Broader umbrella wording is not sufficient when the log records a more specific twig or sub-step status.

---

## Mandatory closeout line

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

## Evidence / proof (fill in)

&lt;Commands, commit hash, clawbot capture, etc. — see [`../global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md).&gt;

**Plan/log status sync: PASS**
