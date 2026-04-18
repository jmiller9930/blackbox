# Pattern game + player agent — team brief

**Repo:** `renaissance_v4/game_theory/` · **Plug-in type:** `PatternGameAgent` (`from renaissance_v4.game_theory import PatternGameAgent`)

**Why we’re here (pattern discovery, indicator context):** **`QUANT_RESEARCH_AGENT_DESIGN.md`**.

This note is what operators and integrators can forward as-is: what runs, what does **not** run, and how to kick off jobs.

---

## What this stack does

1. **Referee (deterministic replay)** — Loads strategy manifests, replays stored bars, emits WIN/LOSS-style summaries (PnL, trades, etc.). **Scores are not from an LLM.**

2. **Player agent layer** — Wraps the same parallel batch, adds **audit fields** (`agent_explanation`, tier/window echo, etc.), and builds a **markdown operator report** from Referee results.

3. **Anna (optional)** — Same Ollama stack as runtime Anna (`scripts/runtime`). She can append an **advisory narrative** from the report text. She does **not** change scores and does **not** replace governance.

4. **Repo context (optional)** — `ANNA_CONTEXT_PROFILE` + `scripts/agent_context_bundle.py` can prepend **checked-in docs** (e.g. game spec, policy package standard) into Anna’s prompt. That is **context injection**, not model training.

---

## What “training the agent” does **not** mean

- We are **not** fine-tuning or updating LLM weights in this module.
- **“Experience”** is persisted as: **git** (specs, manifests), **JSONL logs** (optional), and **your scenario JSON** — not gradient updates.

If the team needs **formal Jupiter policy packages** (JUP), that path is still **`scripts/validate_policy_package.py`** and the layout in `docs/architect/policy_package_standard.md`. The pattern game helps you **compare manifests and runs**; it does **not** emit finished policy packages by itself.

---

## Training the **orchestrator agent** (not the LLM)

If you do not care about weight training, “train the agent” still matters as **repeatable improvement of the runner + memory**:

| In place now | What it does |
|----------------|---------------|
| **Presets + custom JSON** | Swap scenario batches to explore manifests and story fields. |
| **Echo fields** | `training_trace_id`, `prior_scenario_id`, `agent_explanation` — audit trail and curriculum hooks. |
| **JSONL log** | Optional append of **one line per scenario result** for offline analysis. |
| **`run_memory.jsonl`** | Structured **append-only** lines: hypothesis + `indicator_context` + manifest hash + Referee metrics + `decision_audit` + `post_mortem` placeholders (`run_memory.py`). Pattern game: `--memory-log default`; batch: `--run-memory` or `RUN_MEMORY_LOG`. Not gradient learning — **durable audit + curriculum hooks**. |
| **`logs/` session folders** | Every pattern-game run (default): `logs/run_<UTC>_<id>/HUMAN_READABLE.md` + `run_record.json` + `SESSION.txt`. Parallel batches: `logs/batch_<UTC>_<id>/BATCH_README.md` + one subfolder per scenario. Disable: `--no-session-log` or `PATTERN_GAME_NO_SESSION_LOG=1`. Base path: `PATTERN_GAME_SESSION_LOGS_ROOT` or `--session-logs-root`. |
| **Memory bundle (behavior)** | Optional JSON (`pattern_game_memory_bundle_v1`) merges **whitelisted** manifest keys (ATR multiples today) **before** replay — **memory affects execution**. CLI: `--memory-bundle` / `PATTERN_GAME_MEMORY_BUNDLE`. Scenarios: `memory_bundle_path`. Enforce: `PATTERN_GAME_REQUIRE_MEMORY_BUNDLE=1`. Example: `examples/memory_bundle_example.json`. `decision_audit` records when a bundle was applied. |
| **RAM / instant I/O** | Export **`PATTERN_GAME_MEMORY_ROOT=/path/to/tmpfs`** — all default paths use that tree: `logs/`, `run_memory.jsonl`, `experience_log.jsonl`. Mount tmpfs (Linux) or a ramdisk; permanence = whatever that filesystem provides (sync elsewhere if you need survive reboot). See `memory_paths.py`. |
| **Single-silo + context (RAG scope)** | Memory is **one silo** (pattern-game / replay), not the universe. **`indicator_context`** must carry **context around indicators** (regime, direction, transition, velocity) — “six feet of water” without tide direction is **noise**. Every `run_record` includes `context_silo` + `indicator_context_quality`; see `context_memory.py` and the tide block in `HUMAN_READABLE.md`. |
| **Anna + LLM (factual help)** | `player_agent` + Ollama: **`anna_narrate_pattern_report`** and **`anna_answer_operator_question`**. Repo prefix from `scripts/agent_context_bundle.py` — **`pattern_game`** profile includes game spec + `QUANT_RESEARCH_AGENT_DESIGN.md` + `context_memory.py` + **Renaissance V4 fusion source** (`renaissance_v4/core/fusion_engine.py`, `signal_weights.py`, `fusion_result.py`) so explanations can align with the same deterministic math as replay. If `ANNA_CONTEXT_PROFILE` is empty/none, calls default it to **pattern_game** so she is not “alone” without docs. CLI: ``--ask "…"`` for a standalone question. She does **not** change Referee scores. |
| **Hypothesis gate** | `PATTERN_GAME_REQUIRE_HYPOTHESIS=1` or `validate_scenarios(..., require_hypothesis=True)` — blocks scenarios with empty `agent_explanation.hypothesis`. |
| **Repo context** | `ANNA_CONTEXT_PROFILE` + `agent_context_bundle` — same governance docs every call. |
| **`PatternGameAgent`** | Single import for host apps; `plugin_info()` for dashboards. |

