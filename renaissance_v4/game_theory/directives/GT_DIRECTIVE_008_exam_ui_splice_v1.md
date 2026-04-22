# GT_DIRECTIVE_008 — Exam UI splice (§11.7 / §12)

**Date:** 2026-04-21  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §11.7 and §12)  
**To:** Engineering  
**CC:** Product, Referee, UI, Operator  
**Scope:** `renaissance_v4/game_theory` (Pattern Machine `web_app.py` + tests; exam APIs already from §11.3–§11.5)

**Predecessor:** `GT_DIRECTIVE_007_grading_service_v1.md` (**§11.5 — CLOSED**). Exam timeline APIs (`GET …/decision-frames`, `GET …/frames/<id>`) are shared with prior slices; this directive closes **operator-visible UI wiring** only.

## Canonical workflow record

Workflow: Architect issues → Engineer implements → Engineer appends update → Operator notifies → Architect accepts/rejects.

## Fault

Without an **exam_unit_id-driven UI splice**, operators cannot navigate the committed decision-frame timeline or inspect frame JSON from the Pattern Machine Student surface; exam closure stays API-only and does not satisfy §11.7 / §12 product acceptance.

## Directive

Per architecture **§11.7** and **§12**:

* UI in the **Student → learning → outcome** fold hosts the exam timeline strip (`#pgExamUiSplice`).
* Timeline loads by **`exam_unit_id`** via **`GET /api/v1/exam/units/<exam_unit_id>/decision-frames`**.
* Ordered frame **carousel**; **drill-down** via **`GET /api/v1/exam/frames/<decision_frame_id>`** into **`#pgExamDrillHost`**.
* **Click** and **keyboard** (Enter / Space) activation on cards.
* **Clear / reset** of splice-local state without breaking the rest of the page.
* **Boot-time wiring** (init on page load).
* **Tests:** HTML markers for shell + wiring; HTTP smoke for the two GET routes the UI uses.
* **Delivery:** commit, `git push`, remote restart (`gsync` / pattern-game as applicable).

## Proof required

Per architecture §11.7 / §12 and §16.0 minimum bar: automated tests merged; HTTP 200 on the UI’s GET paths in a golden flow; `PATTERN_GAME_WEB_UI_VERSION` bump when HTML/JS changes; commit + push + deploy record.

## Deficiencies log update

No change to `pattern_game_operator_deficiencies_work_record` required for this slice unless a new UI defect is filed.

---

## Engineer update

**Status:** implementation complete; requesting architect acceptance — **superseded:** acceptance recorded below (2026-04-21).

**Summary:** Exam timeline splice lives under `#pgExamUiSplice` with `wireExamUiSpliceV1` boot wiring; loads decision frames by `exam_unit_id`; carousel cards fetch drill JSON into `#pgExamDrillHost`; clear resets local splice state; click + Enter/Space supported.

**Files:** `renaissance_v4/game_theory/web_app.py` (`PATTERN_GAME_WEB_UI_VERSION`, HTML + inline JS), `tests/test_exam_ui_timeline_splice_v1.py`.

**Proof:** `test_index_html_contains_exam_timeline_splice_shell` (markers + wiring strings); `test_exam_timeline_http_flow_after_seal` (NO_TRADE sealed unit → `decision-frames` 200 → frame GET 200). Deploy: committed, pushed, `gsync` / pattern-game restarted per operator record.

**Remaining gaps (non-blockers for this slice):** Full embed into L2/L3 run-selection as primary navigation is a **product integration** choice (architect note: exam_unit_id-driven strip is acceptable for v1).

---

## Architect review

**Status:** **CLOSED** — §11.7 / §12 accepted (2026-04-21)

**Context:** Review of exam UI splice delivery: timeline load by `exam_unit_id`, decision-frame carousel, frame drill-down, clear/reset, boot wiring, tests, and deploy.

**Decision:** **ACCEPTED** as the current UI splice shape. It is acceptable that the first version is an **exam_unit_id-driven strip** rather than being fully embedded into the existing L2/L3 run-selection flow; that is a product integration choice, not a blocker to accepting the splice itself.

### Architect Acceptance — §11.7 / §12

Exam UI splice implementation satisfies the required timeline and drill-down behavior for this slice.

* exam timeline loads from the decision-frame API by exam_unit_id
* ordered frame cards render in a carousel
* selected frame drill-down loads from the frame API
* interaction supports click and keyboard activation
* clear/reset behavior is present
* UI wiring is active on page boot
* tests cover required HTML markers and HTTP smoke for the routes used by the UI
* implementation was committed, pushed, and deployed

This slice is accepted and closed.

**Directive GT_DIRECTIVE_008 §11.7 / §12 is accepted.**

**GT_DIRECTIVE_008 §11.7 / §12 is now CLOSED.**

---

## Closed slices (exam path — cumulative)

The following **§11** / **§12** engineering slices are **CLOSED** in repo directive records:

* **§11.1** State Machine — `GT_DIRECTIVE_003_exam_state_machine_v1.md`
* **§11.2** Deliberation Capture — `GT_DIRECTIVE_004_deliberation_capture_v1.md`
* **§11.3** Decision Frame Schema — `GT_DIRECTIVE_005_decision_frame_schema_v1.md`
* **§11.4** Downstream Frame Generator — `GT_DIRECTIVE_006_downstream_frame_generator_v1.md`
* **§11.5** Grading Service — `GT_DIRECTIVE_007_grading_service_v1.md`
* **§11.7 / §12** UI Splice — **this file (`GT_DIRECTIVE_008_exam_ui_splice_v1.md`)**

**One-line summary:** The exam system is now wired through UI: timeline in, frame drill-down in, accepted, and closed.

---

## Next step (engineering)

**§11.6 — API layer** (route matrix, optional E2E `submit → seal → frames → grade`) if contract gaps remain; later **centralized pack registry** for grading config. UI splice follow-on: deeper L2/L3 integration when product prioritizes it.
