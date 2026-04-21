# D14-5 — Structured reasoning implementation plan (no fake reasoning)

This plan maps each `structured_reasoning_v1` field to a **source path**, classifies **exportable now** vs **generatable now** (deterministic from existing artifacts) vs **requires new instrumentation**, and matches Directive D14.GC.5.

## Fields (target schema)

| Field | Intended meaning |
|-------|------------------|
| `context_factors_considered` | What the fusion / regime / recall layers surfaced as inputs to the decision |
| `pattern_candidates` | Pattern IDs or labels evaluated before selection |
| `pattern_selected` | Winning pattern / template id for this decision |
| `groundhog_influence` | How Groundhog bundle or retrieval biased thresholds or signal weights for *this trade* |
| `decision_basis_summary` | Short narrative aligned to logged fusion/risk rationale |
| `baseline_difference_summary` | Student vs baseline policy delta at decision time (not aggregate win%) |

## Field-by-field classification

### `context_factors_considered`

| | |
|-|-|
| **Source path** | Fusion audit (`fuse_signal_results` output), regime classifier labels, decision-window snapshot in `run_memory` / `student_decision_audit` traces, Decision Context Recall match metadata when enabled |
| **Exportable now** | **Partial** — pieces exist in run_memory JSONL and scenario `run_record` shards, but there is **no single joined “factors list” export** per trade |
| **Generatable now** | **No** (without inventing) — would need a deterministic reducer over existing audit dicts per `graded_unit_id` |
| **Requires instrumentation** | **Yes** — emit a explicit `context_factors_v1` list at fusion boundary keyed by decision id / `graded_unit_id` |

### `pattern_candidates`

| | |
|-|-|
| **Source path** | Candidate stack in replay (`candidate_search` / pattern evaluation counters in learning audit), pattern module pass/fail rows if exported |
| **Exportable now** | **No** — per-candidate lists are not present in `OutcomeRecord` or Student store line consistently |
| **Generatable now** | **Partial** — only where `run_record` / drill buffers expose last-N candidates (manifest-dependent) |
| **Requires instrumentation** | **Yes** — persist “considered pattern ids” on the decision row at evaluation time |

### `pattern_selected`

| | |
|-|-|
| **Source path** | Execution / signal path selected pattern id in manifest replay; pattern_game_meta in batch summaries |
| **Exportable now** | **Partial** — scenario-level hints exist; **per-trade** selection often inside execution manager state not serialized to `OutcomeRecord` |
| **Generatable now** | **No** without guessing |
| **Requires instrumentation** | **Yes** — write `pattern_selected_id` into outcome metadata or parallel result row at trade close |

### `groundhog_influence`

| | |
|-|-|
| **Source path** | Groundhog bundle merge audit, `context_signature_v1` on `student_learning_record_v1`, recall bias counters on scorecard / batch |
| **Exportable now** | **Partial** — Student store + bundle audit give **scenario/run** influence; **per-trade multi-trade** Groundhog attribution remains `data_gap` until exporter names which window used Groundhog (per architecture spec §7) |
| **Generatable now** | Scenario-level summaries only; **not** a substitute for per-trade attribution in multi-trade rows |
| **Requires instrumentation** | **Yes** for strict per-trade narrative — tie retrieval/bundle keys to `trade_id` at decision open |

### `decision_basis_summary`

| | |
|-|-|
| **Source path** | Fusion “reason” strings, risk governor denial/allow reasons, optional LLM operator narrative (`agent_explanation` is not Referee truth) |
| **Exportable now** | **No** as a single vetted field — scattered strings exist; no canonical summary field |
| **Generatable now** | **Risky** — string concatenation would **infer** from partial logs → conflicts with “no guessing” |
| **Requires instrumentation** | **Yes** — append one structured `decision_basis_v1` at the single choke-point where fusion + risk agree |

### `baseline_difference_summary`

| | |
|-|-|
| **Source path** | Baseline policy shadow run vs main lane deltas (where implemented), `decision_changed` when baseline stack is run |
| **Exportable now** | **No** — `student_decision_record_v1` marks baseline fields `data_gap` until baseline-vs-student same-window export exists |
| **Generatable now** | **No** |
| **Requires instrumentation** | **Yes** — dual-run baseline lane must emit comparable feature snapshots per decision |

## What can ship immediately vs pipeline

| Horizon | Work |
|---------|------|
| **Immediate (code-only)** | Keep all six fields as literal `data_gap` in `build_student_decision_record_v1` until exports land; extend UI to show the gap list (done in D14). |
| **Short (1–2 instruments)** | Log `pattern_selected_id` + `fusion_factor_ids` on trade open/close in replay, then re-run batch → new exporter reads JSON only. |
| **Medium** | Baseline shadow lane + diff blob per `graded_unit_id`; Groundhog-to-trade linkage table for multi-trade batches. |

## Explicit note

**Do not** fill these fields by templating aggregate scorecard metrics or inferring from win rate — that would violate GC.4 honesty rules.
