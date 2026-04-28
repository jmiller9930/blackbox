# Pattern game — run report (human-readable)

- **run_id:** `13487cd5-ccdf-44fa-af82-4a6b2fc2764a`
- **UTC:** 2026-04-28T17:46:22.665649+00:00
- **source:** `parallel_scenarios`

## What actually ran

The **Referee** is a deterministic forward replay: it does not “decide” like a learned policy. It applies **fixed rules** from your manifest and engine to historical bars. Below is exactly what was on the ticket for this run.

- **Manifest path:** `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/baseline_v1_recipe.json`
- **Manifest SHA-256:** `224fd8f625fae7bd4008274fbcf4597140f8757fdce25e565132c73a9b21e5d2`
- **ATR overrides:** none — values came from the manifest / catalog defaults.

## Hypothesis & indicator context (what you said you were testing)

> Full-history baseline v1 stack on ingested SOLUSDT 5m yields positive expectancy vs strict binary trade scorecard under outcome_rule_v1 (testable vs this replay only).

*No structured indicator_context was supplied.*

### Single-silo memory (not the universe)

Retrieval here is **one silo**: pattern-game replay + what you attach — **not** general RAG over the world. What must persist is **context around indicators** (regime, direction, transition, velocity). Without that, you only store **noise**.

> **Tide check:** Six feet of water does not tell you if the tide is **coming in or going out**. An indicator **value** without **context** (regime, direction, transition, velocity) is **noise** — not memory worth promoting. This silo stores **context around indicators**, not the universe.

- **Context quality (raw, this run):** `missing` (signal keys matched: [])
- **Warning:** Context is thin or absent — review before promoting any “memory.”

## Learning / Memory Evidence (operator drill-down)

Quick answers: **Did training-informed memory influence this run?** **What object was used?** **Where did it come from?** **What behavior changed?** **Was that visible in the outcome?**

| Question | Answer |
|----------|--------|
| Did training-informed memory influence this run? (memory merge) | **No** |
| Training evidence (summary) | **none** (none / partial / confirmed) |
| Memory in use | **no** |
| Promoted memory (canonical bundle) | **inactive** (active / inactive) |
| Context quality (operator label) | **missing** (missing / thin / rich) |
| Training claim | `observed_only` |
| Proof type | **replay only** |
| Outcome change visible vs no-memory replay? | **unknown** |

- **Learned from:**
  - Memory bundle path: `—`
  - Bundle `from_run_id`: `—`
  - Scenario `prior_run_id` (metadata): `—`
- **What changed this run:** No memory bundle was merged into the manifest before replay. Execution followed the on-disk manifest (plus any scenario ATR overrides listed below).
- **Outcome visibility:** No memory merge — outcome reflects manifest-only replay (plus scenario ATR overrides).

- **Promoted bundle note:** Promoted bundle auto-merge was skipped for this scenario.

- **Ablation:** not available — Same scenario was not also run without memory in this batch — no paired ablation proof.

### Memory & prior knowledge (technical decision audit)

- **Parameters merged from a memory bundle before replay (changes trades):** **No** (distinct from metadata-only links such as `prior_run_id` on the scenario).

Trade decisions came from: (1) manifest JSON on disk, (2) optional CLI/scenario ATR overrides (applied after any bundle), (3) bar data forward in time. No memory bundle was merged. run_memory JSONL / prior session folders are **not** auto-read to alter execution.

No prior_run_id was supplied.

## Referee results (measurement — not narrative invention)

| Field | Value |
|-------|--------|
| wins | 0 |
| losses | 0 |
| trades | 0 |
| expectancy | 0.0 |
| average_pnl | 0.0 |
| max_drawdown | 0.0 |
| cumulative_pnl | 0.0 |
| validation_checksum | 9012edeac8f3cafad6dc30152ef8fd6a0d8765162d2360e615ec25db0675f817 |
| dataset_bars | 240 |

Ledger summary (full):

```json
{
  "total_trades": 0,
  "wins": 0,
  "losses": 0,
  "win_rate": 0.0,
  "gross_pnl": 0.0,
  "net_pnl": 0.0,
  "average_pnl": 0.0,
  "expectancy": 0.0,
  "max_drawdown": 0.0,
  "avg_mae": 0.0,
  "avg_mfe": 0.0
}
```

## Outcome lenses (same Referee row — not a second ledger)

Binary **WIN/LOSS** counts are one scorecard. Here we **interpret** the same summary row so you can answer: did money improve, was edge positive, was drawdown contained, was win rate above a coin flip — **without** mixing in a separate data source.

- **Any positive signal (under these lenses):** **Yes** (see `positive_signals` in `run_record.json`)
- **Lenses:**
  - `drawdown` → **none_or_flat**
  - `edge` → **non_positive**
  - `money` → **flat**
- **Positive signals:** `cumulative_pnl_non_negative`, `no_negative_drawdown_in_metrics`
- _Lenses interpret the same Referee row — not a second ledger. win_rate is binary scorecard; money/edge/drawdown are separate questions._

```json
{
  "schema": "outcome_measures_v1",
  "from_referee_row": true,
  "binary_scorecard": {
    "wins": 0,
    "losses": 0,
    "trades": 0
  },
  "portfolio": {
    "cumulative_pnl": 0.0,
    "expectancy": 0.0,
    "average_pnl": 0.0,
    "max_drawdown": 0.0
  },
  "lenses": {
    "money": "flat",
    "edge": "non_positive",
    "drawdown": "none_or_flat"
  },
  "positive_signals": [
    "cumulative_pnl_non_negative",
    "no_negative_drawdown_in_metrics"
  ],
  "positive_any": true,
  "note": "Lenses interpret the same Referee row — not a second ledger. win_rate is binary scorecard; money/edge/drawdown are separate questions."
}
```

## Post-mortem (for you or Anna — optional)

- **why:** None
- **next_hypothesis:** None

_Nothing in this section affected the Referee. Fill in after you review the run._
