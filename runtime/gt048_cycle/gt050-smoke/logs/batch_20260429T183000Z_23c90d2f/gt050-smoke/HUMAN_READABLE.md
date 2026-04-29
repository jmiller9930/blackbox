# Pattern game — run report (human-readable)

- **run_id:** `e73dfeb2-988c-477a-94d4-40b80ca07c66`
- **UTC:** 2026-04-29T18:30:00.981197+00:00
- **source:** `parallel_scenarios`

## What actually ran

The **Referee** is a deterministic forward replay: it does not “decide” like a learned policy. It applies **fixed rules** from your manifest and engine to historical bars. Below is exactly what was on the ticket for this run.

- **Manifest path:** `/Users/bigmac/Documents/code_projects/blackbox/renaissance_v4/configs/manifests/sr1_deterministic_trade_proof_v1.json`
- **Manifest SHA-256:** `339543b8c9e3a4c17850b66c4c841e4c1c076c6393a15ec3fea4f5fa91910e8f`
- **ATR overrides:** none — values came from the manifest / catalog defaults.

## Hypothesis & indicator context (what you said you were testing)

*(No hypothesis string was supplied for this run.)*

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
| Training claim | `none` |
| Proof type | **replay only** |
| Outcome change visible vs no-memory replay? | **unknown** |

- **Learned from:**
  - Memory bundle path: `—`
  - Bundle `from_run_id`: `—`
  - Scenario `prior_run_id` (metadata): `—`
- **What changed this run:** No memory bundle was merged into the manifest before replay. Execution followed the on-disk manifest (plus any scenario ATR overrides listed below).
- **Outcome visibility:** No memory merge — outcome reflects manifest-only replay (plus scenario ATR overrides).

- **Promoted bundle note:** No bundle merge — promoted bundle was not in effect for this run.

- **Ablation:** not available — Same scenario was not also run without memory in this batch — no paired ablation proof.

### Memory & prior knowledge (technical decision audit)

- **Parameters merged from a memory bundle before replay (changes trades):** **No** (distinct from metadata-only links such as `prior_run_id` on the scenario).

Trade decisions came from: (1) manifest JSON on disk, (2) optional CLI/scenario ATR overrides (applied after any bundle), (3) bar data forward in time. No memory bundle was merged. run_memory JSONL / prior session folders are **not** auto-read to alter execution.

No prior_run_id was supplied.

## Referee results (measurement — not narrative invention)

| Field | Value |
|-------|--------|
| wins | 7 |
| losses | 0 |
| trades | 7 |
| win_rate | 1.0 |
| expectancy | 0.1407 |
| average_pnl | 0.1407 |
| max_drawdown | 0.0 |
| cumulative_pnl | 0.9848999999999878 |
| validation_checksum | 8924a79fb16b9b5feea3ea98a5a95fa3ddd47f901c0b75fe87a5c888b74cedd4 |
| dataset_bars | 80 |

Ledger summary (full):

```json
{
  "total_trades": 7,
  "wins": 7,
  "losses": 0,
  "win_rate": 1.0,
  "gross_pnl": 0.9848999999999878,
  "net_pnl": 0.9848999999999878,
  "average_pnl": 0.14069999999999824,
  "expectancy": 0.14069999999999824,
  "max_drawdown": 0.0,
  "avg_mae": 0.2600000000000193,
  "avg_mfe": 1.4699999999999949
}
```

## Outcome lenses (same Referee row — not a second ledger)

Binary **WIN/LOSS** counts are one scorecard. Here we **interpret** the same summary row so you can answer: did money improve, was edge positive, was drawdown contained, was win rate above a coin flip — **without** mixing in a separate data source.

- **Any positive signal (under these lenses):** **Yes** (see `positive_signals` in `run_record.json`)
- **Lenses:**
  - `drawdown` → **none_or_flat**
  - `edge` → **positive**
  - `money` → **positive**
  - `win_rate_vs_coinflip` → **above**
- **Positive signals:** `cumulative_pnl_positive`, `expectancy_positive`, `average_trade_pnl_positive`, `win_rate_above_half`, `no_negative_drawdown_in_metrics`
- _Lenses interpret the same Referee row — not a second ledger. win_rate is binary scorecard; money/edge/drawdown are separate questions._

```json
{
  "schema": "outcome_measures_v1",
  "from_referee_row": true,
  "binary_scorecard": {
    "wins": 7,
    "losses": 0,
    "trades": 7,
    "win_rate": 1.0
  },
  "portfolio": {
    "cumulative_pnl": 0.9848999999999878,
    "expectancy": 0.1407,
    "average_pnl": 0.1407,
    "max_drawdown": 0.0
  },
  "lenses": {
    "money": "positive",
    "edge": "positive",
    "win_rate_vs_coinflip": "above",
    "drawdown": "none_or_flat"
  },
  "positive_signals": [
    "cumulative_pnl_positive",
    "expectancy_positive",
    "average_trade_pnl_positive",
    "win_rate_above_half",
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
