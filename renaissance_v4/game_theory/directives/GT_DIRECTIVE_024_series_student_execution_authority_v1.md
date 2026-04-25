# GT_DIRECTIVE_024 series — Student execution authority, lane separation, and trace proof

**Status:** OPEN — micro-directives **024A** through **024E** (no single “wire Student into replay” patch).  
**Audience:** Engineering, Product, Referee, Data, UI.  
**Depends on:** Code-grounded fact that the parallel Run Exam path scores **control replay** (`parallel_runner._worker_run_one` → `control_replay`); Student seam emits `student_output_v1` **after** batch replay (shadow for **scored execution** today). **GT_DIRECTIVE_023** (learning effectiveness) is orthogonal closure.

**One-line summary:** Move the Student from observer to execution authority through a staged, proven lane system: first define intent, then run a Student-controlled replay lane, then separate metrics, then prove the chain visually in the LangGraph trace.

---

## Series acceptance bar (all must be true before claiming learning affects scored outcomes)

1. Student output is converted to **validated** `student_execution_intent_v1`.  
2. Student execution intent is **consumed before** Student-lane replay outcomes are generated.  
3. Student-controlled replay is **scored separately** from baseline/control.  
4. Scorecard and L1 **identify execution authority** (and lane).  
5. Trace proves **Student → execution → score** linkage.  
6. **Baseline/control replay remains unchanged** (byte-stable default path when Student lane is off or omitted).

**Rejected approaches:** A vague `decision_provider_v1` dropped into `run_manifest_replay` without contracts, lane tags, scorecard separation, and proof — see architecture challenge (024A must pick a **code-grounded** injection strategy).

---

## Shared vocabulary (required terms)

| Term | Meaning |
|------|--------|
| `execution_lane_v1` | Which replay row produced the metric: e.g. `baseline_control` \| `student_controlled` (extensible). |
| `execution_authority_v1` | Who owns the decision that **entered** the trade for that lane: e.g. `manifest` \| `student_thesis` \| `recall_biased_replay` (must be distinguishable from Student). |
| `student_execution_intent_v1` | Validated contract consumed by Student-lane replay (**024B**); not raw `student_output_v1`. |
| `control_replay` | Existing harness/score path replay dict (today: scored for parallel Run Exam batch row). |
| `student_controlled_replay` | Separate replay run whose outcomes are attributed to Student authority when intent is consumed. |
| `recall_biased_replay` | Replay with decision-context recall / fusion bias enabled — **not** synonymous with Student-controlled; must remain taggable separately. |

---

## GT_DIRECTIVE_024A — Student execution authority design contract

**Delivered design doc (code citations + A/B/C verdict):** `renaissance_v4/game_theory/directives/GT_DIRECTIVE_024A_student_execution_authority_design_contract_v1.md`

**Objective:** Define the exact architecture for Student-controlled execution **before** touching replay implementation code.

**Required output (design document must prove):**

- Where Student decision is **generated** (seam / Ollama / store).  
- Where it becomes **execution intent** (`student_execution_intent_v1`).  
- Where replay **consumes** that intent (injection point named from code).  
- How **baseline/control replay** remains unchanged (default path, checksum policy).  
- How **Student execution** is scored **separately** (scorecard rows or explicit sub-keys).  
- How **L1 / L2 / L3** distinguish **execution authority** (no silent mixing).  
- How **trace** proves Student authority (event chain + digests).

**Required decision (engineering must state explicitly):**

Implementation will use one or a combination of:

- Existing **apply / candidate** replay mechanisms (`context_candidate_search._replay_with_apply_dict`, bundle apply whitelist), **or**  
- A **new replay row type** / harness selection policy (without relabeling control as Student), **or**  
- A **narrow** post-fusion / pre-execution hook (lane-scoped, tested), **or**  
- Another **code-grounded** injection point justified in the doc.

**Scope:** **024A — no production replay code changes** except documentation and tests **only if** needed to lock interfaces (optional).

**Done condition:** Architect has a clear design showing how Student moves from observer to execution authority **without corrupting** baseline semantics.

---

## GT_DIRECTIVE_024B — Student execution intent schema

**Implementation:** `renaissance_v4/game_theory/student_proctor/student_execution_intent_v1.py`  
**Proof:** `docs/proof/exam_v1/GT_DIRECTIVE_024B_student_execution_intent_schema_v1.md`

**Objective:** Create the **validated** contract that converts `student_output_v1` into something replay can safely consume. **Do not wire replay yet.**

**Artifact:** `student_execution_intent_v1` with at least:

- `source_student_output_id` **or** digest of sealed `student_output_v1`  
- `job_id`  
- `fingerprint` (aligned with exam / scorecard fingerprint rules)  
- `scenario_id` **or** trade/window identifier (as chosen in 024A)  
- `action`: `enter_long` \| `enter_short` \| `no_trade`  
- `direction`: `long` \| `short` \| `flat`  
- `confidence_01`, `confidence_band`  
- `invalidation_text`  
- `supporting_indicators`, `conflicting_indicators`  
- `context_fit`  
- `created_at_utc`  
- `schema_version`

**Validation rules:**

- `action` must agree with `direction`.  
- `no_trade` must map to **flat** or **no entry** (documented mapping).  
- `enter_long` → `long`; `enter_short` → `short`.  
- `confidence_01` in **[0, 1]**.  
- LLM profile: **complete thesis fields** required before intent is valid.  
- Intent must be **deterministic** from sealed Student output (same input → same digest).

