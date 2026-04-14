# Development governance — BLACK BOX

**Purpose:** Canonical pointers for **plan vs directive vs execution** and **where** contracted scope lives. Binding work is **contracted**, not implied (see project contract in `.cursor/rules/`).

---

## Authoritative documents (read order)

| Document | Role |
|----------|------|
| [`blackbox_master_plan.md`](../blackbox_master_plan.md) | Master rehydration narrative; phase status |
| [`development_plan.md`](development_plan.md) | Actionable Phase 5+ tasks; Pillar 1 spine; **Slack operator** subsection |
| [`directives/README.md`](directives/README.md) | Architect directive registry |
| [`directives/directive_execution_log.md`](directives/directive_execution_log.md) | Directive closure / evidence |
| [`../working/current_directive.md`](../working/current_directive.md) | Active implementation slice (when present) |
| **[`policy_package_standard.md`](policy_package_standard.md)** | **Mandatory contract** for **any** new Jupiter baseline policy (JUPv3, JUPv4, JUPv5, …): Sean / AI output → reviewable package → merge. Not optional. |

**Plan / log sync:** When scope or status changes, update **master plan** and **directive execution log** in the **same change set** with matching granularity (`Plan/log status sync: PASS`).

### Jupiter baseline policy — Sean / AI → Blackbox (non‑negotiable)

New baseline Jupiter policies are **not** ad-hoc Python in the bridge. They **must** follow the **policy package contract** end to end:

1. **Read** [`policy_package_standard.md`](policy_package_standard.md) — folder layout, required **`POLICY_SPEC.yaml`**, **`INTEGRATION_CHECKLIST.md`**, engineering checklist (ledger slot, `signal_mode`, evaluator, `sean_jupiter_baseline_signal`, bundle/API, tests, deploy proof).
2. **Generate** using the AI instruction pattern in [`jupv4_grok_implementation_prompt.md`](jupv4_grok_implementation_prompt.md) (same idea for **JUPv5+**; update titles/paths in the prompt as needed).
3. **Gate mechanically** before deep integration: `python3 scripts/validate_policy_package.py <package_dir>` (requires PyYAML). **Fail closed** — send the package back, do not “fix forward” in ledger code without a passing package.
4. **Integrate** in **one** PR: slot + wiring + tests per the checklist — no silent string slots.

**Canonical reference policy:** [`JUPv3.md`](JUPv3.md). Blackbox does **not** execute unreviewed policy strings; merged code + tests + operator slot selection only.

---

## Slack → OpenClaw / BlackBox conversational operator

**Canonical directive-driven program:** [`slack_conversational_operator/canonical_development_plan.md`](slack_conversational_operator/canonical_development_plan.md) — **BBX-SLACK-001** through **009**, operator accept/reject loop, deferred MVP items.

**Technical LDD:** [`slack_conversational_operator/slack_conversational_operator_system_ldd.md`](slack_conversational_operator/slack_conversational_operator_system_ldd.md) — includes **§0.5** / **§24** (live route inventory, interception posture, cutover) and **§25** (readiness gate — **no BBX-SLACK-002 code start** until **§25.3** package accepted).

**Constraint:** Jupiter **V2** trading policy behavior remains **untouched** by this workstream unless **separately authorized**.

---

## Templates

- New directive: [`directives/DIRECTIVE_TEMPLATE.md`](directives/DIRECTIVE_TEMPLATE.md)
- Closeout: [`directives/CLOSEOUT_PACKET_TEMPLATE.md`](directives/CLOSEOUT_PACKET_TEMPLATE.md)

---

## Agent training (analyst / strategist)

Governed agent development (Anna and others) stays within **directives, proof, risk tiers, and Layer 3/4 gates** — same as all other work. Operational personas (Telegram, Slack) must not bypass execution boundaries.
