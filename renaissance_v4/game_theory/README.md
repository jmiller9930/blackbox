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

Each line in the JSON file is one scenario object with `manifest_path` and optional `scenario_id`, `atr_stop_mult`, `atr_target_mult`.
