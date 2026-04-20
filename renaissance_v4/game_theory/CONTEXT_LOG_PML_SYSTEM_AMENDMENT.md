# CONTEXT LOG — “Student & Proctor” Canon (BLACKBOX / PML System Amendment)

**Short name (for conversations):** **“Student–Proctor Canon”** or **“PML Training Loop Amendment.”**  
**Purpose:** Single place to restore intent when designing or reviewing code. **Not** a substitute for Referee math — **normative product + training-loop story** aligned with minimal future code changes.

**Status:** Living amendment — **gaps** at the end are intentional placeholders to revisit before implementation.

---

## 1. Why this log exists

Operators have been circling **memory** and **context** because two different stories were mixed:

- **Story A (shipped in parts of the stack):** Referee runs deterministic replay; **Anna** (pattern-game path) often receives **post-hoc** report text + docs + a **short OHLCV snapshot** — **advisory narration**, scores unchanged.
- **Story B (non-negotiable intent — this document):** **Student** at time *t* decides **under uncertainty**; **Referee** holds **immutable truth**; **reveal** then **learning records** then **cross-run behavior change**.

This file **locks Story B** as the **canonical training-loop amendment**. Implementation may lag; **intent** does not.

---

## 2. Core model — two roles, one timeline, split epistemics

| Role | Name in product | What it is |
|------|------------------|------------|
| **Student** | Anna / Agent | Sits at the **trade window**; decides **without** full truth at decision time. |
| **Proctor** | Referee / Deterministic Engine | Holds **immutable standard**: execution, PnL, WIN/LOSS, graded scales — **gold standard** for “what happened.” |

They **share the same historic timeline** (replay), but **do not share information at decision time** in the **intended** loop:

- The **Student** does **not** see future bars, unrevealed outcomes, full-run aggregates, or the Referee’s **flashcards** while choosing.
- The **Referee** processes the **full** forward simulation and **always** has **forward truth** for grading — but **does not inform** the Student **during** her decision in the **intended** design.

**Important bridge (honesty):** Today’s codebase implements **one** deterministic replay engine; the **Student** is not yet fully in the **per-timestep** causal loop in the pattern-game **Anna** path. This document defines **what “done” looks like**, not a claim that every line ships today.

---

## 3. The Student (Anna) — view, arsenal, job

**Where she sits:** At a **single time *t*** on replay, in the **trade window** — **as the operator would see it**: **5m period candles**, **market as it was up to *t*** (causal), **not** the whole future strip as if known then.

**What she receives (intended minimum bundle at *t*):**

- **Market data up to *t*** (and indicator computations that only require history ≤ *t*).
- **Derived indicators** (catalog/cookbook — deployable modules and their readings in **context**, not raw numbers alone).
- **Contextual interpretation:** regime, structure, fusion state (conflict / alignment), volatility flavor — **bullish / bearish / chop / transition** style questions answered in **structured** form where possible.
- **Retrieved memory** from **prior revealed** experiences (pattern signatures, learning records — **matchable** keys).

**What she must not receive before decision (non-negotiable in intent):**

- Future market data (&gt; *t*).
- Trade outcomes **not yet revealed** for this round / decision.
- Full-run statistics (aggregates that leak the “ending of the movie” into the choice).
- **Referee decisions / flashcards** (entries, exits, WIN/LOSS, PnL) **for the current graded unit** until **reveal**.

**Her job:** **Pattern recognition under uncertainty** — apply **memory + context** to the **indicators at play**, ask **“have I seen this before?”**, and produce a **forward-only** decision:

- Act or not; direction if applicable; **which pattern/recipe** she is applying; optional confidence / parameters — **all** in whatever **machine-checkable** schema the system defines.

**Higher goal than binary win:** **Maximize quality** on a **graded scale** (see §6), not only flip GREEN/RED.

---

## 4. The Referee (Engine) — immutable standard

