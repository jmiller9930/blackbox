# Memory Chain Verification And Adversarial Audit

Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/memory_chain_verification_and_adversarial_audit_20260419_165324.md`

## 1. Engineering claim under test

Claim under test:

> A winner is persisted in audit artifacts, but it is not automatically promoted into executable next-run memory. The next run only changes if there is explicit bundle promotion or an explicit memory_bundle_path.

Verified facts and unproven claims are separated below.

## 2. Phase 1 verification results

### 2.1 Verify WRITE path

Verified code evidence:

- `game_theory/operator_test_harness_v1.py`
  - `build_groundhog_commit_block_v1(...)`
  - Docstring: `Recommendation only — does not write groundhog_memory_bundle.json.`
  - Fields built for audit:
    - `groundhog_commit_candidate`
    - `groundhog_commit_apply`
    - `groundhog_commit_reason_codes`
    - `no_commit_reason`
- `game_theory/operator_test_harness_v1.py`
  - `run_operator_test_harness_v1(...)`
  - Persists the recommendation inside `operator_test_harness_v1.groundhog_commit_recommendation_v1`
- `game_theory/parallel_runner.py`
  - `run_scenarios_parallel(...)`
  - Builds `run_memory` records with `build_run_memory_record(...)`
  - Writes per-scenario session log folders with `run_record.json`
- `game_theory/run_memory.py`
  - `build_run_memory_record(...)`
  - Audit/history fields written:
    - `run_id`
    - `utc`
    - `manifest_path`
    - `hypothesis`
    - `indicator_context`
    - `prior_run_id`
    - `referee`
    - `outcome_measures`
    - `decision_audit`
    - `learning_memory_evidence`
    - `learning_run_audit_v1`
  - `decision_audit.human_readable_summary` explicitly states:
    - `run_memory JSONL / prior session folders are not auto-read to alter execution.`
- `game_theory/groundhog_memory.py`
  - `write_groundhog_bundle(...)`
  - Executable memory artifact path:
    - `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/groundhog_memory_bundle.json`
  - Executable fields written:
    - `schema`
    - `from_run_id`
    - `note`
    - `apply.atr_stop_mult`
    - `apply.atr_target_mult`
- `game_theory/web_app.py`
  - `api_groundhog_memory_post()`
  - Only served-host write path found for the canonical Groundhog bundle

Verified served-host runtime evidence:

- Run A start request:
  ```http
  POST /api/run-parallel/start
  Content-Type: application/json

  {"operator_recipe_id":"pattern_learning","evaluation_window_mode":"12","evaluation_window_custom_months":null,"max_workers":1,"log_path":false}
  ```
- Run A start response:
  ```json
  {"job_id":"ea3eccf6eaa640ef96cb24298ca35c7c","ok":true,"total":1,"workers_used":1}
  ```
- Run A completed artifact:
  - Session log dir:
    - `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/logs/batch_20260419T214859Z_a4a0c98e`
  - `run_record.json`:
    - `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/logs/batch_20260419T214859Z_a4a0c98e/tier1_twelve_month_default/run_record.json`
  - `run_id`:
    - `10f8502e-1b0e-4e59-b449-e86f56d26cb5`
- Groundhog bundle state after Run A:
  ```json
  {"bundle":null,"env_enabled":false,"exists":false,"ok":true,"path":"/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/groundhog_memory_bundle.json"}
  ```
- Filesystem state after Run A:
  ```text
  $ ls -l game_theory/state
  total 0
  ```
- `run_memory.jsonl` line count after Run A and Run B:
  ```text
  $ wc -l game_theory/run_memory.jsonl
         3 game_theory/run_memory.jsonl
  ```

Verification result for WRITE path:

- `winner is persisted in audit artifacts`
  - **PARTIALLY VERIFIED**
  - Verified:
    - winner-selection fields and Groundhog recommendation fields are wired into audit objects and session-log artifacts
  - Missing runtime artifact:
    - no served-host run in this audit produced a non-null `selected_candidate_id`
- `winner is automatically promoted into executable next-run memory`
  - **NOT VERIFIED**
  - Concrete evidence shows the opposite on the run path:
    - no call from `api_parallel_start.run_job` to `write_groundhog_bundle(...)`
    - no append to `run_memory.jsonl` from the served-host batch path

### 2.2 Verify LOAD path

Verified code evidence:

- `game_theory/groundhog_memory.py`
  - `resolve_memory_bundle_for_scenario(...)`
  - Load trigger order:
    1. explicit `memory_bundle_path`
    2. else canonical `groundhog_memory_bundle.json` only when `PATTERN_GAME_GROUNDHOG_BUNDLE=1`
- `game_theory/parallel_runner.py`
  - `_worker_run_one(...)`
  - Reads `scenario["memory_bundle_path"]` or calls `resolve_memory_bundle_for_scenario(...)`
- `game_theory/pattern_game.py`
  - `prepare_effective_manifest_for_replay(...)`
  - Calls `apply_memory_bundle_to_manifest(...)`
  - Populates:
    - `memory_bundle_audit`
    - `mb_path_for_proof`
    - effective manifest ATR values

Verified served-host runtime evidence, Run B without manual promotion:

- Run B start response:
  ```json
  {"job_id":"646d3648764c407695211fa117212300","ok":true,"total":1,"workers_used":1}
  ```
- Run B completed artifact:
  - `run_id`:
    - `ae9da2af-1b5e-4491-b08a-d7651c717c8f`
  - `decision_audit.prior_outcomes_or_parameters_loaded_into_replay_engine=false`
  - `decision_audit.memory_bundle=null`
  - `learning_run_audit_v1.memory_bundle_loaded=false`
  - `learning_run_audit_v1.memory_bundle_applied=false`
  - `learning_run_audit_v1.memory_records_loaded_count=0`
  - `learning_run_audit_v1.memory_used_v1=false`
  - `learning_memory_evidence.learned_from.bundle_path=null`
  - `learning_memory_evidence.groundhog_mode=inactive`
- Groundhog endpoint before Run B:
  ```json
  {"bundle":null,"env_enabled":false,"exists":false,"ok":true,"path":"/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/groundhog_memory_bundle.json"}
  ```

Verified explicit-load runtime evidence, explicit `memory_bundle_path`:

- Request:
  ```http
  POST /api/run
  Content-Type: application/json

  {
    "manifest_path":"/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json",
    "memory_bundle_path":"/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/examples/memory_bundle_example.json"
  }
  ```
- Response excerpts:
  - `memory_bundle_audit.bundle_path=/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/examples/memory_bundle_example.json`
  - `memory_bundle_audit.keys_applied=["atr_stop_mult","atr_target_mult"]`
  - `memory_bundle_proof.memory_bundle_loaded=true`
  - `memory_bundle_proof.memory_bundle_applied=true`
  - `memory_bundle_proof.manifest_atr_on_disk={"atr_stop_mult":null,"atr_target_mult":null}`
  - `memory_bundle_proof.manifest_atr_after_bundle_merge={"atr_stop_mult":1.78,"atr_target_mult":3.35}`
  - `learning_run_audit_v1.memory_bundle_loaded=true`
  - `learning_run_audit_v1.memory_bundle_applied=true`
  - `learning_run_audit_v1.memory_bundle_path_resolved=/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/examples/memory_bundle_example.json`
  - `learning_run_audit_v1.memory_used_v1=true`

Verification result for LOAD path:

- `load is automatic`
  - **PARTIALLY VERIFIED**
  - Verified automatic only for:
    - canonical Groundhog bundle when env is enabled and file exists
  - Verified explicit only for:
    - `memory_bundle_path`
  - Unproven runtime artifact:
    - canonical Groundhog auto-load after `POST /api/groundhog-memory` was not runtime-tested in this audit because served host had `env_enabled=false`

### 2.3 Verify USE path

Verified code evidence:

- `game_theory/memory_bundle.py`
  - `apply_memory_bundle_to_manifest(...)`
  - Merges whitelisted keys into manifest before replay
- `game_theory/pattern_game.py`
  - `prepare_effective_manifest_for_replay(...)`
  - bundle merge happens before validation and replay
- `research/replay_runner.py`
  - `run_manifest_replay(...)`
  - execution managers, fusion, regime, and signals are built from the effective manifest

Verified effect categories:

- candidate generation
  - explicit memory bundle: **No direct effect found**
  - verified code path only merges manifest keys before replay, not candidate enumeration
- ranking
  - explicit memory bundle: **Indirectly yes, by altering replay inputs/metrics if candidate search is run**
  - no direct ranking function reads audit artifacts
- manifest merge
  - **VERIFIED**
  - `apply_memory_bundle_to_manifest(...)`
- replay configuration
  - **VERIFIED**
  - `manifest_atr_after_bundle_merge` and `manifest_atr_effective` change
- execution behavior
  - **VERIFIED**
  - `memory_bundle_proof.execution_pipeline_note` states replay builds execution components from effective manifest
  - explicit bundle proof showed ATR values changed before replay

Verification result for USE path:

- `loaded memory changes replay configuration / execution`
  - **VERIFIED**
- `audit/history artifacts are auto-read back into replay`
  - `run_memory.jsonl`: **VERIFIED FALSE**
  - `run_record.json`: **VERIFIED FALSE**
  - `batch_scorecard.jsonl`: **VERIFIED FALSE**

### 2.4 Verification summary by engineering claim

1. `A winner is persisted in audit artifacts`
   - **PARTIALLY VERIFIED**
   - Code and artifact schema support it.
   - Missing runtime artifact: no non-null winner captured in this audit.

2. `It is not automatically promoted into executable next-run memory`
   - **VERIFIED** for the winner-to-Groundhog path.
   - No automatic promotion call was found from winner selection into bundle write or other executable memory writers.

3. `The next run only changes if there is explicit bundle promotion or an explicit memory_bundle_path`
   - **NOT VERIFIED**
   - Adversarial phase below found another executable memory lane.

## 3. Phase 2 adversarial findings

### 3.1 Is there any hidden or indirect automatic promotion path?

Verified findings:

- No direct winner-selection bridge to `write_groundhog_bundle(...)` found.
- No call to `append_context_memory_record(...)` from normal run paths.
- `rg -n "append_context_memory_record\\(" -S .` returned only:
  - `./game_theory/context_signature_memory.py:209:def append_context_memory_record(`

Adversarial conclusion:

- No hidden automatic promotion from `selected_candidate_id` to executable bundle was found.

### 3.2 Is any audit artifact read back into executable replay inputs?

Verified false:

- `run_memory.jsonl`
  - no reader on replay path found
  - `run_memory.py` explicitly states it is not auto-read to alter execution
- session `run_record.json`
  - used by drill/export tooling only
- `batch_scorecard.jsonl`
  - used by scorecard/drill/UI history only

Verified true for a different executable memory store:

- `research/replay_runner.py`
  - inside `run_manifest_replay(...)`
  - when `decision_context_recall_enabled and recall_fusion_ok`:
    - `memory_records_cache = read_context_memory_records(decision_context_recall_memory_path)`
- `game_theory/operator_test_harness_v1.py`
  - `run_operator_test_harness_v1(...)`
  - defaults:
    - `decision_context_recall_enabled=True`
    - `decision_context_recall_apply_bias=True`
- `game_theory/context_signature_memory.py`
  - default file:
    - `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/context_signature_memory.jsonl`

Adversarial runtime proof:

- Before seeding:
  ```text
  $ ls -l game_theory/state
  total 0
  $ context_signature_memory.jsonl missing
  ```
- Seeded adversarial record written to:
  - `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/context_signature_memory.jsonl`
- Seeded record facts:
  - `record_id=audit_ctxsig_20260419_1`
  - `effective_apply={"fusion_min_score":0.34}`
  - `outcome_summary={"expectancy":1.0,"max_drawdown":-1.0,"win_rate":1.0,"total_trades":10,"cumulative_pnl":10.0}`
  - `signature_key=c134c4d635bb0d0930515fb16198838c7313bc6c9036defb9976502a6cfed396`

### 3.3 Is there any post-run hook, scheduler, startup hook, or worker callback that engineering missed?

Verified findings:

- `game_theory/web_app.py` `api_parallel_start.run_job`
  - records scorecard
  - does not call `write_groundhog_bundle(...)`
  - does not call `append_context_memory_record(...)`
- `parallel_runner.py`
  - progress callback only reports completion status
  - no persistence bridge from winner selection
- `pattern_game_operator_reset.py`
  - explicit destructive reset only
  - no startup/post-run promotion
- `module_board.py`
  - status-only checks

Adversarial conclusion:

- No missed post-run hook or scheduler was found for winner auto-promotion.

### 3.4 Is there any silent bridge between winner selection and bundle creation?

Verified finding:

- No.
- `groundhog_commit_recommendation_v1` is audit output only.
- The only served-host writer for the canonical Groundhog bundle is `POST /api/groundhog-memory`.

### 3.5 If engineering is incomplete, what exact nuance is missing?

Verified missing nuance:

- There is a second executable memory lane unrelated to Groundhog bundles:
  - Decision Context Recall reads `context_signature_memory.jsonl` automatically during operator-harness replays.
- This lane is not populated by the normal winner path.
- But once populated, a later run can change automatically without `memory_bundle_path` and without Groundhog promotion.

### 3.6 If engineering is wrong, where exactly is it wrong?

Engineering is wrong in the absolute clause:

> The next run only changes if there is explicit bundle promotion or an explicit memory_bundle_path.

Concrete contradiction:

- After seeding canonical `context_signature_memory.jsonl`, a later operator-harness run changed automatically with:
  - `memory_records_loaded=1`
  - `recall_matches=11`
  - `recall_bias_applied=11`
  - no `memory_bundle_path`
  - Groundhog still inactive

Served-host adversarial run:

- Start:
  ```json
  {"job_id":"2d264237f0334b63b2dd795793ca097b","ok":true,"total":1,"workers_used":1}
  ```
- Completion excerpts:
  - `learning_audit_v1.memory_records_loaded=1`
  - `learning_audit_v1.recall_stats.matches=11`
  - `learning_audit_v1.recall_stats.bias_applied=11`
  - `learning_run_audit_v1.learning_mechanisms_observed_v1=["recall_match","recall_fusion_bias","context_candidate_search"]`
  - `learning_run_audit_v1.memory_bundle_applied=false`
  - `learning_run_audit_v1.memory_bundle_loaded=false`
  - `learning_run_audit_v1.memory_used_v1=false`
  - drill-down proof:
    - `decision_context_recall_bias_diff`
    - `old=0.35`
    - `new=0.34`
    - `from_record_id="audit_ctxsig_20260419_1"`

This is an automatic executable change on the next run without bundle promotion and without `memory_bundle_path`.

## 4. First broken breadcrumb in the automatic learning chain

For the winner-to-next-run automatic promotion chain, the first broken breadcrumb is:

- File:
  - `game_theory/web_app.py`
- Function:
  - `api_parallel_start` inner `run_job`
- Exact break:
  - batch results are collected
  - no call is made to:
    - `write_groundhog_bundle(...)`
    - `append_context_memory_record(...)`
  - winner selection remains audit-only

## 5. Final verdict

**B — engineering is mostly correct but incomplete**

Why:

- Correct:
  - winner selection is not automatically promoted into Groundhog executable memory
  - normal served-host run path does not auto-write Groundhog bundle or `run_memory.jsonl`
- Incomplete:
  - another executable memory lane exists
  - operator-harness runs auto-read canonical `context_signature_memory.jsonl`
  - once that store exists, later runs can change automatically without bundle promotion or `memory_bundle_path`

## 6. Exact gap or fault

- Missing bridge for winner auto-promotion:
  - file:
    - `game_theory/web_app.py`
  - function:
    - `api_parallel_start` inner `run_job`
  - gap:
    - no winner recommendation is promoted into executable memory

- Contradiction omitted by engineering:
  - file:
    - `research/replay_runner.py`
  - function:
    - `run_manifest_replay`
  - omitted bridge:
    - automatic read of canonical `context_signature_memory.jsonl` when decision-context recall is enabled

## 7. Concrete fix recommendation

If engineering wants the claim to be strictly true in product behavior:

- file:
  - `game_theory/operator_test_harness_v1.py`
- function:
  - `run_operator_test_harness_v1`
- recommendation:
  - change `decision_context_recall_enabled` default from `True` to `False`
  - require explicit operator opt-in before replay auto-reads `context_signature_memory.jsonl`

If engineering wants to keep current behavior:

- update the claim and operator copy to say:
  - winner memory is not auto-promoted
  - Groundhog bundle still requires explicit promotion
  - but operator-harness replays may auto-read context-signature memory if that canonical store exists

## 8. Final one-sentence truth

Engineering is not fully correct because winner selection in `game_theory/web_app.py` does not connect to executable memory, but `research/replay_runner.py` does automatically connect canonical `context_signature_memory.jsonl` to later operator-harness replay behavior.

## Unproven claims / missing artifacts

- No served-host run in this audit produced a non-null `selected_candidate_id`
- Canonical Groundhog auto-load after `POST /api/groundhog-memory` was not runtime-tested because the served host reported `env_enabled=false`

Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/memory_chain_verification_and_adversarial_audit_20260419_165324.md`
