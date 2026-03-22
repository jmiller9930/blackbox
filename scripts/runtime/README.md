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

**`analyst_decision_engine.py`** — Rule-based recommendations from decision context: **`NO_TRADE`** (unstable), **`REDUCED_RISK`** (degraded), **`ALLOW`** (healthy). Imports Phase 2.2 builder unless **`--use-latest-stored-context`** (reads latest **`[Decision Context]`** task). Output: `kind: analyst_decision_v1`, `confidence`, `reasoning`, `context_snapshot`, `caution_flags`, `signal_input` stub. Optional **`--store`** → task title **`[Analyst Decision]`**.

```bash
python3 scripts/runtime/analyst_decision_engine.py
python3 scripts/runtime/analyst_decision_engine.py --use-latest-stored-context
python3 scripts/runtime/analyst_decision_engine.py --store
```

## Simulated action router — Phase 2.4

**`simulated_action_router.py`** — Maps latest analyst output to safe **action intent** only: **`HOLD`** (NO_TRADE), **`WATCH`** (REDUCED_RISK), **`PAPER_TRADE_READY`** (ALLOW). No execution, no exchanges. Consumes **live** analyst (same options as Phase 2.3) or **`--use-latest-stored-analyst`**. Optional **`--include-decision-context-ref`**. Output: `kind: simulated_action_v1`, `source_decision`, `action`, `rationale`, `caution_flags`, `execution_notes`, `next_step_recommendation`. **`--store`** → title **`[Simulated Action]`**.

```bash
python3 scripts/runtime/simulated_action_router.py
python3 scripts/runtime/simulated_action_router.py --use-latest-stored-analyst --include-decision-context-ref
python3 scripts/runtime/simulated_action_router.py --store
```

## Paper trade ticket — Phase 2.5

**`paper_trade_ticket_builder.py`** — Builds **`paper_trade_ticket_v1`** from **live** simulated action (`compute_simulated_action`) or **`--use-latest-stored-simulated-action`**. Statuses: **`NOT_CREATED`** (HOLD), **`WATCH_ONLY`** (WATCH), **`READY`** (PAPER_TRADE_READY with placeholders for market/direction). Optional **`--attach-analyst-ref`** / **`--attach-decision-context-ref`**. **`--store`** → **`[Paper Trade Ticket]`** task.

```bash
python3 scripts/runtime/paper_trade_ticket_builder.py --use-latest-stored-simulated-action --attach-analyst-ref --attach-decision-context-ref
python3 scripts/runtime/paper_trade_ticket_builder.py --store
```

## Paper execution record — Phase 2.6

**`paper_execution_recorder.py`** — Turns a paper-trade ticket into **`paper_execution_record_v1`**: **`SKIPPED`** (NOT_CREATED), **`WATCHING`** (WATCH_ONLY), **`PAPER_EXECUTED`** (READY) with `execution_mode: paper` and placeholders (no fills/prices). Consumes **`--use-latest-stored-paper-ticket`** or builds ticket live (same options as Phase 2.5). Optional **`--attach-simulated-action-ref`** / **`--attach-analyst-ref`**. **`--store`** → **`[Paper Execution]`** task.

```bash
python3 scripts/runtime/paper_execution_recorder.py --use-latest-stored-paper-ticket --attach-simulated-action-ref --attach-analyst-ref
python3 scripts/runtime/paper_execution_recorder.py --store
```

## Paper execution outcome — Phase 2.7

**`paper_execution_outcome_evaluator.py`** — Reads a paper execution record (live via `compute_paper_execution_record_document`, or **`--use-latest-stored-paper-execution`** for the latest **`[Paper Execution]`** task) and emits **`paper_execution_outcome_v1`** with **`outcome_status`**: `NOT_APPLICABLE` | `MONITORING` | `SUCCESS` | `FAILURE` | `UNKNOWN` (bounded rule-only; no market data). Optional **`--with-ticket-summary`** / **`--with-analyst-summary`** attach latest stored paper ticket and analyst summaries. When computing live execution, use the same flags as Phase 2.6 for the ticket (`--use-latest-stored-paper-ticket`, …) and **`--recorder-attach-analyst`** for analyst in the recorder path. **`--store`** → **`[Paper Outcome]`** task.

```bash
python3 scripts/runtime/paper_execution_outcome_evaluator.py --use-latest-stored-paper-execution --with-ticket-summary --with-analyst-summary
python3 scripts/runtime/paper_execution_outcome_evaluator.py --use-latest-stored-paper-ticket --attach-simulated-action-ref --recorder-attach-analyst
python3 scripts/runtime/paper_execution_outcome_evaluator.py --use-latest-stored-paper-execution --store
```

## Trade episode — Phase 2.8

**`trade_episode_aggregator.py`** — Reads the latest **`[Paper Outcome]`** task and walks **task_id** references backward: paper execution → paper trade ticket → simulated action → analyst decision. Embeds **decision_context_reference** blobs from simulated action / ticket under **`decision_reference.decision_context_embedded`**. **`system_state_summary`** is the analyst’s **`context_snapshot`** when present. **`alert_reference`** / **`task_reference`** are filled only if **`coordination.responded_to_alert_id`** appears in loaded JSON (otherwise null + note). **`--store`** → **`[Trade Episode]`** completed task. No new tables, no row updates, no APIs.

```bash
python3 scripts/runtime/trade_episode_aggregator.py
python3 scripts/runtime/trade_episode_aggregator.py --store
```

## System insight — Phase 2.9

**`insight_generator.py`** — Reads **N** most recent **`[Trade Episode]`** tasks (`--recent`, default **8**, max 50), deterministic **rule-only** interpretation: **`system_insight_v1`** with **`outcome_summary`**, **`decision_alignment`** (readiness × analyst decision table), **`risk_signals`** (caution flag aggregation), **`structural_gaps`** (null links, placeholders). No ML, no trading, no mutation except optional **`--store`** → **`[System Insight]`** completed task.

```bash
python3 scripts/runtime/insight_generator.py
python3 scripts/runtime/insight_generator.py --recent 5
python3 scripts/runtime/insight_generator.py --store
```
