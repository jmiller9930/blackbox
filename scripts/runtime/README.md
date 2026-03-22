# Phase 1.7–1.8 runtime workflows

Run from the **repository root** (`blackbox/`).

## DATA — one-shot health checks

```bash
export BLACKBOX_SQLITE_PATH="${BLACKBOX_SQLITE_PATH:-data/sqlite/blackbox.db}"
python3 scripts/runtime/data_health_workflow.py
```

Optional: `GATEWAY_HEALTH_URL`, `OLLAMA_BASE_URL`, `--no-forced-failure`.

## DATA — watchdog (Phase 1.8)

Runs the same checks on an interval; **alerts** are emitted only when a check **newly fails** (sustained failure does not spam). SIGINT/SIGTERM stops cleanly.

```bash
export BLACKBOX_SQLITE_PATH="${BLACKBOX_SQLITE_PATH:-data/sqlite/blackbox.db}"
python3 scripts/runtime/data_health_workflow.py --watchdog --interval 5 --max-iterations 3
```

Use `--max-iterations` for bounded tests; omit `--max-iterations` for continuous monitoring.

## Cody — structured plan → task row

```bash
export BLACKBOX_SQLITE_PATH="${BLACKBOX_SQLITE_PATH:-data/sqlite/blackbox.db}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
python3 scripts/runtime/cody_plan_workflow.py "Your engineering request here"
```

Task `description` is JSON with `schema_version`, normalized fields, `parse_method` (`json` | `headings` | `fallback`), and `raw_model_output`.

## Cody — coordination: DATA alert → plan task (Phase 1.9)

Requires at least one **open**, **unacknowledged** alert (e.g. from DATA health workflow). Picks the **latest** such alert unless `--alert-id` is set. Writes a task whose JSON includes `coordination.responded_to_alert_id` and `alert_snapshot`. Default: sets `acknowledged_at` and `status='acknowledged'` on that alert (`--no-consume-alert` to skip).

```bash
export BLACKBOX_SQLITE_PATH="${BLACKBOX_SQLITE_PATH:-data/sqlite/blackbox.db}"
python3 scripts/runtime/data_health_workflow.py   # ensure a fresh alert if needed
python3 scripts/runtime/cody_alert_coordination.py
```

## Outcome recording — Phase 2.0 (feedback loop)

**`task_outcome_recorder.py`** — merge an `outcome` object into existing `tasks.description` JSON (requires valid JSON already, e.g. from Cody coordination):

```bash
python3 scripts/runtime/task_outcome_recorder.py --task-id "<uuid>" --status success \
  --notes "manual sign-off" --validated-by human
```

**`data_task_outcome_validate.py`** — DATA runs a **minimal** check: if title/description looks **disk-related** (keywords: disk, df, `/var/log`, usage, space), records `outcome` with `validated_by: DATA` after `shutil.disk_usage` on `/var/log` and `/`; otherwise `status: unknown`. Preserves `coordination.responded_to_alert_id`.

```bash
python3 scripts/runtime/data_task_outcome_validate.py --task-id "<uuid>"
# optional: --dry-run
```

Chain: **alert → task (coordination) → outcome** in one JSON document.

## Reflection — Phase 2.1 (lightweight)

**`cody_reflection_workflow.py`** — deterministic (no ML) scan of recent **non–reflection** tasks: parses `outcome` and `coordination.responded_to_alert_id`, buckets success / failure / unknown, keyword themes, `recommended_improvements`, `confidence_notes`. Prints JSON.

```bash
python3 scripts/runtime/cody_reflection_workflow.py --limit 25
python3 scripts/runtime/cody_reflection_workflow.py --limit 25 --store   # also save as a completed task row
```

Stored rows use title prefix `[Reflection]` and are excluded from the next scan by default.

## Decision context — Phase 2.2

**`decision_context_builder.py`** — bundles **health** (`system_health_logs`), **alerts**, **operational tasks/outcomes**, and the **latest `[Reflection]`** summary into one JSON (`kind: decision_context_v1`). Rule-based **`system_readiness`**: `healthy` | `degraded` | `unstable`; **`caution_flags`** are explicit strings. No trades, no ML.

```bash
python3 scripts/runtime/decision_context_builder.py
python3 scripts/runtime/decision_context_builder.py --store --health-limit 80 --task-limit 40
```

Operational tasks exclude `[Reflection]` and `[Decision Context]` rows from counts. Stored decision-context tasks use title prefix **`[Decision Context]`**.

## Analyst decision engine — Phase 2.3

**`analyst_decision_engine.py`** — Rule-based **analyst_decision_v1** from Phase 2.2 context: `NO_TRADE` (unstable), `REDUCED_RISK` (degraded), `ALLOW` (healthy). Uses **`decision_context_builder.build_payload`** by default, or **`--from-latest`** to load the newest stored `[Decision Context]` task. Optional **`--signal`** placeholder only. **`--store`** writes **`[Analyst Decision]`** task rows. No trades, no APIs, no registry agent.

```bash
python3 scripts/runtime/analyst_decision_engine.py
python3 scripts/runtime/analyst_decision_engine.py --from-latest --store
```
