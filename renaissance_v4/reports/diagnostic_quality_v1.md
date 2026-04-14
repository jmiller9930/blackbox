# RenaissanceV4 — Economic quality diagnostic v1 (read-only)

Generated: **2026-04-14 20:54:57 UTC** · `renaissance_v4/research/diagnostic_quality_pipeline.py`

- **Dataset bars:** 210240
- **Closed trades (unique outcomes):** 1702

## Portfolio (all closed trades)

- n=1702 | win%=0.2803 | E=-0.004783 | avg_pnl=-0.004783 | max_dd=48.420914 | avg_mae=1.351504 | avg_mfe=1.867938
- **Total gross PnL:** -8.14062857

## 7.1 Signal-level performance (contributing signal tags)

Each trade is duplicated into **every** contributing signal row (same method as scorecards). `n` is **not** unique trade count across rows.

| Signal | n (tagged) | win_rate | expectancy | avg_pnl | max_dd | avg_MAE | avg_MFE | share of loss mass* |
|--------|------------|----------|------------|---------|--------|---------|---------|----------------------|
| `trend_continuation` | 46 | 0.2826 | -0.109149 | -0.109149 | 7.347714 | 1.020652 | 1.468478 | 1.3% |
| `pullback_continuation` | 44 | 0.2727 | -0.174214 | -0.174214 | 10.924000 | 0.963636 | 1.288636 | 1.9% |
| `breakout_expansion` | 51 | 0.2745 | -0.018174 | -0.018174 | 4.394457 | 6.490196 | 5.799020 | 0.2% |
| `mean_reversion_fade` | 1605 | 0.2804 | -0.001366 | -0.001366 | 40.801886 | 1.197701 | 1.754474 | 0.6% |

*Share of loss mass* = abs(group gross PnL) / abs(sum of negative trade PnLs portfolio-wide) when group PnL is negative; else 0.

### Signal **family** (each trade counted once per distinct family in its contributing list)

| Family | n (rows) | win_rate | expectancy | avg_pnl | max_dd | avg_MAE | avg_MFE |
|--------|----------|----------|------------|---------|--------|---------|---------|
| `trend_family` | 46 | 0.2826 | -0.109149 | -0.109149 | 7.347714 | 1.020652 | 1.468478 |
| `mean_reversion_family` | 1605 | 0.2804 | -0.001366 | -0.001366 | 40.801886 | 1.197701 | 1.754474 |
| `breakout_family` | 51 | 0.2745 | -0.018174 | -0.018174 | 4.394457 | 6.490196 | 5.799020 |

## 7.2 Regime performance (exit `regime` on outcome)

| Regime | n | win_rate | expectancy | avg_pnl | max_dd |
|--------|---|----------|------------|---------|--------|
| `unstable` | 1292 | 0.2307 | -0.035681 | -0.035681 | 62.946457 |
| `trend_up` | 85 | 0.2118 | -0.132588 | -0.132588 | 13.176514 |
| `volatility_compression` | 9 | 0.5556 | 0.205810 | 0.205810 | 0.409143 |
| `volatility_expansion` | 49 | 0.3061 | 0.148181 | 0.148181 | 5.062514 |
| `trend_down` | 65 | 0.3692 | 0.153564 | 0.153564 | 4.271200 |
| `range` | 202 | 0.5792 | 0.149178 | 0.149178 | 1.760057 |

## 7.3 Directional performance

| Side | n | win_rate | expectancy | avg_pnl |
|------|---|----------|------------|---------|
| `long` | 811 | 0.2824 | -0.002623 | -0.002623 |
| `short` | 891 | 0.2783 | -0.006749 | -0.006749 |

## 7.4 Exit-reason performance

| exit_reason | n | win_rate | avg_pnl | avg_MAE | avg_MFE |
|-------------|---|----------|---------|---------|---------|
| `stop` | 1225 | 0.0000 | -0.321747 | 1.619053 | 1.239886 |
| `target` | 477 | 1.0000 | 0.809224 | 0.664403 | 3.480860 |

## 7.5 Risk-tier performance (`size_tier` at entry)

| Tier | n | win_rate | expectancy | avg_pnl | max_dd |
|------|---|----------|------------|---------|--------|
| `full` | 65 | 0.2462 | -0.168299 | -0.168299 | 20.393143 |
| `probe` | 1053 | 0.2811 | -0.000332 | -0.000332 | 9.194571 |
| `reduced` | 584 | 0.2825 | 0.005391 | 0.005391 | 30.014286 |

## 7.6 Time distribution (chronological trade thirds)

- **first_third_of_trades (chronological):** n=567 | win%=0.2857 | E=-0.029649 | avg_pnl=-0.029649 | max_dd=33.307371 | avg_mae=1.412169 | avg_mfe=1.982451
- **middle_third:** n=567 | win%=0.2734 | E=0.006092 | avg_pnl=0.006092 | max_dd=19.189771 | avg_mae=1.612875 | avg_mfe=2.158148
- **final_third:** n=568 | win%=0.2817 | E=0.009183 | avg_pnl=0.009183 | max_dd=11.205200 | avg_mae=1.030035 | avg_mfe=1.463926

## Dominant root cause (evidence-ranked)

> The system is alive but economically weak because **aggregate expectancy is negative** (`-0.004783`) with **large path drawdown** (`max_dd=48.4209` on the equity curve built from these trades). **Regime:** the worst gross PnL bucket by **exit regime** is **`unstable`** (gross PnL **-46.099429**). **Signals (tagged rows):** the weakest named contributor among the four primaries is **`pullback_continuation`** (gross PnL **-7.665429** across tagged outcomes). **Exit path:** stops dominate count (`stop` n=1225, avg_pnl=-0.321747) vs targets (`target` n=477, avg_pnl=0.809224), indicating **adverse exits hit more often than favorable targets** under current SL/TP geometry.

## Reproduce

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.research.diagnostic_quality_pipeline
```

