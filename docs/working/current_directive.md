# Current directive

**Status:** Active — **Phase 5.3b stored-data backtest / simulation loop**

**Last updated:** 2026-03-26 17:24 CDT — **Architect (Codex):** accepted and closed Phase 5.3a after code review plus local pytest verification, synced the roadmap docs, and issued the next directive from `docs/architect/development_plan.md`.

**Previous directive closed:** 2026-03-26 17:24 CDT — **Architect (Codex):** Phase 5.3a deterministic strategy evaluation contract accepted and closed.

**Shared docs meaning:** When the user says `shared docs`, read and update:
- `docs/working/current_directive.md`
- `docs/working/shared_coordination_log.md`

**Shared docs manual:** `docs/working/HOW_TO_SHARED_DOCS.md`
**Bridge state:** `docs/working/foreman_bridge.json`
**Developer handoff:** `docs/working/developer_handoff.md`
**Cursor enforcement rule:** `.cursor/rules/foreman-bridge-enforcement.mdc`
**Foreman MCP server:** `scripts/runtime/foreman_bridge_mcp.py`

**Project-wide rule:** Shared-docs protocol is project-wide for BLACK BOX unless the operator explicitly changes it.

**Architect review:** Pending Developer→Architect asks live in **`shared_coordination_log.md` → `## Architect review requested`**. Operator shortcut **`architect review`** = read that section first. See `HOW_TO_SHARED_DOCS.md` § Architect review requests.

**Directive authority:** This file is the live directive source unless replaced by a newer directive written here.

---

## Title

**PHASE 5.3B — STORED-DATA BACKTEST / SIMULATION LOOP**

---

## Objective

Build the next Phase 5 slice from `docs/architect/development_plan.md` by creating a **stored-data-only backtest / simulation loop** on top of the validated `5.3a` deterministic strategy evaluation surface.

This directive is about **simulation**, not execution. It must stay read-only against market storage and must not invent any Billy, Layer 4, or live trading behavior.

This directive is satisfied only by implementation, tests, proof written into shared docs, and clear remaining gaps.

---

## Scope

- Align to:
  - `docs/blackbox_master_plan.md`
  - `docs/architect/development_plan.md` (Phase 5.3 direction)
  - `docs/architect/directives/directive_execution_log.md`
  - `docs/working/HOW_TO_SHARED_DOCS.md`
  - `docs/working/shared_coordination_log.md`
- Preserve separation:
  - Anna = strategy/analysis
  - Billy = execution
  - Foreman = coordination/closure

## Required implementation

- Add a deterministic backtest / simulation surface that reads **stored** market data only and reuses the existing `5.3a` strategy evaluation contract.
- Keep the first version scoped to a single symbol / small universe.
- Emit a structured simulation artifact with:
  - participant scope
  - symbol
  - deterministic strategy version
  - simulation window or sample count
  - summary result fields
  - abstain / skip counts when applicable
- Enforce tier alignment:
  - do not auto-assign or escalate `risk_tier`
  - simulation behavior must remain inside the selected tier
- Keep this slice read-only and non-executing:
  - no Billy behavior
  - no Layer 4 intent
  - no live venue actions
  - no order placement or account mutation

## Notes / constraints

- Use the existing market-data store, participant-scoped read contracts from Phase 5.2a, and the validated strategy evaluation contract from Phase 5.3a.
- The first implementation may be simple, but it must be deterministic and testable.
- Foreman talking-stick enforcement remains hard: developer acts only with the stick; architect validates only with the stick.

---

## Execution / proof protocol (reminder)

- Record implementation proof in `docs/working/shared_coordination_log.md` with timestamps (files changed, commands, tests, remaining gaps).
- When ready, return the handoff phrase: **`have the architect validate shared-docs`**.
