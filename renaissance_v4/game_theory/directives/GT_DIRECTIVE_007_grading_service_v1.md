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

**Status:** implementation complete (2026-04-22); **§11.5 CLOSED** — architect accepted (2026-04-22).

**Summary:** Added `exam_grading_service_v1.py` with `ExamPackGradingConfigV1` (economic modes: `expectancy`, `profit_factor_drawdown`, `no_trade_neutral`; optional `win_rate_overlay` that never replaces base E as sole pass when `require_also_base_pass` is true), explicit **P1/P2/P3** sub-scores blended by pack `process_weights`, `PASS = E_passes AND P >= p_min`. Pack configs registered in dev via `register_exam_pack_grading_config_v1` and `POST /api/v1/exam/packs/<exam_pack_id>/grading-config`. `GET …/grade` reads committed timeline + frame-0 deliberation + unit pack ids; **409** incomplete, **422** invalid/missing refs or bad economic inputs, **500** missing pack grading config.

**Files:** `exam_grading_service_v1.py`, `web_app.py` (routes + version), `tests/test_exam_grading_service_v1.py`, `renaissance_v4/game_theory/docs/proof/exam_v1/fixture_exam_grading_pack_and_outcomes_v1.json`, `docs/proof/exam_v1/operator_proof_exam_grade_gt007_v1.json`.

Requesting architect acceptance — **superseded:** architect acceptance recorded below (2026-04-22).

---

## Architect review

**Status:** **CLOSED** — §11.5 accepted (2026-04-22)

**Context:** Review of §11.5 grading service delivery including engine, API, tests, proof artifacts, and deploy status at commit **92ac42df**.

**Decision:** GT_DIRECTIVE_007 §11.5 is **ACCEPTED** and **CLOSED**.

**Verified:** Economic **E** supports pack modes `expectancy`, `profit_factor_drawdown`, `no_trade_neutral`; thresholds and context keys from pack only; `win_rate_overlay` is a secondary **AND** on base E when configured, not a sole pass gate; inputs from last downstream `downstream_context` via pack keys; no indicator recomputation. **P**: P1 H1–H3 + H4 completeness; P2 H4 primary vs sealed `enter`; P3 timeline integrity (ENTER downstream + OHLC snapshots, NO_TRADE no downstream, monotonic timestamps); blend via pack `process_weights`. **PASS** = `(E passes) AND (P ≥ p_min)` from pack. **API** `GET …/grade`: **200** / **409** incomplete / **422** invalid or config issues / **500** missing pack grading config / **404** unknown unit. **Audit:** `exam_pack_id`, `exam_pack_version`, `graded_at`, `grading_mode`. Pack binding via `register_exam_pack_grading_config_v1` / retrieval; tests cover PASS, fail E, fail P, boundaries, PF+DD, HTTP, fixture + operator proof. **Deploy:** **92ac42df** on `origin/main`; gsync completed; pattern-game restarted on clawbot (PID **2502506**).

**Architect note:** Using **last downstream** frame context as the economic scalar source is acceptable for this slice (pack-defined keys, no recomputation). Future refinement may add multi-frame aggregation; not required for §11.5. Dev `POST …/grading-config` is acceptable until a **centralized pack registry** lands in a later slice.

### Architect Acceptance — §11.5

Grading service implementation satisfies the requirements of §11.5.

* Economic grading supports pack-defined modes (expectancy, profit factor + drawdown, neutral)
* No hardcoded thresholds are used; all thresholds come from exam_pack configuration
* Win rate is not used as a sole pass condition
* Process scoring enforces hypothesis completeness, decision consistency, and mechanism adherence
* PASS condition is correctly implemented as (E AND P ≥ p_min)
* All grading inputs are derived from committed decision frames and deliberation payloads
* No recomputation of indicators or decisions occurs
* API endpoint returns correct status codes and includes required audit fields
* Fixture, automated tests, and operator proof artifacts are present
* Implementation was committed, pushed, and deployed without impacting prior directives

**Directive GT_DIRECTIVE_007 §11.5 is accepted.**

**GT_DIRECTIVE_007 §11.5 is now CLOSED.**

**One-line summary:** The system can now judge decisions using pack-defined economics and process rules — the exam engine is fully functional.

---

## Next step (engineering)

**Active slice:** **§11.7 / §12 — UI splice** (timeline + drill-down) per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`.
