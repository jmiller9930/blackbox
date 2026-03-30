# Current directive

**Status:** **Standby** — **no active engineering slice** until a new directive is written here after **operator/architect** conversation (2026-03-30).

**Last updated:** 2026-03-30 — **Architect:** Phase **5.4 (continued)** Layer 3 approval routing **closed**; **Phase 5.4** marked **COMPLETE** in `development_plan.md`. **Next `DIRECTIVE` on the governance bus is intentionally deferred** pending operator discussion.

**Previous directive closed:** 2026-03-30 — **5.4 (continued)** — Layer 3 approval routing for `CandidateTradeV1` (see `docs/architect/directives/directive_5_4_layer3_routing_closeout.md`). Prior: **5.4 CandidateTradeV1** artifact (`directive_5_4_candidate_trade_artifact_v1_closeout.md`).

**Shared docs meaning:** When the user says `shared docs`, read and update:
- `docs/working/current_directive.md`
- `docs/working/shared_coordination_log.md`

**Shared docs manual:** `docs/working/HOW_TO_SHARED_DOCS.md`
**Bridge state:** `docs/working/foreman_bridge.json`
**Developer handoff:** `docs/working/developer_handoff.md`
**Cursor enforcement rule:** `.cursor/rules/foreman-bridge-enforcement.mdc`
**Foreman MCP server:** `scripts/runtime/foreman_bridge_mcp.py`

**Project-wide rule:** Shared-docs protocol is project-wide for BLACK BOX unless the operator explicitly changes it.

**Architect review:** See **`shared_coordination_log.md` → `## Architect review requested`**.

**Directive authority:** This file is the live directive source. While **Standby**, do **not** infer a new slice from chat alone — wait for an update in **this file** or explicit operator/architect instruction recorded in governed docs.

**Talking stick / Foreman:** Unchanged unless a future directive scopes Foreman work.

**Autonomous handoff:** `python3 scripts/runtime/governance_bus.py --peek` — when **Standby**, follow bus `next_actor` and operator direction.

---

## Title

**STANDBY — NEXT DIRECTIVE PENDING OPERATOR CONVERSATION**

---

## Objective

No contracted implementation work until **`development_plan.md`** / operator defines the next slice (likely **5.5** execution adapter or other plan block) and this file is replaced with a full directive scaffold.

---

## Notes

- Canonical plan pointer: **`docs/architect/development_plan.md`**
- Completed block: **§5.4 Signal → approval binding** — **COMPLETE**