The Referee is the **gold / immutable standard**:

- **Executes** the policy path (manifest, signals, fusion, execution, costs).
- **Determines** entries and exits **on the tape** under rules.
- **Computes** PnL and **WIN/LOSS** (and any **graduated** quality metrics you define from **replay truth**).

**Flashcards metaphor:** The Referee holds the **answer key** for the **session** and each **reveal unit** — what actually happened — **not** something the Student may read **during** the exam in the intended product.

**Wins and losses are both data** — neither is philosophically “bad”; both feed learning **after** reveal.

---

## 5. Reveal phase — when truth meets belief

**After** the Student commits at *t* (for the chosen **graded unit** — step, trade, or segment per spec), the **Referee reveals**:

- **What actually happened** (structured): fills, exit, PnL, WIN/LOSS, **graded score** if any.

**Comparison moment (learning substrate):**

- **What she believed** (her structured output) vs **what occurred** (Referee).
- **Error or correctness** in **context space**, not only “wrong number.”

**Best practice (product, not optional fluff):** On **loss**, still **reveal** — otherwise there is no **credit assignment**. Prefer **Referee-grounded** explanation layers:

- **Layer A:** **What happened** (structured facts — no LLM invention).
- **Layer B:** **Why in context** — which factors the system can attribute from traces/logs (fusion, regime, exit path), and only **honest** counterfactuals the engine can support.

Avoid **pure memorization** of a single price; optimize **“why a different allowed choice might have scored better”** in **indicator + context** vocabulary.

---

## 6. Graded wins — binary floor, continuous quality

A “win” is **not** only binary in the **learning** sense:

- The same nominal WIN can be **strong or weak** depending on **entry/exit quality**, **how well** indicators + context supported the trade, and **how much edge** was captured vs left **(e.g. efficiency, giveback, R-multiple style measures)**.

**Referee** defines any **sliding scale** from **immutable** execution data. The Student’s aim is to **climb** that scale over time through **understanding** (memory + context), not to hack a headline win rate.

---

## 7. Learning — what “real” means

**Each decision (or graded unit) should produce a persistent learning record** including at minimum (conceptually):

- **Contextual situation at *t*** (signature / features matchable later).
- **Student’s decision** (structured).
- **Actual outcome** (Referee).
- **Graded quality** (scalar or small vector).
- **Error attribution** in allowed form (what was wrong in **context**, not vibes).

**Learning is not** merely logging.

**Learning is real only when** stored experience **changes future decisions** under **similar** context (cross-run or later in session — per policy).

---

## 8. Cross-run behavior — critical requirement

A **completed run** must be able to **influence** a **future run**:

- **Run 1** writes learning records (and/or eligible memory promotions per harness rules).
- **Run 2** **loads** them, **matches** current situation to prior records, and **behavior** (**Student decisions** or **allowed** bias paths — per minimal implementation) **differs** when matches fire.

**Definition check:** If **Run 2** is **identical** to **Run 1** in all **observable decision-relevant** ways when memory claims to be loaded and matches exist, **learning has not occurred** in the sense of this amendment.

**Operator hygiene:** Clearing **scorecard** / batch **history** (UI visibility) is **not** the same as **resetting learning state** / memory stores — operators should treat **“clear card”** vs **“reset learning”** as **different** controls (conceptually: **scoreboard paper** vs **trophy case**).

---

## 9. Memory + context = understanding (normative)

The team’s **operating definition:**

- **Context** = **what kind of market** this is and how **indicators interlock** (direction, regime, transition, fusion story).
- **Memory** = **graded prior episodes** you can **match** to ask **“have I seen this before?”**

If an **explicit algorithm** can be written (retrieve → compare → apply → check), it should be **written down** and **followed** wherever the product requires **auditability** — **minimal** extra prose, **maximal** repeatability.

**Referee still measures** — “understanding” **steers** decisions; it does **not** replace the **immutable standard** for scores.

