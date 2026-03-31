# Closeout / gate packet — canonical template

**Governance (non-negotiable):** [`../development_governance.md`](../development_governance.md) — **You cannot canonically close a directive** unless **every mandatory section** below is **fully** filled. Architect, developer, or **both** in one person must complete **all** role-owned content per that document (**Directive templates — mandatory for closure**). This template and the governance doc are **bidirectionally coupled**; closure is invalid if either is ignored.

**Purpose:** Copy this scaffold for **closure-only** artifacts, gate packets, proof summaries, or returns when a full [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md) file is not used. Normative rules are the same; this file is a short path for copy-paste.

**What this closes:** Use this template when **closing out** an architect-issued **directive** or **development work package** (same thing in governance terms: a numbered/titled slice authorized in `current_directive.md` and `development_plan.md`). The **closeout packet** is the artifact that proves that slice is done; **every mandatory section below must appear** in that packet (or the full directive file that contains the same sections) for closure to be **canonical**. Missing a mandatory section means the directive is **not** closed, regardless of chat or informal sign-off.

**Standard closeout ends with:** (1) documentation sync, (2) **Git commit + remote sync** (for any closeout that ships code/docs to the canonical repo), (3) `Plan/log status sync: PASS`. Older closeouts may omit (2); **new** closeouts must not.

---

## Documentation / Status Synchronization (Mandatory)

**Requirement:** In one change set, update **`docs/blackbox_master_plan.md`** and **`docs/architect/directives/directive_execution_log.md`** so they describe the **same** completion status and scope at the **same level of detail** (no “done” in the log and “TBD” in the master plan).

**Why:** Prevents split-brain: the roadmap, the execution trail, and future audits must tell one story. If they diverge, the next developer or RAG pass cannot trust either file.

**Non-negotiable for closure:** Yes. A closeout without matching master plan + execution log updates is **not** a completed directive.

This work is not considered complete, closed, advanced, or canonically valid unless:

- `docs/blackbox_master_plan.md` is updated to **matching status granularity**
- `docs/architect/directives/directive_execution_log.md` is updated to the **same status/scope**
- **both updates occur in the same change set**

If a twig/sub-step is recorded in the execution log as **active**, **complete**, **closed**, **implemented**, or **corrected**, then the master plan must reflect the same status **explicitly**. Broader umbrella wording is not sufficient when the log records a more specific twig or sub-step status.

---

## Mandatory closeout line (Mandatory)

**Requirement:** The literal line `Plan/log status sync: PASS` must appear in the closeout (or in the closing block of the full directive document).

**Why:** Forces an explicit human-readable assertion that documentation sync was checked, not assumed. Architects and automation can grep for failure to include the line.

**Non-negotiable for closure:** Yes. Without it, the template says the work is not complete.

Every completion, gate packet, closeout, or return summary must include:

`Plan/log status sync: PASS`

If this line is missing, the work is not considered complete.

---

## Developer verification checklist (before return) (Mandatory)

**Requirement:** Copy the checklist into the closeout (or tick it in the PR body) and ensure every box is satisfied before asking for architect acceptance.

**Why:** Checklist is the pre-flight so “closed” is not claimed with stale roadmap text, a silent execution-log drift, or a missing sync line.

**Non-negotiable for closure:** Yes — the items must be true; the checklist is the attestation path.

Before return, verify:

- [ ] `docs/blackbox_master_plan.md` matches current implemented state
- [ ] `docs/architect/directives/directive_execution_log.md` matches current implemented state
- [ ] status granularity matches in both documents
- [ ] no stale wording remains for prior twigs/sub-steps
- [ ] completion summary includes `Plan/log status sync: PASS`

---

## Git commit and remote sync (Mandatory for accepted implementation)

**Requirement:** If the directive shipped **code, tests, or material repo files**, record the **full commit SHA**, **branch**, proof that **`git push`** to the canonical remote completed, and **primary-host SHA** when [`docs/runtime/execution_context.md`](../../runtime/execution_context.md) requires clawbot verification. Purely **docs-only** work may state **Git proof: N/A** with one line of justification.

**Why:** Tests and prose in a chat are not durable; **Git** is how the org knows *which* immutable revision is canonical. Without commit + push, re-initiation and audit cannot reproduce the closed state.

**Non-negotiable for closure:** Yes for **implementation** closes. Docs-only may use **N/A** only with explicit justification.

If this closeout records **accepted** work that changed the canonical repo (code, tests, or governance docs), closure is **not** complete until the change set is **committed** and **pushed** to the team’s canonical remote (typically `origin` on `main`). **Docs-only** directives may use **N/A** with one-line justification.

Record explicitly:

| Field | Value |
|-------|--------|
| **Commit (full SHA)** | `&lt;output of git rev-parse HEAD on the machine where you committed&gt;` |
| **Branch** | e.g. `main` (or branch name issued by architect) |
| **Remote sync** | Confirm `git push` to `origin` completed (or document alternate canonical remote/process) |
| **Primary host** | If [`docs/runtime/execution_context.md`](../../runtime/execution_context.md) requires verification on **clawbot**: run `git pull origin main` then `git rev-parse HEAD` on **`~/blackbox`** and record that SHA (must match or explain the promoted commit) |

**Git proof:** `PASS` | `N/A` (docs-only — state why)

If **Git proof** is not `PASS` or defensible `N/A`, the closeout does not meet the canonical bar.

**Reference pattern:** [`directive_4_6_3_4_close.md`](directive_4_6_3_4_close.md) (ACCEPTED PROOF / Git State / Git Proof).

---

## Documentation mismatch failure rule (Mandatory)

**Requirement:** Acknowledge this rule in the governance corpus (this template satisfies that); if a mismatch is found after a premature close, fix docs **before** starting the next directive.

**Why:** Stops the program from compounding errors: a wrong roadmap poisons every downstream slice.

**Non-negotiable for closure:** The **rule** is part of governance; the closeout must not contradict it (e.g. do not claim closure while leaving known mismatches unfixed).

If documentation status mismatch is discovered after return:

- the work is considered **incomplete**
- documentation must be corrected **before any next directive begins**
- **no** subsequent twig or phase may proceed until sync is restored

---

## Evidence / proof (fill in) (Mandatory)

**Requirement:** Replace the placeholder with **concrete** proof: commands run, pass counts, log excerpts, or live-channel steps as required by [`../global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md) and the directive’s scope. Tie results to **artifacts** (paths) listed in the execution log.

**Why:** Closure is evidence-based, not narrative. This section is what allows someone else to **re-run** or **re-audit** without trusting memory.

**Non-negotiable for closure:** Yes — an empty evidence section means the directive is not demonstrably complete.

&lt;Commands, pytest counts, live-channel capture if required — see [`../global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md).&gt;

**Git commit and remote sync** — use the **Git commit and remote sync** section above (do not omit for implementation closes).

**Plan/log status sync: PASS**
