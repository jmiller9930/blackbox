# Architecture — backward ladder: Student at the table (non-negotiable end state → today)

**Audience:** Architect, engineering, operators.  
**Companion:** `ARCHITECTURE_PLAN_STUDENT_PROCTOR_PML.md`, `E2E_ROADMAP_STUDENT_PROCTOR_PML.md`, `STUDENT_FIRST_PERSON_TRADEPATH.md`, `TRADING_CONTEXT_REFERENCE_V1.md` (indicator lexicon + codebase map).  
**Purpose:** One **backward** chain from **declared goal** to **current codebase**, with **directives** and **context taxonomy** (including **examples**). Revise **in place**; append **revision history** at the bottom.

---

## 0) Project goals & binding definitions — **this is the deliverable**

This section answers: **What are we building?** **What counts as a trade?** **What counts as learned behavior?** **Titles and plumbing are not enough** — acceptance uses the definitions below.

### 0.1 Goals (understood)

1. Train an agent (**Student**) to **place trades** meaning: emit **valid trade intent** from **only** the **data we provide** before reveal — causal **tape** at minimum, plus any **contract-allowed** indicators, structured context, and **memory** slices.
2. **Proctor / Referee** holds **grading** (fills, PnL, quality) **after** the Student commits; **reveal** joins intent ↔ truth; **learning records** feed **future** decisions.
3. Prove **learned behavior** (see **0.3**) with **pre-registered** metrics and **baselines** — not vibes.

### 0.2 What a **trade** is (binding)

A **trade** is a **contract-valid** **`student_output_v1`** (and, when specified, **`trade_intent_v*`**) produced **before reveal** from **legal pre-reveal context only**: at minimum **causal market context** (tape through decision time); **not** a guess, **not** smuggled Referee truth. **“Place a trade”** = this **intent line** — **not** authoring Referee execution. See also **§A.2** “no market context, no trade.”

### 0.3 What **learned behavior** is (binding)

**Learned behavior** is demonstrated when **all** of the following hold:

1. **Data boundary:** The Student’s decision uses **only** the **data we provided** for that episode (tape + allowed features + memory per schema — **no** current-trade answer key pre-reveal).
2. **Pattern stance:** The Student **pattern-matches** or **does not pattern-match** under an **operational** rule fixed in contract/tests — including **approximate** / **similarity** match (**not** requiring identical bars or exact historical repetition; **rhyme**, not photocopy — **§C.2**).
3. **Positive result vs baseline:** When match (or policy conditioned on match / non-match as specified) yields a **pre-registered** **positive** outcome **relative to** **no-match**, **memory-off**, or another **declared baseline** — that is what we **call learned behavior** for this initiative.

**Sliding metrics** (when to enter, how much edge distribution, exit quality) fit here as long as they are **defined** and **measured** — not reduced to a single binary win if the product says otherwise.

### 0.4 Closure: do we understand what ships?

| Question | Answer |
|----------|--------|
| **Project goal** | Student **trades** (intent) from **provided** context; **learning** that can **change** behavior; Referee **stable**; **evidence** per **0.3**. |
| **Primary deliverable** | **Valid trade** (**0.2**) + path to prove **learned behavior** (**0.3**) on your metrics. |
| **What “trade” means** | **Intent** pre-reveal per **0.2** — **this section** is the **authoritative** product definition. |

---

## A) Non-negotiables (this development round)

**Primary deliverable (P0):** Satisfy **§0.2** and **§0.3** on agreed metrics — **correct trade** from **provided** data; **learned behavior** where match / approximate match + **positive vs baseline** is shown. Richer context, UX, and 24/7 operation are **successive**; they **must not** replace **§0** as the definition of done.

