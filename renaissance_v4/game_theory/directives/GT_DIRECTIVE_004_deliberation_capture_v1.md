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

**Status:** implementation + proof landed — **Requesting architect acceptance**

**Work performed**

- **`exam_deliberation_capture_v1.py`** — Pydantic **§11.2** contract: H1–H3 rows (`market_interpretation`, `indicator_support`, `resulting_action`, `falsification_condition`), H4 (`comparative_evaluation`, `primary_selection`, `bounded_reasoning`), version gate (`schema_version` ∈ **1.0.0**), JSON key **`schema`** = `exam_deliberation`, pack envelope `pack_deliberation_policy` (`k_min`, `data_gap_allowed_paths`), **`data_gaps`** only on allowed paths, **`assert_non_placeholder_deliberation_v1`**, in-memory **frame 0** store + `deliberation_http_route_matrix_v1()`.
- **`schemas/exam_deliberation_payload_v1.schema.json`** — generated JSON Schema artifact (`$id` + **required** includes `schema`, `schema_version`, `exam_unit_id`, `hypotheses`, `h4`).
- **Fixtures / proof:** `docs/proof/exam_v1/fixture_exam_deliberation_valid_k3_v1.json` (K=3, full H4), `docs/proof/exam_v1/operator_proof_frame0_deliberation_dev_v1.json` (dev GET shape + paths).
- **`web_app.py`** — `PUT` / `GET` **`/api/v1/exam/units/<exam_unit_id>/frames/0/deliberation`**; **200** success, **400** envelope JSON/Pydantic errors, **404** unknown unit / no deliberation, **422** `exam_unit_id` mismatch vs path, policy / placeholder / semantic errors; docstring + **`PATTERN_GAME_WEB_UI_VERSION`** → **2.19.33**.
- **Tests:** `tests/test_exam_deliberation_capture_v1.py` — fixture round-trip, schema file checks, malformed + bad version, `k_min`, `data_gap` allow/deny, **placeholder regression**, exporter dict, HTTP matrix, full PUT/GET 200, 404/422/400 cases, pure store round-trip.

**HTTP route matrix (this slice)**

| Method | Path | Success | Errors |
|--------|------|---------|--------|
| `PUT` | `/api/v1/exam/units/{exam_unit_id}/frames/0/deliberation` | **200** | **400** envelope validation, **404** unknown `exam_unit_id`, **422** deliberation `exam_unit_id` ≠ path, policy / placeholder |
| `GET` | `/api/v1/exam/units/{exam_unit_id}/frames/0/deliberation` | **200** | **404** unknown unit or deliberation not stored |

**Proof produced**

- `python3 -m pytest tests/test_exam_deliberation_capture_v1.py tests/test_exam_state_machine_v1.py` — **25 passed** (8 state machine + 17 deliberation).
- Commit + push + **`python3 scripts/gsync.py --no-commit --force-restart`** (pattern-game) after merge.

**Remaining gaps (explicitly out of §11.2 scope)**

- No durable DB; no auth; pack policy still **submitted with body** until a pack registry exists; **§11.3** decision_frame parent/child not implemented; **§11.4** downstream generator not built; **UI splice** not done.

**Alignment with architecture**

- Implements **§11.2** “H1–H4 exporter (non-placeholder); schema versioned” and **§1** learning model deliberation / H4 bullets as **typed fields**, not parallel-runner traces.
- **§11.1** untouched (ordering / invalidation).

**Requesting architect acceptance**

---

## Architect review

**Status:** pending architect review

Architect will append one of:

- `Accepted`
- `Rejected — rework required`
