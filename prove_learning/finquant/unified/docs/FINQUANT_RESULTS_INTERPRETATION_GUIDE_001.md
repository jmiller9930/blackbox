# FinQuant Results Interpretation Guide 001

**Status:** Draft operator guide  
**Scope:** `finquant/unified/` isolated project only  
**Audience:** Operator / evaluator

---

## 1. Purpose

This guide explains how to interpret FinQuant test results, exam results, and learning results.

It exists to answer three operator questions:

1. Did the student run correctly?
2. Did the student make a good decision?
3. Did the student actually learn anything?

These are not the same question.

---

## 2. The Three Result Layers

Every isolated FinQuant run should be interpreted at three layers.

### Layer 1 — Runtime / Wiring

This layer answers:

- did the runner start,
- did the chosen mode execute,
- did artifacts get written,
- did the model path run when expected.

Examples of runtime success:

- process exits `0`
- `decision_trace.json` exists
- `run_summary.json` exists
- `llm_used_v1` or equivalent model-use field is true when the run was intended to use a model

What runtime success does **not** mean:

- it does not mean the decision was good
- it does not mean the student learned

### Layer 2 — Judgment / Exam Quality

This layer answers:

- was the action appropriate,
- was `NO_TRADE` chosen when it should have been,
- did the entry thesis make sense,
- was the exit reasonable,
- did the case pass or fail.

Examples:

- a run can be runtime-successful but judgment-failed
- a run can use a real LLM and still fail the exam

Judgment success means the student reasoned well enough for the governed test surface.

### Layer 3 — Learning / Memory

This layer answers:

- was learning persisted,
- was prior memory retrieved later,
- did retrieval influence behavior,
- was the influence actually beneficial,
- can the improvement be proven honestly.

This is the hardest layer and the most important for the unified-agent goal.

---

## 3. Control Run vs Candidate Run

The basic learning proof uses two runs.

### Control run

The control run is the student without memory influence.

Interpret it as:

- what the student does on its own,
- without prior lesson reuse,
- under the same causal scenario family.

### Candidate run

The candidate run is the student with governed memory/context enabled.

Interpret it as:

- what changed after prior experience became available,
- whether retrieved memory affected the decision,
- whether that change improved the result.

The candidate run should only be compared to the control when the scenario family is comparable.

---

## 4. How To Read The Main Artifacts

### `run_summary.json`

Use this first.

It tells you:

- which config/mode ran
- whether LLM use was enabled
- how many decisions were emitted
- whether learning records were written
- the final status for the run

Read this as the top-line summary, not the proof by itself.

### `decision_trace.json`

Use this to inspect the actual decision path.

It tells you:

- what action the student chose
- what thesis and invalidation it gave
- whether the source was `llm`, `hybrid`, or something else
- whether raw model output was captured

Read this when you need to know what the student actually did.

### `learning_records.jsonl`

Use this to confirm whether the run produced persistent learning material.

If this file is absent or empty when learning was expected, the student may have engaged without actually storing learning.

### `retrieval_trace.json`

Use this to see whether prior records were returned during a memory/context run.

Important interpretation:

- retrieval enabled does not mean retrieval matched
- retrieval matched does not mean retrieval influenced the decision

### `evaluation.json`

Use this to understand why the test/exam passed or failed.

This is the main judgment artifact.

### `student_learning_referee_report_v1.json`

Use this as the final operator-facing learning verdict.

This is the artifact that should tell you whether the student merely ran, merely retrieved, or genuinely demonstrated learned behavior.

### `test_framework_summary.json`

Use this when you run a named test pack.

It tells you:

- which pack ran
- how many tests passed
- the overall pack status
- each test verdict
- where each referee report lives

Read this first when you want the fastest operator-level answer from a multi-test run.

---

## 5. Common Result States

### State: Wiring success only

Typical signs:

- runner exits successfully
- artifacts exist
- model path may have run
- but the case still fails

Meaning:

- plumbing works
- judgment does not yet work well enough

### State: Judgment failure

Typical signs:

- exam fails
- action was inappropriate
- the student forced a trade when `NO_TRADE` was correct

Meaning:

- the student is connected
- but the reasoning policy still needs work

### State: Engagement without learning

Typical signs:

- student ran
- memory or model path engaged
- but no durable learning rows were written

Meaning:

- the student participated
- the system did not convert that experience into reusable learning

### State: Memory available, no impact

Typical signs:

- retrieval returned records
- but action/confidence/thesis did not materially change

Meaning:

- memory exists
- but it is not yet influencing judgment in a meaningful way

### State: Learned behavior proven

Typical signs:

- control run and candidate run are both present
- memory was eligible and retrieved
- behavior changed
- the change is attributable to retrieved learning
- the changed behavior is better

Meaning:

- this is the target state
- the student has shown real cumulative behavior

---

## 6. How To Interpret Referee Verdicts

### `CONTROL_ONLY`

Interpretation:

- only the baseline/control side exists so far
- there is no learning comparison yet

### `ENGAGEMENT_WITHOUT_STORE_WRITES`

Interpretation:

- the student ran
- but nothing durable was stored

Operator takeaway:

- do not claim learning

### `MEMORY_AVAILABLE_NO_MATCH`

Interpretation:

- prior memory existed
- but no eligible records matched the candidate scenario

Operator takeaway:

- memory inventory exists, but recall did not fire here

### `MEMORY_MATCH_NO_IMPACT`

Interpretation:

- retrieval occurred
- but it did not materially change judgment

Operator takeaway:

- memory recall exists
- learning influence is not yet proven

### `BEHAVIOR_CHANGED_NOT_PROVEN_BETTER`

Interpretation:

- the student behaved differently
- but the proof does not show that the change improved the result or process

Operator takeaway:

- change alone is not enough

### `FALSE_LEARNING_CLAIM_REJECTED`

Interpretation:

- something looked like learning
- but attribution, causal validity, or proof integrity failed

Operator takeaway:

- reject the learning claim

### `LEARNED_BEHAVIOR_PROVEN`

Interpretation:

- the student used prior validated experience
- judgment changed for a traceable reason
- and that change was better

Operator takeaway:

- this is a valid learning win

---

## 7. Fast Operator Checklist

When you want a quick read, check in this order:

1. Did the run complete and write artifacts?
2. Did the decision pass or fail the case?
3. Were learning rows written?
4. Did retrieval match any prior records?
5. Did behavior change between control and candidate?
6. Did the referee say that change was proven and better?

If you stop at step 1, you only know the system ran.
If you stop at step 2, you only know whether it judged well.
You need all the way through step 6 to claim learning.

For named test packs, add:

7. Did the top-level `test_framework_summary.json` mark the pack `PASS` or `FAIL`?

---

## 8. What Not To Misread

Do not misread these situations:

- good economics on one run does not automatically mean learning
- retrieval enabled does not automatically mean retrieval mattered
- model-used true does not automatically mean judgment was correct
- behavior changed does not automatically mean behavior improved
- stored rows existing does not automatically mean those rows were later used

This guide is intentionally conservative.

---

## 9. Completion Meaning

When the isolated FinQuant project is working correctly, the operator should be able to read the artifacts and answer all of the following clearly:

- did the student run,
- did the student reason well,
- did the student store learning,
- did the student later retrieve learning,
- did that retrieval change behavior,
- and was the changed behavior actually better.

If the artifacts cannot answer those questions, the system is not finished.