1. **Student at the table.** The training agent (**Student**) must be able to **sit at the table and place trades** in the product sense: **trade-shaped intent** (enter / abstain, direction, risk posture, and—when the contract allows—size/horizon) produced from **legal pre-reveal** context. This is not optional for “done.”
2. **No market context, no trade (non-negotiable).** Without **causal market context**—at minimum the tape up to decision time (*t*), and in full product form the structured **price / structure / indicator / time** interpretation the architecture admits—a submission is **not** a trade worth training on; it is a **guess**. **We do not guess.** Memory and pattern layers **sit on top of** market context, not instead of it.
3. **Context + memory must be able to affect outcomes** when those resources exist: if the system provides **causal market context**, **indicator / pattern context** allowed by contract, and **retrieved memory**, then **policies and metrics** must admit demonstrable **cross-run** and **within-run** influence on **Student decisions** (and, where defined, **paper** or **alignment** outcomes)—not a decorative column.
4. **Referee stays substrate.** Ground truth (replay, `OutcomeRecord`, grading) is **stable plumbing**; **default change surface** is **Student learning**, not rewriting the Referee pipeline (`STUDENT_FIRST_PERSON_TRADEPATH.md` §1).

---

## B) Alignment: what “context” is (with concrete examples)

**Shared definition.** In this system, **context** means everything the Student is **allowed** to condition on **before reveal** for the current graded unit: causal **market state**, optional **indicator / feature** fields (when present in contract), **pattern/cookbook** hooks, and **cross-run memory** slices merged into the legal pre-reveal bundle. Context is **not** Referee truth for *this* trade before decision time (no `pnl`, `mfe`, `exit_reason`, etc. in the pre-reveal packet — see `PRE_REVEAL_FORBIDDEN_KEYS_V1` in `contracts_v1.py`).

**What we are aligning on**

| Term | Meaning here |
|------|----------------|
| **Causal market context** | OHLCV (and later: only indicators derived from bars with `open_time <= decision_open_time_ms`). |
| **Indicator context** | Numbers or labels summarizing regime **as of *t*** (volatility bucket, momentum, distance to VWAP, …)—same causal rule. |
| **Pattern / cookbook context** | Named recipes the Student cites (`pattern_recipe_ids`) or narrative `reasoning_text` — still pre-reveal-safe. |
| **Memory context** | **Prior runs’** Student-facing slices (`retrieved_student_experience_v1`), matched by a **signature key** — not the Referee “cheat sheet” for the trade we are about to grade. |

---

### B.1 Example — causal packet (shape as implemented today)

`build_student_decision_packet_v1` / `build_student_decision_packet_v1_with_cross_run_retrieval` produce a **`student_decision_packet_v1`** whose core **market context** is **`bars_inclusive_up_to_t`**: each row is one 5m bar, causal up to entry/decision time.

```json
{
  "schema": "student_decision_packet_v1",
  "contract_version": 1,
  "symbol": "SOLUSDT",
  "table": "market_bars_5m",
  "decision_open_time_ms": 1700001000000,
  "graded_unit_type_hint": "closed_trade",
  "bar_count": 48,
  "bars_inclusive_up_to_t": [
    {
      "open_time": 1700000000000,
      "symbol": "SOLUSDT",
      "open": "101.10",
      "high": "101.55",
      "low": "100.90",
      "close": "101.20",
      "volume": "12345.67"
    }
  ]
}
```

(Real packets many bars; one row shown for clarity.) **This is the canonical “market tape up to *t*” context.**

---

### B.2 Example — retrieval key (matches operator runtime v1)

The seam builds a **signature** so similar **entry moments** retrieve prior experience. **Current code** uses:

`student_entry_v1:{symbol}:{entry_time}`

Concrete: `student_entry_v1:SOLUSDT:1700001000000`

That string is both **`retrieval_signature_key`** for lookup and embedded as:

```json
"context_signature_v1": {
  "schema": "context_signature_v1",
  "signature_key": "student_entry_v1:SOLUSDT:1700001000000"
}
```

on the **learning record** (`student_proctor_operator_runtime_v1._signature_key_for_trade`). **Align:** “same context” for retrieval v1 means **same symbol + same entry bar time** unless you change the keying strategy.

---

### B.3 Example — one retrieval slice (memory context, pre-reveal-safe)

Each element under **`retrieved_student_experience_v1`** is a **`student_retrieval_slice_v1`**: **prior** Student output and ids — **no** leaked PnL keys on the slice (projection strips forbidden fields). Illustrative:

