# Current directive

**Status:** Active — **Phase 5.4 (continued) — Layer 3 approval routing for trade candidates**

**Last updated:** 2026-03-30 — **Architect:** Phase D closeout for **5.4 CandidateTradeV1**; next open **`development_plan.md` §5.4** task: route through **Layer 3** approval; no execution without **APPROVED** artifact.

**Previous directive closed:** 2026-03-30 — **Architect:** **5.4 — Candidate trade artifact (v1)** accepted and closed (see `docs/architect/directives/directive_5_4_candidate_trade_artifact_v1_closeout.md`).

**Shared docs meaning:** When the user says `shared docs`, read and update:
- `docs/working/current_directive.md`
- `docs/working/shared_coordination_log.md`

**Shared docs manual:** `docs/working/HOW_TO_SHARED_DOCS.md`
**Bridge state:** `docs/working/foreman_bridge.json`
**Developer handoff:** `docs/working/developer_handoff.md`
**Cursor enforcement rule:** `.cursor/rules/foreman-bridge-enforcement.mdc`
**Foreman MCP server:** `scripts/runtime/foreman_bridge_mcp.py`

**Project-wide rule:** Shared-docs protocol is project-wide for BLACK BOX unless the operator explicitly changes it.

**Architect review:** Pending developer→architect asks live in **`shared_coordination_log.md` → `## Architect review requested`**.

**Directive authority:** This file is the live directive source unless replaced by a newer directive written here.

**Canonical slice identity (5.4 continued):** Wire **`CandidateTradeV1`** (or a thin adapter) into the **Layer 3** approval path per **`docs/architect/layer_3_approval_interface_design.md`** and **`docs/architect/development_plan.md` §5.4** (remaining task: approval routing). **No** Layer 4 execution, **no** venue/Billy live actions in this slice unless a future directive explicitly expands scope.

**Talking stick / Foreman:** Use shared docs for proof unless a directive re-enables stick gating.

**Autonomous handoff:** `python3 scripts/runtime/governance_bus.py --peek` (`--as Architect` / `--as Developer` / `--developer-phase-b` as appropriate).

---

## Title

**PHASE 5.4 (CONTINUED) — LAYER 3 APPROVAL ROUTING FOR CANDIDATE TRADES**

---

## Objective

Route **`CandidateTradeV1`** trade candidates into the **Layer 3** approval flow so that **no downstream execution** consumes a candidate without a canonical **APPROVED** artifact tied to Layer 3 policy. This slice binds the Phase 5 engine candidate to the existing **decision surface** contract (see `scripts/runtime/approval_interface/` and design docs); it does **not** implement Layer 4 execution.

---

## Acceptance criteria (Architect — Phase A)

- **Plan alignment:** Maps to **`docs/architect/development_plan.md` §5.4** open line: **Route to Layer 3 approval flow; no execution without APPROVED artifact.**
- **Design alignment:** Behavior and artifacts remain consistent with **`docs/architect/layer_3_approval_interface_design.md`** (approve / reject / defer; audit; no execution from L3 UI).
- **Non-execution:** No live venue calls, no Billy execution, no Layer 4 intent emission in this slice unless explicitly scoped later.
- **Proof:** `docs/working/shared_coordination_log.md` lists files, pytest / harness commands, gaps.
- **Review:** Developer uses **`have the architect validate shared-docs`** when ready for Phase C.

---

## Scope

- Align to:
  - `docs/blackbox_master_plan.md` §5.4
  - `docs/architect/layer_3_approval_interface_design.md`
  - `docs/design/twig6_approval_model.md` (artifact shape) where applicable
  - `scripts/runtime/market_data/candidate_trade.py` (`CandidateTradeV1`)
  - `scripts/runtime/approval_interface/` (existing L3 surface — extend/wire, do not bypass)
- Out of scope: Layer 4, venue adapters, autonomous messaging approval.

## Required implementation (minimum direction)

- Define how a **`CandidateTradeV1`** is submitted or mirrored into the **approval artifact** model expected by Layer 3 (IDs, status, linkage, expiration fields per policy).
- Enforce **no execution** without **APPROVED** state on the approval record (tests or harness proving reject/defer paths do not emit execution).
- Tests covering the binding contract you introduce.

## Notes / constraints

- Prefer **thin** adapters over duplicating approval business logic.
- If the repo’s `approval_interface` uses a different legacy artifact shape, document the mapping explicitly in code comments and shared log.

---

## Execution / proof protocol (reminder)

- Record proof in `docs/working/shared_coordination_log.md` with timestamps.
- Handoff phrase: **`have the architect validate shared-docs`**.
