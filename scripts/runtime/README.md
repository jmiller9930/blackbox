# Phase 1.7–1.8 runtime workflows

Run from the **repository root** (`blackbox/`).

## Unified app stack (single launch command)

Bring up the full local operations stack (Hermes supervisor + Sentinel relay + Textual TUI) with one command:

```bash
python3 sentinel.py --start
```

Additional commands:

```bash
python3 sentinel.py --status
python3 sentinel.py --restart
python3 sentinel.py --stop
python3 sentinel.py --start --headless
```

Stack sequencing (enforced by `sentinel.py`):

- **Start order:** `hermes_supervisor.py` -> `sentinel_relay.py` -> `governance_monitor.py`
- **Stop order:** `governance_monitor.py` -> `sentinel_relay.py` -> `cursor-agent workers` -> `hermes_supervisor.py`
- **Restart order:** full stop order first, then full start order

Hermes supervisor artifacts (written under `.governance/`):

- `hermes_status.json` — live status, player health, active issues
- `hermes_skills.jsonl` — successful/failed auto-fix history (skill promotion ledger)

Directive publication safety (single-writer):

```bash
# Re-pin existing current_directive.md (no body write)
python3 scripts/runtime/governance_bus.py --agent Architect --type DIRECTIVE --issue-directive-atomic --phase A --content "..." --next-actor developer

# Write new directive body + pin hash in one locked transaction
python3 scripts/runtime/governance_bus.py --agent Architect --type DIRECTIVE --publish-directive-atomic --directive-input-file "/path/to/new_current_directive.md" --phase A --content "..." --next-actor developer
```

## Execution context — Phase 4.0

**[`docs/runtime/execution_context.md`](../docs/runtime/execution_context.md)** — phase, host, proof rules. **`context_loader.py`** prints JSON (preflight before mandated clawbot verification):

```bash
python3 scripts/runtime/context_loader.py
```

## Anna training — curriculum + method (operator CLI)

**Preflight:** `check-readiness` — Solana **RPC** (`SOLANA_RPC_URL` or public fallback), **Pyth** stream status file under `docs/working/artifacts/`, **`data/sqlite/market_data.db`** presence (ticks/snapshots for Anna when pipeline loads them). **Enforced:** all other `anna_training_cli` subcommands run this gate first (exit 5 on failure). Anna analyst (`anna_analyst_v1.py`), proposal builder, and Telegram `@anna` dispatch run the same **data-source** checks before producing output. Optional **`ANNA_PREFLIGHT_REQUIRE_SOLANA=1`** adds RPC to the gate. **`ANNA_SKIP_PREFLIGHT=1`** — tests/dev only.

Assign **grade 12 equivalent (paper only)**, invoke the **Karpathy-aligned loop** method, append **notes**. State: `data/runtime/anna_training/state.json` (gitignored; `BLACKBOX_ANNA_TRAINING_DIR` overrides). See **`docs/architect/ANNA_GOES_TO_SCHOOL.md`** §1.1.

```bash
python3 scripts/runtime/anna_training_cli.py check-readiness
python3 scripts/runtime/anna_training_cli.py status
python3 scripts/runtime/anna_training_cli.py curricula
python3 scripts/runtime/anna_training_cli.py assign-curriculum grade_12_paper_only
python3 scripts/runtime/anna_training_cli.py invoke-method karpathy_loop_v1
python3 scripts/runtime/anna_training_cli.py note "Operator check-in text"
```

**Paper trades + report card (Sean):** log each paper outcome (`won` / `lost` / `breakeven` / `abstain`) with P&L and timeframe; **`dashboard`** prints a Rich summary + table; **`report-card --out path.md --recipient Sean`** writes a markdown “grade 12” summary you can email or paste. Data: `data/runtime/anna_training/paper_trades.jsonl` (gitignored).

```bash
python3 scripts/runtime/anna_training_cli.py log-trade --symbol SOL-PERP --side long --result won --pnl-usd 12.5 --timeframe 5m --notes "optional"
python3 scripts/runtime/anna_training_cli.py dashboard
python3 scripts/runtime/anna_training_cli.py report-card --out docs/working/anna_grade12_report_card.md --recipient Sean --operator "Your name"
```

## Execution plane — Phase 4.3 (mock)

