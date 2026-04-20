# Host RCA Zero Replay First Failure

Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/host_rca_zero_replay_first_failure_20260419_150548.md`

## 1. Reproduction details

- Exact recipe selected: `custom`
- Exact evaluation window selected: `12`
- Exact host: `macdaddy`
- Exact served host URL used for reproduction: `http://127.0.0.1:8766`
- Exact UI version: `2.5.8`
- Exact commit: `983e0176048bd105702f1185344b89e6da45075c`
- Exact timestamp of reproduced run start: `2026-04-19T20:06:54Z`
- Exact `job_id`: `23b3ea35fca142a7b9f92963803ee78e`

Raw request was sent to the live served endpoint on this host:

```text
POST http://127.0.0.1:8766/api/run-parallel/start
```

## 2. Start request evidence

### Raw `/api/run-parallel/start` payload

Exact JSON sent to the live served host:

```json
{
  "scenarios_json": "[{\"scenario_id\":\"job_test\",\"manifest_path\":\"renaissance_v4/configs/manifests/baseline_v1_recipe.json\",\"agent_explanation\":{\"hypothesis\":\"Smoke test: baseline manifest completes one replay on lab data.\"}}]",
  "max_workers": 1,
  "log_path": false,
  "operator_recipe_id": "custom",
  "evaluation_window_mode": "12",
  "evaluation_window_custom_months": null
}
```

### Raw start response from the live host

```http
HTTP/1.1 200 OK
Server: Werkzeug/3.1.8 Python/3.11.0
Date: Sun, 19 Apr 2026 20:06:54 GMT
Content-Type: application/json

{"job_id":"23b3ea35fca142a7b9f92963803ee78e","ok":true,"total":1,"workers_used":1}
```

### Parsed backend payload

`api_parallel_start()` parses request JSON with:

```python
data = request.get_json(force=True, silent=True) or {}
```

No server-side request-body log artifact exists in this directory.

Missing artifact:
- There is no host log file in this directory that prints the parsed `data` object from `api_parallel_start()`

Concrete parsed payload on this host is the JSON object above after `request.get_json(...)`.

### `_prepare_parallel_payload(...)` result on this host for the same payload

```json
{
  "ok": true,
  "scenarios": [
    {
      "scenario_id": "job_test",
      "manifest_path": "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json",
      "agent_explanation": {
        "hypothesis": "Smoke test: baseline manifest completes one replay on lab data."
      },
      "operator_recipe_id": "custom",
      "operator_recipe_label": "Custom JSON",
      "evaluation_window": {
        "calendar_months": 12,
        "operator_window_mode": "12",
        "recipe_default_calendar_months": 12,
        "window_overrode_recipe_default": false,
        "json_calendar_months_before_override": null,
        "referee_note": "Replay uses the last ~12 calendar months of available 5m bars (approximate day cutoff; see replay_data_audit)."
      }
    }
  ],
  "max_workers": 1,
  "log_path": null,
  "val_msgs": [
    "Evaluation window (12 mo) exceeds replay tape length (max ~1 mo from ~0d of 5m bars). Replay will proceed on the available tape and the final replay_data_audit will show the actual span."
  ],
  "operator_batch_audit": {
    "operator_recipe_id": "custom",
    "operator_recipe_label": "Custom JSON",
    "evaluation_window_mode": "12",
    "evaluation_window_effective_calendar_months": 12,
    "evaluation_window_cap_warning": "Evaluation window (12 mo) exceeds replay tape length (max ~1 mo from ~0d of 5m bars). Replay will proceed on the available tape and the final replay_data_audit will show the actual span.",
    "recipe_default_calendar_months": 12,
    "window_overrode_recipe_default": false,
    "manifest_path_primary": "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json",
    "policy_framework_path": null,
    "policy_framework_audit": null
  }
}
```

## 3. Scenario evidence

- Number of scenarios created: `1`
- Scenario ids: `["job_test"]`
- Manifest path for scenario `job_test`:
  `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json`
- Policy framework path for scenario `job_test`: `null`
- Effective evaluation window for scenario `job_test`: `12` calendar months

Concrete status payload from the live host confirms a single scenario was submitted:

```json
{
  "total": 1,
  "workers_used": 1
}
```

## 4. Worker evidence

### Whether worker started

Yes.

Concrete live status payload from the served host:

```json
{
  "completed": 1,
  "last_scenario_id": "job_test",
  "last_ok": false,
  "last_message": "job_test: failed (JSONDecodeError: Expecting value: line 1 column 1 (char 0))",
  "status": "done"
}
```

Concrete server log snippet from the running host process:

```text
127.0.0.1 - - [19/Apr/2026 15:06:54] "POST /api/run-parallel/start HTTP/1.1" 200 -
[session_log] batch folder=/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/logs/batch_20260419T200654Z_106ea152 (1 scenarios — see BATCH_README.md)
127.0.0.1 - - [19/Apr/2026 15:07:42] "GET /api/run-parallel/status/23b3ea35fca142a7b9f92963803ee78e HTTP/1.1" 200 -
```

