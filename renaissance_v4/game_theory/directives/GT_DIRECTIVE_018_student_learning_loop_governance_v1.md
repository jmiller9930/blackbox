# GT_DIRECTIVE_018 — Student learning loop **governance** (good loop vs bad loop)

**Date:** 2026-04-24  
**Status:** **ACTIVE** — v1 retrieval slice **SHIPPED**; **v2 memory promotion slice SHIPPED** (promote/hold/reject, store gate, retrieval eligibility, run learning API + proof). **OPEN** for deliberation artifacts, richer relevance scoring, and operator metrics until accepted or deferred.  
**From:** Architect / operator product lock  
**To:** Engineer  
**CC:** Product, Referee, UI  
**Scope:** `renaissance_v4/game_theory/student_proctor` — cross-run retrieval, Student loop seam audit, learning store **read path** behavior. **Does not** replace **GT_DIRECTIVE_015** (run / brain profile contract); **cross-references** it.

---

## Fault (why this exists)

Without explicit **governance**, a feedback loop that writes **all** graded rows into memory and retrieves **unbounded** or **stale-first** slices risks:

- **Garbage memory** — noisy rows treated like patterns.  
- **Sloppy context** — too many or irrelevant slices in the packet.  
- **Narrative drift** — LLM or Student appears coherent while **E/P** do not improve (**bad learning loop** per operator brief).

015 addresses **what** a run declares; **018** addresses **how** retrieved memory is **bounded and ordered** so the loop stays **testable and honest** at the mechanism layer.

---

## Directive (v1 — implemented)

### 18.1 Retrieval cap (programmatic)

- **Env:** `PATTERN_GAME_STUDENT_MAX_RETRIEVAL_SLICES` — integer, default **8**, clamped **0–128**. Invalid values fall back to **8**.  
- **API:** `build_student_decision_packet_v1_with_cross_run_retrieval(..., max_retrieval_slices=None)` uses the env default; explicit integers still override (clamped 0–128).  
- **Code:** `student_learning_loop_governance_v1.resolved_max_retrieval_slices_v1`, used from `cross_run_retrieval_v1.py`.

### 18.2 Newest-first attachment

- Matching learning rows for a signature key are attached **newest-first** (last appended in the JSONL store first), then capped.  
- Prevents silently biasing the Student toward **stale** rows when the cap is `<` total matches.

### 18.3 Seam audit (operator visibility)

- Every non-skipped `student_loop_seam_after_parallel_batch_v1` result includes **`learning_loop_governance_v1`**:  
  - `max_retrieval_slices_resolved`  
  - `retrieval_attachment_order_v1` = `newest_first`

---

## Future slices (not v1 — track here)

- Memory **quality** gates before append (or mark “low confidence” rows).  
- Retrieval **relevance** scoring / regime match (beyond signature equality).  
- Structured **H1–H4** + **NO_TRADE** pressure in LLM / seal path.  
- **P** enforcement coupling and **smell** metrics (NO_TRADE rate, H4 vs outcome contradiction).  
- Anti–echo-chamber **down-weighting** of repeated failure signatures.

---

## Proof required

1. **Unit tests** — `resolved_max_retrieval_slices_v1` (explicit override, env, clamp, invalid env).  
2. **Integration** — cap + newest-first on `build_student_decision_packet_v1_with_cross_run_retrieval`.  
3. **Seam** — `learning_loop_governance_v1` present on audit when seam runs.  
4. **Doc** — This directive; **§18.4** row in `STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md`; **GT_DIRECTIVE_015** cross-ref.

---

## Deficiencies log

Track **“GT_DIRECTIVE_018 — learning loop governance”** until **Accepted** or deferred in writing.

---

## Engineer update

**2026-04-24 — v1 shipped**

- Added `student_proctor/student_learning_loop_governance_v1.py`.  
- `cross_run_retrieval_v1.py` — env-resolved cap, **newest-first** slice order, `max_retrieval_slices` default `None`.  
- `student_proctor_operator_runtime_v1.py` — `learning_loop_governance_v1` on seam audit.  
- Tests: `tests/test_student_learning_loop_governance_v1.py`; `test_cross_run_retrieval_v1` order assertion updated.

**2026-04-24 — v2 memory promotion (GT_018 build)**

- `student_proctor/learning_memory_promotion_v1.py` — L3+scorecard classifier; `build_student_panel_run_learning_payload_v1`.  
- Seam — `memory_promotion_batch_v1`; append only when decision ≠ `reject`; `learning_governance_v1` + `memory_promotion_context_v1` on rows.  
- `student_learning_store_v1.py` — `retrieval_eligible_only` on signature listing (default **true**).  
- `GET /api/student-panel/run/<job_id>/learning` — operator run payload.  
- Proof: `docs/proof/exam_v1/GT_DIRECTIVE_018_learning_governance_v1.md`.  
- Tests: `tests/test_gt_directive_018_learning_memory_promotion_v1.py`.

**Remaining:** future slices listed above.

---

## Architect review

**Status:** **v1 slice — proof complete in repo** (unit + integration + seam audit tests). Directive **stays OPEN** for future slices (memory quality, H1–H4 / NO_TRADE, P metrics, dashboards) until those are shipped or explicitly deferred in writing.
