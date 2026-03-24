# Architect directives (registry)

**Purpose:** Single place to **find and track** architect-issued directives. Implementation and proof still follow [`agent_verification.md`](../agent_verification.md) and [`global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md).

Add new directives here as **`directive_<id>_<short_title>.md`** and a row in the table below.

---

## Index

| ID | Title | Document | Status |
|----|--------|----------|--------|
| **4.6.3.3** | Messaging interface abstraction (Anna decoupled from Telegram) | [`directive_4_6_3_3_messaging_interface.md`](directive_4_6_3_3_messaging_interface.md) | Active — open decisions: [`directive_4_6_3_3_architect_followup.md`](directive_4_6_3_3_architect_followup.md) |
| **—** | Expose master plan via raw Git URL (ChatGPT / tooling) | [`../../cursor_directive_expose_master_plan.md`](../../cursor_directive_expose_master_plan.md) | Active (ops) |
| **4.6.4** | Anna benchmark / architect submission artifact | [`../../benchmarks/anna_directive_4_6_4_architect_submission.md`](../../benchmarks/anna_directive_4_6_4_architect_submission.md) | Benchmark / evidence |
| **Global** | Mandatory clawbot proof (all phases) | [`../global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md) | Non-negotiable |

---

## Related (not standalone directive files)

- **Phase 4.6.3.2** (`agent_learning_core`) — stub on master plan only; see [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md).
- **Local / remote dev workflow** — [`../local_remote_development_workflow.md`](../local_remote_development_workflow.md).

---

## How to add a directive

1. Add `directive_<phase_or_id>_<slug>.md` in this folder.
2. Add a row to the **Index** table.
3. Reference it from [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md) when it maps to a roadmap phase.
