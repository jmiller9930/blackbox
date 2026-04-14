# RenaissanceV4 — Robustness & Monte Carlo (post-baseline)

This layer sits **on top** of the locked tag **`RenaissanceV4_baseline_v1`**. It does **not** replace deterministic replay; Monte Carlo only **reorders or resamples** PnL from an existing closed-trade list.

## Prerequisites

- `git checkout RenaissanceV4_baseline_v1` (or a **candidate branch** for experiments — never mutate baseline in place).
- `PYTHONPATH` at repo root (or `cd` to repo and `export PYTHONPATH=.`).
- Full-history SQLite at `renaissance_v4/data/renaissance_v4.sqlite3` (same as replay diagnostics).
- `pip install -r renaissance_v4/requirements.txt` (NumPy required for Monte Carlo).

## Execution order (mandatory first pass)

1. **Baseline reference** (once per machine / dataset refresh):

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.research.robustness_runner baseline-mc --seed 42 --n-sims 10000
```

This writes:

| Artifact | Purpose |
|----------|---------|
| `renaissance_v4/state/baseline_deterministic.json` | Deterministic metrics from replay |
| `renaissance_v4/state/baseline_monte_carlo_summary.json` | Full MC summaries (shuffle + bootstrap) |
| `renaissance_v4/reports/experiments/baseline_v1_trades.json` | Normalized closed trades |
| `renaissance_v4/reports/monte_carlo/monte_carlo_baseline_v1_reference.md` | Human-readable MC report |

2. **Candidate workflow** (after changing code on a branch — one subsystem at a time):

```bash
# Export trades from current checkout (candidate)
python3 -m renaissance_v4.research.robustness_runner export-trades \
  --output renaissance_v4/reports/experiments/candidate_my_change.json

# Compare to frozen baseline reference
python3 -m renaissance_v4.research.robustness_runner compare \
  --experiment-id exp_my_change_001 \
  --candidate-trades renaissance_v4/reports/experiments/candidate_my_change.json \
  --subsystem risk_governor \
  --description "Single-parameter test: …" \
  --files-changed renaissance_v4/core/risk_governor.py
```

Outputs:

- `renaissance_v4/reports/monte_carlo/monte_carlo_<experiment_id>.md`
- `renaissance_v4/reports/robustness/robustness_<experiment_id>.md`
- `renaissance_v4/reports/experiments/experiment_<experiment_id>.md`
- `renaissance_v4/state/monte_carlo_<experiment_id>_summary.json`
- Appends `renaissance_v4/state/experiment_index.json`

3. **Example pipeline check** (baseline trades vs themselves — sanity):

```bash
python3 -m renaissance_v4.research.robustness_runner example-flow --seed 42 --n-sims 2000
```

## Modules

| Module | Role |
|--------|------|
| `research/monte_carlo.py` | Shuffle / bootstrap simulation, distribution stats |
| `research/trade_export.py` | JSON export / load of closed trades |
| `research/baseline_comparator.py` | Struct for baseline vs candidate |
| `research/promotion_recommender.py` | Rules: improve / degrade / inconclusive (advisory) |
| `research/experiment_tracker.py` | Append-only `state/experiment_index.json` |
| `research/robustness_runner.py` | CLI orchestration |

## Operator dashboard (BLACK BOX UI)

- **Nav:** Dashboard → **RenaissanceV4** (hash `#/renaissance`), or open `/renaissance` (redirects to the same view).
- **API:** `GET /api/v1/renaissance/baseline`, `…/experiments`, `…/experiments/<id>`, `GET|POST /api/v1/renaissance/jobs` (same origin as other dashboard APIs).
- **Jobs** enqueue `robustness_runner` subprocesses on the API host (long-running); do not spam.

## Rules

- Monte Carlo **never invents** trades; inputs are **only** replay PnLs.
- **Do not** compare a candidate without a prior **`baseline-mc`** on the same dataset policy.
- **Do not** auto-promote from recommender output — architecture governs promotion.

## Config hints

See `renaissance_v4/configs/experiment_configs/*.json` for example command patterns.