Approval-gated mock execution, kill switch, and audit to `system_events` (no schema change). **No** wallets, exchanges, or secrets.

```bash
python3 scripts/runtime/execution_cli.py create_execution_request
python3 scripts/runtime/execution_cli.py run_execution
python3 scripts/runtime/execution_cli.py approve_execution_request
python3 scripts/runtime/execution_cli.py toggle_kill_switch --off   # or --on
```

State: `data/runtime/execution_plane/` (gitignored JSON). With no `--request-id`, approve/run default to the **latest** request.

## Execution feedback — Phase 4.4 (+ 4.4.1 amendment)

Each `run_execution` appends **one** `system_events` row (`event_type`=`execution_feedback_v1`) with structured **outcome** and **insight** (`insight_kind`: `execution_succeeded` | `blocked_*`). Canonical store only — no duplicate task/file storage.

```bash
python3 scripts/runtime/execution_cli.py create_execution_request
python3 scripts/runtime/execution_cli.py approve_execution_request
python3 scripts/runtime/execution_cli.py run_execution
# persistence proof (example):
# sqlite3 data/sqlite/blackbox.db "SELECT event_type, payload FROM system_events WHERE source='execution_plane' ORDER BY created_at DESC LIMIT 5;"
```

## Learning visibility — Phase 4.5

Read-only query, JSON aggregates, and human-readable report over `execution_feedback_v1` rows (filters: `--insight-kind`, `--type success|failure`, `--request-id`).

```bash
python3 scripts/runtime/learning_cli.py list_insights
python3 scripts/runtime/learning_cli.py summarize_insights
python3 scripts/runtime/learning_cli.py generate_report
```

## Slack — operator messaging (Phase 4.6 / 4.6.1 / 4.6.2)

**Primary human channel:** **Slack** (Socket Mode). Set **`messaging.backend`** to **`slack`** in `config/messaging_config.json` (see **Messaging interface — Directive 4.6.3.4** below). The same **multi-persona** routing applies: **`@anna`**, **`@data`** (`status` / `report` / `insights` or free text), **`@cody`** (engineering stub); unprefixed defaults; `[Anna]` / `[DATA]` / `[Cody]` labels in formatted replies. **No** execution, approval, or kill switch from chat.

Implementation still uses the shared **`telegram_interface/`** dispatch + **`response_formatter`** path internally (Directive 4.6.3.3); Slack is the transport — not a second Anna brain.

**Context engine (DATA hashtags):** **`#context_engine`** — snapshot from the context-engine status model (🟢 online / 🟡 degraded / 🔴 offline or problem), with restart hints when not healthy. **`#status`** — same context-engine block plus the execution/phase snapshot (`build_status_text`). The UI can mirror this with green/yellow/red indicators against the same status fields.

**Composable hashtags:** message = **only** `#tokens` (e.g. `#status #system` = full stack; `#status #context_engine` = that slice). See [`docs/runtime/slack_hashtag_language.md`](../docs/runtime/slack_hashtag_language.md).

**Anna LLM (Ollama) — messaging path:** use **`ANNA_USE_LLM`** (`0` = rules/playbook only, e.g. CI). For Telegram-only overrides, **`ANNA_TELEGRAM_USE_LLM`** exists in the legacy bot path. Set **`OLLAMA_BASE_URL`** to the network LLM host on clawbot (not localhost unless Ollama runs there). Set **`OLLAMA_MODEL`** to a tag present on that host. Optional **`OLLAMA_STRICT=1`** requires `OLLAMA_BASE_URL` to be set. Verify before start:

```bash
cd scripts/runtime && PYTHONPATH=. python3 tools/check_ollama_runtime.py
```

### Telegram (optional / lab only)

**Not** the operator channel in current practice. Optional **`backend: telegram`** in `config/messaging_config.json`, or run **`python3 scripts/runtime/telegram_interface/telegram_bot.py`** with **`TELEGRAM_BOT_TOKEN`**, for legacy tests or isolated lab use.

## Messaging interface — Directive 4.6.3.3 (CLI validation)

Anna dispatch runs through **`messaging_interface`** (`run_dispatch_pipeline` → shared formatter; Slack uses the same normalized payload). **Primary validation surface:**