```json
{
  "schema": "student_retrieval_slice_v1",
  "contract_version": 1,
  "source_record_id": "660e8400-e29b-41d4-a716-446655440001",
  "source_run_id": "run_prior_abc",
  "prior_graded_unit_id": "trade_xyz",
  "signature_key": "student_entry_v1:SOLUSDT:1700001000000",
  "prior_student_output": {
    "schema": "student_output_v1",
    "graded_unit_id": "trade_xyz",
    "act": true,
    "direction": "long",
    "pattern_recipe_ids": ["range_fade"],
    "confidence_01": 0.55,
    "student_decision_ref": "550e8400-e29b-41d4-a716-446655440000"
  },
  "prior_symbol_hint": "SOLUSDT"
}
```

**Memory context** = this list (possibly empty) attached to the packet **before** the Student policy runs.

---

### B.4 Example — indicator context (concrete names; schema path is future unless frozen)

**Indicators** are **not** a second tape; they are **derived** from causal bars (and optionally other **pre-reveal** tables your architect allows). Examples of what we **mean** by indicator context (numbers illustrative):

| Indicator (example) | Plain language | Causal rule |
|--------------------|----------------|-------------|
| `return_5b` | Close-to-close return over last 5 bars | Uses only bars with `open_time <= t` |
| `atr_14_relative` | e.g. ATR(14)/close | Same |
| `dist_vwap_session_pct` | Distance from session VWAP as % | VWAP from causal session bars only |
| `vol_regime` | Label: `low` / `mid` / `high` | Bucket from realized vol on past window |
| `session_segment` | e.g. `open_first_hour` | Clock + exchange calendar, no outcomes |

**Today:** these may **not** yet live as first-class columns on `student_decision_packet_v1`; the **architecture** still treats them as **indicator context** once added under a versioned schema. **Stub** Student may ignore them; a trained policy must **use** them when present.

---

### B.5 Example — pattern / cookbook context (output side, still “context” for the narrative)

Emitted on **`student_output_v1`** (from `legal_example_student_output_v1()`):

```json
"pattern_recipe_ids": ["trend_continuation"],
"reasoning_text": "Hypothesis: continuation in line with cookbook.",
"confidence_01": 0.65
```

This is **declared** pattern context plus optional text — **not** Referee data.

---

### B.6 What is **not** context (before reveal)

- Any key in **`PRE_REVEAL_FORBIDDEN_KEYS_V1`**: e.g. `pnl`, `mfe`, `mae`, `exit_reason`, `binary_scorecard`, `referee_truth`, `reveal_v1`, `outcome_record`.
- **Future bars**: any bar with `open_time > decision_open_time_ms`.
- **Referee outcome** for the **current** graded unit inside the decision packet.

If it appears in the pre-reveal bundle, **`validate_pre_reveal_bundle_v1`** must reject it (unless the contract is explicitly revised).

---

### B.7 One-sentence alignment check

**Context = causal market bars + (optional) derived indicators + optional memory slices + pattern hooks — everything legally visible before reveal — and never the unrevealed grade for this trade.**

Add your favorite indicator names to **B.4** (and the contract) when you freeze them; the **categories** above stay stable.

---

## C) Backward ladder (goal → prerequisites → today)

Read **from top (goal) downward** to “today”; implementation reads the **same** list **upward**.

| Rung | Name | What must be true |
|------|------|-------------------|
| **5 — Goal** | **Student places trades (intent line)** | Operator-visible path: for each graded unit, **Student** emits validated **`student_output_v1`** (and, when specified, richer **`trade_intent_v1`**) as the **candidate trade** from **legal** inputs only. |
| **4 — Learning changes behavior** | **Memory affects decisions** | **`retrieved_student_experience_v1`** is merged into the pre-reveal packet **before** choice; **learning records** persist **reveal** results; **next run** retrieval can **change** `act`, `direction`, `confidence_01`, or `pattern_recipe_ids` vs a no-memory baseline (ablation provable). |
| **3 — Grading without leakage** | **Reveal is the only merge** | **`reveal_v1`** joins **Student snapshot** + **Referee truth** **after** decision; **pre-reveal** packets pass **`validate_pre_reveal_bundle_v1`** (no forbidden outcome keys). |
| **2 — Causal packet** | **Decision-time state** | **`student_decision_packet_v1`**: at minimum **`bars_inclusive_up_to_t`** from SQLite (`student_context_builder_v1`); optional **notes**; plus **Directive 06** path with retrieval. |
| **1 — Immutable truth line** | **Referee / replay** | **`OutcomeRecord`**, replay outcomes, WIN/LOSS / PnL from engine—**not** Student-authored; **not** the iteration focus. |
| **0 — Today (floor)** | **What exists now** | Contracts frozen (`contracts_v1`), packet builder, cross-run retrieval, **post-batch** Student seam (`student_proctor_operator_runtime_v1`), **stub** `student_output_v1` (`shadow_student_v1`), append-only learning store. **Gaps:** decision **before** batch outcome in **job order** (if strict blind exam), richer **trade** fields, **explicit** indicator arrays in packet, **paper/hypo** economics line, UI **default** hero for Student. |

