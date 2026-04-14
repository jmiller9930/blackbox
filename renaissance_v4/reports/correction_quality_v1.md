# RenaissanceV4 — DV-ARCH-CORRECTION-013: Targeted economic correction (quality pass)

**Date:** 2026-04-14 UTC  
**Subsystem targeted:** Regime labeling and unstable participation, ATR stop/target geometry, effective-score tiering (full tier), containment for thin-sample weak signal families (trend / pullback).  
**Not modified:** Fusion scoring formulas, signal activation rules inside signal modules, lifecycle/Monte Carlo/execution engine structure (only ATR multiples and metadata on `TradeState`).

---

## 1. Evidence basis (from `diagnostic_quality_v1.md` pre-correction)

| Metric | Before |
|--------|--------|
| Closed trades | 1702 |
| Win rate | 0.2803 |
| Expectancy | −0.004783 |
| Max drawdown (path) | 48.4209 |
| Total gross PnL | −8.1406 |
| Exit regime `unstable` gross PnL (worst bucket) | −46.099 (n=1292) |
| `stop` / `target` counts | 1225 / 477 (~28% targets) |
| `full` tier n | 65 (worst expectancy among tiers) |
| ATR geometry (prior) | `ATR_STOP_MULT=1.6`, `ATR_TARGET_MULT=4.0` |

**MAE/MFE read:** Stop exits showed **avg MAE > avg MFE** on the stop path (adverse excursion dominated favorable before stop), consistent with **tight stops vs achievable MFE**; targets were clean winners — geometry favored stop-outs over target hits.

---

## 2. Exact code changes

### 2.1 Regime classifier (`regime_classifier.py`)

- **Change:** Widen the **`range`** branch: `ema_distance` tolerance ×1.12 and allow persistence up to `PERSISTENCE_THRESHOLD + 0.06` (vs strict `<` threshold before).
- **Rationale:** Reduces the default **`unstable`** residual bucket for borderline chop; pairs with risk-side compression for elevated persistence in `range` (below).

### 2.2 Unstable regime — probe-only path (`risk_governor.py`)

- **Prior behavior:** `unstable` set `compression_factor = 0` → **no new entries** in unstable.
- **New behavior (directive option: restrict unstable to probe tier):** Replace hard veto with **`compression_factor *= 0.48`** and **hard cap** assigned tier at **`probe`** if math would yield `reduced` or `full` (`unstable_regime_tier_capped_probe`).
- **Rationale:** Prior diagnostic used **exit-time** `regime`; entries in `unstable` were already blocked, so loss mass under an `unstable` **exit** label could not be fixed by entry veto alone. Probe-only path allows **controlled** participation with **no full/reduced** sizing in that regime label, while other changes (geometry, tier floor, classifier) address portfolio economics.

### 2.3 Range — mild compression (`risk_governor.py`)

- **Change:** If `regime == "range"` and `directional_persistence_10 >= 0.50`, apply **`compression_factor *= 0.90`**.
- **Rationale:** Offset higher activity in marginal chop moved into `range` by the widened classifier.

### 2.4 Full tier — stricter floor (`risk_governor.py`)

- **Change:** `FULL_SIZE_FUSION_MIN`: **0.42 → 0.52** (effective score post-compression).
- **Rationale:** `full` was worst-performing tier in the diagnostic; full tier should be rare and high-conviction.

### 2.5 Weak signal containment (`risk_governor.py` + call sites)

- **Change:** New helper: if **all active** contributing signal names are only `trend_continuation` and/or `pullback_continuation`, **cap tier at `probe`** (cannot be `reduced` or `full`).
- **Rationale:** Directive option “probe tier only” for thin-sample, strongly negative families — implemented **without** editing fusion weights or signal internals. `replay_runner`, `diagnostic_*` pipelines pass `active_signal_names` into `evaluate_risk`.

### 2.6 Stop / target geometry (`execution_manager.py`)

