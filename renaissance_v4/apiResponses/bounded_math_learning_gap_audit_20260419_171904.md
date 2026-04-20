Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/apiResponses/bounded_math_learning_gap_audit_20260419_171904.md`

# Bounded Math Learning Gap Audit

Audit basis:
- Repo HEAD: `5f3f68c1265bec7c1a7df13e580a76b6d0751acb`
- Workspace artifacts inspected:
  - `game_theory/batch_scorecard.jsonl`
  - `game_theory/state/context_signature_memory.jsonl`
- Negative-control searches run:
  - `rg -n "eval\\(|exec\\(|compile\\(" -S game_theory research registry configs`
  - `rg -n "expression(_language)?|formula|grammar|safe interpreter|AST|ast\\.|operator primitives|primitive library" -S game_theory research registry configs`

## 1. Primitive boundary check

Concrete bounded surface that exists:
- `game_theory/memory_bundle.py:23-43` defines `BUNDLE_APPLY_WHITELIST`, a fixed allowlist of replay-tunable keys.
- `game_theory/memory_bundle.py:119-154` validates numeric ranges per allowed key.
- `game_theory/memory_bundle.py:172-222` merges only whitelisted keys into a manifest.
- `game_theory/policy_framework.py:68-108` rejects framework documents whose `tunable_surface.memory_bundle_apply_keys` contain keys outside `BUNDLE_APPLY_WHITELIST`.
- `configs/manifests/baseline_v1_policy_framework.json` declares the current bounded adaptation categories and repeats the same bundle-apply surface.

What this proves:
- There is an explicit bounded adaptation surface.
- That surface is a bounded manifest-parameter surface, not a bounded mathematical primitive library.

Explicit questions:
- Is there an explicit allowlist of math/operator primitives?
  - No artifact found.
  - The audited allowlist is for manifest keys such as `fusion_min_score`, `trend_continuation_min_confidence`, and `atr_stop_mult`, not operator primitives such as `+`, `-`, `*`, `/`, `min`, `max`, or AST node types.
- Is there an expression grammar, schema, or safe interpreter?
  - No artifact found in the audited tree.
  - The negative-control search for `expression`, `formula`, `grammar`, `AST`, and `safe interpreter` returned only an unrelated architecture markdown line in `game_theory/shared_mind_multi_agent_architecture.md:247`.
- Are candidate formulas bounded by depth, size, or operator restrictions?
  - No, because no candidate formula representation exists in the audited path.
  - What is bounded today is candidate count and numeric parameter ranges:
    - `game_theory/context_candidate_search.py:40-41` sets min/max candidate count.
    - `game_theory/context_candidate_search.py:88-107` clamps numeric values.
- Is arbitrary code execution possible anywhere in the candidate path?
  - No direct `eval`, `exec`, or `compile` path was found in `game_theory`, `research`, `registry`, or `configs`.
  - Runtime does use dynamic imports, but through catalog resolution only:
    - `manifest/validate.py:24-155` restricts manifest module ids to catalog membership before replay.
    - `manifest/runtime.py:33-141` resolves ids to catalog-defined imports/callables.
  - In the audited candidate path, candidate objects do not carry import paths or code strings.

Exact missing piece:
- No bounded math expression schema or AST exists between `game_theory/memory_bundle.py` and `game_theory/context_candidate_search.py`.
- The first missing artifact is an expression representation that can be validated before replay.

## 2. Candidate generation check

Concrete generator:
- `game_theory/context_candidate_search.py:143-326` implements `generate_candidates_v1`.

Candidate object structure emitted by code:
- `candidate_id`
- `parent_reference_id`
- `context_family`
- `generation_reason_codes`
- `apply_patches`
- `apply_effective`

What generation actually does:
- `game_theory/context_candidate_search.py:183-260` emits hard-coded deterministic nudges for bounded manifest keys.
- `game_theory/context_candidate_search.py:263-285` optionally blends toward prior bundle values for a few fusion keys.
- `game_theory/context_candidate_search.py:286-326` deduplicates and pads candidates to a bounded count.

What generation does not do:
- It does not emit formula trees.
- It does not emit rule expressions.
- It does not emit operator graphs.
- It does not emit callable bodies.

Runtime proof:
- `game_theory/batch_scorecard.jsonl` row `ea3eccf6eaa640ef96cb24298ca35c7c` records:
  - `candidate_count: 3`
  - `selected_candidate_id: null`
  - `policy_framework_id: "baseline_v1_policy_framework"`
- `game_theory/batch_scorecard.jsonl` row `2d264237f0334b63b2dd795793ca097b` records:
  - `candidate_count: 3`
  - `selected_candidate_id: null`
  - `memory_records_loaded: 1`

Classification:
- `B — parameter-only mutation`

## 3. Evaluation check

Concrete evaluation path:
- `game_theory/operator_test_harness_v1.py:194-213` calls `run_context_candidate_search_v1(...)`.
- `game_theory/context_candidate_search.py:468-668` replays control plus each candidate under identical replay settings.
- `game_theory/context_candidate_search.py:404-452` materializes a temporary manifest and calls `research.replay_runner.run_manifest_replay(...)`.

Exact metrics used for comparison:
- `game_theory/context_candidate_search.py:329-356`
  - `pnl`
  - `trade_count`
  - `max_drawdown`
  - `expectancy`
  - `win_rate`
  - `closes_recorded`
  - `entries_attempted`
  - `signal_scorecards_negative_expectancy_count`
  - `outcome_quality_v1`
- `game_theory/context_candidate_search.py:359-401`
  - ranking tuple = `(expectancy, -max_drawdown, pnl, trade_count)`
  - candidate must strictly beat control

Replay proof artifacts written:
- `game_theory/context_candidate_search.py:642-663` writes `context_candidate_search_proof`.
- `game_theory/operator_test_harness_v1.py:282-331` embeds that proof into `operator_test_harness_v1`.
- `game_theory/learning_run_audit.py:138-169` flattens candidate-search results into `learning_run_audit_v1`.
- `game_theory/batch_scorecard.jsonl` contains the resulting summary fields:
  - `candidate_count`
  - `selected_candidate_id`
  - `winner_vs_control`
  - `decision_windows_total`
  - `bars_processed`

Runtime proof:
- `game_theory/batch_scorecard.jsonl` row `ea3eccf6eaa640ef96cb24298ca35c7c` shows:
  - `learning_status: "learning_active"`
  - `candidate_count: 3`
  - `replay_decision_windows_sum: 11`
  - `bars_processed: 11`

Is this layer already sufficient for bounded math candidates?
- Partially.
- The replay/ranking/proof layer is already concrete and working for candidate objects that can be materialized into replayable manifest inputs.
- The missing upstream artifact is the bounded expression representation and generator.

## 4. Persistence check

Executable memory that exists:
- `game_theory/groundhog_memory.py:34-36` defines the canonical executable bundle path:
  - `game_theory/state/groundhog_memory_bundle.json`
- `game_theory/groundhog_memory.py:44-63` resolves that bundle for later runs.
- `game_theory/groundhog_memory.py:65-86` writes the bundle.
- `game_theory/memory_bundle.py:172-222` merges that bundle into the manifest before replay.
- `game_theory/web_app.py:505-522` exposes manual promotion through `POST /api/groundhog-memory`.

Discovery memory that exists:
- `game_theory/context_signature_memory.py:22` defines:
  - `game_theory/state/context_signature_memory.jsonl`
- `game_theory/context_signature_memory.py:210-276` appends structured JSONL records.
- Stored fields include:
  - `record_id`
  - `timestamp_utc`
  - `source_run_id`
  - `source_artifact_paths`
  - `context_signature`
  - `signature_key`
  - `bundle_apply_keys`
  - `effective_apply`
  - `outcome_summary`
  - `optimizer_reason_codes`

Automatic write path that exists:
- `game_theory/context_memory_operator.py:29-145`
- It writes contextual JSONL memory only when all of these are true:
  - mode is `read_write`
  - run classification is `learning_engaged`
  - `selected_candidate_id` is truthy
  - `winner_metrics` is a dict

What does not exist:
- No automatic winner-to-Groundhog promotion path.
- `game_theory/operator_test_harness_v1.py:61-87` builds `groundhog_commit_recommendation_v1` and explicitly labels it “Recommendation only”.
- `rg -n "write_groundhog_bundle\\(" -S game_theory research` returned only:
  - `game_theory/groundhog_memory.py:65`
  - `game_theory/web_app.py:516`

Difference between discovery memory and executable memory:
- Discovery memory:
  - `game_theory/state/context_signature_memory.jsonl`
  - read by Decision Context Recall
  - affects bounded bias during replay
  - not merged as a manifest bundle
- Executable memory:
  - explicit bundle path or canonical Groundhog bundle
  - merged into manifest before replay
  - directly changes replay configuration

Runtime artifacts:
- `game_theory/state/context_signature_memory.jsonl` exists and currently contains one seeded record.
- `game_theory/state/groundhog_memory_bundle.json` is missing from `game_theory/state` in the current workspace listing.

Answer:
- Where are winners written?
  - Contextual winners can be written to `game_theory/state/context_signature_memory.jsonl`.
  - Executable winners can be written only by explicit Groundhog promotion.
- Are they written only to audit/history artifacts?
  - Automatic winner persistence today is to contextual JSONL, not to executable Groundhog memory.
- Is there an executable memory artifact for promoted winners?
  - Yes, `groundhog_memory_bundle.json`, but manual only.
- Is promotion automatic, manual, or absent?
  - Manual for executable memory.

First broken breadcrumb for winner persistence:
- `game_theory/operator_test_harness_v1.py:61-87` and `game_theory/web_app.py:505-522`
- Winner selection stops at a recommendation block; only the manual API writes the executable bundle.

Missing runtime artifact:
- No organically selected winner artifact with `selected_candidate_id != null` exists in the currently inspected batch rows.
- Because of that, automatic contextual write of a real winner is not proven by a non-seeded runtime artifact in this workspace.

## 5. Contextual reuse check

Concrete load path:
- `game_theory/parallel_runner.py:156-181`
  - operator-harness scenarios pass `context_signature_memory_mode` and `context_signature_memory_path`
- `game_theory/operator_test_harness_v1.py:171-178`
  - derives `mem_store_path`
- `game_theory/operator_test_harness_v1.py:194-213`
  - passes `decision_context_recall_memory_path=mem_store_path`
- `research/replay_runner.py:303-306`
  - calls `read_context_memory_records(decision_context_recall_memory_path)`

Concrete context gates:
- `game_theory/context_signature_memory.py:102-136`
  - exact match required on:
    - `dominant_regime`
    - `dominant_volatility_bucket`
  - bounded tolerances required on:
    - structure shares
    - conflict share
    - directional shares

Concrete use path:
- `research/replay_runner.py:319-323`
  - finds matching records per decision window
- `game_theory/decision_context_recall.py:132-209`
  - can bias fusion thresholds from matching memory
- `game_theory/decision_context_recall.py:216-370`
  - can bias signal-module contribution multipliers and suppress modules
- `research/replay_runner.py:380-386`
  - passes the adjusted thresholds/multipliers into `fuse_signal_results(...)`

What loaded memory affects:
- Candidate generation:
  - No direct use found in `generate_candidates_v1(...)` unless a caller supplies `memory_prior_apply`.
  - In the operator-harness replay path audited here, the concrete automatic reuse is Decision Context Recall, not candidate-generation seeding.
- Ranking:
  - No direct ranking override found.
- Manifest merge:
  - Only explicit bundle path or Groundhog merge affects manifest pre-replay.
- Replay configuration:
  - Yes, via bounded fusion thresholds and signal multipliers inside replay.
- Execution behavior:
  - Yes, because replay fusion outputs feed later risk/execution decisions.

Runtime proof that context-aware reuse exists:
- `game_theory/state/context_signature_memory.jsonl` contains one record:
  - `record_id: "audit_ctxsig_20260419_1"`
  - `effective_apply: {"fusion_min_score": 0.34}`
  - `source_run_id: "adversarial_audit_seed"`
- `game_theory/batch_scorecard.jsonl` row `ea3eccf6eaa640ef96cb24298ca35c7c` shows no loaded contextual memory:
  - `memory_records_loaded: 0`
  - `recall_matches: 0`
  - `recall_bias_applied: 0`
- `game_theory/batch_scorecard.jsonl` row `2d264237f0334b63b2dd795793ca097b` shows loaded contextual memory and conditional reuse:
  - `memory_records_loaded: 1`
  - `recall_matches: 11`
  - `recall_bias_applied: 11`

Answer:
- Is prior winner memory loaded on later runs?
  - Context-signature memory is loaded on later operator-harness runs.
  - Automatic loading of executable Groundhog memory is not proven in current runtime artifacts because no Groundhog bundle file exists.
- What context fields are checked before reuse?
  - `dominant_regime`
  - `dominant_volatility_bucket`
  - bounded share tolerances
- Is there any evidence of context-aware conditional reuse?
  - Yes, the `2d264...` batch row proves context-signature reuse with matches and applied bias.

First broken breadcrumb if reuse is scoped to the target design:
- Automatic reuse exists for contextual replay bias.
- Automatic winner-to-executable reuse does not exist because no winner promotion bridge writes Groundhog memory from harness output.

## 6. Distance-from-target matrix

Capability status:
1. Bounded primitive library: `PARTIAL`
2. Safe expression generation: `ABSENT`
3. Candidate evaluation against control: `PRESENT`
4. Validated promotion into executable memory: `PARTIAL`
5. Context-aware reuse on future runs: `PARTIAL`

Gap map:

1. Gap:
   - No bounded expression schema / AST / operator set exists.
   - Current bounded surface is only a parameter-key allowlist.
   - File/function where it should connect:
     - `game_theory/context_candidate_search.py:143-326`
     - `game_theory/memory_bundle.py:23-43`
   - Implementation difficulty: `HIGH`
   - Dependency order: `1`

2. Gap:
   - No safe expression generator exists.
   - Current candidate generation emits only `apply_effective` dictionaries.
   - File/function where it should connect:
     - `game_theory/context_candidate_search.py:143-326`
   - Implementation difficulty: `HIGH`
   - Dependency order: `2`

3. Gap:
   - Replay evaluation is present, but there is no expression-to-replay materialization path.
   - File/function where it should connect:
     - `game_theory/context_candidate_search.py:_replay_with_apply_dict`
     - `research/replay_runner.py:130-816`
   - Implementation difficulty: `MEDIUM`
   - Dependency order: `3`

4. Gap:
   - Automatic promotion from validated winner to executable bundle is missing.
   - File/function where it should connect:
     - `game_theory/operator_test_harness_v1.py:61-87`
     - `game_theory/groundhog_memory.py:65-86`
   - Implementation difficulty: `MEDIUM`
   - Dependency order: `4`

5. Gap:
   - Automatic future-run reuse of promoted winners under matching context is incomplete for executable memory.
   - Current automatic reuse exists only for contextual replay bias.
   - File/function where it should connect:
     - `game_theory/context_memory_operator.py:29-145`
     - `game_theory/groundhog_memory.py:44-63`
     - `game_theory/parallel_runner.py:156-181`
   - Implementation difficulty: `MEDIUM`
   - Dependency order: `5`

## 7. First broken breadcrumb

First broken breadcrumb:
- `game_theory/context_candidate_search.py:143-326`
- `generate_candidates_v1(...)` emits bounded manifest-parameter patches only.
- No expression candidate object, no grammar, and no AST validator exist before this step.

Reason this is first:
- The target design starts with bounded mathematical primitives and bounded expression generation.
- The audited system’s first concrete learning object is a bundle-apply dict, not an expression.

## 8. Closest current classification (A-E)

`B — foundation exists but expression learning does not`

Reason:
- Present:
  - bounded parameter surface
  - replay evaluation
  - control-vs-candidate comparison
  - contextual replay reuse
- Missing:
  - bounded expression language
  - expression generator
  - automatic winner-to-executable promotion bridge

## 9. Recommended build order

1. Define a bounded expression schema with an explicit operator/node allowlist and size/depth limits.
2. Add schema validation and fail-closed parsing before any replay call.
3. Extend `generate_candidates_v1(...)` to emit expression candidates instead of only scalar patch dicts.
4. Add a deterministic materialization step that turns a validated expression candidate into replayable manifest/runtime inputs.
5. Reuse the existing replay/evaluation/ranking proof path for those candidates.
6. Add a validated promotion bridge from selected winner to executable memory.
7. Gate later reuse of promoted winners by the existing context-signature match rules or an equivalent explicit context contract.

## 10. Final one-sentence truth

The system is currently at stage B because it can do bounded parameter search plus replay-based evaluation and context-conditioned recall, but it cannot yet do bounded mathematical expression learning due to the missing link in `game_theory/context_candidate_search.py:generate_candidates_v1`.

Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/apiResponses/bounded_math_learning_gap_audit_20260419_171904.md`