---

## C.1) Context wiring status (what is actually connected today)

**Answer in one line:** **Partially.** Causal **market** context and **memory** context are wired into the **Student** pre-reveal path; **structured** price / structure / indicator / time buckets from `TRADING_CONTEXT_REFERENCE_V1.md` have a **versioned optional annex** (`student_context_annex_v1` on the packet, validated by `validate_student_context_annex_v1`) but are **not** yet **filled by default** builders from OHLCV.

| Layer | Wired for Student pre-reveal? | Where |
|-------|-------------------------------|--------|
| **Causal OHLCV (tape up to *t*)** | **Yes** | `student_context_builder_v1.build_student_decision_packet_v1` → `bars_inclusive_up_to_t` |
| **Cross-run memory** | **Yes** | `cross_run_retrieval_v1.build_student_decision_packet_v1_with_cross_run_retrieval` → `retrieved_student_experience_v1` (match on `student_entry_v1:{symbol}:{entry_time}`) |
| **Leakage guard** | **Yes** | `validate_pre_reveal_bundle_v1` on built packets |
| **Rich `price_context` / `structure_context` / `indicator_context` / `time_context` JSON** | **Annex contract only** (optional) | Valid **shape** via `student_context_annex_v1`; **default** packet builder still **does not** populate buckets — future **projection** (`feature_engine` / `indicator_engine` / session clock) attaches a legal annex when implemented |
| **Replay-only features** (`FeatureSet`, fusion signals, engine `pattern_context_v1`) | **Parallel path** | `replay_runner`, `signals/*` — **not** automatically the same object the stub Student consumes; **merge is intentional future work** |
| **Pattern tags on output** | **Stub** | `shadow_student_v1` emits `pattern_recipe_ids` etc. from packet **without** full fusion feed |

**Conclusion:** The **non-negotiable** “no market context, no trade” is **satisfied at minimum** by **bars**; the **full** product picture in the reference doc requires **additional wiring** before policies can depend on pre-computed indicator labels without re-deriving from bars. Operator batch results include **`wiring_honesty_annotation_v1`** (**D7**) so “full context” claims stay aligned with what is actually attached.

---

## C.2) Approximation vs exact match (memory semantics — architecture principle vs code today)

**Principle (non-negotiable for honest training design):** The market **never** replays an **identical** pattern as the norm. **Patterns can rhyme**; what retrieval represents is **approximation** — **similar** context in **regime / structure / volatility** space — not “this chart happened before.” Memory should eventually behave like **nearest-neighbors** or **tolerance-matched** episodes, **not** “only if the tape keys line up bit-for-bit.”

| Layer | What it does today | Fit with “approximation” |
|-------|-------------------|----------------------------|
| **Student learning retrieval** (`student_proctor_operator_runtime_v1`, `cross_run_retrieval_v1`) | Lookup by **exact** key **`student_entry_v1:{symbol}:{entry_time}`** | **Exact** match on symbol + entry bar time. That often retrieves **only** when the **same** moment is replayed (or keyed the same), **not** when a **different** moment is merely **similar** in market structure. So: **implementation is narrower than the philosophy** above. |
| **Engine context signature memory** (`context_signature_memory.py`) | Hashes **`pattern_context_v1`**, uses **`SignatureMatchParamsV1`** (tolerances on structure/vol **shares**) | **Closer** to **approximate** matching — **family** resemblance, not identity. |

