# GT_DIRECTIVE_023 — Learning effectiveness (operator proof)

## Scope

Read-only **`learning_effectiveness_report_v1`** built from **`batch_scorecard.jsonl`** + **`student_learning_records_v1.jsonl`**. Optional **`training_dataset_v1.jsonl`** appears only as **`training_dataset_v1_line_count`** in `sources_v1` when the file exists. No grading, no L3, no store mutation.

## Automated proof

- **Tests:** `renaissance_v4/game_theory/tests/test_gt_directive_023_learning_effectiveness_v1.py`  
  - Two fingerprints from distinct `operator_batch_audit` hashes; **3** vs **1** `done` runs.  
  - Scorecard lines written **out of time order**; report **`runs_ordered_v1`** is **early → mid → late** by `started_at_utc`.  
  - Slopes, memory-vs-baseline deltas, LLM-vs-memory deltas, promotion **next-run** means, population variance — **numeric assertions** on the fixture.  
  - **Determinism:** frozen `_utc_iso`; two `json.dumps(..., sort_keys=True)` builds **identical**.  
  - **HTTP:** `GET /api/training/learning-effectiveness` and **`?summary=1`** return expected `schema` values.

## Example fingerprint trend (fixture, 3-run series)

After chronological sort, **E** is **0.1 → 0.5 → 0.9** (exam scores on all three lines). Ordinal least-squares slope **`slope_e_over_ordinal_v1` ≈ 0.4** (increasing). **PASS** series **0 → 1 → 1**; slope positive ⇒ **`pass_trend_label_v1` = `increasing`**.

## Example memory vs baseline delta (same fingerprint)

Per-profile means on that fingerprint: baseline **E = 0.1**, `memory_context_student` **E = 0.5** ⇒ **`delta_mean_e_memory_student_vs_baseline_v1` = 0.4** (same for **P** delta **0.4**; pass-rate delta **1.0** because baseline pass **0** and memory pass **1**).

## Example LLM vs non-LLM delta (same fingerprint)

`memory_context_llm_student` mean **E = 0.9** vs memory stub **0.5** ⇒ **`delta_mean_e_llm_vs_memory_student_v1` = 0.4**.

## Promotion next-run (018 linkage)

Fixture: **`job_fp1_early`** has a **promote** row in the learning store; the **next** scorecard run in that fingerprint is **`job_fp1_mid`** with **E = 0.5** ⇒ bucket **after promoted source**. **`job_fp1_mid`** is **hold** only; next run **`job_fp1_late`** has **E = 0.9** ⇒ bucket **after non-promoted source**. Report surfaces **`mean_e_next_run_after_promoted_source_v1`** vs **`mean_e_next_run_after_non_promoted_source_v1`** for this synthetic pair (not a claim about production causality).

## Verdict statement on fixture data

With this fixture, **`verdict_improving_flag_v1`** is **true** (positive E slope fingerprint, positive memory-vs-baseline and LLM-vs-memory E deltas). On **real** logs, read **`verdict_v1.statement_v1`** literally — it will read either **`system_improving_v1`** … or **`not_improving_or_inconclusive_v1`** … per the module’s heuristic.

## HTTP verification (local)

```bash
curl -s "http://127.0.0.1:8765/api/training/learning-effectiveness?summary=1" | python3 -m json.tool | head -n 40
```

Expect **`"schema": "learning_effectiveness_report_summary_v1"`** and no **`runs_ordered_v1`** inside **`fingerprints_v1`** entries.

## Materialize (server file)

```bash
curl -s -X POST "http://127.0.0.1:8765/api/training/learning-effectiveness/materialize" \
  -H "Content-Type: application/json" \
  -d '{"confirm":"MATERIALIZE_LEARNING_EFFECTIVENESS_REPORT_V1"}' | python3 -m json.tool
```