**Proof required:**

- Valid intent builds from valid `student_output_v1`.  
- Invalid action/direction rejected.  
- Missing thesis rejected for LLM profile.  
- `no_trade` maps to no execution intent for entry.  
- Intent digest **stable** across identical input.

**Done condition:** Student output can be safely transformed into execution intent; **replay code paths unchanged** from 024B deliverable alone.

---

## GT_DIRECTIVE_024C — Student execution lane / replay integration

**Objective:** Add a **Student-controlled** replay lane **without** changing baseline behavior. Baseline remains **default** and **byte-stable** when Student lane is not used.

**Required behavior:**

- `execution_lane_v1 = baseline_control` — **current path unchanged**.  
- `execution_lane_v1 = student_controlled` — consumes `student_execution_intent_v1`.  
- Referee still **evaluates outcomes** from the Student-controlled lane (closed trades, PnL semantics unchanged **within that lane**).  
- **Do not** overwrite `control_replay` artifacts with Student outcomes.  
- **Do not** relabel baseline outcomes as Student outcomes.  
- If intent says `no_trade`, Student lane **must not** enter.  
- If intent differs from baseline, Student lane **must be able** to produce **different** outcomes.

**Engineering must prove** the exact **injection point** from code (file + function). Any hook must be **narrow**, **tested**, and **lane-scoped**. If using candidate/apply mechanics, Student lane must be explicitly **`execution_authority_v1 = student_thesis`**, not confused with **`recall_biased_replay`**.

**Required trace events (minimum):**

- `student_execution_intent_created`  
- `student_execution_intent_consumed`  
- `student_controlled_replay_started`  
- `student_controlled_replay_completed`  
- `referee_used_student_output` (true / false / unknown — must become **true** when Student lane outcomes are what Referee scored for that lane)

**Done condition:** A Student-controlled lane can run and produce outcomes **distinct** from baseline while baseline remains unchanged.

---

## GT_DIRECTIVE_024D — Scorecard, L1, E/P, and data separation

**Objective:** **Prevent metric mixing.** Every operator-visible aggregate must state which lane and authority produced it.

**Required fields (scorecard / denorm / API as applicable):**

- `execution_lane_v1`  
- `execution_authority_v1`  
- `control_replay_job_id` **or** digest  
- `student_replay_job_id` **or** digest  
- `student_execution_intent_digest_v1`  
- `outcomes_hash_v1`  
- `exam_e_score_v1`, `exam_p_score_v1` (must be tied to the **lane displayed**)  
- `l1_e_value_source_v1`, `l1_p_value_source_v1` (must encode lane / authority where relevant)

**Rules:**

- Baseline metrics **remain** baseline metrics.  
- Student metrics **must be labeled** Student-controlled.  
- Recall-biased replay **must not** be confused with Student-controlled replay.  
- L1 **must not** aggregate different execution authorities as the same series without explicit grouping.  
- L2/L3 **must show** execution authority (and intent digest where applicable).  
- E/P **must** tie to the lane being displayed.

**Required tests:**

- Baseline run unchanged.  
- Student lane metrics separate from baseline metrics.  
- L1 groups by execution authority.  
- L3 shows lane + intent digest.  
- Mixed lane data produces explicit **`data_gap`** or separation (no silent blend).

**Done condition:** Operator can tell **exactly** which execution authority produced the displayed score.

---

## GT_DIRECTIVE_024E — LangGraph trace proof of Student authority

**Objective:** Debug / learning-loop trace must **prove** whether Student controlled execution (not decorate).

**Learning loop trace must show (ordered evidence):**

1. Student output sealed  
2. `student_execution_intent_v1` created  
3. Intent consumed by replay  
4. Student-controlled replay produced outcomes  
5. `referee_used_student_output` (true when Student lane is what was scored for that proof)  
6. Score derived from Student-controlled outcomes  
7. Learning governance processed **that** result  
8. Learning store appended or rejected **based on that** result  

**Required top-level verdicts:**

- `STUDENT AUTHORITY PROVEN`  
- `STUDENT SHADOW ONLY`  
- `STUDENT AUTHORITY BROKEN`  
- `INCONCLUSIVE`  

**Critical node: Student → Execution coupling**

Must surface:

- `referee_used_student_output` = true \| false \| unknown  
- `execution_authority_v1`  
- `execution_lane_v1`  
- `intent_digest`  
- `outcomes_hash`  
- `score_source`  

If Referee did not consume Student intent: **`STUDENT SHADOW ONLY`**.  
If intent consumed and outcomes produced under Student lane scoring: **`STUDENT AUTHORITY PROVEN`**.

**Required comparison (same fingerprint):**

Profiles such as:

- `baseline_control`  
- `memory_context_student_controlled`  
- `memory_context_llm_student_controlled`  

Compare at minimum:

- `student_action_v1`  
- `execution_authority_v1`  
- `outcomes_hash_v1`  
- `exam_e_score_v1`, `exam_p_score_v1`  
- `expectancy_per_trade`  
- `referee_win_pct`  

**Done condition:** Operator can **visually prove** whether Student decisions changed execution and scoring.

---

## Handoff note for implementers

Implement **024A → 024B → 024C → 024D → 024E** in order. Do not skip B to “save time.” Do not merge D into C without scorecard review. **Product / Referee sign-off** on 024A injection choice before 024C code lands.

**Canonical architecture doc:** `renaissance_v4/game_theory/docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` (cross-link from §1.0.1 implementation mapping as execution truth evolves).