**Gap:** Product and pedagogy should say **“similar prior contexts”**; the **Student** store **v1** keying does **not** yet fully deliver that story **unless** runs reuse the same `(symbol, entry_time)` or the key is expanded (e.g. **bucketed** timestamps, **`context_signature_v1`-style** keys with tolerances, or architect-approved **fuzzy** match).

**Roadmap (not optional forever if memory is central):** Version **`student_retrieval_v2`** (or extend matching API): **match** learning rows by **bounded distance** on signed features / regime labels / retrieval ranking — reusing patterns from **`context_signature_memory`** where appropriate and **keeping** pre-reveal safety.

**D8** below locks **honesty** so docs/UI do not promise “the pattern came back” when the code only does **exact** key match. Operator batch audit includes **`memory_semantics_annotation_v1`** (**D8** proof).

---

## C.3) Phased honesty — process order vs causal packet (**D6**)

**Two different questions:**

| Question | **As-built operator seam** | **Causal pre-reveal packet** |
|----------|---------------------------|--------------------------------|
| Does the **job** run the Student shadow **before** any ``OutcomeRecord`` exists in the batch result row? | **No.** Pattern-game flow calls ``run_scenarios_parallel`` first; ``student_loop_seam_after_parallel_batch_v1`` runs **after** ``replay_outcomes_json`` is available. | N/A |
| Does the **decision packet** smuggle the current trade’s PnL / exit? | N/A | **No** — ``bars_inclusive_up_to_t`` + optional retrieval only; **D2** forbids outcome keys pre-reveal. |

**Marketing / training claims:** Do **not** describe this pipeline as **strict “exam blind”** in the **process** sense (Student code path runs after outcomes are in the batch structure) until job order changes. You **may** honestly say the **packet** is **causal at entry** and **reveal** grades afterward. The ``student_loop_seam_audit_v1`` payload includes **`phased_honesty_annotation_v1`** (Directive **06** tests) so API/ops can surface the distinction.

---

## D) Directives (normative; map to implementation)

**D1 — Student-first product.** UX and APIs **default** to the **Student** lane; Referee output is **context for grading**, not the main training story (`STUDENT_FIRST_PERSON_TRADEPATH.md`).  
*Closeout:* **§F** (git, sync, services).

**D2 — Pre-reveal legality.** Any object consumed **before** reveal MUST pass **`validate_pre_reveal_bundle_v1`**; no forbidden keys (`contracts_v1`).  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d2_pre_reveal_legality_v1.py`.  
*Closeout:* **§F**.

**D3 — Context plurality (minimum vs target).** A Student decision MUST draw from **at least** causal **`bars_inclusive_up_to_t`** (implemented). SHOULD incorporate **`retrieved_student_experience_v1`** when the learning store has matches (implemented). SHOULD evolve toward structured **`price_context` / `structure_context` / `indicator_context` / `time_context`** per `TRADING_CONTEXT_REFERENCE_V1.md` **only** when emitted on a **versioned** annex (**`student_context_annex_v1`** on the decision packet; **`validate_student_context_annex_v1`** + **`validate_pre_reveal_bundle_v1`**). MAY use **pattern/cookbook** tags via **`pattern_recipe_ids`** / `reasoning_text` on **`student_output_v1`** (stub today).  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d3_context_plurality_v1.py`.  
*Closeout:* **§F**.

**D4 — Memory must matter.** When retrieval is enabled and matches exist, **telemetry or tests** MUST show **deltas** vs no-retrieval (policy output or downstream metric)—otherwise “memory” is unproven.  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d4_memory_must_matter_v1.py` (shadow **confidence** / **pattern_recipe_ids** / **refs** / **reasoning** vs bars-only; zero-match control; operator **primary_trade** retrieval count).  
*Closeout:* **§F**.

**D5 — Referee immutability.** Students MUST NOT authorize ledger writes or change Referee numbers; **`reveal_v1`** compares and persists **Student** learning artifacts only within **`student_learning_record_v1`** rules (`ARCHITECTURE_PLAN` §2.1).  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d5_referee_immutability_v1.py` (``referee_truth_v1`` = outcome projection; Student fields do not override Referee; learning **subset** traces **reveal**; smuggled ``referee_truth`` on student output rejected).  
*Closeout:* **§F**.

