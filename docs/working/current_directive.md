# Current directive

**Status:** Active — **Phase 5.4 candidate trade artifact (v1)**

**Last updated:** 2026-03-30 — **Architect:** Phase D closeout for **5.3E**; next slice **5.4** first task from `development_plan.md` §5.4 (candidate artifact only in this directive; Layer 3 routing is a **later** slice).

**Previous directive closed:** 2026-03-30 — **Architect:** Phase **5.3E** guardrailed self-directed paper/backtest experiments accepted and closed (see `docs/architect/directives/directive_5_3_e_guardrailed_experiments_closeout.md`).

**Shared docs meaning:** When the user says `shared docs`, read and update:
- `docs/working/current_directive.md`
- `docs/working/shared_coordination_log.md`

**Shared docs manual:** `docs/working/HOW_TO_SHARED_DOCS.md`
**Bridge state:** `docs/working/foreman_bridge.json`
**Developer handoff:** `docs/working/developer_handoff.md`
**Cursor enforcement rule:** `.cursor/rules/foreman-bridge-enforcement.mdc`
**Foreman MCP server:** `scripts/runtime/foreman_bridge_mcp.py`

**Project-wide rule:** Shared-docs protocol is project-wide for BLACK BOX unless the operator explicitly changes it.

**Architect review:** Pending developer→architect asks live in **`shared_coordination_log.md` → `## Architect review requested`**. Operator shortcut **`architect review`** = read that section first. See `HOW_TO_SHARED_DOCS.md` § Architect review requests.

**Directive authority:** This file is the live directive source unless replaced by a newer directive written here.

**Canonical slice identity (5.4):** This directive is **Phase 5.4 — signal → approval binding** (`docs/architect/development_plan.md` §5.4). This slice implements only the **first** unchecked task: a **candidate trade artifact** derived from existing strategy/signal surfaces. It does **not** require Layer 3 approval wiring, execution, or Billy in this directive.

**Talking stick / Foreman:** Unless this directive is amended to scope Foreman/Talking Stick work, stick gating remains **suspended** for core engine slices per operator 2026-03-29 precedent for 5.3E; use **shared docs** for proof. Re-check `talking_stick.json` and `foreman-bridge-enforcement.mdc` if a future directive re-enables stick gating.

**Autonomous handoff (operator 2026-03-30):** Before ending a turn, agents holding an architect or developer role should run `python3 scripts/runtime/governance_bus.py --peek` (optionally `--as Architect` / `--as Developer`). If **next_actor** matches the role, continue the chain without waiting on the operator.

---

## Title

**PHASE 5.4 — CANDIDATE TRADE ARTIFACT (V1)**

---

## Objective

Introduce a **typed, deterministic candidate trade artifact** that can be produced from the existing Phase 5.3 strategy outputs (evaluation, selection, fast-gate context as applicable) and that carries **size**, **risk envelope**, **time validity (expiry)**, and **full participant scope** (participant id/type, account/wallet context, selected risk tier, strategy profile) as required by `docs/blackbox_master_plan.md` §5.4.

This artifact is the **input shape** for future Layer 3 approval. This directive does **not** implement approval routing, execution, or venue interaction.

---

## Acceptance criteria (Architect — Phase A)

- **Plan alignment:** Maps to **`docs/architect/development_plan.md` §5.4** first task: create **candidate trade artifact** from signal (size, risk, expiry), including participant scope on the artifact.
- **Non-execution:** No orders, no live venue calls, no Billy, no Layer 3 **APPROVED** state machine in this slice (artifact + tests + docs proof only).
- **Determinism:** Same inputs → same artifact fields where the spec defines deterministic behavior; document any intentional nondeterminism (e.g. wall-clock expiry anchor) explicitly.
- **Proof:** `docs/working/shared_coordination_log.md` lists files, pytest commands/results, and gaps.
- **Review:** Developer uses **`have the architect validate shared-docs`** when ready for Phase C.

---

## Scope

- Align to:
  - `docs/blackbox_master_plan.md` §5.4
  - `docs/architect/development_plan.md` §5.4
  - `scripts/runtime/market_data/signal_contract.py` and existing `StrategyEvaluationV1` / `StrategySelectionV1` / gate artifacts as integration points
  - `docs/architect/directives/directive_execution_log.md`
- Out of scope for this directive:
  - Layer 3 approval flow implementation
  - Execution adapter or Layer 4 intent

## Required implementation

- Define a versioned dataclass or Pydantic-style structure (match repo conventions) for **CandidateTradeV1** (or equivalent name) with explicit fields for size, risk limits/caps, expiry, and participant scope mirroring `ParticipantScope` + strategy profile references.
- Provide a **pure function or small module** that builds the candidate from the validated 5.3 outputs (document which inputs are required vs optional).
- Unit tests proving serialization stability, required-field enforcement, and guardrails (no tier mutation).

## Notes / constraints

- Prefer extending existing contracts over parallel ad-hoc dicts.
- If SQLite or store access is needed, keep read-only patterns consistent with Phase 5.2–5.3.

---

## Execution / proof protocol (reminder)

- Record implementation proof in `docs/working/shared_coordination_log.md` with timestamps (files changed, commands, tests, remaining gaps).
- When ready, return the handoff phrase: **`have the architect validate shared-docs`**.
