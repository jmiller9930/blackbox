# RenaissanceV4 — Pipeline diagnostic v1 (read-only)

Generated: **2026-04-14 18:59:53 UTC** by `renaissance_v4/research/diagnostic_pipeline.py` (DV-ARCH-DIAGNOSTIC-008).

**No thresholds, weights, or signal/fusion/risk logic were modified.** This pass only counts outcomes 
using the **same** `evaluate` → `fuse_signal_results` → `evaluate_risk` sequence as `replay_runner.py`.

## Dataset

- **Rows in `market_bars_5m`:** 210240
- **Decision steps (bars processed after 50-bar warmup):** 210191

## 5.1 Signal layer

Per signal, counts are **per decision bar** (same bar may increment multiple counters).

| Signal | `active` | direction `long` | direction `short` | direction `neutral` |
|--------|----------|--------------------|--------------------|---------------------|
| `trend_continuation` | 4320 | 2170 | 2150 | 205871 |
| `pullback_continuation` | 393 | 203 | 190 | 209798 |
| `breakout_expansion` | 649 | 334 | 315 | 209542 |
| `mean_reversion_fade` | 21142 | 10410 | 10732 | 189049 |

- **Decision bars with ≥1 signal `active`:** 26416 (12.5676% of steps).

## 5.2 Fusion layer

- **Fusion `long`:** 0 (0.0000% of decision steps)
- **Fusion `short`:** 0 (0.0000%)
- **Fusion `no_trade`:** 210191 (100.0000%)

**`no_trade` breakdown (mutually exclusive buckets):**

| Reason bucket | Count | % of decision steps |
|---------------|-------|---------------------|
| no_gross_directional_score (no active long/short contributions) | 183775 | 87.4324% |
| fusion_score<0.55 (after overlap) or tie | 26416 | 12.5676% |

## 5.3 Risk layer

- **Risk `allowed` (all fusion outputs):** 0 (0.0000%)
- **Risk `blocked` (all fusion outputs):** 210191 (100.0000%)

When fusion was **directional** (`long` or `short`):

- **Risk allowed:** 0
- **Risk blocked:** 0

**Veto reason counts (only when fusion was directional and risk blocked):**

| Veto reason | Count |
|-------------|-------|
| *(none — fusion rarely directional or risk never blocked directional)* | 0 |

**Size tier when risk allowed (any fusion output):**

| Size tier | Count |
|-----------|-------|
| *(none — risk never allowed)* | 0 |

## 5.4 Pipeline breakdown (Signal → Fusion → Risk → Execution gate)

- **Hypothetical new entries (flat book, same gate as replay):** `0`
  (count of bars where `fusion ∈ {{long,short}}` **and** `risk_decision.allowed`).

If this count is **0**, execution never receives an open instruction — **closed trades stay 0**.

## Regime distribution (informational)

| Regime | Bars | % of steps |
|--------|------|------------|
| `unstable` | 100116 | 47.6310% |
| `range` | 72579 | 34.5300% |
| `volatility_compression` | 31735 | 15.0982% |
| `trend_up` | 2411 | 1.1471% |
| `trend_down` | 2383 | 1.1337% |
| `volatility_expansion` | 967 | 0.4601% |

## 7. Root cause analysis (data-backed)

The system produced zero closed trades because:

> **Fusion never emitted `long` or `short` (0 / 210191 decision steps).**  
> - **87.43%** of steps: **no gross directional score** — no active signal contributions entered the weighted long/short sums (regime mismatch, suppression, or inactive signals dominated).  
> - **12.57%** of steps: non-zero gross contribution existed, but the **fused score stayed below `MIN_FUSION_SCORE` (0.55)** after overlap penalty (conflict was not the dominant bucket in this dataset).  
> **Risk** therefore never sized a directional trade (`allowed` always false with veto `no_trade_from_fusion`), and **execution received 0 open instructions** — so **0 closed trades** is consistent with pipeline behavior, not an execution bug.

## 8. Reproduce

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.research.diagnostic_pipeline
```

Writes this file by default to `renaissance_v4/reports/diagnostic_v1.md`.

