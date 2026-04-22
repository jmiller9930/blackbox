# GT_DIRECTIVE_004 — Deliberation capture (§11.2)

**Date:** 2026-04-22  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §11.2)  
**To:** Engineer  
**CC:** Product, Referee, UI, Operator  
**Scope:** `renaissance_v4/game_theory` only

**Predecessor:** `GT_DIRECTIVE_003_exam_state_machine_v1.md` (**§11.1 — CLOSED**).  
**Successor:** `GT_DIRECTIVE_005_decision_frame_schema_v1.md` (**§11.3 — active**).

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

**Status:** **CLOSED** — **GT_DIRECTIVE_004 §11.2** fully accepted (2026-04-22). Do **not** reopen unless a **regression** is found. Next slice: **§11.3** → **`GT_DIRECTIVE_005_decision_frame_schema_v1.md`**.

**Work performed**

- **`exam_deliberation_capture_v1.py`** — Pydantic **§11.2** contract: H1–H3 rows (`market_interpretation`, `indicator_support`, `resulting_action`, `falsification_condition`), H4 (`comparative_evaluation`, `primary_selection`, `bounded_reasoning`), version gate (`schema_version` ∈ **1.0.0**), JSON key **`schema`** = `exam_deliberation`, pack envelope `pack_deliberation_policy` (`k_min`, `data_gap_allowed_paths`, **`allow_no_trade_primary`**), **`data_gaps`** only on allowed paths, **`validate_h4_primary_selection_integrity_v1`** (duplicate hypothesis ids; `NO_TRADE` primary pack-gated), **`assert_non_placeholder_deliberation_v1`**, in-memory **frame 0** store + `deliberation_http_route_matrix_v1()`.
- **`schemas/exam_deliberation_payload_v1.schema.json`** — generated JSON Schema artifact (`$id` + **required** includes `schema`, `schema_version`, `exam_unit_id`, `hypotheses`, `h4`).
- **Fixtures / proof:** `docs/proof/exam_v1/fixture_exam_deliberation_valid_k3_v1.json` (K=3, full H4), `docs/proof/exam_v1/operator_proof_frame0_deliberation_dev_v1.json` (dev GET shape + paths).
- **`web_app.py`** — `PUT` / `GET` **`/api/v1/exam/units/<exam_unit_id>/frames/0/deliberation`**; **200** success, **400** envelope JSON/Pydantic errors, **404** unknown unit / no deliberation, **422** `exam_unit_id` mismatch vs path, policy / placeholder / H4 integrity / semantic errors; docstring + **`PATTERN_GAME_WEB_UI_VERSION`** → **2.19.34**.
- **Tests:** `tests/test_exam_deliberation_capture_v1.py` — fixture round-trip, schema file checks, malformed + bad version, `k_min`, `data_gap` allow/deny, **H4 integrity** (duplicate ids, `NO_TRADE` disallowed by pack), **placeholder regression**, exporter dict, HTTP matrix, full PUT/GET 200, 404/422/400 cases, pure store round-trip.

**HTTP route matrix (this slice)**

| Method | Path | Success | Errors |
|--------|------|---------|--------|
| `PUT` | `/api/v1/exam/units/{exam_unit_id}/frames/0/deliberation` | **200** | **400** envelope validation, **404** unknown `exam_unit_id`, **422** deliberation `exam_unit_id` ≠ path, policy / placeholder / **H4 integrity** |
| `GET` | `/api/v1/exam/units/{exam_unit_id}/frames/0/deliberation` | **200** | **404** unknown unit or deliberation not stored |

**Proof produced**

- `python3 -m pytest tests/test_exam_deliberation_capture_v1.py tests/test_exam_state_machine_v1.py` — **28 passed** (8 state machine + 20 deliberation).
- Commit + push + **`python3 scripts/gsync.py --no-commit --force-restart`** (pattern-game) after merge.

**Remaining gaps (explicitly out of §11.2 scope)**

- No durable DB; no auth; pack policy still **submitted with body** until a pack registry exists; **§11.3** decision_frame parent/child not implemented; **§11.4** downstream generator not built; **UI splice** not done.

**Alignment with architecture**

- Implements **§11.2** “H1–H4 exporter (non-placeholder); schema versioned” and **§1** learning model deliberation / H4 bullets as **typed fields**, not parallel-runner traces.
- **§11.1** untouched (ordering / invalidation).

**Final verification (2026-04-22)** — **H4 primary_selection integrity**: `validate_h4_primary_selection_integrity_v1` (duplicate `hypothesis_id`, declared-id match, pack `allow_no_trade_primary` for `NO_TRADE`); negative tests + HTTP **422**; `PATTERN_GAME_WEB_UI_VERSION` **2.19.34**.

---

## Architectural constraints (audit — documentation)

**`pack_deliberation_policy` on submit (temporary):** The server currently accepts `pack_deliberation_policy` from the client request body for development. **This is not the long-term audit posture.** In future slices, **`pack_deliberation_policy` MUST be derived from authoritative `exam_pack_id` + pack version** (pack registry / signed config) and **MUST NOT remain client-controlled at submit time**. Engineering and Product should treat today’s behavior as **dev-only** until that migration lands.

---

## Architect review

**Status:** **Accepted — CLOSED** (2026-04-22)

**Architect Acceptance Confirmed — GT_DIRECTIVE_004 (§11.2) CLOSED**

Verified: H4 primary selection integrity enforced centrally; duplicate hypothesis IDs rejected; `primary_selection` must match a declared `hypothesis_id` unless `NO_TRADE`; `NO_TRADE` primary pack-gated via `allow_no_trade_primary`; HTTP **422** for integrity failures; negative tests (duplicate ids, disallowed NO_TRADE primary, HTTP 422); **`tests/test_exam_deliberation_capture_v1.py`** + **`tests/test_exam_state_machine_v1.py`** — **28 passed**; audit note recorded for future **pack_deliberation_policy** sourcing from **exam_pack_id** + version (not client-controlled long term); deploy + remote restart successful; **§11.3** not started without authorization.

**Acceptance statement — architecture contract satisfied**

* H1–H4 are explicitly structured and validated  
* Schema is versioned and enforced  
* Placeholder-only payloads are blocked  
* H4 selection integrity is enforced  
* `data_gap` remains pack-gated  
* Frame 0 deliberation is available over HTTP  
* Fixture and regression tests are in place  
* Audit constraint on pack-policy sourcing is documented  
* Deployment is complete  

**Directive status:** **GT_DIRECTIVE_004 §11.2 is CLOSED.** Do not reopen unless a regression is found.

**Next engineering slice:** **§11.3 — Decision Frame Schema** → **`GT_DIRECTIVE_005_decision_frame_schema_v1.md`**.

---

*Original acceptance record (subset):* Deliberation capture implementation satisfied §11.2 requirements (H1–H3 fields, H4 capture, schema at API boundary, placeholder rejection, pack-gated `data_gap`, frame 0 HTTP, fixtures/tests, no downstream/grading/UI scope creep). Contingency follow-ups **(1)** H4 integrity **`validate_h4_primary_selection_integrity_v1`** + tests **(2)** pack policy audit note — **done** (see **Architectural constraints** above).
