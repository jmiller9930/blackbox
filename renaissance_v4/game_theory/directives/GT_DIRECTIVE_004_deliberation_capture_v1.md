# GT_DIRECTIVE_004 — Deliberation capture (§11.2)

**Date:** 2026-04-22  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §11.2)  
**To:** Engineer  
**CC:** Product, Referee, UI, Operator  
**Scope:** `renaissance_v4/game_theory` only

**Predecessor:** `GT_DIRECTIVE_003_exam_state_machine_v1.md` (**§11.1 — CLOSED**).

## Canonical workflow record

This file is the canonical record for this directive.

Workflow:

1. Architect issues directive here.
2. Engineer reads and performs work.
3. Engineer appends response below.
4. Operator notifies Architect to review this folder.
5. Architect appends acceptance or rework below.

## Fault

Without a **non-placeholder H1–H4 deliberation exporter** and **versioned schema**, packs cannot prove hypothesis capture, **data_gap** rules stay implicit, and integrations risk shipping placeholder-only paths as “done.”

## Directive

Implement **§11.2 — Deliberation capture** (architecture verbatim intent):

1. **H1–H4 exporter** (non-placeholder): populates all required H fields per chosen schema name (e.g. `exam_deliberation` or aligned name in code).
2. **Schema versioned**: artifact + validation (JSON Schema, Pydantic, or equivalent) that **rejects** malformed payloads.
3. **`data_gap`**: allowed **only** where the pack explicitly permits omission; otherwise required fields must not silently become empty strings.

## Proof required

Per **Proof (non-negotiable) — 11.2** in `docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`:

- **Automated tests:** exporter fills **all** required H fields; **no** silent empty strings where schema requires content; **`data_gap`** only where pack explicitly allows omission.
- **Schema proof:** versioned schema artifact + validation test rejecting malformed payloads.
- **Fixture:** checked-in sample `exam_deliberation` (or chosen schema name) with **≥ K** hypotheses + **H4** selection block — referenced by tests.
- **Regression:** test that **placeholder-only** export path **cannot** ship as “done” for this directive’s scope (assert non-placeholder invariants).
- **Operator evidence:** diff or excerpt showing **real** deliberation record attached to **frame 0** in dev.
- **HTTP proof:** any new **submit deliberation** route returns **200** on valid body, **4xx** on invalid — documented in PR or this file’s engineer update.

## Deficiencies log update

Engineer must list any remaining gaps (persistence, auth, UI polish) under **Engineer update → remaining gaps**; do not claim **§11.2** architect acceptance until proof above is satisfied.

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
