# Architect directives (registry)

**Purpose:** Single place to **find and track** architect-issued directives. Implementation and proof still follow [`agent_verification.md`](../agent_verification.md) and [`global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md).

**Canonical templates (mandatory for new work):**
- **Full directive:** [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md) — copy scaffold for every new `directive_<id>_<short_title>.md`.
- **Closeout / gate / proof summary only:** [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md) — mandatory plan/log sync, **Git commit + remote sync** (for implementation closes), checklist, `Plan/log status sync: PASS`, and mismatch failure rule.

Add new directives here as **`directive_<id>_<short_title>.md`** and a row in the table below.

**Documentation / status synchronization (mandatory):** A directive, twig, sub-step, or closure is not complete unless `docs/blackbox_master_plan.md` and `directive_execution_log.md` are updated in the **same change set** with **matching granularity** (see **Documentation / Status Synchronization** in [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md)). Closeouts must include `Plan/log status sync: PASS`. **Implementation** closeouts must also record **Git commit and remote sync** (commit SHA, push to `origin`, primary-host SHA when required) per [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md). If mismatch is found after return, work is incomplete; fix docs before starting the next directive or phase.

---

## Index

| ID | Title | Document | Status |
|----|--------|----------|--------|
| **4.6.3.3** | Messaging interface abstraction (Anna decoupled from Telegram) | [`directive_4_6_3_3_messaging_interface.md`](directive_4_6_3_3_messaging_interface.md) | **Closed** — see [`directive_4_6_3_3_closure_evidence.md`](directive_4_6_3_3_closure_evidence.md) |
| **4.6.3.4** | Messenger config + Slack adapter bring-up | [`directive_4_6_3_4_slack_adapter_and_config.md`](directive_4_6_3_4_slack_adapter_and_config.md) | **Active** — one backend at runtime; **no** OpenClaw gateway in this leaf |
| **4.6.3.4.C** | Slack Anna activation (routing + ingress + enforcement + Ollama) | [`directive_4_6_3_4_c_slack_anna_closure.md`](directive_4_6_3_4_c_slack_anna_closure.md) | **Closed** — live `#blackbox_lab`; see closure doc |
| **4.6.3.5.A** | Anna live data grounding v1 + final identity containment | master plan phase entry [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md) | **Closed** — live 4-prompt proof on `#blackbox_lab`: no-data fallback + concept answer + system-consistent `hello` |
| **4.6.3.2.A** | Learning Core containment slice (lifecycle + validated-only reuse gate) | master plan phase entry [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md) | **Closed (containment scope only)** — committed/accepted (`ea9c215`) |
| **—** | Expose master plan via raw Git URL (ChatGPT / tooling) | [`../../cursor_directive_expose_master_plan.md`](../../cursor_directive_expose_master_plan.md) | Active (ops) |
| **DV-ARCH-POLICY-LOAD-028** | Unified policy submission — Kitchen-first, no live assignment without evaluation | [`../DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md`](../DV-ARCH-POLICY-LOAD-028_unified_policy_submission.md) | **Documented** + **partial** — see directive §13 (024 ingest, 023 activation); full states + package submit + enforcement TBD |
| **4.6.4** | Anna benchmark / architect submission artifact | [`../../benchmarks/anna_directive_4_6_4_architect_submission.md`](../../benchmarks/anna_directive_4_6_4_architect_submission.md) | Benchmark / evidence |
| **Global** | Mandatory clawbot proof (all phases) | [`../global_clawbot_proof_standard.md`](../global_clawbot_proof_standard.md) | Non-negotiable |
| **BBX-SLACK-001** | Slack operator — governance lock (Phase 0) | [`directive_bbx_slack_001_governance_lock.md`](directive_bbx_slack_001_governance_lock.md) | Program umbrella + LDD pointers; close per template |
| **BBX-SLACK-002** | Slack operator — end-to-end transport path | [`directive_bbx_slack_002_transport_path.md`](directive_bbx_slack_002_transport_path.md) | Activate after 001 acceptance |
| **BBX-SLACK-003** | Slack operator — intent and clarification loop | [`directive_bbx_slack_003_intent_clarification.md`](directive_bbx_slack_003_intent_clarification.md) | Activate after 002 acceptance |
| **BBX-SLACK-004** | Slack operator — grounded tool layer | [`directive_bbx_slack_004_grounded_tool_layer.md`](directive_bbx_slack_004_grounded_tool_layer.md) | Activate after 003 acceptance |
| **BBX-SLACK-005** | Slack operator — context integration | [`directive_bbx_slack_005_context_integration.md`](directive_bbx_slack_005_context_integration.md) | Activate after 004 (order vs 006 per canonical plan) |
| **BBX-SLACK-006** | Slack operator — named-agent overlays | [`directive_bbx_slack_006_named_agent_overlays.md`](directive_bbx_slack_006_named_agent_overlays.md) | Activate after 004 |
| **BBX-SLACK-007** | Slack operator — auditability and operator proof | [`directive_bbx_slack_007_auditability.md`](directive_bbx_slack_007_auditability.md) | Activate when program order allows |
| **BBX-SLACK-008** | Slack operator — MVP stabilization | [`directive_bbx_slack_008_mvp_stabilization.md`](directive_bbx_slack_008_mvp_stabilization.md) | Activate after prior phases |
| **BBX-SLACK-009** | Slack operator — deferred scope fence (not MVP) | [`directive_bbx_slack_009_deferred_scope_fence.md`](directive_bbx_slack_009_deferred_scope_fence.md) | Docs/governance record; may accept early |
| **—** | Slack operator — full phased narrative + operator tests | [`../slack_conversational_operator/canonical_development_plan.md`](../slack_conversational_operator/canonical_development_plan.md) | **Canonical program expectations** (not a substitute for per-ID directive files) |

---

## Related (not standalone directive files)

- **Phase 4.6.3.2** (`agent_learning_core`) — Part A accepted (containment only), Part B planning target; see [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md).
- **Local / remote dev workflow** — [`../local_remote_development_workflow.md`](../local_remote_development_workflow.md).

---

## How to add a directive

1. Copy [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md) to `directive_<phase_or_id>_<slug>.md` and fill in scope, proof, and evidence; keep all **(Mandatory)** sections.
2. Add a row to the **Index** table.
3. In the **same change set**, update [`../../blackbox_master_plan.md`](../../blackbox_master_plan.md) and [`directive_execution_log.md`](directive_execution_log.md) to matching status granularity.
4. Closeout / return must include `Plan/log status sync: PASS` and **Git commit and remote sync** when the work changed the canonical repo (see template).
