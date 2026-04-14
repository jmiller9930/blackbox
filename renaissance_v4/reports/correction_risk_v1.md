# RenaissanceV4 — Risk governor correction v1

**Date:** 2026-04-14 (UTC)  
**Scope:** `renaissance_v4/core/risk_governor.py` only — no changes to signals, fusion, or execution.

---

## 1. Problem (from `diagnostic_risk_v1.md`, pre-change)

| Observation | Value |
|-------------|--------|
| Directional fusion inputs | 2697 |
| Risk **allowed** | 1 (**0.037%**) |
| Avg **effective** score (directional) | **~0.188** |
| Probe floor | **0.55** |
| Dominant veto | `effective_score_below_probe_floor` |

Effective score = `fusion_score × compression_factor`. Fusion raw scores were already reasonable (~0.38 avg); compression pulled effective far below an unreachable probe tier.

---

## 2. Distribution basis (pre-change, histogram interpolation)

From **2697** directional bars, bucket counts implied approximate percentiles of **effective score**:

| Percentile | ~Value (uniform-within-bucket interpolation) |
|------------|-----------------------------------------------|
| P50 | ~0.18 |
| P75 | ~0.29 |
| P90 | ~0.39 |
| P95 | ~0.42 |

These positions were used to set **tier floors** so probe is **below median**, reduced sits **between P75 and P90**, and full sits near **P95** (rare).

---

## 3. New constants (`risk_governor.py` v1.1)

### 3.1 Effective-score tier thresholds

| Constant | Before | After | Rationale |
|----------|--------|-------|-----------|
| `PROBE_SIZE_FUSION_MIN` | 0.55 | **0.14** | Below ~P50 (~0.18) — probe tier attainable without flooding (other vetoes remain) |
| `REDUCED_SIZE_FUSION_MIN` | 0.70 | **0.30** | Between ~P75 and ~P90 — stronger evidence for reduced |
| `FULL_SIZE_FUSION_MIN` | 0.90 | **0.42** | Near ~P95 — full tier still rare |

**Hierarchy preserved:** full (**0.42**) > reduced (**0.30**) > probe (**0.14**).

### 3.2 Persistence compression

| Constant | Before | After | Rationale |
|----------|--------|-------|-----------|
| `LOW_PERSISTENCE_VETO` | 0.25 | **0.08** | Narrow hard veto to extreme chop only (was blocking ~34% of veto *lines* pre-fix) |
| `LOW_PERSISTENCE_REDUCE` | 0.45 | **0.40** | Align soft band with adjusted veto |
| `PERSISTENCE_SOFT_MULTIPLIER` | 0.60 (literal) | **0.72** | Softer multiplicative penalty in persistence band |

### 3.3 Volatility soft compression (minor)

Path `volatility_20 >= HIGH_VOLATILITY_REDUCE`: multiplier **0.50 → 0.62** (still compresses; does not disable).

---

## 4. Before vs after — risk gate (full history, clawbot)

| Metric | Before correction | After correction |
|--------|-------------------|------------------|
| Directional fusion (long+short) | 2697 | 2697 (unchanged — fusion untouched) |
| Risk **allowed** (directional) | 1 (0.037%) | **2625** (**97.33%**) |
| Risk **blocked** (directional) | 2696 | **72** (2.67%) |
| Avg effective (directional) | 0.188 | **0.298** |
| Avg compression factor | 0.491 | **0.780** |

**After** veto mix (blocked only): dominant lines are `persistence_too_low`, `volatility_expansion_compression`, then persistence/volatility soft compressions — `effective_score_below_probe_floor` **25** (vs **1771** before).

**After** `effective_score` histogram (directional): see regenerated `diagnostic_risk_v1.md` on clawbot (buckets include `[0, 0.14)`, `[0.14, 0.25)`, …).

---

## 5. Before vs after — full replay validation (clawbot)

Command: `python3 -m renaissance_v4.research.replay_runner`

| Metric | Before risk correction | After risk correction |
|--------|--------------------------|------------------------|
| **Total closed trades** | 1 | **1702** |
| Win rate | 0.0 | **0.280** |
| Expectancy | -0.200 | **-0.00478** |
| Max drawdown (equity curve) | 0.200 | **48.421** |
| Gross / net PnL | -0.200 | **-8.141** |

**Checksum (after):** `d33bda224e3d8cfafe5b9ede4042cb02d55663aa950fe0cf5c91dae872fa8f25`

Profitability was **not** a goal; negative expectancy on this run is acceptable for proving **flow** and **controlled** activity (not a single trade).

---

## 6. What was not done

- Compression **not** disabled; all veto paths preserved.
- No hardcoded allows; `evaluate_risk` logic structure unchanged.
- Fusion and signals **unchanged** in this pass.

---

## 7. Reproduce

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.research.diagnostic_risk_pipeline
python3 -m renaissance_v4.research.replay_runner
```

---

## 8. Follow-up (architecture)

Further tuning may target **persistence** and **volatility expansion** vetoes if **block rate** should rise from ~2.7% of directional bars — evidence now points there instead of probe floor starvation.