---

## 10. Current gap (as of this writing — code vs canon)

**The system already can:**

- Record outcomes and structured run artifacts.
- Load and optionally apply **memory / bias** paths **within** replay in places (e.g. decision-context recall, signature stores, harness **read_write** semantics) — **operator-dependent** configuration.

**The system does not yet fully implement (Student–Proctor canon):**

- **Anna** as **causal decision-maker at each *t*** with **reveal-graded** learning records wired **every step** in the pattern-game **default** path (today: **post-hoc** narration from `player_agent` is **advisory**).
- **Guaranteed** cross-run **behavioral** change from **Student** learning records **independent** of “same manifest file” — when stores don’t change or **Student** isn’t in the loop, **Groundhog** repeats remain.

This gap explains **deterministic repeats** and the **feeling** that “learning doesn’t stick” even when **recall** metrics are large.

---

## 11. Implementation principles (when coding)

- **Minimal diffs** — only touch surfaces required to implement the **Student–Proctor** loop; do **not** refactor unrelated paths.
- **Referee immutable** — no LLM path **authorizes** trades or **overwrites** numbers.
- **Explicit schemas** for Student output, reveal payload, and learning records.
- **Leakage tests** — automated checks that pre-reveal bundles **cannot** contain illegal fields.

---

## 12. Gaps — touched (design detail for implementation)

This section **does not** replace specs in code; it locks **decisions and reuse** so engineering can stay minimal later. Items **1–8** map to the original backlog.

---

### 12.1 Credit assignment (graded win — Referee-only scalars)

**Goal:** A **sliding-scale** quality signal derived **only** from replay truth, not LLM opinion.

**Already in-repo (reuse first):** `renaissance_v4/game_theory/pattern_outcome_quality_v1.py` — `compute_pattern_outcome_quality_v1` over `list[OutcomeRecord]` yields:

- `expectancy_per_trade`, `avg_win_size`, `avg_loss_size`, `win_loss_size_ratio`, `exit_efficiency`, counts.
- Per-trade building blocks use `OutcomeRecord.pnl`, `mfe`, `mae` (and implicitly direction, times, `contributing_signals`, `regime` on the record).

**`OutcomeRecord` fields** (`renaissance_v4/core/outcome_record.py`): `trade_id`, `symbol`, `direction`, `entry_time`, `exit_time`, `entry_price`, `exit_price`, `pnl`, `mae`, `mfe`, `exit_reason`, `contributing_signals`, `regime`, sizing fields, `metadata`.

**Decisions still to freeze:**

| Decision | Options | Recommendation |
|----------|---------|------------------|
| Primary **session** grade | Single scalar vs small vector | Start with **vector** `{expectancy_per_trade, exit_efficiency, win_loss_size_ratio}` + optional **composite** = documented weighted sum (one number for dashboards only). |
| **Trade-level** grade | Same formula as above / per-trade exit efficiency slice | Reuse **per-trade exit efficiency** logic already inside `pattern_outcome_quality_v1` loop (exposed per trade only if you add a `per_trade_scores` export — **small** additive function). |
| Session vs trade **unit** for Student reveal | Align Student “round” to **closed trade** first — aligns with `OutcomeRecord` granularity. |

**Non-goal:** Let the LLM invent “quality” — **Referee computes**, Student **interprets** in text only.

---

### 12.2 Student action space — discrete vs continuous; shadow vs execution

**Goal:** Define what Anna **may output** at decision time without breaking immutability.

**Recommended phasing:**

