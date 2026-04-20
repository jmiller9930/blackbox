# GT-DIRECTIVE-002 — Prove memory + context on the **standard UI** path

**Status:** Operator protocol + engineering wiring (catalog parallel now forwards UI memory mode into replay).

## What counts as “normal UI path”

| Surface | Same contract as browser | Memory bundle | Decision Context Recall (context JSONL) |
|--------|---------------------------|---------------|-------------------------------------------|
| **`POST /api/run-parallel`** or **`POST /api/run-parallel/start`** | Yes — body matches `fetch(..., { body: JSON.stringify({...}) })` from the operator UI | Scenario `memory_bundle_path` **or** server Groundhog when enabled | Batch `context_signature_memory_mode`: **`off`** / **`read`** / **`read_write`** (echoed onto each scenario by `_prepare_parallel_payload`) |
| **`POST /api/run`** (single replay) | Yes | Optional `memory_bundle_path` in JSON | **Not wired** — no recall on this endpoint; use parallel or learning harness for DCR |

## Run A vs Run B (same tape, window, manifest, scenarios)

Use **identical** `scenarios` array and `evaluation_window_mode` / `evaluation_window_custom_months`. Only change memory controls.

**Run A — memory/context effectively OFF**

- `context_signature_memory_mode`: **`off`**
- No `memory_bundle_path` on scenarios (and `skip_groundhog_bundle`: **true** if the lab has Groundhog env on, so the control is not silently merged)

**Run B — memory/context ON**

- `context_signature_memory_mode`: **`read_write`** (or **`read`**)
- Optional: set `context_signature_memory_path` on a scenario if not using the default JSONL under `renaissance_v4/game_theory/state/context_signature_memory.jsonl`
- Optional: set `memory_bundle_path` on scenarios to a promoted bundle file if proving **bundle** path as well

## Proof fields (batch row / `learning_audit_v1` / scenario row)

After each batch completes, read **`batch_scorecard.jsonl`** last line or **`GET /api/run-parallel/status/<job_id>`** `result` rollup:

| Field | Meaning |
|-------|--------|
| `memory_used` / `memory_bundle_proof.memory_bundle_applied` | Promoted bundle merged |
| `replay_attempt_aggregates_v1.recall_bias_applied_total` | Fusion recall bias windows |
| `replay_attempt_aggregates_v1.recall_signal_bias_applied_total` | Per-signal recall bias |
| `replay_attempt_aggregates_v1.recall_match_windows_total` | Context signature matches |
| `replay_attempt_aggregates_v1.memory_records_loaded_count` | JSONL records loaded (arm), not proof of impact alone |
| `learning_audit_v1.recall_stats` | Same counters as above in batch rollup |
| `validation_checksum` / trade lists / `cumulative_pnl` | Behavior delta vs Run A |

**Acceptance:** At least one of `memory_bundle_applied`, `recall_bias_applied_total > 0`, `recall_signal_bias_applied_total > 0` **and** a behavior delta (checksum, trade count, fusion direction counts, or trade ids) vs Run A.

## Example `curl` (matches UI JSON; adjust host and preset body)

```bash
# Run A — OFF
curl -sS -X POST http://127.0.0.1:8765/api/run-parallel \
  -H 'Content-Type: application/json' \
  -d @path/to/run_a_body.json | tee run_a_parallel.json

# Run B — ON
curl -sS -X POST http://127.0.0.1:8765/api/run-parallel \
  -H 'Content-Type: application/json' \
  -d @path/to/run_b_body.json | tee run_b_parallel.json
```

Minimal shape (operator UI supplies full scenario list + hypotheses):

```json
{
  "scenarios": [ { "manifest_path": "renaissance_v4/configs/manifests/baseline_v1_recipe.json", "scenario_id": "ui_proof_1", "hypothesis": "memory context proof", "evaluation_window": { "calendar_months": 12 } } ],
  "evaluation_window_mode": "12",
  "context_signature_memory_mode": "read_write",
  "max_workers": 2
}
```

## Plain-English conclusions (pick one after two runs)

- **“Memory/context worked in the normal UI path”** — if Run B shows the acceptance counters + a behavior delta vs Run A.
- **“Memory/context did not work in the normal UI path”** — if Run B shows **zero** bias/matches **and** no bundle apply **and** identical outcomes to Run A: then cite **why** (e.g. empty JSONL, no signature matches on that window, fusion engine skipped recall, or single `/api/run` where recall is not wired).

## Engineering note (gating)

Recall bias requires **non-empty** context memory JSONL and **matching** signatures on the tape; `memory_records_loaded > 0` alone is **not** impact proof.

## One-line truth

**The parallel UI/API path is the standard operator batch path;** with `context_signature_memory_mode` not `off`, replay now runs Decision Context Recall the same way as `run_pattern_game` callers expect—**prove each deployment with Run A/B artifacts above**, not with the “Learning ACTIVE” chip alone.
