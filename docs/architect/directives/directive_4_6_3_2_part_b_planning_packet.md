# Directive 4.6.3.2 Part B — Planning Packet (No Runtime Implementation)

## Scope Statement

This document defines **planning boundaries only** for Part B.  
No runtime implementation is authorized by this packet.

Part A (`ea9c215`) is accepted as containment-only completion.

---

## Documentation / Status Synchronization (Mandatory)

When this packet is **approved**, **superseded**, or treated as **canonically closed** as planning, the same rules apply as for implementation directives:

- This packet is not considered complete, closed, advanced, or canonically valid unless `docs/blackbox_master_plan.md` and `docs/architect/directives/directive_execution_log.md` are updated to **matching status granularity** in the **same change set**.
- If a twig/sub-step is recorded in the execution log as active, complete, closed, implemented, or corrected, the master plan must reflect the same status **explicitly** (broader umbrella wording is not sufficient).
- Closeout or approval summaries must include: `Plan/log status sync: PASS`.

**Before return (checklist):**

- [ ] `docs/blackbox_master_plan.md` matches current planning/implementation state for Part B
- [ ] `docs/architect/directives/directive_execution_log.md` matches the same
- [ ] status granularity matches in both documents
- [ ] no stale wording remains for prior twigs/sub-steps
- [ ] completion summary includes `Plan/log status sync: PASS`

**Mismatch failure rule:** If documentation status mismatch is discovered after return, the work is considered incomplete; documentation must be corrected before any next directive begins; no subsequent twig or phase may proceed until sync is restored.

Canonical scaffolds: [`DIRECTIVE_TEMPLATE.md`](DIRECTIVE_TEMPLATE.md), [`CLOSEOUT_PACKET_TEMPLATE.md`](CLOSEOUT_PACKET_TEMPLATE.md).

---

## 1) Shared Reuse Boundary Rules

Future reuse must remain constrained by these contract rules:

- Reuse input unit is a lifecycle-managed learning record.
- Reuse eligibility remains **validated-only**.
- Non-validated states (`candidate`, `under_test`, `rejected`) are non-reusable.
- Reuse checks must be deterministic and auditable.
- Any new consumer path must call the same validated gate contract, not custom ad-hoc checks.

---

## 2) Future Agent Gate Requirement

When non-Anna agents integrate, they must pass through the same validated-only gate:

- No direct bypass to raw candidate memory.
- No agent-specific “temporary trust” exceptions.
- No silent fallback from failed gate to non-validated reuse.

Contract intent: one reusable-truth standard for all agents.

---

## 3) DATA-First Integration Boundary

DATA is the next planned integration target.

DATA boundary for Part B planning:

- Integrate read/use path through validated-only gate first.
- Preserve DATA persona/routing behavior.
- Keep responses factual/state-oriented; no learning-driven behavior shifts outside approved scope.

---

## 4) Cody-After-DATA Boundary

Cody integration is sequenced after DATA.

Cody boundary for Part B planning:

- Reuse limited to validated pattern constraints only.
- No expansion into autonomous policy mutation or execution-side logic.
- Preserve existing Cody role boundaries and runtime behavior.

---

## 5) Mia/Billy Status

- Mia remains stubbed unless separately directed.
- Billy remains stubbed unless validated-signal governance is explicitly approved.

No runtime expansion is planned for Mia/Billy in Part B kickoff.

---

## 6) Implementation Freeze Rule for This Step

For this packet:

- planning/docs only,
- no runtime changes,
- no schema expansion beyond accepted Part A,
- no new agent runtime wiring.

---

## Acceptance Intent (Planning Phase)

Part B planning is considered ready when:

- shared boundary rules are approved,
- DATA-first and Cody-following-DATA sequencing is approved,
- Mia/Billy stub constraints are explicitly reaffirmed,
- implementation authorization is issued in a separate directive.

When this packet or its successors are closed or advanced in the log, the **Documentation / Status Synchronization** section above applies; any closeout must include `Plan/log status sync: PASS`.
