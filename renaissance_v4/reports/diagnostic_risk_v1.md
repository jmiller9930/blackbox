# RenaissanceV4 — Risk governor diagnostic v1 (read-only)

Generated: **2026-04-14 19:54:16 UTC** · `renaissance_v4/research/diagnostic_risk_pipeline.py`

No risk thresholds, compression constants, or other logic were modified. This pass only observes 
`fuse_signal_results` → `evaluate_risk` on the full bar history.

## 7.1 Directional fusion population (input to risk)

- **Fusion `long`:** 1287
- **Fusion `short`:** 1410
- **Total directional (`long` + `short`):** 2697

## 7.2 Risk allow vs block (directional inputs only)

- **Allowed:** 1 (`0.0371%` of directional bars)
- **Blocked:** 2696 (`99.9629%` of directional bars)

### Blocked — veto reason frequency

Each veto string from `RiskDecision.veto_reasons` is counted (a single bar may contribute multiple reasons).

| Rank | Veto reason | Count |
|------|-------------|-------|
| 1 | `effective_score_below_probe_floor` | 1771 |
| 2 | `persistence_compression_applied` | 1071 |
| 3 | `persistence_too_low` | 923 |
| 4 | `volatility_expansion_compression` | 104 |
| 5 | `volatility_compression_applied` | 36 |
| 6 | `volatility_too_high` | 5 |

## 7.3 Compression path (directional fused outcomes only)

- **Probe / minimum tier floor (`effective_score`):** `0.55` (see `risk_governor.PROBE_SIZE_FUSION_MIN`)
- **Average raw `fusion_score` (pre-risk):** 0.38185541
- **Average `compression_factor` (post-regime/vol/persistence chain):** 0.49135150
- **Average `effective_score` (`fusion_score × compression_factor`):** 0.18769439
- **Average effective score when blocked:** 0.18755311
- **Average effective score when allowed:** 0.56858293

### Distribution of `effective_score` (directional bars)

| Bucket | Count |
|--------|-------|
| <0 | 0 |
| [0, 0.25) | 1877 |
| [0.25, 0.45) | 796 |
| [0.45, 0.55) | 23 |
| >=0.55 | 1 |

## 7.4 Regime interaction (blocked directional only)

| Regime | Blocked count |
|--------|----------------|
| `range` | 2377 |
| `volatility_compression` | 160 |
| `volatility_expansion` | 104 |
| `trend_up` | 32 |
| `trend_down` | 23 |

## 7.5 Signal-family interaction (blocked directional only)

Counts by coarse family derived from `FusionResult.contributing_signals` (a bar may increment multiple families).

| Family | Count |
|--------|-------|
| `mean_reversion_family` | 2537 |
| `breakout_family` | 104 |
| `trend_family` | 55 |

## Dominant root cause (explicit)

> The system is alive at fusion, but risk blocks **2696** of **2697** directional fused bars (`99.96%`). The dominant veto tag (counted per veto line when multiple apply) is **`effective_score_below_probe_floor`** (1771 occurrences, **45.3%** of 3910 total veto line events). Average effective score on blocked directional bars is **0.187553** vs probe floor **0.55**.

## Reproduce

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.research.diagnostic_risk_pipeline
```

Default output: `renaissance_v4/reports/diagnostic_risk_v1.md`