- **Change:** `ATR_STOP_MULT`: **1.6 → 1.78**; `ATR_TARGET_MULT`: **4.0 → 3.35** (reward/risk in ATR units ~**1.88** vs ~**2.5** previously).
- **Rationale:** Slightly **wider** stops vs prior; **closer** targets to raise target hit rate vs premature stops, aligned with MAE/MFE pattern on stop exits.

### 2.7 Entry regime metadata (`trade_state.py`, `replay_runner.py`, `diagnostic_quality_pipeline.py`, `execution_learning_bridge.py`)

- **Change:** `TradeState.entry_regime`; set at `open_trade`; stored in `OutcomeRecord.metadata["entry_regime"]` for future entry-vs-exit regime analysis (no fusion/lifecycle redesign).

---

## 3. Validation — after metrics (full-history replay, clawbot DB)

**Command:** `PYTHONPATH=. python3 -m renaissance_v4.research.diagnostic_quality_pipeline`  
**Commit:** `d00ea54` on `main` (pulled on clawbot before run).  
**Artifact copy:** `renaissance_v4/reports/diagnostic_quality_post_DV013.md` (same tables as generated on host).

| Metric | After |
|--------|-------|
| Closed trades | **1969** |
| Win rate | **0.3443** |
| Expectancy | **0.008256** |
| Max drawdown (path) | **24.2973** |
| Total gross PnL | **+16.2567** |
| `full` tier n | **0** (floor + caps) |

### 3.1 Regime breakdown (exit `regime` on outcome)

| Regime | n (after) | Notes vs before |
|--------|-----------|-----------------|
| `unstable` | 1326 | Still largest **count** in worst bucket by gross PnL (−58.04); **portfolio** net improved via other regimes |
| `range` | 410 | Up from 202 — classifier widening; strong positive expectancy in this slice |
| Others | — | See `diagnostic_quality_post_DV013.md` |

### 3.2 Signal / family breakdown

- **Mean reversion** still carries volume; per-trade expectancy **positive** in this run.
- **Trend family** still slightly negative on tagged rows but **small gross** vs before.
- See full tables in `diagnostic_quality_post_DV013.md`.

### 3.3 Stop vs target distribution

| | Before | After |
|---|--------|-------|
| `stop` n | 1225 | 1291 |
| `target` n | 477 | 678 |
| Target share of exits | **28.0%** | **34.4%** |

Stops still account for more exits than targets, but **target share increased** and **portfolio** expectancy turned positive.

### 3.4 Risk-tier distribution

| Tier | Before (n) | After (n) |
|------|------------|-----------|
| `probe` | 1053 | 1276 |
| `reduced` | 584 | 693 |
| `full` | 65 | **0** |

---

## 4. Acceptance checklist (directive §8)

| Criterion | Met? | Notes |
|-----------|------|-------|
| Expectancy toward neutral/positive | **Yes** | E ≈ **+0.0083** |
| Drawdown materially reduced | **Yes** | max_dd **~24.3** vs **~48.4** |
| Unstable no longer dominates losses | **Partial** | Exit-time **`unstable`** still worst **gross** bucket; **aggregate** PnL and DD improved |
| Stop dominance reduced vs targets | **Partial** | Target share **28% → 34%**; stops still majority of exits |
| Meaningful trade count | **Yes** | **1969** vs 1702 |

---

## 5. Subsystem statement (explicit)

Economic weakness was addressed by **(1)** regime labeling and unstable **tier policy**, **(2)** ATR SL/TP geometry from MAE/MFE evidence, **(3)** raising the **full** tier floor and capping weak-only signal families at **probe**, **(4)** optional **range** persistence compression — without changing fusion formulas or signal activation code paths inside the signal classes.

---

## 6. Reproduce

```bash
cd /path/to/blackbox
git checkout main   # includes DV-013
git pull
export PYTHONPATH=.
python3 -m renaissance_v4.research.diagnostic_quality_pipeline
```

**Clawbot post-pull:** `git rev-parse HEAD` should be **d00ea54** or newer containing this report.