| Phase | Action space | Effect on execution |
|-------|----------------|----------------------|
| **A — Shadow only** | Structured JSON: `{hypothesis_id, act: bool, direction: long|short|flat, pattern_tags[], confidence_01, free_reason}` | **Zero** effect on `fuse_signal_results` / orders. Referee runs as today. After run, compare Student vs Referee **per graded unit** (offline alignment score). |
| **B — Advisory influence (optional)** | Same schema; fed into **existing** whitelisted paths only (e.g. memory bundle suggestions, **never** raw order API) | Only if product requires; still **no** LLM direct to execution. |
| **C — Execution-influencing Student** | Not default — would be a **new** policy class. **Out of scope** for minimal Student–Proctor v1 unless explicitly approved. |

**Discrete vs continuous:** Start **discrete** (act / direction / recipe id from a **fixed enum**). Continuous knobs (e.g. size) **without** a boundary invite hallucination — defer.

---

### 12.3 Reveal policy — unit of grading; what to show on loss

**Goal:** One **reveal** moment: Student belief vs Referee truth; loss still **informs**.

**Unit of grading (pick one v1):**

1. **Per closed trade** (recommended first) — lines up with `OutcomeRecord`, harness, outcome quality.
2. Per **decision window** / bar — only if replay exposes a stable `decision_id` for every bar you care about (heavier instrumentation).

**On loss, always reveal:**

- **Layer A (mandatory):** structured Referee fields for that unit — PnL sign/magnitude, WIN/LOSS per `outcome_rule_v1`, exit reason, key times/prices as already in ledger.
- **Layer B (learning):** `regime`, `contributing_signals`, **graded scalars** from §12.1 for that trade or rolling window.
- **Layer C (optional, Referee-grounded):** “distance to best achievable exit in hindsight” **only** if computable from logged MAE/MFE without fiction — else omit.

**LLM:** May **narrate** Layers A–B; **must not** add numbers not in the payload.

---

### 12.4 Learning record schema — versioned, matchable

**Goal:** Store `{situation, belief, outcome, error}` such that **Run 2** can retrieve by **signature**.

**Two layers (do not conflate):**

1. **Engine memory** (existing): `context_signature_memory` / DCR — **deterministic**, key = `pattern_context_v1`-derived signature; used for **fusion bias**, not Anna prose.
2. **Student learning record** (new when implemented): schema e.g. `student_learning_record_v1`:

   - `schema`, `record_id`, `utc`, `source_run_id`, `graded_unit` (`trade_id` or `bar_index`),
   - `context_signature` (reuse hash contract from `derive_context_signature_v1` **or** a **narrower** Student-only signature if needed),
   - `student_output` (JSON from §12.2),
   - `referee_outcome` (subset of `OutcomeRecord` + quality vector from §12.1),
   - `alignment_flags` (bool/string error codes),
   - `manifest_sha256`, `strategy_id` (audit).

**Append-only JSONL** under `game_theory/state/` or `PATTERN_GAME_MEMORY_ROOT`-governed path — mirror how `run_memory` / `context_signature_memory` work.

**Retrieval:** Same as case-based reasoning — **k-nearest** or **exact** signature bucket + tolerance policy (already philosophically aligned with `context_signature_memory` matching).

---

### 12.5 Cross-run proof test (“learning = different behavior”)

**Goal:** Automated test that **fails** if Run 2 is bit-for-bit identical **where** learning should apply.

**Definitions:**

- **“Same conditions”** = same manifest file, same bar window, same seed if any — **but** Run 2 **loads** N prior `student_learning_record_v1` lines (or engine memory **write** from Run 1 in **read_write** paths that **change** `apply`).
- **“Different behavior”** depends on phase:
  - **Phase A (shadow):** Student JSON outputs differ OR **alignment histogram** shifts — execution may still match (Referee deterministic).
  - **Phase B+ (engine affected):** `decision_audit` / `bundle_optimizer` / DCR **apply diff** non-empty OR trade list hash differs.

**Minimal pytest shape:** Fixture run Run 1 → writes record → Run 2 **with** load → assert `!=` on chosen **fingerprint** (trade count hash, or `student_decision_trace` hash, or `memory_bundle` merge diff).

