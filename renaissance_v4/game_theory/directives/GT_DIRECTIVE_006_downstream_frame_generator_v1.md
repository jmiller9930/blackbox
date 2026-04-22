# GT_DIRECTIVE_006 — Downstream frame generator (§11.4)

**Date:** 2026-04-22  
**From:** Architect (per `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` §11.4, **§7**)  
**To:** Engineer  
**CC:** Product, Referee, UI, Operator  
**Scope:** `renaissance_v4/game_theory` only

**Predecessor:** `GT_DIRECTIVE_005_decision_frame_schema_v1.md` (**§11.3 — CLOSED**).

## Canonical workflow record

This file is the canonical record for this directive.

Workflow:

1. Architect issues directive here.
2. Engineer reads and performs work.
3. Engineer appends response below.
4. Operator notifies Architect to review this folder.
5. Architect appends acceptance or rework below.

## Fault

Without a **deterministic downstream frame generator** per pack **§7** termination rules, ENTER timelines lack real **frames 1…n**, operators cannot prove **no lookahead** past Decision A seal, and §11.3 placeholders cannot become **moment truth** downstream cards.

## Directive

Implement **§11.4 — Downstream frame generator** (architecture **§7**):

1. Generate **ordered downstream `decision_frame`** records after frame 0 for **ENTER** units only, per pack termination mode (fixed `D`, until invalidation, volatility/regime cap).
2. **No lookahead** relative to seal time; **leakage** tests on API payloads.
3. Integrate with **§11.3** timeline contract without breaking **§11.1** / **§11.2** / **§11.3** fetch semantics unless additive and documented.

## Proof required

Per **Proof (non-negotiable) — 11.4** in `docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`:

- **Automated tests:** one test per **termination mode** in **§7** — expected **frame count** or **stop index** on golden strip.  
- **Golden replay:** small **known** OHLC strip where termination outcome is **deterministic**; tests assert slice boundaries **no lookahead** relative to seal time.  
- **Leakage test:** generator **MUST NOT** emit downstream fields into frame 0 payload before seal in API responses.  
- **Fixture:** committed **input strip + expected frames[]** for at least one mode.  
- **Operator evidence:** timeline dump or excerpt showing **n** frames matching expected **n**.  
- **HTTP proof:** frame list endpoint **200**; response matches test golden (hash or snapshot in CI). Prefer **remote HTTP proof artifact** in `docs/proof/…` when local `curl` is not meaningful.

## Deficiencies log update

Engineer must list remaining gaps under **Engineer update → remaining gaps**; do not claim **§11.4** architect acceptance until proof above is satisfied.

---

## Engineer update

**Status:** implementation complete (2026-04-21); **§11.4 CLOSED** — architect accepted (2026-04-22).

**Summary:** Implemented §11.4 downstream frame generation after `decision_a_sealed` for **ENTER** only: frames **1..n** append after frame **0**, bar-close timestamps, one termination mode per unit (`fixed_bars` default **D=5**, `until_invalidation`, `volatility_regime_cap`), strict no-lookahead (each bar parsed only when emitted). **NO_TRADE** still commits a single opening frame. Added dev `POST /api/v1/exam/units/<id>/ohlc-strip` for strip + optional termination; default synthetic strip when unset.

**Files changed:**

- `renaissance_v4/game_theory/exam_downstream_frame_generator_v1.py` — generator, dev stores, synthetic strip
- `renaissance_v4/game_theory/exam_decision_frame_schema_v1.py` — `price_snapshot` / `downstream_context` on payload, ENTER validation (1 + n downstream), `build_complete_enter_timeline_v1`, recursion fix on NO_TRADE builder, timeline reset clears downstream stores
- `renaissance_v4/game_theory/web_app.py` — seal hook uses `build_complete_enter_timeline_v1`, new POST route, UI version bump
- `renaissance_v4/game_theory/docs/proof/exam_v1/fixture_exam_downstream_ohlc_strip_v1.json` — deterministic OHLC strip + documented expectations
- `renaissance_v4/game_theory/docs/proof/exam_v1/golden_exam_unit_timeline_two_frames_enter_v1.json` — downstream row uses real `price_snapshot`
- `docs/proof/exam_v1/operator_proof_downstream_gt006_v1.json` — operator-facing proof excerpt
- `tests/test_exam_downstream_frame_generator_v1.py` — termination modes, NO_TRADE, ordering, no-lookahead, HTTP
- `tests/test_exam_decision_frame_schema_v1.py` — ENTER rule updates

**Proof produced:** Automated tests above; fixture + golden; operator JSON under `docs/proof/exam_v1/`; `GET …/decision-frames` returns ordered frames including downstream after ENTER seal.

**Remaining gaps:** Pack registry still absent (dev POST / defaults only); no remote `curl` artifact checked in from production host.

Requesting architect acceptance — **superseded:** architect acceptance recorded below (2026-04-22).

---

## Architect review

**Status:** **CLOSED** — §11.4 accepted (2026-04-22)

**Context:** Review of the §11.4 implementation summary, proof artifacts, test coverage, and deploy status.

**Decision:** GT_DIRECTIVE_006 §11.4 is **ACCEPTED**.

**Verified:** Downstream frame generator is implemented within intended scope. After `decision_a_sealed`: **ENTER** → frame 0 plus downstream 1..n; **NO_TRADE** → single opening frame, no downstream. Termination via policy model: `fixed_bars` (default D=5), `until_invalidation`, `volatility_regime_cap` (threshold or `max_bars`). Frame model: `frame_type="downstream"`, bar-close timestamps, minimal payload (`price_snapshot` + downstream context), frame 0 unchanged. No-lookahead: sequential bar access, no full-strip pre-parse. Integration: extended §11.3 structure, additive seal wiring, synthetic strip fallback for dev. Proof: dedicated tests, updated decision-frame tests, fixture + operator proof, HTTP coverage, commit/push/gsync; acceptance baseline `main` included **5106bfaf** (downstream slice); follow-on courtesy commits may advance `main` without reopening §11.4.

**Architect note:** Lack of direct remote `curl` from review environment is not a blocker — automated HTTP tests and successful remote restart suffice. For future slices, continue saving one operator-visible remote HTTP proof artifact when direct live `curl` is not available from the current environment.

### Architect Acceptance — §11.4

Downstream frame generator implementation satisfies the requirements of §11.4.

* ENTER units generate downstream frames after Decision A seal
* NO_TRADE units correctly remain single-frame timelines
* downstream frames are ordered and appended after frame 0
* frame timestamps are anchored to bar close
* termination modes are implemented for fixed bars, until invalidation, and volatility/regime cap
* no-lookahead behavior is enforced through sequential bar access
* downstream payloads remain within scope and do not introduce grading or execution semantics
* fixture, operator proof artifact, and automated tests are present
* HTTP behavior for downstream frame retrieval is covered
* implementation was committed, pushed, and deployed without reopening prior directives

**Directive GT_DIRECTIVE_006 §11.4 is accepted.**

**GT_DIRECTIVE_006 §11.4 is now CLOSED.**

**One-line summary:** The exam timeline now extends beyond the initial decision and can represent what happens afterward without leaking the future.

---

## Next step (engineering)

**§11.5 — Grading Service:** see **`GT_DIRECTIVE_007_grading_service_v1.md`** (issued 2026-04-22).
