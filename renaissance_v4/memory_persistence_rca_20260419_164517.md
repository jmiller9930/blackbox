# Memory Persistence RCA

Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/memory_persistence_rca_20260419_164517.md`

## 1. Write path proof

Code evidence:

- `game_theory/operator_test_harness_v1.py`, `build_groundhog_commit_block_v1(...)`:
  - Docstring: `Recommendation only — does not write groundhog_memory_bundle.json.`
- `game_theory/groundhog_memory.py`, `write_groundhog_bundle(...)`:
  - Writes canonical artifact `game_theory/state/groundhog_memory_bundle.json`
  - Stored fields:
    - `schema`
    - `from_run_id`
    - `note`
    - `apply.atr_stop_mult`
    - `apply.atr_target_mult`
- `game_theory/web_app.py`, `/api/groundhog-memory` POST:
  - Calls `write_groundhog_bundle(...)`
  - This is the only served-host write path found for the canonical winner bundle
- `game_theory/web_app.py`, `api_parallel_start` inner `run_job`:
  - Calls `run_scenarios_parallel(...)` without `run_memory_log_path`
  - Served-host run path does not append `game_theory/run_memory.jsonl`

Served-host runtime evidence, Run A:

- Start request:
  ```http
  POST /api/run-parallel/start
  Content-Type: application/json

  {"operator_recipe_id":"pattern_learning","evaluation_window_mode":"12","evaluation_window_custom_months":null,"max_workers":1,"log_path":false}
  ```
- Response:
  ```json
  {"job_id":"ea3eccf6eaa640ef96cb24298ca35c7c","ok":true,"total":1,"workers_used":1}
  ```
- Completed run artifact:
  - Session log directory: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/logs/batch_20260419T214859Z_a4a0c98e`
  - Run record: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/logs/batch_20260419T214859Z_a4a0c98e/tier1_twelve_month_default/run_record.json`
  - `run_id`: `10f8502e-1b0e-4e59-b449-e86f56d26cb5`
  - `selected_candidate_id`: `null`
  - `groundhog_commit_candidate`: `false`
  - `groundhog_commit_apply`: `{}`
- Groundhog artifact after Run A:
  ```json
  {"bundle":null,"env_enabled":false,"exists":false,"ok":true,"path":"/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/groundhog_memory_bundle.json"}
  ```
- Filesystem proof after Run A:
  ```text
  $ ls -l game_theory/state
  total 0
  ```
- Generic run-memory proof after Run A and Run B:
  ```text
  $ wc -l game_theory/run_memory.jsonl
         3 game_theory/run_memory.jsonl
  ```

Answer:

- Does persistence actually occur after the run: **No**
- Concrete reason:
  - the run path produced only a recommendation object and never called `write_groundhog_bundle(...)`
  - the served-host batch path also did not append `run_memory.jsonl`

## 2. Load path proof

Code evidence:

- `game_theory/groundhog_memory.py`, `resolve_memory_bundle_for_scenario(...)`
  - Load trigger order:
    - explicit `memory_bundle_path`
    - else canonical `game_theory/state/groundhog_memory_bundle.json` only if `PATTERN_GAME_GROUNDHOG_BUNDLE=1`
- `game_theory/parallel_runner.py`, `_worker_run_one(...)`
  - Calls `resolve_memory_bundle_for_scenario(...)`
  - Passes resolved path into `prepare_effective_manifest_for_replay(...)` or `run_pattern_game(...)`
- `game_theory/pattern_game.py`, `prepare_effective_manifest_for_replay(...)`
  - Calls `apply_memory_bundle_to_manifest(...)`
  - Returns `memory_bundle_audit`

Served-host runtime evidence:

- Host memory endpoint before Run B:
  ```json
  {"bundle":null,"env_enabled":false,"exists":false,"ok":true,"path":"/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/groundhog_memory_bundle.json"}
  ```
- Run B start request:
  ```http
  POST /api/run-parallel/start
  Content-Type: application/json

  {"operator_recipe_id":"pattern_learning","evaluation_window_mode":"12","evaluation_window_custom_months":null,"max_workers":1,"log_path":false}
  ```
- Run B response:
  ```json
  {"job_id":"646d3648764c407695211fa117212300","ok":true,"total":1,"workers_used":1}
  ```
- Completed Run B artifact:
  - Session log directory: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/logs/batch_20260419T214935Z_385401c0`
  - Run record: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/logs/batch_20260419T214935Z_385401c0/tier1_twelve_month_default/run_record.json`
  - `run_id`: `ae9da2af-1b5e-4491-b08a-d7651c717c8f`
  - `decision_audit.prior_outcomes_or_parameters_loaded_into_replay_engine`: `false`
  - `decision_audit.memory_bundle`: `null`
  - `learning_run_audit_v1.memory_bundle_loaded`: `false`
  - `learning_run_audit_v1.memory_bundle_applied`: `false`
  - `learning_run_audit_v1.memory_records_loaded_count`: `0`
  - `learning_run_audit_v1.memory_used_v1`: `false`
  - `learning_memory_evidence.learned_from.bundle_path`: `null`
  - `learning_memory_evidence.groundhog_mode`: `inactive`

Answer:

- Is memory actually loaded on the later run: **No**
- Concrete reason: no bundle file exists, `PATTERN_GAME_GROUNDHOG_BUNDLE` is off on the served host, and no scenario supplied `memory_bundle_path`

## 3. Use path proof

Code evidence:

- `game_theory/memory_bundle.py`, `apply_memory_bundle_to_manifest(...)`
  - This is the point where loaded memory changes replay inputs
  - It merges whitelisted keys into the manifest before replay
- `game_theory/run_memory.py`, `build_decision_audit(...)`
  - States whether prior outcomes or parameters were loaded into replay
- `game_theory/run_memory.py`, `build_learning_memory_evidence(...)`
  - Exposes whether memory was applied and whether Groundhog mode was active

Concrete runtime objects proving non-use:

Run A `run_record.json`:

```json
{
  "decision_loaded": false,
  "memory_bundle": null,
  "memory_applied": false,
  "groundhog_mode": "inactive",
  "learned_from": {
    "prior_run_id_metadata": null,
    "bundle_path": null,
    "bundle_from_run_id": null,
    "batch_folder": null
  },
  "memory_operator_note_v1": "No memory bundle path resolved for this replay — execution-only with respect to promoted memory.",
  "memory_records_loaded_count": 0,
  "memory_used_v1": false,
  "selected_candidate_id": null,
  "groundhog_commit_candidate": false,
  "groundhog_commit_apply": {}
}
```

Run B `run_record.json`:

```json
{
  "decision_loaded": false,
  "memory_bundle": null,
  "memory_applied": false,
  "groundhog_mode": "inactive",
  "learned_from": {
    "prior_run_id_metadata": null,
    "bundle_path": null,
    "bundle_from_run_id": null,
    "batch_folder": null
  },
  "memory_operator_note_v1": "No memory bundle path resolved for this replay — execution-only with respect to promoted memory.",
  "memory_records_loaded_count": 0,
  "memory_used_v1": false,
  "selected_candidate_id": null,
  "groundhog_commit_candidate": false,
  "groundhog_commit_apply": {}
}
```

Answer:

- Is loaded memory consumed: **No**
- Effects on later run:
  - candidate generation: **No evidence of influence**
  - ranking: **No evidence of influence**
  - initialization: **No**
  - replay configuration: **No**

## 4. Runtime proof

### Run A

- Host: `http://127.0.0.1:8766`
- Commit: `601e81a0a81879ab3343de29aaebbd703843de2c`
- Timestamp: `2026-04-19T21:48:59Z`
- Recipe: `pattern_learning`
- Evaluation window: `12`
- Job id: `ea3eccf6eaa640ef96cb24298ca35c7c`
- Winner id: **missing artifact**
  - Concrete value returned by host: `selected_candidate_id=null`
