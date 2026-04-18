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