**Reasonable follow-ons (staged, not all implemented):** retrieval over `experience_log.jsonl` + past reports; ranked “next scenario” suggestions from Referee stats; Foreman-triggered batches; export paths that **hand off** to a human-run `validate_policy_package.py` on a real package folder. Say the word when you want one of these cut as a ticket.

---

## Web UI: financial data status (green / red)

The local Flask UI (`python3 -m renaissance_v4.game_theory.web_app`) shows a **status strip** at the top: green when the **SQLite** DB is readable, **`market_bars_5m`** exists, replay has **enough rows** (same minimum as `replay_runner`), and **SOLUSDT** has at least a **~335-day** calendar span (12-month style check with slack for gaps).

**API:** `GET /api/data-health` — JSON with `overall_ok`, `summary_line`, counts, spans, and `database_path` for operators.

---

## Plug-in API (for applications)

```python
from pathlib import Path
from renaissance_v4.game_theory import PatternGameAgent

agent = PatternGameAgent(repo_root=Path("/path/to/blackbox"))
agent.list_presets()
out = agent.run_preset("tier1_twelve_month.example.json", max_workers=8, with_anna=False)
# out["results"], out["report_markdown"]
```

- **`repo_root`** — Black Box checkout (defaults to the tree that contains this package).
- **`presets_dir`** — Override if your app stores preset JSON somewhere other than `game_theory/examples/`.

---

## Presets vs your own scenarios

| Mode | How |
|------|-----|
| **Preset** | Drop `*.json` files under `game_theory/examples/` (or your `presets_dir`). `list_presets()` / `load_preset(filename)`. |
| **Custom** | Build a **JSON array** of scenario objects, or `{ "scenarios": [ ... ] }`, following the contract in `renaissance_v4/game_theory/README.md` (required: `manifest_path`; optional: tier, `evaluation_window`, `agent_explanation`, etc.). Start from `examples/tier1_scenario.template.json` or `tier1_twelve_month.example.json`. |

Invalid JSON or missing `manifest_path` fails validation before replay.

---

## Workers (parallelism)

- **Not threads** — The Referee batch uses a **process pool** (CPU-bound replay; avoids GIL limits).
- **How many** — Pass `max_workers` / `-j` on CLIs. The **web UI** exposes a slider; the cap comes from **`get_parallel_limits()`** (logical CPUs and a hard cap). Fewer workers = more headroom for other jobs on the host.

---

## Logs and “blow-by-blow” output

**Fair expectation:**

- **Per scenario:** Each finished scenario produces a **result object** in the batch (Referee summary, echoed agent fields, errors if any).
- **Optional JSONL:** If you enable logging (`experience_log.jsonl` / `log_path` in APIs), the runner **appends one JSON line per scenario result** — suitable for downstream tooling.
- **Markdown report:** The player agent path adds a **human-readable batch report** (`report_markdown`). Optional Anna section is **narrative**, not a second scorecard.

**Correction vs a loose claim “policy contracts she generates”:** The runner does **not** automatically produce **JUP policy contract packages** or run **`validate_policy_package.py`** per row. It produces **replay outcomes + audit metadata + optional LLM prose**. Formal policy packaging remains a **separate, explicit** workflow when you promote a candidate manifest.

---

## Anna and context (optional)

| Env / parameter | Role |
|-----------------|------|
| `PLAYER_AGENT_USE_ANNA` / `ANNA_USE_LLM` | Turn Anna narrative on/off (see `player_agent.py`). |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Point at your Ollama host. |
| `ANNA_CONTEXT_PROFILE` | e.g. `policy`, `pattern_game`, or `policy,pattern_game` — prepends whitelisted repo docs. |
| `anna_context_profile=` on `PatternGameAgent.run(...)` | Same, scoped to that call (also sets `REPO_ROOT` for path resolution). |

---

## CLI / web (prototype)

- **Player agent CLI:** `python3 -m renaissance_v4.game_theory.player_agent` — see `--help` (`--anna` / `--no-anna`).
- **Web UI:** `python3 -m renaissance_v4.game_theory.web_app` — preset or paste JSON, workers slider, optional JSONL log.

---

## Lab deploy (clawbot)

After you push, run **`python3 scripts/gsync.py`** from repo root. When pulled commits touch **`renaissance_v4/game_theory/`** (or **`scripts/agent_context_bundle.py`**), the remote runs **`scripts/pattern_game_remote_restart.sh`**, which frees port **8765** and starts the Flask UI again. **`--force-restart`** restarts both **UIUX.Web** docker and the pattern-game web even if `git pull` did nothing new. Env: **`GSYNC_PATTERN_GAME_PREFIXES`** to add more path triggers.

---

## Proof (automated)

Run from repo root with `PYTHONPATH=.`:

```bash
python3 -m pytest tests/test_pattern_game_agent.py tests/test_player_agent.py tests/test_agent_context_bundle.py -v
```

Smoke (load preset + validate):

```bash
python3 -c "from pathlib import Path; from renaissance_v4.game_theory import PatternGameAgent; a=PatternGameAgent(repo_root=Path('.').resolve()); s=a.load_preset('tier1_twelve_month.example.json'); print(a.validate(s))"
```

---

## Version anchor

Integrators should record **`git rev-parse HEAD`** on the branch they deploy; this brief was written against the tree that contains `PatternGameAgent` and `scripts/agent_context_bundle.py`.