```bash
# from repository root (blackbox/)
echo "What day is it?" | python3 -m messaging_interface.cli_adapter
```

Prints **JSON** with normalized fields (`interpretation.summary`, `answer_source`, `intent`, `topic`, `limitation_flag` for Anna). Phase closure requires this path per directive.

### Messaging interface — Directive 4.6.3.4 (config + single backend)

**Unified entry** (loads `config/messaging_config.json`, or falls back to `config/messaging_config.example.json`):

```bash
# from repository root — backend is `cli` | `slack` | `telegram` in config
echo "What day is it?" | python3 -m messaging_interface
```

Copy `config/messaging_config.example.json` to `config/messaging_config.json` (gitignored) and set **`messaging.backend`**. Optional env overrides (merged after file load): **`TELEGRAM_BOT_TOKEN`**, **`SLACK_BOT_TOKEN`**, **`SLACK_APP_TOKEN`**.

**Slack (Socket Mode):** set `backend` to `slack`, fill `messaging.slack.bot_token` (starts with `xoxb-`) and `app_token` (`xapp-`), enable Socket Mode and subscribe to **`message.channels`** / **`message.im`** (and scopes `chat:write`, `users:read` as needed). Requires **`slack-bolt`** (`requirements.txt`). The adapter calls **`run_dispatch_pipeline`** only — same dispatch as CLI (and optional Telegram backend), not a separate Anna path.

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

### Operator notifications — Slack (primary) / SMS (optional)

**Module:** `modules/notification_gateway/` — short **trade**, **system**, and **Anna training** templates (who/what/when/where). **Recommended default in lab:** **Slack Incoming Webhook** — set `BLACKBOX_NOTIFY_MODE=webhook`, `BLACKBOX_NOTIFY_WEBHOOK_URL` to your Slack app’s Incoming Webhook URL, and **`BLACKBOX_NOTIFY_WEBHOOK_FORMAT=slack`** so each notify posts **`{"text": "..."}`** with tier line + body + recipient names (one HTTP POST per event for the whole distro). SMS remains available via **Twilio** (`BLACKBOX_NOTIFY_MODE=twilio` + `TWILIO_*`) or **Textbelt** (`BLACKBOX_NOTIFY_MODE=textbelt`; optional `BLACKBOX_NOTIFY_TEXTBELT_KEY`; US `+1` only on hosted API — use when you return to SMS).

**Priority tiers (SMS):** bodies are prefixed **`T1` / `T2` / `T3`** — **T1** trading, **T2** system/availability, **T3** agents/training. **`BLACKBOX_NOTIFY_SMS_TIERS`** (default `1,2,3`) lists which tiers may send SMS; e.g. `1,2` silences tier-3 training/agent texts while keeping money and ops alerts.

**Routine trades → T3 (optional):** set **`BLACKBOX_NOTIFY_TRADE_ROUTINE_TIER=yes`** (or `3` / `on`) so benign statuses like “filled” route to tier 3; loss/reject/error patterns stay tier 1.

**Recipients (distro):** in order of precedence — `BLACKBOX_NOTIFY_DISTRO` (comma-separated E.164), `BLACKBOX_NOTIFY_RECIPIENTS_PATH`, `config/notification_recipients.local.json` (gitignored; copy from [`config/notification_recipients.example.json`](../config/notification_recipients.example.json)), then `config/notification_recipients.json`, else legacy **`BLACKBOX_NOTIFY_PHONE_E164`** for a single number.

**DATA health → SMS:** `BLACKBOX_NOTIFY_SYSTEM=1` broadcasts a **tier-2** system alert to the distro when the workflow writes an **`alerts`** row (watchdog transition or forced-failure probe). Optional **`BLACKBOX_HOST_LABEL`** appears as “Where”.

**Anna / training milestones:** call **`notify_training_milestone(event_kind=..., summary=...)`** (tier **3**) from the university or training layer when Anna **graduates**, **completes** a phase, or **improves** on a metric (wire those call sites when that state machine exists).

**Trade path:** call **`notify_trade(...)`** (tier **1** by default, or **3** for routine when env allows) from the execution / approval layer when a ticket is placed or terminal state is known (does not auto-wire from chat).

