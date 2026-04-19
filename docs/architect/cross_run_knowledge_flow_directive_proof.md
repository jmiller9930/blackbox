# Cross-run knowledge flow — directive proof (production → persistence → loading → influence)

**Purpose:** Answer whether any artifact from run *N* is consumed on run *N+1* and changes **replay decisions**, with **code-path and runtime evidence**. Complements `scripts/prove_memory_bundle_e2e.py` (bundle merge audit).

**Executable evidence:** `scripts/prove_cross_run_knowledge_flow.py` (JSON to stdout).

---

## Final classification (single answer)

**Partially stateful via memory bundle only (narrow, opt-in).**  
There is **no** closed loop where `experience_log.jsonl` or `run_memory.jsonl` **feed back into** `run_manifest_replay`. Those files are **append-only sinks** for audit/analysis. **Groundhog / explicit bundle** merge **whitelisted manifest keys** (`atr_stop_mult`, `atr_target_mult`) **before** replay — that is the only **automatic** cross-run behavioral lever when env + file conditions are met.

**Not “fully stateless”** if Groundhog or explicit `memory_bundle_path` is used; **not “logs-based adaptation.”**

---

## 1. Artifact inventory

### memory bundle (explicit path or Groundhog `state/groundhog_memory_bundle.json`)

| Stage | Finding | Code / proof |
|-------|---------|----------------|
| **Production** | Written by `write_groundhog_bundle()` or human promotion; schema `pattern_game_memory_bundle_v1` | `renaissance_v4/game_theory/groundhog_memory.py` |
| **Persistence** | File on disk under `…/state/groundhog_memory_bundle.json` (canonical) | `groundhog_bundle_path()` |
| **Loading** | `resolve_memory_bundle_for_scenario` → `apply_memory_bundle_to_manifest` | `groundhog_memory.py`, `memory_bundle.py` |
| **Decision influence** | **Yes — execution geometry** (manifest keys merged before `run_manifest_replay`; `build_execution_manager_from_manifest` uses manifest ATR fields) | `pattern_game.py` → `replay_runner.py` → `renaissance_v4/manifest/runtime.py` |

### experience_log.jsonl

| Stage | Finding | Code / proof |
|-------|---------|----------------|
| **Production** | **Yes** — parent appends one JSON line per scenario after workers finish | `parallel_runner.py` ~197–202 (`fh.write(json.dumps(row, …))`) |
| **Persistence** | Path from `default_experience_log_jsonl()` (`memory_paths.py`) | `PATTERN_GAME_MEMORY_ROOT` prefix when set |
| **Loading** | **No** in replay | **`replay_runner.py` contains no reference to experience_log** (grep) |
| **Decision influence** | **None** — not read by signal/fusion/execution path | Append-only |

### run_memory.jsonl

| Stage | Finding | Code / proof |
|-------|---------|----------------|
| **Production** | **Yes** — `append_run_memory` from parallel parent after each result | `parallel_runner.py` ~249–252 |
| **Persistence** | `default_run_memory_jsonl()` | `memory_paths.py` |
| **Loading** | **No** in replay | `read_run_memory_tail()` exists in `run_memory.py` but **has no importer** in replay/pattern_game (repo grep) |
| **Decision influence** | **None** in `run_manifest_replay` | Structured audit / curriculum hooks only |

### Session artifacts (`logs/batch_*`, `HUMAN_READABLE.md`, `run_record.json`, …)

| Stage | Finding | Code / proof |
|-------|---------|----------------|
| **Production** | **Yes** when session logs enabled | `run_session_log.py`, `write_batch_index_and_scenario_logs` |
| **Loading** | **No** in replay | No loader in `replay_runner.py` / `pattern_game.py` |
| **Decision influence** | **None** for next replay | Operator / tooling |

### retrospective_log.jsonl (related)

| Stage | Finding |
|-------|---------|
| **Loading** | Read by **`hunter_planner.py`** for **batch suggestions**, **not** by `run_manifest_replay`. |

---

## 2. Artifact eligibility (intent in code)

| Artifact | Intended reuse for **replay behavior**? | Where stated |
|----------|-------------------------------------------|--------------|
| Memory bundle | **Yes** — merge into manifest | `memory_bundle.py` module docstring |
| experience_log | **No** for replay — offline / analysis | `parallel_runner.py` append-only |
| run_memory | **No** for replay — durable audit | `run_memory.py`, `LearningLedger` doc (no tuning) |
| Session folders | **No** for automated replay | Write-only narrative |

---

## 3–4. Run 1 vs Run 2 (same scenario, logs appended)

**Script behavior:** Two parallel runs, identical scenario, isolated `PATTERN_GAME_MEMORY_ROOT`, Groundhog **off**, `skip_groundhog_bundle: true`.

**Observed (runtime JSON):**

- `experience_log.jsonl` and `run_memory.jsonl` **gain one line each** on run 2 (`logs_appended`).
- **`validation_checksum`** and **`cumulative_pnl`** **match** run 1 when the tape produces the same trades (`outcome_identical_to_run_1: true` in fixture).

**Conclusion:** Prior JSONL lines **do not** alter the second replay. **Write-only, no read in replay path.**

---

## 5. Groundhog (Run 3 in script — isolated temp `game_theory` root)

Patches `groundhog_memory._GAME_THEORY` to a temp directory, writes bundle, sets `PATTERN_GAME_GROUNDHOG_BUNDLE=1`, runs `run_pattern_game` with auto-resolve.

**Observed:** `memory_bundle_proof` shows **loaded, applied, hash, keys**; **effective manifest ATR** differs from disk-only manifest.

**Influence channel:** Same as bundle proof — **manifest → runtime builders → execution** (not fusion weights).

---

## 6. True cross-run “adaptation”?

| Question | Answer |
|----------|--------|
| Do prior run **outcomes** automatically change the next run’s policy/fusion? | **No** (`LearningLedger` does not tune; logs not consumed by replay). |
| Is there **any** closed loop from run 1 artifacts **except** bundle merge? | **No** in the current codebase for `run_manifest_replay`. |
| Can **manual / Groundhog bundle** change the next run? | **Yes** — narrow ATR (and future whitelisted keys). |

---

## Commands

```bash
cd /path/to/blackbox
PYTHONPATH=. python3 scripts/prove_cross_run_knowledge_flow.py 2>/dev/null | tee /tmp/cross_run_proof.json
```

Commit hash when this doc was added: see `git log -1 --oneline docs/architect/cross_run_knowledge_flow_directive_proof.md`.
