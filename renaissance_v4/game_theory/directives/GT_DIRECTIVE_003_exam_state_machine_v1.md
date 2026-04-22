# GT_DIRECTIVE_003 — Exam state machine (§11.1)

**Date:** 2026-04-21  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`)  
**To:** Engineer  
**CC:** Operator  
**Scope:** `renaissance_v4/game_theory`

## Canonical workflow record

This file is the canonical record for this directive.

Workflow:

1. Architect issues directive here.
2. Engineer reads and performs work.
3. Engineer appends response below.
4. Operator notifies Architect to review this folder.
5. Architect appends acceptance or rework below.

## Fault

Without an explicit **exam unit lifecycle**, implementations risk **wrong reveal order** (§3), **silent mutation** of moment truth, or **ambiguous** HTTP contracts for external systems.

## Directive

Implement **§11.1**:

1. **State machine** enforcing **§3** ordering: opening shown → H1–H3 → H4 → seal Decision A → (if ENTER) downstream released → Decision B complete → unit complete. **NO_TRADE** skips downstream.
2. **Invalid transitions** MUST set unit **`invalid`** (no silent fixups).
3. **Dev API** under **`/api/v1/exam/units`**: create unit, GET unit, POST transition (`event` + `payload`).
4. **Golden fixture** + **automated tests** per architecture **Proof (non-negotiable) — 11.1**.

## Proof required

- Tests: valid ENTER path, valid NO_TRADE path, at least two forbidden transitions → `invalid`.
- Fixture: `docs/proof/exam_v1/golden_exam_unit_transition_trace_valid_v1.json` replayed by test.
- HTTP: `POST /api/v1/exam/units` → **201**; transition **200** / **409** documented.
- PR route matrix for three exam routes.

## Deficiencies log update

If gaps remain (persistence, auth, durable store), list under **Engineer update → remaining gaps**; do not claim Directive 003 “production complete” until Architect accepts.

---

## Engineer update

**Status:** initial implementation landed (pending architect acceptance)

**Work performed:**

- Added `renaissance_v4/game_theory/exam_state_machine_v1.py` — in-memory `ExamUnitState`, forward-only transitions, `INVALID` on violation.
- Added `POST/GET /api/v1/exam/units` and `POST /api/v1/exam/units/<id>/transition` in `web_app.py`; module docstring + `PATTERN_GAME_WEB_UI_VERSION` bump.
- Tests: `tests/test_exam_state_machine_v1.py` (pure + API smoke + golden replay).
- Fixture: `docs/proof/exam_v1/golden_exam_unit_transition_trace_valid_v1.json`.

**Files changed:** (see commit)

**Proof produced:** pytest `tests/test_exam_state_machine_v1.py` green.

**Remaining gaps:** no durable store; no auth; process-local memory only; no UI splice; deliberation payloads not yet attached to frames (Directive **11.2**).

**Requesting architect acceptance**

---

## Architect review

**Status:** pending architect review

Architect will append `Accepted` or `Rejected — rework required` here.
