# GT_DIRECTIVE_005 — Decision frame schema (§11.3)

**Date:** 2026-04-22  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §11.3, **§2**)  
**To:** Engineer  
**CC:** Product, Referee, UI, Operator  
**Scope:** `renaissance_v4/game_theory` only

**Predecessor:** `GT_DIRECTIVE_004_deliberation_capture_v1.md` (**§11.2 — CLOSED**).  
**Successor:** `GT_DIRECTIVE_006_downstream_frame_generator_v1.md` (**§11.4 — active**).

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

**Status:** **CLOSED** — **GT_DIRECTIVE_005 §11.3** accepted (2026-04-22). Do **not** reopen unless a **regression** is found. Next slice: **§11.4** → **`GT_DIRECTIVE_006_downstream_frame_generator_v1.md`**.

**Clarification — “app down” vs Student panel 200**

The **42-pass** proof used Flask **`create_app().test_client()`** (in-process WSGI). That **does not** bind `127.0.0.1:8765`; it exercises the same route handlers as production. **`curl http://127.0.0.1:8765/...`** returned **000** locally because **no** Flask process was listening on that port on the dev machine — **not** a contradiction with **200** from the test client. **Remote** pattern-game was restarted via **`gsync`** (HEAD **65bfd6b1**). **Future closeout:** when local `curl` is meaningless, attach a **remote HTTP proof** artifact (captured status + URL) in `docs/proof/…` so the operator chain is explicit (per Architect note).

**Summary**

- **`exam_decision_frame_schema_v1.py`** — Pydantic **exam_unit_timeline**: parent `exam_unit_id` / pack echo + ordered **`decision_frames`**; child **`DecisionFrameV1`** (`decision_frame_id` canonical `{exam_unit_id}__df{n}` URL-safe, `frame_index`, bar-close **`timestamp`**, `frame_type` `opening`|`downstream`, **`payload`** with `opening_snapshot`, read-through **`deliberation`** dict, **`decision_a`**, `downstream_reserved` placeholder only). Validators: dense 0-based indices, unique ids, parent linkage, **NO_TRADE → exactly 1** opening frame, **ENTER → 1 frame** (runtime seal) or **2 frames** in golden dev fixture. **`commit_timeline_immutable_v1`** (no overwrite). **No** frame PATCH APIs.
- **`web_app.py`** — On successful **`decision_a_sealed`**, commit timeline (**read-through** deliberation from §11.2 store; **ENTER** single opening frame, **NO_TRADE** single frame). **`GET /api/v1/exam/units/<exam_unit_id>/decision-frames`** (**200** / **404** `exam_unit_not_found` / `timeline_not_committed`). **`GET /api/v1/exam/frames/<decision_frame_id>`** (**200** / **404**). **`PATTERN_GAME_WEB_UI_VERSION`** **2.19.35**; module docstring HTTP proof.
- **Golden fixture:** `docs/proof/exam_v1/golden_exam_unit_timeline_two_frames_enter_v1.json` (parent + **2** frames — downstream placeholder; tests round-trip + ENTER=2 rules).
- **Operator proof:** `docs/proof/exam_v1/operator_proof_exam_unit_decision_frames_get_v1.json`.
- **Tests:** `tests/test_exam_decision_frame_schema_v1.py` (golden, NO_TRADE/ENTER counts, ids, commit immutability, negatives, HTTP integration); §11.1/§11.2 tests reset timelines in setup.

**Proof**

- `python3 -m pytest tests/test_exam_decision_frame_schema_v1.py tests/test_exam_deliberation_capture_v1.py tests/test_exam_state_machine_v1.py` — **42 passed**.
- Student panel route smoke (**Flask test client**, not bound TCP): `GET /api/student-panel/runs` → **200** (proves route handlers healthy after exam routes).

**HTTP (documented)**

| Route | 200 | 404 |
|-------|-----|-----|
| `GET /api/v1/exam/units/<exam_unit_id>/decision-frames` | committed timeline | unknown unit; timeline not committed |
| `GET /api/v1/exam/frames/<decision_frame_id>` | one frame | not found |

**Remaining gaps**

- Durable DB; pack-fed **opening_snapshot** OHLCV/indicators (stub zeros today); **§11.4** real downstream payloads; `decision_frame_id` global index for O(1) lookup.

**Architect acceptance received** — directive **§11.3** record complete.

---

## Architect review

**Status:** **Accepted — CLOSED** (2026-04-22)

**Architect Acceptance — §11.3**

Decision frame schema implementation satisfies the requirements of §11.3.

* exam_unit is implemented as the parent container  
* ordered decision_frame[] are implemented as child records  
* decision_frame_id values are stable and explicit  
* frame ordering and parent linkage are validated  
* frame 0 is anchored to opening snapshot stub, deliberation read-through, and Decision A stub  
* NO_TRADE units resolve to exactly one frame  
* ENTER units currently resolve to one opening frame, with downstream generation deferred to §11.4  
* immutable timeline commit behavior is enforced  
* fetch-by-unit and fetch-by-frame APIs are implemented  
* golden fixture, operator proof artifact, and automated tests are present  
* no scope creep into grading, UI splice, or downstream frame generation occurred  

**Directive GT_DIRECTIVE_005 §11.3 is accepted.**

**Directive status:** **CLOSED.** Do not reopen unless a regression is found.

**Next engineering slice:** **§11.4 — Downstream Frame Generator** → **`GT_DIRECTIVE_006_downstream_frame_generator_v1.md`**.

---

**HTTP proof note (closeout discipline):** Local `curl` to `127.0.0.1:8765` may be empty when no listener is bound; in-process **test_client** smoke plus **remote `gsync` restart** satisfied this closeout. Prefer a **captured remote HTTP proof** snippet in `docs/proof/…` for future directives when local TCP is not part of the proof chain.