### Whether `_worker_run_one(...)` was entered

Yes.

Concrete evidence:
- `last_scenario_id: "job_test"`
- `last_message: "job_test: failed (JSONDecodeError: Expecting value: line 1 column 1 (char 0))"`
- session log folder was written for one scenario

### Whether `run_pattern_game(...)` was entered

Yes.

Concrete traceback on the same host, using the same manifest path:

```text
Traceback (most recent call last):
  File "<stdin>", line 5, in <module>
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/pattern_game.py", line 208, in run_pattern_game
    prep = prepare_effective_manifest_for_replay(
```

### Whether `run_manifest_replay(...)` was entered

No.

Concrete traceback on the same host shows failure before the replay call site:

```text
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/pattern_game.py", line 151, in prepare_effective_manifest_for_replay
    errs = validate_manifest_against_catalog(manifest)
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/manifest/validate.py", line 47, in validate_manifest_against_catalog
    catalog = load_catalog(catalog_path)
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/registry/load.py", line 12, in load_catalog
    raw = json.loads(p.read_text(encoding="utf-8"))
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

## 5. Replay evidence

### Whether bar data was loaded

No concrete replay-load artifact exists for this run.

Missing artifacts for the reproduced `job_id`:
- no `replay_data_audit` in the worker result
- no `dataset_bars` in the worker result
- no `referee` block in `run_record.json`
- no `[replay] Loaded ... bars` log line in the host server output

Concrete worker/session artifacts for the reproduced run:

File:
`game_theory/logs/batch_20260419T200654Z_106ea152/job_test/run_record.json`

Relevant fields:

```json
{
  "error": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
  "referee": null,
  "operator_run_audit": {
    "replay_data_audit": null
  }
}
```

### Bars before slicing

Missing artifact for the reproduced run:
- `replay_data_audit.dataset_bars_before_window` is absent because replay was never entered

### Bars after slicing

Missing artifact for the reproduced run:
- `replay_data_audit.dataset_bars_after_window` is absent because replay was never entered

### Decision windows

Concrete live status payload from the served host:

```json
{
  "batch_timing": {
    "decision_windows_total": 0,
    "bars_processed": 0
  }
}
```

These are downstream zero-work fields, not the first failure.

### First failure before replay

Concrete traceback on the host:

```text
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

Concrete failing file content on the host:

File:
`registry/catalog_v1.json`

Leading bytes:

```text
Manifest personal{
  "schema": "renaissance_v4_plugin_catalog_v1",
```

This file is not valid JSON.

## 6. First failed breadcrumb

### What was the first thing that went wrong

The first real failure was a JSON parse failure while loading the plugin catalog during manifest validation, before replay started.

### Exact file / function / condition

- File: [registry/load.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/registry/load.py)
- Function: `load_catalog`
- Condition: `json.loads(p.read_text(encoding="utf-8"))` attempted to parse invalid JSON from `registry/catalog_v1.json`

### Exact error string

```text
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

### Concrete breadcrumb chain on the host

1. live start request succeeded with `total: 1`
2. `_prepare_parallel_payload(...)` returned one non-empty scenario
3. worker started and entered `_worker_run_one(...)`
4. worker entered `run_pattern_game(...)`
5. `prepare_effective_manifest_for_replay(...)` called `validate_manifest_against_catalog(...)`
6. `validate_manifest_against_catalog(...)` called `load_catalog(...)`
7. `load_catalog(...)` raised `JSONDecodeError` on `registry/catalog_v1.json`
8. worker returned `ok: false`
9. later, batch scorecard still wrote `status: "done"` with zero replay work

### Failure type

`config issue`

More exact label:
- invalid host-side catalog file consumed by manifest validation

## 7. Final classification

**manifest/framework resolution failure**

Exact explanation:
- the scenario payload was valid and non-empty
- worker execution started
- replay was blocked by manifest validation because the host plugin catalog file was invalid JSON

## 8. Concrete fix recommendation

Primary fix tied to the first failure:

- Exact file to fix: [registry/catalog_v1.json](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/registry/catalog_v1.json)
- Remove the leading non-JSON text `Manifest personal` so the file begins with `{`

Minimal concrete host-side correction:

```diff
-Manifest personal{
+{
```

Why this fix is tied to the first failure:
- `load_catalog(...)` fails on the very first byte sequence of the current file
- manifest validation cannot complete until this file is valid JSON
- `run_manifest_replay(...)` is never reached until that is corrected

Secondary hardening fix for the downstream no-op symptom:

- Exact file: [game_theory/batch_scorecard.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/batch_scorecard.py)
- Exact function: `record_parallel_batch_finished`
- Change: refuse `status: "done"` when `ok_count == 0` or `replay_decision_windows_sum == 0`

## 9. Final one-sentence RCA

This run produced zero replay work because `registry/catalog_v1.json` failed first in `load_catalog`, which prevented `run_manifest_replay` from ever being entered.
