# Phase 1.7 runtime workflows

Run from the **repository root** (`blackbox/`).

**DATA** — SQLite + gateway + Ollama checks; three rows in `system_health_logs`; optional forced-failure URL writes one `alerts` row when the probe fails:

```bash
export BLACKBOX_SQLITE_PATH="${BLACKBOX_SQLITE_PATH:-data/sqlite/blackbox.db}"
python3 scripts/runtime/data_health_workflow.py
```

Optional: `GATEWAY_HEALTH_URL`, `OLLAMA_BASE_URL`, `--no-forced-failure`.

**Cody** — Ollama structured plan → one `tasks` row (agent `main`, state `planned`):

```bash
export BLACKBOX_SQLITE_PATH="${BLACKBOX_SQLITE_PATH:-data/sqlite/blackbox.db}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
python3 scripts/runtime/cody_plan_workflow.py "Your engineering request here"
```

On a host where the repo lives at `~/blackbox` and the DB is under that tree, set `BLACKBOX_SQLITE_PATH` to the absolute DB path if needed.
