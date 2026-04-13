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

**Plan / log sync:** When scope or status changes, update **master plan** and **directive execution log** in the **same change set** with matching granularity (`Plan/log status sync: PASS`).

---

## Slack → OpenClaw / BlackBox conversational operator

**Canonical directive-driven program:** [`slack_conversational_operator/canonical_development_plan.md`](slack_conversational_operator/canonical_development_plan.md) — **BBX-SLACK-001** through **009**, operator accept/reject loop, deferred MVP items.

**Technical LDD:** [`slack_conversational_operator/slack_conversational_operator_system_ldd.md`](slack_conversational_operator/slack_conversational_operator_system_ldd.md) — includes **§0.5** / **§24** (live route inventory, interception posture, cutover; not a greenfield build).

**Constraint:** Jupiter **V2** trading policy behavior remains **untouched** by this workstream unless **separately authorized**.

---

## Templates

- New directive: [`directives/DIRECTIVE_TEMPLATE.md`](directives/DIRECTIVE_TEMPLATE.md)
- Closeout: [`directives/CLOSEOUT_PACKET_TEMPLATE.md`](directives/CLOSEOUT_PACKET_TEMPLATE.md)

---

## Agent training (analyst / strategist)

Governed agent development (Anna and others) stays within **directives, proof, risk tiers, and Layer 3/4 gates** — same as all other work. Operational personas (Telegram, Slack) must not bypass execution boundaries.
