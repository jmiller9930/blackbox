# Runtime Trace Audit

Full file path: `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/runtime_trace_zero_batch_failure_20260419_150100.md`

## 1. Frontend payload trace

Concrete frontend payload builder is in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L3715).

Exact JSON fields sent by the browser when the click handler runs:

```json
{
  "scenarios_json": "...",
  "max_workers": mw,
  "log_path": true,
  "operator_recipe_id": recipeId,
  "evaluation_window_mode": wm,
  "evaluation_window_custom_months": customM
}
```

Concrete browser-captured JSON for the zero-work completed batch is missing.

Missing data:
- No HTTP access log in this directory for `POST /api/run-parallel/start`
- No browser devtools export in this directory
- Current UI script in this tree is not a reliable source of a live request because the page script fails parse before attaching the handler

Concrete payloads evaluated through `_prepare_parallel_payload(...)`:

Case `valid_custom`:

```json
{
  "scenarios_json": "[{\"scenario_id\": \"s1\", \"manifest_path\": \"renaissance_v4/configs/manifests/baseline_v1_recipe.json\", \"agent_explanation\": {\"hypothesis\": \"h\"}}]",
  "max_workers": 2,
  "log_path": false,
  "operator_recipe_id": "custom",
  "evaluation_window_mode": "12",
  "evaluation_window_custom_months": null
}
```

Case `empty_array`:

```json
{
  "scenarios_json": "[]",
  "max_workers": 1,
  "log_path": false,
  "operator_recipe_id": "custom",
  "evaluation_window_mode": "12",
  "evaluation_window_custom_months": null
}
```

Case `malformed_json`:

```json
{
  "scenarios_json": "[{",
  "max_workers": 1,
  "log_path": false,
  "operator_recipe_id": "custom",
  "evaluation_window_mode": "12",
  "evaluation_window_custom_months": null
}
```

Determination:
- valid scenarios: yes
- empty: yes, rejected
- malformed: yes, rejected

## 2. Backend intake trace

Backend function is `api_parallel_start()` in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L733).

Parsed request body:

```python
data = request.get_json(force=True, silent=True) or {}
```

Concrete `_prepare_parallel_payload(...)` outputs:

Case `valid_custom`:

```json
{
  "ok": true,
  "scenarios": [
    {
      "scenario_id": "s1",
      "manifest_path": "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json",
      "agent_explanation": {
        "hypothesis": "h"
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
  "max_workers": 2,
  "log_path": null
}
```

Case `empty_array`:

```json
{
  "ok": false,
  "error": "No runnable scenarios (empty list after parse/build). Choose a recipe with scenarios or paste Custom JSON."
}
```

Case `malformed_json`:

```json
{
  "ok": false,
  "error": "Expecting property name enclosed in double quotes: line 1 column 3 (char 2)"
}
```

Case `mixed_entries`:

```json
{
  "ok": true,
  "scenarios": [
    {
      "scenario_id": "s1",
      "manifest_path": "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json",
      "agent_explanation": {
        "hypothesis": "h"
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
  "log_path": null
}
```

Determination:
- non-empty: yes
- empty: rejected before worker start
- invalid: malformed JSON rejected; non-dict entries filtered

## 3. Scenario validation trace

