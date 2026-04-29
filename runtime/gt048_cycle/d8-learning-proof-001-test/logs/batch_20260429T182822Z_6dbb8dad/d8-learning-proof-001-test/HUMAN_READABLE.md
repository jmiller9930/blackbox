# Pattern game — run report (human-readable)

- **run_id:** `07dda56e-2e20-4820-9856-ab6d41665d0e`
- **UTC:** 2026-04-29T18:28:22.741413+00:00
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
| wins | 46 |
| losses | 0 |
| trades | 46 |
| win_rate | 1.0 |
| expectancy | 0.132793 |
| average_pnl | 0.132793 |
| max_drawdown | 0.0 |
| cumulative_pnl | 6.108485714285624 |
| validation_checksum | cac1970282e6bd6862bc187d3a6eafe8fe290bcb58f5e1152f83cb62acd2a89b |
| dataset_bars | 240 |

Ledger summary (full):

```json
{
  "total_trades": 46,
  "wins": 46,
  "losses": 0,
  "win_rate": 1.0,
  "gross_pnl": 6.108485714285624,
  "net_pnl": 6.108485714285624,
  "average_pnl": 0.1327931677018614,
  "expectancy": 0.1327931677018614,
  "max_drawdown": 0.0,
  "avg_mae": 0.26000000000001255,
  "avg_mfe": 1.4015217391304275
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
    "wins": 46,
    "losses": 0,
    "trades": 46,
    "win_rate": 1.0
  },
  "portfolio": {
    "cumulative_pnl": 6.108485714285624,
    "expectancy": 0.132793,
    "average_pnl": 0.132793,
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