**Test notify:** `python3 scripts/runtime/tools/send_notification_test.py --ping` (standard one-line: *“This is a system test from the BLACK BOX engine.”*; `--dry-run` prints body only). Same flags with Twilio or webhook: `--who john` / `sean` / `all`; `--kind system|trade|training`; **`--list-sms-tiers`**; **`--trade-status`**.

Example keys / webhook fields: [`config/notification_gateway.example.json`](../config/notification_gateway.example.json).

**Backend / workspace panel (for the UI API developer):** wire **operator-only** controls that delegate to `modules/notification_gateway` (same behavior as `scripts/runtime/tools/send_notification_test.py`). Do **not** duplicate Twilio HTTP; import `notify_system`, `notify_trade`, `notify_training_milestone`, `resolve_recipient_targets`, `parse_sms_allowed_tiers`, and/or call the script.

| Concern | Guidance |
|--------|----------|
| **Persistence** | Store distro as JSON array `[{ "name", "phone_e164" }]` in SQLite (preferred) or atomic write to `config/notification_recipients.json` under repo root; avoid committing secrets. Optional: sync to `BLACKBOX_NOTIFY_RECIPIENTS_PATH` or document that the API process sets `os.environ["BLACKBOX_NOTIFY_RECIPIENTS_PATH"]` to a server-only file before each send. |
| **Read API** | `GET /api/v1/notify/recipients` — list names + masked last-4 only in UI; full E.164 only for authorized edit flows if needed. |
| **Write API** | `PUT /api/v1/notify/recipients` — replace list (validate E.164 with `normalize_to_e164` from `recipients.py`). |
| **Env mirror (optional)** | `GET/PUT /api/v1/notify/settings` — expose `BLACKBOX_NOTIFY_SMS_TIERS`, `BLACKBOX_NOTIFY_MODE` (read-only or admin), `BLACKBOX_HOST_LABEL` for display; applying changes may require process env reload or a small sidecar that only the notify worker reads. |
| **Test send** | `POST /api/v1/notify/test` — body `{ "to": "john" \| "all", "kind": "ping" \| "system" \| "trade" \| "training" }`. Map `ping` → `notify_system(..., component=blackbox_engine, summary=PING_SENTENCE)` as in `send_notification_test.py`. Require **internal staff** auth (same gate as other portal control APIs). Return `{ "ok", "detail" }` from gateway tuple; never log full phone numbers. |
| **Process** | SMS runs **on the host** that has `TWILIO_*` and outbound HTTPS (e.g. clawbot). If the UI API runs in a container, either mount env/secrets there or invoke an **SSH/exec** helper on the lab host—same pattern as other “truth on primary host” jobs. |
| **Panel UX** | Workspace strip or **System** area: table of recipients, **Save**, **Send test (ping)** / kind selector, link to `docs/runtime/slack_hashtag_language.md` for Slack; separate from Slack hashtag doc. |

## Cody — structured plan → task row

```bash
export BLACKBOX_SQLITE_PATH="${BLACKBOX_SQLITE_PATH:-data/sqlite/blackbox.db}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
python3 scripts/runtime/cody_plan_workflow.py "Your engineering request here"
```

Task `description` is JSON with `schema_version`, normalized fields, `parse_method` (`json` | `headings` | `fallback`), and `raw_model_output`.

## Shared docs foreman

**`shared_docs_foreman`** validates the active shared-doc directive against code/test/proof, then automatically writes either:

- a **closure** note when requirements are satisfied, or
- an **amending directive** when closure requirements are missing

Run from the repository root:

```bash
cd scripts/runtime && python3 -m shared_docs_foreman --dry-run
cd scripts/runtime && python3 -m shared_docs_foreman
```

The foreman reads:

- `docs/working/current_directive.md`
- `docs/working/shared_coordination_log.md`

Current specialization: **Phase 5.1 foundation** closure checks.

