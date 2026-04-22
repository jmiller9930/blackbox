# Closed-trade batch proof (carousel + deep dive)

This folder includes **one operator-visible proof run** with **46 real closed trades** in `replay_outcomes_json`, used to show the Student panel L2 carousel (one card per `trade_id`) and L3 deep dive.

## Plain answer (directive)

1. **Yes** — when the selected run’s parallel worker rows have **empty** `replay_outcomes_json`, the carousel has **zero slices**. That is “no enumerated closed trades for that run,” not a missing API route.
2. **This batch** — local proof pipeline:
   - Extended `SOLUSDT` history in the **gitignored** dev DB (`renaissance_v4/data/*.sqlite3`) with `scripts/d14_proof_append_sol_trend_bars.py` so replay can reach `trend_up` regimes.
   - Ran **one** parallel scenario with **`renaissance_v4/configs/manifests/sr1_deterministic_trade_proof_v1.json`** (`fusion_min_score: 0.1` — **lab / proof manifest**, not a production objective).
   - Batch folder: `renaissance_v4/game_theory/logs/batch_20260422T145312Z_47323bdf/`
   - Scorecard line **`job_id=d14_closed_trade_proof_20260422`** appended to **`renaissance_v4/game_theory/batch_scorecard.jsonl`** (file is gitignored; re-append locally if needed).

## API proof (committed JSON)

- L2: `proof_api_selected_run_with_slices.json` — `GET /api/student-panel/run/d14_closed_trade_proof_20260422/decisions` → `"slices"` length **46**, `"grain":"trade_id"`.
- L3: `proof_api_deep_dive.json` — `GET /api/student-panel/decision?job_id=d14_closed_trade_proof_20260422&trade_id=e1741a17f11bdc53ea04e166`.

## Screenshot proof (committed PNG)

Captured with `scripts/d14_capture_student_ui_proof.py` (Playwright) against local Flask `http://127.0.0.1:8765/`:

- `screenshots/d14_before_row_click.png` — L1 run table showing `#tr` = **46**.
- `screenshots/d14_proof_l2_summary_and_carousel.png` — run summary band + carousel slice strip.
- `screenshots/d14_proof_l3_deep_dive.png` — L3 trade deep dive for the first slice’s `trade_id`.

## Reproduce

```bash
# From repo root; uses default sqlite unless RENAISSANCE_V4_DB_PATH is set
PYTHONPATH=. python3 scripts/d14_proof_append_sol_trend_bars.py
PYTHONPATH=. python3 -c "
from pathlib import Path
import json
from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel
from renaissance_v4.game_theory.batch_scorecard import append_batch_scorecard_line
sc = [{'scenario_id': 'd14_trade_proof_sr1', 'manifest_path': 'renaissance_v4/configs/manifests/sr1_deterministic_trade_proof_v1.json'}]
run_scenarios_parallel(sc, max_workers=1, write_session_logs=True)
# Then append scorecard line pointing session_log_batch_dir at the new batch_* folder (see prior commit helper).
"
```

Then start Flask, run `python3 scripts/d14_capture_student_ui_proof.py`.