- Score:
  - `winner_vs_control`: `null`
  - No winner score exists in the run artifact
- Parameters:
  - `groundhog_commit_apply`: `{}`
- Persistence artifact:
  - canonical path exists conceptually: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/state/groundhog_memory_bundle.json`
  - actual file state after run: absent

### Run B

- Host: `http://127.0.0.1:8766`
- Commit: `601e81a0a81879ab3343de29aaebbd703843de2c`
- Timestamp: `2026-04-19T21:49:35Z`
- Recipe: `pattern_learning`
- Evaluation window: `12`
- Job id: `646d3648764c407695211fa117212300`
- Artifact loaded: **No**
  - `memory_bundle_loaded=false`
  - `memory_records_loaded_count=0`
  - `memory_used_v1=false`
- Behavior change:
  - none proven
  - Run B produced the same effective memory state as Run A:
    - `selected_candidate_id=null`
    - `groundhog_commit_candidate=false`
    - `groundhog_commit_apply={}`
    - `decision_windows_total=11`
    - `bars_processed=11`

Missing artifact required by the prompt:

- A served-host run in this repository that produces a non-null winner id
- No such artifact was produced in Run A or Run B
- No such artifact was found in existing `game_theory/logs/**/run_record.json`

## 5. First broken breadcrumb

First broken breadcrumb: **the served-host run path finishes without any persistence call for winner memory**

Exact location:

- File: `game_theory/web_app.py`
- Function: `api_parallel_start` inner `run_job`
- Evidence:
  - `run_job` starts the batch, receives completed results, records the scorecard, and never calls `write_groundhog_bundle(...)`
  - `run_job` does not pass `run_memory_log_path` into `run_scenarios_parallel(...)`
  - the only canonical writer remains `/api/groundhog-memory` POST

Why this is first:

- The harness can produce a recommendation object
- The canonical writer exists separately in `game_theory/groundhog_memory.py`
- The served host exposes that writer only through `POST /api/groundhog-memory`
- The run path `POST /api/run-parallel/start` never calls that writer
- Because nothing is written, there is nothing for a later run to load or use

## 6. Classification

**E — partial chain broken at exact step**

Exact step:

- Recommendation produced on run path
- Persistence missing before any later load/use step

## 7. Exact fix

- File: `game_theory/web_app.py`
- Function: `api_parallel_start` inner `run_job`
- Missing link:
  - after successful results return, when a winner recommendation exists, call `write_groundhog_bundle(...)` with the selected winner apply payload and `from_run_id`

Minimal code change only:

```python
                for row in results:
                    gh = (((row.get("operator_test_harness_v1") or {}).get("groundhog_commit_recommendation_v1")) or {})
                    apply = gh.get("groundhog_commit_apply") or {}
                    if gh.get("groundhog_commit_candidate") and apply:
                        write_groundhog_bundle(
                            atr_stop_mult=float(apply["atr_stop_mult"]),
                            atr_target_mult=float(apply["atr_target_mult"]),
                            from_run_id=job_id,
                        )
                        break
```

Concrete limitation of this fix:

- On the current served host, Run A and Run B did not produce a winner, so this code path would not fire until a future run returns `groundhog_commit_candidate=true`

## 8. FINAL ONE-LINE RCA

This system fails to learn because automatic winner-memory persistence fails first in `game_theory/web_app.py` `api_parallel_start.run_job`, preventing any later run from loading or using promoted memory.

Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/memory_persistence_rca_20260419_164517.md`