**Context packet gate (CANONICAL #013):** [`foreman_v2/context_packet_gate.py`](foreman_v2/context_packet_gate.py) — fail-closed validation of Foreman/orchestration context packets (directive hash, bus hash gate, lane epoch, freshness, consumers). See [`modules/context_ledger/README.md`](../../modules/context_ledger/README.md). Replay: `python3 -m pytest tests/test_context_packet_validator.py -q` and `python3 scripts/runtime/governance_bus.py --peek`.

## Foreman app mode

`shared_docs_foreman --app` is the durable app/runtime mode. It combines:

- validation + bridge-state refresh
- orchestrated handoff processing
- bounded developer loop around `cursor-agent`
- stale-turn tracking in app state

Run it from `scripts/runtime`:

```bash
python3 -m shared_docs_foreman --app
python3 -m shared_docs_foreman --app --watch --interval 15
```

**Safety (runaway prevention):**

- **`FOREMAN_ALLOW_GUI_AUTOMATION=1`** is required for Cursor UI automation; default is off unless set.
- **`FOREMAN_UI_CHAT_AUTOSEND=1`** is required to paste/send into chat; keep off unless you intend it.
- **`/tmp/blackbox-foreman.kill`** — create this file to block all GUI automation (same as operator UI “Kill GUI Automation”).
- With **`--app --watch`**, the CLI enforces a **minimum 15s** sleep between cycles so a LaunchAgent cannot hammer the desktop every few seconds.
- Bridge JSON is written only when **semantic** bridge fields change (not every tick), and the orchestrator **does not** repeat failed stick transfers, handoff history lines, or `mirror_handoff` on every poll while stuck.

Tuning flags:

```bash
python3 -m shared_docs_foreman --app --retry-after 180 --max-developer-attempts 3 --max-architect-attempts 2
```

State / logs:

- `docs/working/foreman_app_state.json`
- `docs/working/foreman_developer_loop_state.json`
- `~/Library/Logs/blackbox/foreman-developer-loop.log`

LaunchAgent source now targets `--app` so the background Foreman service runs the full app loop instead of only the bridge/orchestrator path.

### Foreman app mode

Foreman now also has an **app loop** that acts as the outer coordinator around the validator/orchestrator:

- validates shared docs
- updates bridge / talking-stick / queue state
- detects stale turns
- re-invokes the developer side when a developer-held turn has stalled
- sends visible nudges into the Cursor thread when a turn is stale

Run once:

```bash
cd scripts/runtime && python3 -m shared_docs_foreman --app
```

Run continuously:

```bash
cd scripts/runtime && python3 -m shared_docs_foreman --app --watch --interval 3
```

Useful knobs:

```bash
cd scripts/runtime && python3 -m shared_docs_foreman --app --watch --interval 3 --retry-after 180 --max-developer-attempts 3 --max-architect-attempts 2
```

App state is persisted in:

- `docs/working/foreman_app_state.json`

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

## Insight trends — Phase 2.10

**`insight_trend_tracker.py`** — Aggregates the latest **N** **`[System Insight]`** tasks (`--recent`, default **10**, max **100**) into **`system_trend_v1`**: outcome / alignment / risk / structural / readiness trends, **recent vs prior** half-windows, **`flags`** (e.g. misalignment rising, persistent alerts, structural gaps). Deterministic; no ML. **`--store`** → **`[System Trend]`** completed task.

```bash
python3 scripts/runtime/insight_trend_tracker.py
python3 scripts/runtime/insight_trend_tracker.py --recent 10
python3 scripts/runtime/insight_trend_tracker.py --store
```

## Guardrail policy — Phase 2.11

**`guardrail_policy_evaluator.py`** — Rule-based **operating mode**: `FROZEN` | `CAUTION` | `NORMAL` from **decision context** (live `build_payload` or **`--use-latest-stored-decision-context`**) plus **system trend** (live from recent **`[System Insight]`** rows or **`--use-latest-stored-trend`**). Optional **`--include-insight-reference`**. Output: **`guardrail_policy_v1`**. **`--store`** → **`[Guardrail Policy]`** completed task. **`--self-test`** runs local FROZEN/CAUTION/NORMAL checks (no DB).

```bash
python3 scripts/runtime/guardrail_policy_evaluator.py --use-latest-stored-decision-context --trend-recent 10
python3 scripts/runtime/guardrail_policy_evaluator.py --use-latest-stored-decision-context --use-latest-stored-trend
python3 scripts/runtime/guardrail_policy_evaluator.py --self-test
python3 scripts/runtime/guardrail_policy_evaluator.py --store
```

## Policy-gated action — Phase 2.12

**`policy_gated_action_filter.py`** — Combines **guardrail policy** (live `build_guardrail_document` or **`--use-latest-stored-policy`**) with **simulated action** (live `compute_simulated_action` or **`--use-latest-stored-simulated-action`**). Emits **`policy_gated_action_v1`**: `FROZEN` → **`BLOCKED`** / `FROZEN_BLOCK`; **`CAUTION`** → pass-through for HOLD/WATCH, downgrade **`PAPER_TRADE_READY`** → **`WATCH`** / `CAUTION_DOWNGRADE`; **`NORMAL`** → pass-through / `NORMAL_PASS`. Optional **`--include-optional-refs`**. **`--store`** → **`[Policy Gated Action]`**. **`--self-test`** exercises all three policy results without DB.

```bash
python3 scripts/runtime/policy_gated_action_filter.py --use-latest-stored-policy --use-latest-stored-simulated-action
python3 scripts/runtime/policy_gated_action_filter.py --self-test
python3 scripts/runtime/policy_gated_action_filter.py --store
```

## Anna analyst — Phase 3.2 (v1) + Phase 3.6 (concept retrieval)

**`anna_analyst_v1.py`** — Rule-based **conversational analyst**: trader text → **`anna_analysis_v1`** (runs **data-source preflight** first; stderr JSON + exit **5** on failure). (interpretation, market_context from optional latest **`[Market Snapshot]`**, risk, policy alignment from optional **`[Guardrail Policy]`**, paper-only **`suggested_action`**, **`concepts_used`**, **`concept_support`**, optional **`strategy_awareness`** — Phase 3.8 awareness-only strategy language). **`concepts_used`** lists registry **`concept_id`**s when language matches seeded concepts; **`concept_support`** includes concise **`concept_summaries`** only for those IDs (read-only; not a full registry load). Optional **`--use-latest-decision-context`**, **`--use-latest-trend`** (**`[System Trend]`**). Missing artifacts → null-safe + **`notes`**. No chat transport, no registry **mutation**, no execution, no venue calls. **`--store`** → **`[Anna Analysis]`** completed task.

```bash
python3 scripts/runtime/anna_analyst_v1.py "Liquidity is thin and spreads are widening"
python3 scripts/runtime/anna_analyst_v1.py "Spreads widening" --use-latest-market-snapshot --use-latest-policy --use-latest-trend
python3 scripts/runtime/anna_analyst_v1.py "Test input" --store
```

## Anna proposal builder — Phase 3.3

**`anna_proposal_builder.py`** — Bridges Anna analysis to **`anna_proposal_v1`**: `NO_CHANGE` \| `RISK_REDUCTION` \| `CONDITION_TIGHTENING` \| `OBSERVATION_ONLY`, **`validation_plan`**, **`proposed_effect`** (paper-only). Consumes **`--use-latest-stored-anna-analysis`** or **live** trader text with optional **`--use-latest-market-snapshot`**, **`--use-latest-decision-context`**, **`--use-latest-trend`**, **`--use-latest-policy`**. **`--store`** → **`[Anna Proposal]`**. Reuses **`anna_analyst_v1.build_analysis`** (includes registry-backed **`concepts_used`** / **`concept_support`** when matched). No chat transport.

```bash
python3 scripts/runtime/anna_proposal_builder.py "Liquidity is thin and spreads are widening" --use-latest-market-snapshot --use-latest-policy
python3 scripts/runtime/anna_proposal_builder.py --use-latest-stored-anna-analysis
python3 scripts/runtime/anna_proposal_builder.py "Test proposal" --store
```

## Anna modular package — Phase 3.4

**`scripts/runtime/anna_modules/`** — Internal layers (not standalone user scripts):

| Layer | Module | Role |
|-------|--------|------|
| Input adaptation | `input_adapter.py` | `normalize_trader_text`; load `[Market Snapshot]`, `[Decision Context]`, `[System Trend]`, `[Guardrail Policy]`, stored `[Anna Analysis]`. |
| Interpretation | `interpretation.py` | Keyword → `concepts_used`; summary / signals / assumptions. |
| Risk reasoning | `risk.py` | Risk level, factors, market_context numeric notes. |
| Policy alignment | `policy.py` | Guardrail mode, alignment vs intent, paper-only suggested action. |
| Analysis assembly | `analysis.py` | **`build_analysis`** / **`assemble_anna_analysis_v1`** → `anna_analysis_v1`. |
| Context ledger (Phase 5.9) | `context_ledger_consumer.py` | Optional validated **`ContextBundle`** attach to `anna_analysis_v1` (`context_ledger` key when engaged). After validation, **`contextProfile`** from **`agents/agent_registry.json`** is enforced (CANONICAL #009 — `allowedContextClasses` vs record classes; fail closed). Optional **`build_analysis(..., context_profile_registry_path=…)`** for tests or alternate registry. CLI: **`anna_analyst_v1.py --context-bundle-path`** or env **`ANNA_CONTEXT_BUNDLE_PATH`**. Inert when unset. |
| Online activation gate (Phase 5.9) | *(library)* [`modules/context_ledger/online_activation_evaluator.py`](../../modules/context_ledger/online_activation_evaluator.py) | CANONICAL #011 — read-only **`evaluate_online_activation()`** for §5.9.8 checklist gates; does not alter Anna runtime paths. |
| Proposal shaping | `proposal.py` | **`build_anna_proposal`** / **`assemble_anna_proposal_v1`** → `anna_proposal_v1`. |
| Shared utils | `util.py` | Schema versions, `utc_now`, float helpers. |

**Entrypoints:** `anna_analyst_v1.py` and `anna_proposal_builder.py` import these modules; behavior stays compatible with Phase 3.2 / 3.3. **Advanced reasoning** remains a future phase — extend by adding or editing focused modules, not by growing one flat script.

## Runtime concept retrieval — Phase 3.6

**`anna_modules/concept_retrieval.py`** — Read-only link from Anna to **`data/concepts/registry.json`**: regex detection aligned to registry **`concept_id`**s, **`retrieve_concept_support()`** returns **`concepts_used`** IDs plus **`concept_support`** (`concept_ids`, **`concept_summaries`**). Reuses **`concept_registry_reader`**. **No** registry writes, **no** full-registry embed in output.

## Concept staging & ingestion — Phase 3.7

**`data/concepts/staging_registry.json`** — **`kind`: `trading_concept_staging_v1`**. **Candidate** concepts before they are canonical. This is **not** [`registry.json`](../../data/concepts/registry.json); there is **no** automatic promotion—merge to the canonical registry only via **PR/review** after evidence.

**Lifecycle (staging):** `draft` → `under_test` → `validated` \| `rejected`.

**`concept_ingestor.py`** — JSON only on stdout:

```bash
python3 scripts/runtime/concept_ingestor.py --add --concept-id my_concept --source-type expert \
  --definition "Proposed definition text." --rationale "Why we are capturing this." \
  --signals "signal_a,signal_b" --impact "Expected effect if adopted."
python3 scripts/runtime/concept_ingestor.py --update my_concept --status under_test
python3 scripts/runtime/concept_ingestor.py --list
python3 scripts/runtime/concept_ingestor.py --concept my_concept
```

Optional: `--source-reference`, `--evidence-links` (comma-separated or JSON array). **No** Anna wiring, **no** `registry.json` mutation, **no** new DB tables.

## Advanced strategy awareness — Phase 3.8

**`interpretation.py` + `analysis.py`** — Detects awareness-only strategy language (e.g. market making, spread capture, adverse selection, thin books). **`anna_analysis_v1`** may include **`strategy_awareness`** (`detected`, `explanation`, `risks`, `applicability`, `note`) or **`null`** when nothing matches. **Awareness ≠ execution:** descriptive and advisory only; **no** trade commands, **no** automation, **no** registry writes, **no** policy bypass.

## Trading concept registry — Phase 3.5 (scaffold)

**Canonical file:** **`data/concepts/registry.json`** — **`kind`: `trading_concept_registry_v1`**, versioned in Git. The registry is **canonical memory** for trading concepts; **not** the LLM. Changes happen through **PR/review**, not runtime mutation.

**Seeded concepts (v1):** Foundation — `price`, `bid`, `ask`, `spread`, `market_order`, `limit_order`, `volume`, `liquidity`, `candle`, `timeframe`. Mechanical — `slippage`, `depth`, `price_impact`, `volatility`, `maker_taker`. Each entry includes `definition`, `trader_meaning`, `why_it_matters`, `data_signals`, impacts, `failure_modes`, `examples`, `status`, `version`.

**`concept_registry_reader.py`** — Read-only JSON queries (Anna consumes via Phase 3.6 `concept_retrieval`):

```bash
python3 scripts/runtime/concept_registry_reader.py --list
python3 scripts/runtime/concept_registry_reader.py --concept slippage
python3 scripts/runtime/concept_registry_reader.py --search liquidity
```

Unknown `--concept` → `found: false` (no fabricated definitions). **No** `tasks` storage by default.

## Hermes PM stack (operator goal — do this in order)

**Goal:** Hermes as **PM voice** in Cursor + **repo** as the bus so **architect/Codex** can run governance.

1. **LLM host (`172.20.2.230` or your host):** Enable API server env vars and run **`hermes gateway`** on port **8642** bound so the host can reach it. See **`scripts/runtime/hermes_gateway_llm_host.example.sh`**. On the host: `curl -sS http://127.0.0.1:8642/health` must return OK.
2. **Mac:** `cp ops/hermes_pm.env.example ops/hermes_pm.env` — set **`HERMES_API_KEY`** to match **`API_SERVER_KEY`** on the server. Run **`./scripts/runtime/hermes_pm_stack.sh`** (starts SSH tunnel, checks health). Use **`status`** / **`stop`** as needed.
3. **Cursor → Models:** Custom OpenAI-compatible — **Base URL** `http://127.0.0.1:8642/v1`, **API key** from `ops/hermes_pm.env`, **model** `hermes-agent`. **Select that model** in the chat where you want Hermes.
4. **Cursor → MCP:** Keep **`hermes`** (tools) and **`pm`** (repo directive + **`pm_request_architect_governance`** ping) **green**.
5. **Nudge architect/Codex:** Use **`pm_request_architect_governance`** or paste the handoff phrase per **`docs/architect/development_governance.md`**. Nothing auto-invokes Codex; **shared docs** are the contract.

**Plain rule:** MCP **`hermes`** = tools. **Gateway + tunnel + custom model** = Hermes **in chat**. Both can be on at once.

### Hermes agent in Cursor chat (OpenAI-compatible, not MCP)

**MCP (`hermes mcp serve`) adds tools; it does not replace the model in the chat.** To get **Hermes’s personality and full agent** as the model answering in Cursor, use Hermes’s **HTTP API** (`hermes gateway`), which is **OpenAI-compatible**.

Official docs: [Hermes API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server).

### On the LLM host

1. Set `API_SERVER_ENABLED=true`, `API_SERVER_KEY` (long random secret), `API_SERVER_HOST=0.0.0.0`, `API_SERVER_PORT=8642` in the env Hermes reads (see Hermes docs; often a mounted `.env` under `/opt/data`).
2. Run **`hermes gateway`** (not only `sleep` in the container). Publish **`127.0.0.1:8642`** to the host. Commented example: **`scripts/runtime/hermes_gateway_llm_host.example.sh`**.
3. Verify: `curl -sS http://127.0.0.1:8642/health` on the host.

### On your Mac (before using Cursor)

Prefer **`./scripts/runtime/hermes_pm_stack.sh`** (tunnel + health check). Alternatively run **`scripts/runtime/hermes_cursor_tunnel_mac.sh`** and leave the terminal open — it forwards `localhost:8642` on the Mac to the remote gateway.

### In Cursor

**Settings → Models:** add a **custom / OpenAI-compatible** model:

- **Base URL:** `http://127.0.0.1:8642/v1`
- **API key:** same value as `API_SERVER_KEY`
- **Model id:** `hermes-agent` (Hermes accepts this field; actual LLM is configured server-side)

Select that model in the chat. **Security:** the tunnel + key mean only your machine with SSH access talks to Hermes; do not expose `0.0.0.0:8642` on the public internet without a VPN or stricter controls.

### Governance ping (Codex / architect)

The **`pm`** MCP server tool **`pm_request_architect_governance`** appends an operator line to **`docs/working/shared_coordination_log.md`** asking the architect to run Phase C validation. It does **not** invoke Codex automatically; it records the ask in shared docs per **`docs/architect/development_governance.md`**.
