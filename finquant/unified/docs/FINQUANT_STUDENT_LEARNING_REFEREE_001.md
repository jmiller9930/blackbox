# FinQuant Student Learning Referee 001

**Status:** Draft working proof contract  
**Scope:** `finquant/unified/` isolated project only  
**Companion docs:** `FINQUANT_UNIFIED_LEARNING_ARCHITECTURE_001.md`, `FINQUANT_UNIFIED_DEVELOPMENT_PLAN_001.md`

---

## 1. Purpose

This document defines the operator-facing artifact that answers the question:

> Did the FinQuant student actually learn anything?

The answer must not be based on vague impressions, lucky economics, or the fact that an LLM happened to run.

The referee artifact exists so the operator can distinguish between:

- a control run,
- an engaged but non-learning run,
- a memory-present but non-influential run,
- and a genuinely learned behavior change.

The behavior under review is not limited to entry direction.
It explicitly includes:

- pattern recognition,
- memory recall,
- context-influenced judgment,
- take-position vs `NO_TRADE` judgment,
- and exit judgment.

---

## 2. Required Two-Run Structure

The minimum learning proof requires two governed runs over the same scenario family.

### Run A — Control

The control run is the baseline student run with:

- no memory retrieval,
- no prior-context injection,
- no persisted lesson reuse,
- and no claim of learning influence.

This run exists to answer:

- what would the student do without memory,
- what confidence would it report,
- and what economic/process result would occur without retrieved lessons.

### Run B — Memory / Context Candidate

The candidate run is the same student lane with:

- retrieval enabled,
- eligible prior lessons available,
- governed memory/context injection allowed,
- and the same no-lookahead constraints as the control run.

This run exists to answer:

- whether prior validated experience was actually retrieved,
- whether that experience affected the decision path,
- and whether the change improved the result or the abstention quality.

---

## 3. Referee Questions

The referee must answer all of these questions explicitly.

### Q1. Was the student actually engaged?

Evidence:

- model path enabled or deterministic student path enabled,
- decision emitted,
- artifacts written,
- no silent stub substitution.

### Q2. Was memory actually available and eligible?

Evidence:

- persisted lesson rows existed before Run B,
- retrieval was enabled,
- retrieval filter/governance allowed at least one eligible record.

### Q3. Was memory actually used?

Evidence:

- retrieval count > 0,
- retrieved record ids captured,
- retrieval summary recorded,
- influence fields populated.

### Q4. Did behavior change?

Evidence:

- action changed, or
- confidence meaningfully changed, or
- thesis / invalidation changed, or
- abstention quality improved, or
- lifecycle / exit behavior improved.

### Q5. Was the behavior change attributable to learning?

Evidence:

- Run A and Run B are comparable,
- causal packet remains pre-reveal,
- retrieved lesson was relevant,
- behavior delta lines up with retrieved lesson content,
- no policy bypass or lookahead contamination occurred.

### Q6. Was the change actually better?

Evidence:

- improved exam result, or
- improved abstention result, or
- improved bounded process/economic score,
- with no cheating and no invalid contract output.

If Q1 through Q6 are not satisfied, the run does not count as proven learning.

---

## 4. Referee Verdicts

The operator-facing artifact must emit one of these verdicts.

### `CONTROL_ONLY`

Run A exists, but no candidate run was evaluated yet.

### `ENGAGEMENT_WITHOUT_STORE_WRITES`

The student ran, but no durable learning rows were created or promoted.

### `MEMORY_AVAILABLE_NO_MATCH`

Memory existed, but no eligible records matched the candidate scenario.

### `MEMORY_MATCH_NO_IMPACT`

Memory was retrieved, but it did not materially change behavior.

### `BEHAVIOR_CHANGED_NOT_PROVEN_BETTER`

Behavior changed, but the evidence does not prove that the change improved the outcome or process.

### `FALSE_LEARNING_CLAIM_REJECTED`

The run appears improved, but the artifact shows the change is not attributable to learning, or causal discipline was violated.

### `LEARNED_BEHAVIOR_PROVEN`

