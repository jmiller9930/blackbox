# GT_DIRECTIVE_007 — Grading service (§11.5)

**Date:** 2026-04-22  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §11.5)  
**To:** Engineer  
**CC:** Product, Referee, UI, Operator  
**Scope:** `renaissance_v4/game_theory` only

**Predecessor:** `GT_DIRECTIVE_006_downstream_frame_generator_v1.md` (**§11.4 — CLOSED**).

## Canonical workflow record

Workflow: Architect issues → Engineer implements → Engineer appends update → Operator notifies → Architect accepts/rejects.

## Fault

Without a **pack-driven grading service**, exam units cannot be judged on **economic (E)** and **process (P)** outcomes; operators cannot prove **PASS/FAIL** from committed artifacts.

## Directive

Implement **§11.5 — Grading service**: E, P, `pass`, audit fields; `GET /api/v1/exam/units/<exam_unit_id>/grade`; no UI splice in this slice.

## Proof required

Per architecture **§11.5** and directive email: automated tests (PASS, fail E, fail P, boundaries, pack binding), fixture, operator proof JSON, HTTP 200/4xx/500 behaviors, commit + push + gsync.

---

## Engineer update

**Status:** implementation complete (2026-04-22)

**Summary:** Added `exam_grading_service_v1.py` with `ExamPackGradingConfigV1` (economic modes: `expectancy`, `profit_factor_drawdown`, `no_trade_neutral`; optional `win_rate_overlay` that never replaces base E as sole pass when `require_also_base_pass` is true), explicit **P1/P2/P3** sub-scores blended by pack `process_weights`, `PASS = E_passes AND P >= p_min`. Pack configs registered in dev via `register_exam_pack_grading_config_v1` and `POST /api/v1/exam/packs/<exam_pack_id>/grading-config`. `GET …/grade` reads committed timeline + frame-0 deliberation + unit pack ids; **409** incomplete, **422** invalid/missing refs or bad economic inputs, **500** missing pack grading config.

**Files:** `exam_grading_service_v1.py`, `web_app.py` (routes + version), `tests/test_exam_grading_service_v1.py`, `renaissance_v4/game_theory/docs/proof/exam_v1/fixture_exam_grading_pack_and_outcomes_v1.json`, `docs/proof/exam_v1/operator_proof_exam_grade_gt007_v1.json`.

Requesting architect acceptance

---

## Architect review

**Status:** pending architect review