**Important:** Current **large recall / bias counts** without **Student** records changing **Anna** are **not** this proof — they prove **engine** recall, not **Student** learning.

---

### 12.6 Anna integration points — smallest surface

**Goal:** Minimal files touched to hang **Phase A** (shadow Student).

| Surface | Role |
|---------|------|
| `replay_runner.py` | Optional callback or **second pass**: emit **per-trade** or **per-window** **Student bundle** (no LLM inside hot loop if latency concerns — **post-bar batch** also acceptable for v0.1). |
| `player_agent.py` | After batch: call **Student** grading **compare** step; append to report; **or** new small module `student_proctor_bridge.py` under `game_theory` to avoid bloating `player_agent`. |
| `web_app.py` | Optional: toggle “shadow student” / show alignment panel — **later**. |

**Reuse:** Do **not** duplicate `pattern_context_v1` extraction — import from existing replay outputs. Do **not** fork `OutcomeRecord`.

---

### 12.7 Calibration metrics — not vanity prose

**Goal:** Measure **Student ↔ Referee agreement** on structured dimensions.

**Examples (computable without new models):**

- **Direction agreement** (when Student chose long/short vs `OutcomeRecord.direction` sign vs PnL — define tie-breaks).
- **Act/agree:** Student `act==false` vs “no trade would have been optimal” **only** if you define optimality from Referee (hard) — defer v1; use **weaker** “session PnL sign agreement” instead.
- **Quality rank correlation:** Spearman between Student **stated confidence** and **exit_efficiency** (requires enough trades).

**Report:** JSON block in run output — **Barney** can format but **not** compute metrics.

---

### 12.8 Algorithm inventory — borrow patterns, not stacks

| Pattern | Use here |
|---------|----------|
| **Case-based reasoning** | Learning records + signature match = **retrieve** similar situations. |
| **Experience replay** | Store transitions `(state, action, reward)`; sample for **training** future Student policy — **offline** first. |
| **Contextual bandits** | Only if Student **discrete** actions and you need explore/exploit — **later**. |
| **RAG + grounding** | Anna prose **must cite** record IDs / fields — same discipline as `player_agent` Referee facts block. |
| **Bandits / deep RL** | **Out of scope** for minimal canon unless explicitly funded. |

**Rule:** Pick **one** retrieval + **one** grading pipeline for v1; avoid importing frameworks until the **schemas** in §12.4 exist.

---

### 12.9 Summary checklist before coding

- [ ] §12.1 **Composite grade** formula documented (weights).
- [ ] §12.2 **Phase A** shadow schema frozen.
- [ ] §12.3 **Reveal** payload template (JSON) for win and loss.
- [ ] §12.4 **`student_learning_record_v1`** draft schema reviewed.
- [ ] §12.5 **Test** fingerprint chosen (what must differ).
- [ ] §12.6 **Integration** list approved (which files).
- [ ] §12.7 **Calibration** metrics v1 list (2–3 metrics max).
- [ ] §12.8 **No** new ML stack until schemas exist.

---

## 13. One-line anchor

**The Student must decide without knowing outcomes, be graded by the Referee afterward, and use graded experience to change future decisions — or it is not learning.**

---

## 14. Related in-repo pointers (not duplicates of this log)

- `GAME_SPEC_INDICATOR_PATTERN_V1.md` — pattern game rules, Referee authority.
- `QUANT_RESEARCH_AGENT_DESIGN.md` — research intent, indicator context.
- `TEAM_BRIEF_PATTERN_GAME_AGENT.md` — what runs today, logs, memory channels.
- `baseline_v1_policy_framework.json` — learning-goal alignment vocabulary (outcome quality vs raw win count).
- `context_memory.py`, `context_signature_memory.py`, `decision_context_recall.py` — **engine** memory paths (distinct from **Student** learning loop until wired).

---

*End of CONTEXT LOG entry — Student–Proctor / PML System Amendment.*
