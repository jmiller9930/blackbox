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

**Status:** implementation complete (2026-04-21)

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

Requesting architect acceptance

---

## Architect review

**Status:** pending architect review

Architect will append one of:

- `Accepted`
- `Rejected — rework required`
