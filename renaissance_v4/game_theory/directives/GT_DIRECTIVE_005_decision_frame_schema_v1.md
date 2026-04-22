# GT_DIRECTIVE_005 — Decision frame schema (§11.3)

**Date:** 2026-04-22  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §11.3, **§2**)  
**To:** Engineer  
**CC:** Product, Referee, UI, Operator  
**Scope:** `renaissance_v4/game_theory` only

**Predecessor:** `GT_DIRECTIVE_004_deliberation_capture_v1.md` (**§11.2 — CLOSED**).

## Canonical workflow record

This file is the canonical record for this directive.

Workflow:

1. Architect issues directive here.
2. Engineer reads and performs work.
3. Engineer appends response below.
4. Operator notifies Architect to review this folder.
5. Architect appends acceptance or rework below.

## Fault

Without a **versioned parent `exam_unit` + ordered `decision_frame[]` contract**, frame keying (**§2**, **§4**) stays implicit, carousel/timeline consumers cannot prove ordering or **`decision_frame_id`** uniqueness, and ENTER vs NO_TRADE frame-count rules remain ambiguous.

## Directive

Implement **§11.3 — Decision frame schema**:

1. **Parent unit** + **ordered** `decision_frame[]` per architecture **§2** (frame 0 = opening + deliberation slice linkage + Decision A when sealed; frames 1…n only when applicable per ENTER path — align with existing §11.1 state machine, **without** implementing §11.4 downstream generation in this slice unless minimally required for schema placeholders).
2. **Round-trip** serialize / parse with stable ordering; **`decision_frame_id`** unique within unit.
3. **Keying tests:** frame 0 vs 1…n linkage; **ENTER** vs **NO_TRADE** frame count rules per **§2** / pack defaults.
4. **Contract documentation** matching **§4** / **§8** echoes (`exam_pack_id`, `exam_unit_id`, etc.).

## Proof required

Per **Proof (non-negotiable) — 11.3** in `docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`:

- **Automated tests:** round-trip serialize/parse `exam_unit` + ordered `decision_frame[]`; ordering stable; **`decision_frame_id`** uniqueness within unit.
- **Keying tests:** frame 0 vs 1…n linkage per **§2**; ENTER vs NO_TRADE frame count rules.
- **Fixture:** minimal **golden JSON** (parent + 2 frames) under `tests/` or `docs/proof/…` consumed by tests.
- **Contract:** documented field list matches **§4** / **§8** references.
- **Operator evidence:** sample GET (or export) showing nested frames in correct order.
- **HTTP proof:** fetch-by-unit and fetch-by-frame routes **200** with golden shape (**404** documented for missing).

## Deficiencies log update

Engineer must list remaining gaps (persistence, pack registry, UI) under **Engineer update → remaining gaps**; do not claim **§11.3** architect acceptance until proof above is satisfied.

---

## Engineer update

**Status:** pending engineer response

Engineer must append:

- summary of work performed
- files changed
- proof produced
- remaining gaps
- explicit line: `Requesting architect acceptance`

---

## Architect review

**Status:** pending architect review

Architect will append one of:

- `Accepted`
- `Rejected — rework required`
