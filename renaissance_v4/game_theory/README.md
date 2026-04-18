# Game theory (prototype)

Small **pattern game** runner, spec, and **agent / training–related markdown** collected for experiments before product integration.

## Run the pattern game (CLI)

From repo root with `PYTHONPATH=.`:

```bash
python3 -m renaissance_v4.game_theory.pattern_game \
  --manifest renaissance_v4/configs/manifests/baseline_v1_recipe.json
```

Optional: `--atr-stop-mult 2.0 --atr-target-mult 3.0`  
Legacy import: `renaissance_v4.research.pattern_game` re-exports the same API.

## Documents in this folder

| File | Purpose |
|------|--------|
| `GAME_SPEC_INDICATOR_PATTERN_V1.md` | Pattern game rules, prohibitions, checklist |
| `shared_mind_multi_agent_architecture.md` | Shared-mind multi-agent trading research design |
| `agent_artifacts.md` | SRA artifact types (files still live in `state/agent_artifacts/`) |
| `MANIFEST_REPLAY_INTEGRATION.md` | Manifest-driven replay + SRA API notes |

## Code

- `pattern_game.py` — validate manifest → replay → binary WIN/LOSS scorecard
- `parallel_runner.py` — run **many** scenarios at once with a **process pool** (uses multiple CPU cores; GIL-safe). Appends optional JSONL to `experience_log.jsonl`.

### Parallel batch (maximize compute)

From repo root (`PYTHONPATH=.`):

```bash
python3 -m renaissance_v4.game_theory.parallel_runner \
  renaissance_v4/game_theory/examples/parallel_scenarios.example.json
```

`-j N` caps workers; `--log /path/to.jsonl` overrides the experience log path (default: `game_theory/experience_log.jsonl`).

Each **element** of the JSON array is one scenario object with `manifest_path` and optional `scenario_id`, `atr_stop_mult`, `atr_target_mult`.

## Scenario JSON contract (parallel batch)

**Purpose:** One **JSON array** of scenario **objects**. The **Referee** reads only what it needs to replay; optional fields carry **agent / ML / curriculum** metadata so every run can answer: *what was tried, why, which values, what changed vs last time* — without affecting deterministic scores.

### Required

| Field | Type | Meaning |
|-------|------|--------|
| `manifest_path` | string | Path to a validated strategy manifest (resolved from repo root when using `PYTHONPATH=.`). |

### Optional (replay)

| Field | Type | Meaning |
|-------|------|--------|
| `scenario_id` | string | Stable label for this row (defaults to `unknown` in results). |
| `atr_stop_mult` | number | Override stop distance as ATR multiple (game runner). |
| `atr_target_mult` | number | Override take-profit as ATR multiple. |
| `emit_baseline_artifacts` | boolean | Emit extra replay reports when true. |

### Optional (agent / training — **echoed in results, not scored**)

These are **whitelisted** and copied into each parallel result (and JSONL log lines) for operators and downstream ML:

| Field | Type | Meaning |
|-------|------|--------|
| `agent_explanation` | object (recommended) or string | **Why** this candidate was proposed, **which values** / knobs matter, **what was learned** from prior trials, and **how behavior changed** vs a prior scenario. Suggested object keys: `why_this_strategy`, `indicator_values`, `learned`, `behavior_change` (all freeform). |
| `training_trace_id` | string | Idempotency / grouping id for a training or search batch. |
| `prior_scenario_id` | string | Link to the previous scenario in a curriculum or chain. |

**Rules:** The Referee **does not** parse `agent_explanation` for WIN/LOSS. Undocumented top-level keys are **ignored** by the runner (you may get a validation **warning** in the API). For a filled-in example see `examples/parallel_scenarios_with_agent_trace.example.json`.

### Web UI presets

The local Flask UI can **load** any `*.json` file from `game_theory/examples/` via the preset dropdown so you do not have to paste JSON by hand.
