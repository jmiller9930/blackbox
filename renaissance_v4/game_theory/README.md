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

### Optional (agent / tier / window — **echoed in results, not scored**)

These are **whitelisted** and copied into each parallel result (and JSONL log lines) for operators and downstream ML:

| Field | Type | Meaning |
|-------|------|--------|
| `tier` | string | Game tier label, e.g. **`T1`**. Same engine; payload differs by tier in later phases. |
| `evaluation_window` | object | Declarative evaluation intent. For the standard **12‑month** run use e.g. `{ "calendar_months": 12 }` plus any notes. **Referee note:** replay today still uses the bar range available in SQLite until optional date/window slicing is implemented; this field is still **required contract** for comparisons and audit. |
| `game_spec_ref` | string | Which written spec this row follows (e.g. `GAME_SPEC_INDICATOR_PATTERN_V1.md`). |
| `agent_explanation` | object (recommended) or string | Partner- or agent-authored **story**: why this candidate, which values, what was learned, behavior vs prior. Suggested keys: `why_this_strategy`, `indicator_values`, `learned`, `behavior_change`. |
| `training_trace_id` | string | Idempotency / grouping id for a training or search batch. |
| `prior_scenario_id` | string | Link to the previous scenario in a curriculum or chain. |

**Rules:** The Referee **does not** use these fields for WIN/LOSS. Undocumented top-level keys are **ignored** by the runner (you may get a validation **warning** in the API).

### Tier 1 + twelve months (shared default)

For **everyone running the same T1 / 12‑month contract**, start from:

- **`examples/tier1_twelve_month.example.json`** — runnable preset with `tier: "T1"` and `evaluation_window.calendar_months: 12`.
- **`examples/tier1_scenario.template.json`** — same shape with empty `agent_explanation` strings for a partner to fill in (copy to a new file or paste in the web UI).

Other examples: `parallel_scenarios.example.json`, `parallel_scenarios_with_agent_trace.example.json`.

### Templates & pickle-friendly lists

- **Template:** JSON array of objects — copy `tier1_scenario.template.json`, edit `scenario_id` and `agent_explanation`, keep `tier` / `evaluation_window` unless the run definition changes.
- **Pickle / multiprocessing:** Build scenarios as **`list[dict]`** with **JSON types only** (`str`, `int`, `float`, `bool`, `null`, `list`, `dict`). Do **not** put `Path`, classes, or callables in scenario dicts; workers **pickle** each dict. Typical pattern: `scenarios = json.loads(path.read_text())` then `run_scenarios_parallel(scenarios, ...)`.

### Web UI

One screen: **preset** (loads `examples/*.json` into the editor) **or** **paste** your own JSON — that is the whole control surface. **Workers** slider: top end is the host **hard cap** from `get_parallel_limits()`; **default** starts at **recommended** (usually logical CPU count). Tier 1 example preset auto-loads when available. No separate “single run” or ATR fields in the UI.