The candidate run retrieved eligible prior learning, behavior changed for a traceable reason, and the changed behavior was better under the governed evaluation surface.

---

## 5. Required Artifact Fields

The referee report should be emitted as `student_learning_referee_report_v1.json`.

Minimum required fields:

- `schema`
- `created_at_utc`
- `scenario_id`
- `student_id`
- `control_run_id`
- `candidate_run_id`
- `control_profile_v1`
- `candidate_profile_v1`
- `model_requested_v1`
- `model_resolved_v1`
- `ollama_base_url_used_v1`
- `retrieval_enabled_v1`
- `retrieval_match_count_v1`
- `retrieved_record_ids_v1`
- `store_writes_count_v1`
- `memory_impact_class_v1`
- `behavior_delta_v1`
- `outcome_delta_v1`
- `proof_checks_v1`
- `verdict_v1`
- `operator_summary_v1`

---

## 6. Behavior Delta Contract

`behavior_delta_v1` should summarize how Run B differed from Run A.

Minimum subfields:

- `action_changed_v1`
- `control_action_v1`
- `candidate_action_v1`
- `confidence_changed_v1`
- `control_confidence_v1`
- `candidate_confidence_v1`
- `thesis_changed_v1`
- `abstention_changed_v1`
- `exit_behavior_changed_v1`
- `retrieval_attributed_v1`

The referee must be able to say:

- no delta,
- delta but not learning-caused,
- or delta attributable to learning.

---

## 7. Outcome Delta Contract

`outcome_delta_v1` should summarize whether the changed behavior was better.

Minimum subfields:

- `exam_result_changed_v1`
- `control_final_status_v1`
- `candidate_final_status_v1`
- `economic_score_delta_v1`
- `process_score_delta_v1`
- `abstention_quality_improved_v1`
- `notes_v1`

The outcome delta is not limited to raw profit.
It may also prove improvement by showing that a bad trade was correctly avoided.

---

## 8. Proof Checks

`proof_checks_v1` must be a checklist rather than a single boolean.

Recommended checks:

- `control_run_present`
- `candidate_run_present`
- `same_scenario_family`
- `causal_packet_only`
- `retrieval_enabled`
- `eligible_memory_exists`
- `retrieval_match_present`
- `behavior_delta_present`
- `retrieval_attribution_supported`
- `outcome_or_process_improved`
- `no_contract_violation`
- `no_stub_fallback`

Each check should carry:

- `id`
- `pass`
- `detail`

This makes the proof reviewable instead of opaque.

---

## 9. Referee Method

The isolated FinQuant referee should work like this:

1. Run the control profile.
2. Persist governed lessons if the run produces eligible learning.
3. Run the candidate profile with retrieval/context enabled.
4. Compare action, confidence, and thesis fields.
5. Compare economic/process or abstention outcome.
6. Reject any learning claim that cannot be causally attributed.
7. Emit the referee artifact with a hard verdict.

This referee is about **proof**, not optimism.

---

## 10. Initial Profile Mapping

The first isolated FinQuant version should use these profiles:

- `baseline_no_memory_no_context`
- `memory_context_reasoning`

If a live LLM is enabled, the artifact must capture the exact resolved model and host.

Current validated local reasoning host:

- `http://172.20.2.230:11434`

Current validated local reasoning model:

- `qwen2.5:7b`

Validation note:

- `172.20.2.66:11434` did not respond during validation on **May 1, 2026**
- the repository’s existing proof artifacts repeatedly point to `172.20.2.230`

---

## 11. What Does Not Count As Learning

The following do **not** count as proven learning:

- the model was called
- the run completed
- the economics looked good once
- memory rows existed somewhere
- retrieval was enabled but matched nothing
- behavior changed for a reason unrelated to retrieved lessons
- a run improved but the proof cannot attribute the improvement honestly

---

## 12. Closure Standard

Directive F and Directive H are not complete until this artifact exists and can emit all of the following honestly:

- no learning proven,
- learning engaged but not persisted,
- memory match with no impact,
- false learning claim rejected,
- learned behavior proven.

If the referee cannot distinguish those states, the project is not ready to claim cumulative judgment.
