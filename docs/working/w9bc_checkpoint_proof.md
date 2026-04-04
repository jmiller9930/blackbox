# W9b / W9c checkpoint — proof package (Agentic Training Advisor)

**Date:** 2026-04  
**Status:** Lesson memory **wired** into `build_analysis`; **validated-only** injection; **bounded** (top-K, min score from `lesson_memory` module).

**Living status / roundtable:** For the **current** one-page summary of lesson memory + control-plane work (updated as milestones land), see **§4.1** in [`docs/architect/training_conference_roundtable.md`](../architect/training_conference_roundtable.md).

---

## 1. Input scenario (example)

- **User text:** `SOL 5m — should match lesson symbol and nominal regime`  
- **Market tick:** `gate_state: ok` → regime inferred **`nominal`** (see `infer_regime_from_phase5_market`).  
- **Seeded lesson:** `validated`, `symbol=SOL`, `regime_tag=nominal`, `timeframe=5m`, lesson text contains `W9 proof lesson: ...`

---

## 2. Retrieved lesson memory rows

Returned in `anna_analysis_v1` at **`lesson_memory.injected`** (ids, scores, preview, `validation_status`).

---

## 3. Final lesson memory FACT lines

`anna_analysis_v1.lesson_memory.facts` — e.g.  
`FACT (lesson memory): [xxxxxxxx] (score=N) W9 proof lesson: ...`

---

## 4. Prompt / context snapshot

- **Merged authoritative facts** for the LLM come from `merged_rule_facts` → `resolve_answer_layers` → `build_anna_llm_prompt` (`authoritative_facts`).  
- **Debug:** set **`ANNA_LESSON_MEMORY_DEBUG=1`** — `lesson_memory.authoritative_facts_all` lists **all** FACT lines passed to the prompt layer (includes math, carryforward, strategy, **and** lesson lines when enabled).

---

## 5. Resulting `anna_analysis_v1` output

Full JSON includes **`lesson_memory`** and **`pipeline.lesson_memory`** (same payload).  
**Interpretation** (`interpretation.summary`) when **`ANNA_USE_LLM=1`** differs materially because lesson lines are inside **AUTHORITATIVE FACTS** in the prompt. With **`ANNA_USE_LLM=0`**, structural proof is **FACT injection** + pipeline fields; summary may still follow playbook/template rules.

---

## 6. Side-by-side: memory on vs off

| Mode | Env | `lesson_memory.facts` |
|------|-----|------------------------|
| **On** | `ANNA_LESSON_MEMORY_ENABLED=1` | Non-empty when lesson scores ≥ threshold |
| **Off** | `ANNA_LESSON_MEMORY_ENABLED=0` | Empty (no injection) |

**Automated proof:** `tests/test_anna_lesson_memory_e2e.py` — `test_side_by_side_fact_count_differs`.

---

## 7. Behavioral impact (Advisor acceptance — outcomes, not wording-only)

**Standard:** Same input evaluated with memory enabled vs disabled must show a **decision-relevant** delta (not only phrasing).

**Mechanism (deterministic, validated-only):** A validated/promoted lesson may set  
`context_tags` JSON object field **`behavior_effect": "tighten_suggested_action"`** (see `policy.LESSON_BEHAVIOR_TIGHTEN_SUGGESTED`).  
When that lesson is **injected** and baseline `suggested_action.intent` would be **`PAPER_TRADE_READY`**, the pipeline sets intent to **`WATCH`** and records **`lesson_memory.behavior_applied`**.

**Observed downstream signal:** Under `policy.mode=NORMAL` and low risk, `classify_proposal_type` moves from **`NO_CHANGE`** (paper-ready path) to **`OBSERVATION_ONLY`** when intent is tightened — same input, memory off vs on.

**Automated proof:** `tests/test_anna_lesson_memory_behavior.py` — `test_same_input_memory_off_paper_ready_no_change_proposal` vs `test_same_input_memory_on_tightens_intent_and_proposal_type`; candidate rows with `behavior_effect` do **not** apply (`test_behavior_effect_requires_validated_injection`).

---

## 8. Re-run verification

```bash
cd /path/to/blackbox
PYTHONPATH=scripts/runtime:. python3 -m pytest tests/test_anna_lesson_memory.py tests/test_anna_lesson_memory_e2e.py tests/test_anna_lesson_memory_behavior.py -v
```

---

- **`candidate`** never injected (retrieval only sees `validated` / `promoted`).  
- No full ledger injection.  
- **Top-K** / **min score** in `lesson_memory.py` envs.  
- **Behavior** merge applies only to **injected** validated/promoted rows; bounded to the same retrieval gates as FACT injection.
