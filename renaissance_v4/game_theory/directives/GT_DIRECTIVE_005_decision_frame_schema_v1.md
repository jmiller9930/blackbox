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

**Status:** implementation + proof landed — **Requesting architect acceptance**

**Summary**

- **`exam_decision_frame_schema_v1.py`** — Pydantic **exam_unit_timeline**: parent `exam_unit_id` / pack echo + ordered **`decision_frames`**; child **`DecisionFrameV1`** (`decision_frame_id` canonical `{exam_unit_id}__df{n}` URL-safe, `frame_index`, bar-close **`timestamp`**, `frame_type` `opening`|`downstream`, **`payload`** with `opening_snapshot`, read-through **`deliberation`** dict, **`decision_a`**, `downstream_reserved` placeholder only). Validators: dense 0-based indices, unique ids, parent linkage, **NO_TRADE → exactly 1** opening frame, **ENTER → 1 frame** (runtime seal) or **2 frames** in golden dev fixture. **`commit_timeline_immutable_v1`** (no overwrite). **No** frame PATCH APIs.
- **`web_app.py`** — On successful **`decision_a_sealed`**, commit timeline (**read-through** deliberation from §11.2 store; **ENTER** single opening frame, **NO_TRADE** single frame). **`GET /api/v1/exam/units/<exam_unit_id>/decision-frames`** (**200** / **404** `exam_unit_not_found` / `timeline_not_committed`). **`GET /api/v1/exam/frames/<decision_frame_id>`** (**200** / **404**). **`PATTERN_GAME_WEB_UI_VERSION`** **2.19.35**; module docstring HTTP proof.
- **Golden fixture:** `docs/proof/exam_v1/golden_exam_unit_timeline_two_frames_enter_v1.json` (parent + **2** frames — downstream placeholder; tests round-trip + ENTER=2 rules).
- **Operator proof:** `docs/proof/exam_v1/operator_proof_exam_unit_decision_frames_get_v1.json`.
- **Tests:** `tests/test_exam_decision_frame_schema_v1.py` (golden, NO_TRADE/ENTER counts, ids, commit immutability, negatives, HTTP integration); §11.1/§11.2 tests reset timelines in setup.

**Proof**

- `python3 -m pytest tests/test_exam_decision_frame_schema_v1.py tests/test_exam_deliberation_capture_v1.py tests/test_exam_state_machine_v1.py` — **42 passed**.
- Student panel route smoke (Flask test client): `GET /api/student-panel/runs` → **200** (proves app still healthy after exam routes).

**HTTP (documented)**

| Route | 200 | 404 |
|-------|-----|-----|
| `GET /api/v1/exam/units/<exam_unit_id>/decision-frames` | committed timeline | unknown unit; timeline not committed |
| `GET /api/v1/exam/frames/<decision_frame_id>` | one frame | not found |

**Remaining gaps**

- Durable DB; pack-fed **opening_snapshot** OHLCV/indicators (stub zeros today); **§11.4** real downstream payloads; `decision_frame_id` global index for O(1) lookup.

**Requesting architect acceptance**

---

## Architect review

**Status:** pending architect review

Architect will append one of:

- `Accepted`
- `Rejected — rework required`