Concrete intake code in [game_theory/web_app.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/web_app.py#L269):

```python
scenarios = json.loads(raw)
...
scenarios = [x for x in scenarios if isinstance(x, dict)]
...
if not scenarios:
    return {"ok": False, "error": "No runnable scenarios (empty list after parse/build). Choose a recipe with scenarios or paste Custom JSON."}
```

Concrete validation function is [game_theory/scenario_contract.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/scenario_contract.py#L166).

Observed validation behavior:
- empty list: blocking error
- missing/invalid `manifest_path`: blocking error
- missing hypothesis when required: blocking error
- undocumented extra keys: warning only

Concrete answer:
- are scenarios silently dropped: yes, non-dict array entries are dropped before validation
- why does run not fail loudly if empty: it does fail loudly at intake; empty scenario lists are rejected before `run_scenarios_parallel(...)`

## 4. Worker execution trace

Worker entry is `_worker_run_one(...)` in [game_theory/parallel_runner.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/parallel_runner.py#L129).

Batch executor is `run_scenarios_parallel(...)` in [game_theory/parallel_runner.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/parallel_runner.py#L265).

Concrete empty-list guard:

```python
if not scenarios:
    raise ValueError(
        "run_scenarios_parallel: scenarios list is empty — refusing a no-op batch ..."
    )
```

Concrete worker execution evidence from current on-disk scorecard:

- `game_theory/batch_scorecard.jsonl` line 6:

```json
{
  "job_id": "9429e2362cfb493a97f5cf18dd472190",
  "total_scenarios": 1,
  "total_processed": 1,
  "ok_count": 0,
  "failed_count": 1,
  "status": "done",
  "decision_windows_total": 0,
  "bars_processed": 0,
  "work_units_v1": "0 scenarios with audits (ok rows=0, total rows=1)"
}
```

This proves:
- the batch received 1 scenario
- one worker result row was produced
- the worker row was not successful

Concrete worker row reproduction for missing manifest:

```json
{
  "ok": false,
  "scenario_id": "bad1",
  "error": "FileNotFoundError: [Errno 2] No such file or directory: '/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/DOES_NOT_EXIST.json'",
  "summary": null,
  "referee_session": "ERROR"
}
```

Concrete worker row reproduction for baseline manifest in this environment:

```json
{
  "ok": false,
  "scenario_id": "valid1",
  "error": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
  "manifest_path": "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json",
  "summary": null,
  "referee_session": "ERROR"
}
```

## 5. Replay invocation trace

Replay call site:
- `_worker_run_one(...)` calls `run_pattern_game(...)` at [game_theory/parallel_runner.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/parallel_runner.py#L195)
- `run_pattern_game(...)` would call `run_manifest_replay(...)` at [game_theory/pattern_game.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/pattern_game.py#L216)

Concrete traceback reproducing the baseline-manifest worker failure:

```text
Traceback (most recent call last):
  File "<stdin>", line 5, in <module>
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/pattern_game.py", line 208, in run_pattern_game
    prep = prepare_effective_manifest_for_replay(
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/pattern_game.py", line 151, in prepare_effective_manifest_for_replay
    errs = validate_manifest_against_catalog(manifest)
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/manifest/validate.py", line 47, in validate_manifest_against_catalog
    catalog = load_catalog(catalog_path)
  File "/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/registry/load.py", line 12, in load_catalog
    raw = json.loads(p.read_text(encoding="utf-8"))
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

Concrete file content causing the JSON parse failure:

File: `registry/catalog_v1.json`

First bytes:

```text
Manifest personal{
  "schema": "renaissance_v4_plugin_catalog_v1",
  ...
```

Determination:
- was `run_manifest_replay(...)` called for the failing baseline-manifest worker: no
- exact reason: `run_pattern_game(...)` fails in `prepare_effective_manifest_for_replay(...)` during `validate_manifest_against_catalog(...)`, before the replay call

## 6. Scorecard write trace

Concrete write function is `record_parallel_batch_finished(...)` in [game_theory/batch_scorecard.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/batch_scorecard.py#L245).

Concrete zero-work flattening function is `compute_scorecard_learning_rollups_v1(...)` in [game_theory/learning_run_audit.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/learning_run_audit.py#L445).

Concrete zero-audit return shape:

```json
{
  "learning_status": "execution_only",
  "decision_windows_total": 0,
  "bars_processed": 0,
  "candidate_count": 0,
  "work_units_v1": "0 scenarios with audits (ok rows=0, total rows=1)"
}
```

Concrete `done` write condition:

```python
else:
    res = results or []
    ok_n = sum(1 for r in res if r.get("ok"))
    ...
    record = {
        ...
        "ok_count": ok_n,
        "failed_count": len(res) - ok_n,
        "status": "done",
        ...
    }
```

Concrete on-disk completed zero-work row in `game_theory/batch_scorecard.jsonl` line 6:

```json
{
  "job_id": "9429e2362cfb493a97f5cf18dd472190",
  "total_scenarios": 1,
  "total_processed": 1,
  "ok_count": 0,
  "failed_count": 1,
  "status": "done",
  "replay_decision_windows_sum": 0,
  "decision_windows_total": 0,
  "bars_processed": 0,
  "work_units_v1": "0 scenarios with audits (ok rows=0, total rows=1)"
}
```

Concrete session log for the same failure row:

File: `game_theory/logs/batch_20260419T195217Z_20b4a170/job_test/run_record.json`

Relevant fields:

```json
{
  "error": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
  "referee": null,
  "operator_run_audit": {
    "replay_data_audit": null
  },
  "learning_memory_evidence": {
    "run_error": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"
  }
}
```

This proves:
- the worker failed before producing replay output
- the batch still wrote a completed row with zero replay work

## 7. Exact failure point

`record_parallel_batch_finished(...)` done-branch in [game_theory/batch_scorecard.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/batch_scorecard.py#L306)

Reason:
- when `error is None`, the function writes `status: "done"` even if `ok_count == 0` and replay work sums are zero

## 8. Why system did not fail loudly

Two concrete behaviors suppress the failure:

1. [game_theory/learning_run_audit.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/learning_run_audit.py#L445) converts “no successful worker audits” into zero-valued metrics:
   - `decision_windows_total: 0`
   - `bars_processed: 0`
   - `learning_status: execution_only`

2. [game_theory/batch_scorecard.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/batch_scorecard.py#L342) records the batch as `status: "done"` whenever `error is None`, even with:
   - `ok_count: 0`
   - `failed_count: 1`
   - `decision_windows_total: 0`
   - `bars_processed: 0`

## 9. Classification

**E — scorecard incorrectly records empty runs**

Concrete basis:
- accepted payload was non-empty
- intake returned a non-empty scenario list
- worker executed and returned one failed row
- replay was never invoked because manifest validation failed before replay
- scorecard still wrote `status: "done"` with zero replay work

## 10. Minimal fix

Exact file:
- [game_theory/batch_scorecard.py](/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/game_theory/batch_scorecard.py)

Exact function:
- `record_parallel_batch_finished`

Minimal code change only:

```python
    else:
        res = results or []
        ok_n = sum(1 for r in res if r.get("ok"))
        pct_fields = compute_batch_score_percentages(res)
        learning_batch = aggregate_batch_learning_run_audit_v1(res)
        if ok_n == 0 or int(learning_batch.get("replay_decision_windows_sum") or 0) <= 0:
            error = (
                "zero_replay_work: batch produced no successful replay work "
                f"(ok_rows={ok_n}, decision_windows_sum={int(learning_batch.get('replay_decision_windows_sum') or 0)})"
            )
            pct_fields = {
                "run_ok_pct": 0.0,
                "referee_win_pct": None,
                "referee_wins": 0,
                "referee_losses": 0,
                "avg_trade_win_pct": None,
                "trade_win_rate_n": 0,
            }
            record = {
                "schema": SCHEMA_V1,
                "job_id": job_id,
                "source": source,
                "started_at_utc": started_at_utc,
                "ended_at_utc": ended_at_utc,
                "duration_sec": timing["duration_sec"],
                "total_scenarios": total_scenarios,
                "total_processed": 0,
                "ok_count": 0,
                "failed_count": total_scenarios,
                "note": "Batch failed before producing any successful replay work.",
                "workers_used": workers_used,
                "status": "error",
                "error": error[:4000],
                **pct_fields,
            }
            if operator_batch_audit:
                record["operator_batch_audit"] = operator_batch_audit
            append_batch_scorecard_line(record, path=path)
            return {**timing, **pct_fields}
```

## One-line truth

A batch with zero decision windows is not a run — it is a failure that must be surfaced.
