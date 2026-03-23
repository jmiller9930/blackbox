# Phase 1.7–1.8 runtime workflows

Run from the **repository root** (`blackbox/`).

## Execution context — Phase 4.0

**[`docs/runtime/execution_context.md`](../docs/runtime/execution_context.md)** — phase, host, proof rules. **`context_loader.py`** prints JSON (preflight before mandated clawbot verification):

```bash
python3 scripts/runtime/context_loader.py
```

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

**`anna_analyst_v1.py`** — Rule-based **conversational analyst**: trader text → **`anna_analysis_v1`** (interpretation, market_context from optional latest **`[Market Snapshot]`**, risk, policy alignment from optional **`[Guardrail Policy]`**, paper-only **`suggested_action`**, **`concepts_used`**, **`concept_support`**, optional **`strategy_awareness`** — Phase 3.8 awareness-only strategy language). **`concepts_used`** lists registry **`concept_id`**s when language matches seeded concepts; **`concept_support`** includes concise **`concept_summaries`** only for those IDs (read-only; not a full registry load). Optional **`--use-latest-decision-context`**, **`--use-latest-trend`** (**`[System Trend]`**). Missing artifacts → null-safe + **`notes`**. No Telegram, no registry **mutation**, no execution, no venue calls. **`--store`** → **`[Anna Analysis]`** completed task.

```bash
python3 scripts/runtime/anna_analyst_v1.py "Liquidity is thin and spreads are widening"
python3 scripts/runtime/anna_analyst_v1.py "Spreads widening" --use-latest-market-snapshot --use-latest-policy --use-latest-trend
python3 scripts/runtime/anna_analyst_v1.py "Test input" --store
```

## Anna proposal builder — Phase 3.3

**`anna_proposal_builder.py`** — Bridges Anna analysis to **`anna_proposal_v1`**: `NO_CHANGE` \| `RISK_REDUCTION` \| `CONDITION_TIGHTENING` \| `OBSERVATION_ONLY`, **`validation_plan`**, **`proposed_effect`** (paper-only). Consumes **`--use-latest-stored-anna-analysis`** or **live** trader text with optional **`--use-latest-market-snapshot`**, **`--use-latest-decision-context`**, **`--use-latest-trend`**, **`--use-latest-policy`**. **`--store`** → **`[Anna Proposal]`**. Reuses **`anna_analyst_v1.build_analysis`** (includes registry-backed **`concepts_used`** / **`concept_support`** when matched). No Telegram.

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
| Proposal shaping | `proposal.py` | **`build_anna_proposal`** / **`assemble_anna_proposal_v1`** → `anna_proposal_v1`. |
| Shared utils | `util.py` | Schema versions, `utc_now`, float helpers. |

**Entrypoints:** `anna_analyst_v1.py` and `anna_proposal_builder.py` import these modules; behavior stays compatible with Phase 3.2 / 3.3. **Telegram** and **advanced reasoning** remain future phases — extend by adding or editing focused modules, not by growing one flat script.

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