**D6 — Phased honesty.** Until process order places the Student **strictly before** `OutcomeRecord` is available, document **seam ordering** as a known limitation; **do not** claim “exam blind” without that gate.  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d6_phased_honesty_v1.py`; operator audit **`phased_honesty_annotation_v1`**; see **§C.3**.  
*Closeout:* **§F**.

**D7 — Wiring honesty.** Marketing, UI copy, and **directive closeout** MUST NOT claim “full trading context” (indicators, regime panels, etc.) on the **Student** path until those fields are **actually attached** to the legal pre-reveal bundle and tested. The **diagram** in `ARCHITECTURE_PLAN_STUDENT_PROCTOR_PML.md` §3 is **aspirational** for indicator/pattern pipes; **as-built** Student context is **`bars` + optional retrieval** until extended (see **§C.1** above).  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d7_wiring_honesty_v1.py`; operator audit **`wiring_honesty_annotation_v1`** (`full_structured_trading_context_baseline_claim_supported_v1` stays **false** until product opts in).  
*Closeout:* **§F**.

**D8 — Memory semantics honesty.** Do **not** describe Student memory as **“the same pattern again”** unless matching logic proves **similarity** under a defined metric. **As-built** Student retrieval v1 is **exact key** (`student_entry_v1:{symbol}:{entry_time}`) — see **§C.2**. Broader **approximation** retrieval is **design intent** and **partially** reflected in **engine** `context_signature_memory`; **align** Student store matching when the architect approves **v2** semantics.  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d8_memory_semantics_honesty_v1.py`; operator audit **`memory_semantics_annotation_v1`**.  
*Closeout:* **§F**.

**D9 — Deliverable vocabulary.** “**Trade**” and “**learned behavior**” in release notes, UI, and **directive closeout** MUST match **§0.2** and **§0.3**. Do not ship narrative that redefines **trade** as Referee fills or **learn** as metrics without a **baseline**.  
*Proof tests:* `renaissance_v4/game_theory/tests/test_directive_d9_deliverable_vocabulary_v1.py`; operator audit **`deliverable_vocabulary_annotation_v1`**.  
*Closeout:* **§F**.

**Rule:** A directive is **not** accepted as **done** until **§F** has been executed for that slice of work (agent / operator checklist).

---

## E) Alignment checklist (this round)

- [ ] **§0 binding definitions** agreed and **metrics for 0.3** (match / no-match / baselines) **pre-registered** — **D9**.
- [ ] **Table metaphor enforced in UI:** Student lane visible as **primary**.
- [ ] **Trade intent** path clear: **`student_output_v1`** complete per contract; roadmap for **`trade_intent_v1`** if needed.
- [ ] **Memory:** retrieval wired (**done in code**); **ablation** story (on/off) **proven in tests/telemetry**.
- [ ] **Rich context:** versioned projection attaches **`price_context` / `structure_context` / `indicator_context` / `time_context`** (per `TRADING_CONTEXT_REFERENCE_V1.md`) **or** explicit **not-yet** in release notes — **D7**.
- [ ] **No false claims:** docs/UI match **§C.1** wiring (bars + retrieval vs full buckets).
- [ ] **Memory wording:** copy matches **§C.2** + **D8** (approximation vs exact key).
- [ ] **E2E proof** per `E2E_ROADMAP_STUDENT_PROCTOR_PML.md` for binding bars.
- [ ] **§F closeout** completed for this milestone (git commit, pull, push if required, Flask/Docker restart).

---

### E.1) Talking points (return to — not committed scope)

Short list for **architecture / product** discussion. Items here are **not** “done” until promoted into **§C.1**, a **directive**, or an implementation plan.

| # | Topic | Notes |
|---|--------|--------|
| 1 | **Bar timeframe options (15m / 30m vs 5m)** | The codebase is **5m-shaped** today (`market_bars_5m`, replay, Student packet builder, ingest, pattern-game allowlists). Supporting **15m** and **30m** is a **bounded extension**—new tables or a unified bar table + **explicit** timeframe, **one** canonical series per run, and **aligned** `entry_time` / retrieval keys so replay, Student, and memory do not disagree. Does **not** invalidate pre-reveal or Referee contracts **if** causal rules and keying stay disciplined. |
| 2 | *Reserved* | Add the next deferred topic here when ready. |

---

## F) Directive closeout — git, remote sync, Flask & Docker (mandatory for implementers / agents)

Run **after** code and tests for the directive milestone; **before** calling the directive **closed**.

1. **Commit locally** — Stage and commit **all** intended changes in this repo (clear message; no stray secrets):
   - `git status`
   - `git add` (scoped or as appropriate)
   - `git commit -m "…"`  
2. **Integrate remote** — Bring in upstream changes so local branch is not stale:
   - `git fetch` (optional but recommended)
   - `git pull` on your working branch (use team **rebase** or **merge** policy; resolve conflicts before continuing).  
3. **Publish** (if this work should exist on **remote**) — `git push` to the appropriate remote/branch. Skip only if you are on a **local-only** experiment and policy allows.  
4. **Restart the pattern-game / Flask web service** so running code matches the tree you committed. Typical dev entry (adjust host/port to your setup):
   - `python3 -m renaissance_v4.game_theory.web_app --host 127.0.0.1 --port 8765`  
   Stop the **previous** process first (Ctrl+C, or `pkill`/systemd/`launchctl` as your environment uses), then start again; or restart the **supervisor** / **process manager** that wraps Flask.  
5. **Docker** — If your deployment uses containers (e.g. **`UIUX.Web/docker-compose.yml`** or project-specific compose under `vscode-test/`), rebuild/restart as required after code changes, e.g.:
   - `docker compose up -d --build` (from the compose file’s directory)  
   Use **only** the compose file(s) your team uses; **not** every environment uses Docker for the pattern game.

**Agents / automation:** Do not assert “directive complete” until **§F** steps applicable to the environment have been run or explicitly waived by operator policy (e.g. CI-only machine with no local Flask).

---

## G) Revision history

| Version | Date | Notes |
|---------|------|--------|
| 1.0 | 2026-04-20 | Initial backward ladder, directives, context examples, alignment to contracts/code. |
| 1.1 | 2026-04-20 | §B expanded: definition table, JSON-shaped examples (packet, signature_key, retrieval slice), indicator examples, not-context boundaries, alignment one-liner. |
| 1.2 | 2026-04-20 | §A: non-negotiable “no market context, no trade / we do not guess”; memory/pattern on top of market context. |
| 1.3 | 2026-04-20 | §C.1 context wiring status (bars+memory yes; rich JSON buckets not yet). Directives D3/D7 updated; checklist E aligned. |
| 1.4 | 2026-04-20 | §A **P0** primary deliverable: Student places a trade correctly (intent line, contract-valid, causal context). |
| 1.5 | 2026-04-20 | §C.2 approximation vs exact Student retrieval; directive **D8**; checklist memory wording. |
| 1.6 | 2026-04-20 | **§0** project goals + binding definitions of **trade** (0.2) and **learned behavior** (0.3); P0 aligned; **D9**; checklist §0 metrics. |
| 1.7 | 2026-04-20 | **§F** directive closeout (git commit, pull, push, Flask restart, Docker); *Closeout: §F* on D1–D9; checklist item. |
| 1.8 | 2026-04-20 | **D3** closure: **`student_context_annex_v1`**, proof tests module. |
| 1.9 | 2026-04-20 | **D4** closure: memory delta proof tests (`test_directive_d4_memory_must_matter_v1`). |
| 1.10 | 2026-04-20 | **D5** closure: Referee immutability proof tests (`test_directive_d5_referee_immutability_v1`). |
| 1.11 | 2026-04-20 | **§E.1** talking points (deferred): multi-timeframe bars + placeholder row. |
| 1.12 | 2026-04-20 | **D6** closure: **§C.3** phased honesty; ``phased_honesty_annotation_v1`` on seam audit; proof tests. |
| 1.13 | 2026-04-20 | **D7** closure: ``wiring_honesty_annotation_v1`` on seam audit; proof tests. |
| 1.14 | 2026-04-20 | **D8** closure: ``memory_semantics_annotation_v1`` on seam audit; proof tests. |
| 1.15 | 2026-04-20 | **D9** closure: ``deliverable_vocabulary_annotation_v1`` on seam audit; proof tests. |
