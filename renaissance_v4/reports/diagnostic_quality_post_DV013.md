# RenaissanceV4 — Economic quality diagnostic v1 (read-only)

Generated: **2026-04-14 21:07:58 UTC** · `renaissance_v4/research/diagnostic_quality_pipeline.py`

- **Dataset bars:** 210240
- **Closed trades (unique outcomes):** 1969

## Portfolio (all closed trades)

- n=1969 | win%=0.3443 | E=0.008256 | avg_pnl=0.008256 | max_dd=24.297305 | avg_mae=1.353073 | avg_mfe=1.725394
- **Total gross PnL:** 16.25669214

## 7.1 Signal-level performance (contributing signal tags)

Each trade is duplicated into **every** contributing signal row (same method as scorecards). `n` is **not** unique trade count across rows.

| Signal | n (tagged) | win_rate | expectancy | avg_pnl | max_dd | avg_MAE | avg_MFE | share of loss mass* |
|--------|------------|----------|------------|---------|--------|---------|---------|----------------------|
| `trend_continuation` | 41 | 0.3659 | -0.014088 | -0.014088 | 1.587201 | 1.345122 | 1.518049 | 0.1% |
| `pullback_continuation` | 38 | 0.3684 | -0.000206 | -0.000206 | 1.139493 | 1.019474 | 1.368684 | 0.0% |
| `breakout_expansion` | 50 | 0.4000 | 0.046433 | 0.046433 | 5.026367 | 6.661600 | 5.775200 | 0.0% |
| `mean_reversion_fade` | 1878 | 0.3424 | 0.007728 | 0.007728 | 27.566052 | 1.211912 | 1.622098 | 0.0% |

*Share of loss mass* = abs(group gross PnL) / abs(sum of negative trade PnLs portfolio-wide) when group PnL is negative; else 0.

### Signal **family** (each trade counted once per distinct family in its contributing list)

| Family | n (rows) | win_rate | expectancy | avg_pnl | max_dd | avg_MAE | avg_MFE |
|--------|----------|----------|------------|---------|--------|---------|---------|
| `trend_family` | 41 | 0.3659 | -0.014088 | -0.014088 | 1.587201 | 1.345122 | 1.518049 |
| `breakout_family` | 50 | 0.4000 | 0.046433 | 0.046433 | 5.026367 | 6.661600 | 5.775200 |
| `mean_reversion_family` | 1878 | 0.3424 | 0.007728 | 0.007728 | 27.566052 | 1.211912 | 1.622098 |

## 7.2 Regime performance (exit `regime` on outcome)

| Regime | n | win_rate | expectancy | avg_pnl | max_dd |
|--------|---|----------|------------|---------|--------|
| `unstable` | 1326 | 0.2353 | -0.043767 | -0.043767 | 65.444676 |
| `trend_up` | 94 | 0.2234 | -0.193095 | -0.193095 | 18.250243 |
| `volatility_expansion` | 46 | 0.3261 | -0.087298 | -0.087298 | 7.920134 |
| `volatility_compression` | 12 | 0.5000 | 0.023343 | 0.023343 | 1.029600 |
| `trend_down` | 81 | 0.3827 | 0.043460 | 0.043460 | 4.932141 |
| `range` | 410 | 0.7146 | 0.225996 | 0.225996 | 1.075544 |

## 7.3 Directional performance

| Side | n | win_rate | expectancy | avg_pnl |
|------|---|----------|------------|---------|
| `long` | 952 | 0.3445 | 0.010009 | 0.010009 |
| `short` | 1017 | 0.3441 | 0.006615 | 0.006615 |

## 7.4 Exit-reason performance

| exit_reason | n | win_rate | avg_pnl | avg_MAE | avg_MFE |
|-------------|---|----------|---------|---------|---------|
| `stop` | 1291 | 0.0000 | -0.300021 | 1.707080 | 1.112122 |
| `target` | 678 | 1.0000 | 0.595257 | 0.678997 | 2.893142 |

## 7.5 Risk-tier performance (`size_tier` at entry)

| Tier | n | win_rate | expectancy | avg_pnl | max_dd |
|------|---|----------|------------|---------|--------|
| `probe` | 1276 | 0.3386 | -0.000230 | -0.000230 | 7.379859 |
| `reduced` | 693 | 0.3550 | 0.023882 | 0.023882 | 26.903218 |

## 7.6 Time distribution (chronological trade thirds)

- **first_third_of_trades (chronological):** n=656 | win%=0.3537 | E=0.007537 | avg_pnl=0.007537 | max_dd=17.022019 | avg_mae=1.443567 | avg_mfe=1.858491
- **middle_third:** n=656 | win%=0.3384 | E=-0.003816 | avg_pnl=-0.003816 | max_dd=19.795791 | avg_mae=1.625579 | avg_mfe=2.016098
- **final_third:** n=657 | win%=0.3409 | E=0.021029 | avg_pnl=0.021029 | max_dd=6.952069 | avg_mae=0.990624 | avg_mfe=1.302237

## Dominant root cause (evidence-ranked)

> The system is alive but economically weak because **aggregate expectancy is negative** (`0.008256`) with **large path drawdown** (`max_dd=24.2973` on the equity curve built from these trades). **Regime:** the worst gross PnL bucket by **exit regime** is **`unstable`** (gross PnL **-58.035607**). **Signals (tagged rows):** the weakest named contributor among the four primaries is **`trend_continuation`** (gross PnL **-0.577605** across tagged outcomes). **Exit path:** stops dominate count (`stop` n=1291, avg_pnl=-0.300021) vs targets (`target` n=678, avg_pnl=0.595257), indicating **adverse exits hit more often than favorable targets** under current SL/TP geometry.

## Reproduce

```bash
cd /path/to/blackbox
export PYTHONPATH=.
python3 -m renaissance_v4.research.diagnostic_quality_pipeline
```

