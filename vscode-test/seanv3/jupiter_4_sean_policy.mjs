/**
 * Jupiter_4 Sean momentum perps — SeanV3-native port aligned with
 * modules/anna_training/jupiter_4_sean_policy.py (generate_signal_from_ohlc_v4).
 * No BOS; uses EMA9/21 crossover + price vs EMA21 + RSI(52/48) + volume spike + ATR expected move.
 */

import {
  emaSeries,
  rsi,
  calculateAtr,
  EMA_SHORT_PERIOD,
  EMA_LONG_PERIOD,
  RSI_PERIOD,
} from './jupiter_3_sean_policy.mjs';

export const RSI_LONG_THRESHOLD = 52.0;
export const RSI_SHORT_THRESHOLD = 48.0;
export const VOLUME_SPIKE_MULTIPLIER = 1.2;
export const MIN_EXPECTED_MOVE = 0.5;
export const ATR_PERIOD = 14;

/** Aligned with Python: max(EMA_LONG_PERIOD, ATR_PERIOD) + 50 */
export const MIN_BARS = Math.max(EMA_LONG_PERIOD, ATR_PERIOD) + 50;

export const CATALOG_ID = 'jupiter_4_sean_perps_v1';
export const ENGINE_ID = 'jupiter_4_sean_policy_mjs_v1';
export const POLICY_ENGINE_ID = 'jupiter_4';

/**
 * @param {number[]} closes
 * @param {number[]} highs
 * @param {number[]} lows
 * @param {number[]} volumes
 * @returns {{ shortSignal: boolean, longSignal: boolean, signalPrice: number, diag: Record<string, unknown> }}
 */
export function generateSignalFromOhlcV4(closes, highs, lows, volumes) {
  const diag = { policy_engine: POLICY_ENGINE_ID, catalog_id: CATALOG_ID };
  const n = closes.length;
  if (n < MIN_BARS) {
    return {
      shortSignal: false,
      longSignal: false,
      signalPrice: 0,
      diag: { ...diag, reason: 'insufficient_history', min_bars: MIN_BARS },
    };
  }
  if (highs.length !== n || lows.length !== n || volumes.length !== n) {
    return {
      shortSignal: false,
      longSignal: false,
      signalPrice: 0,
      diag: { ...diag, reason: 'length_mismatch' },
    };
  }

  const ema9 = emaSeries(closes, EMA_SHORT_PERIOD);
  const ema21 = emaSeries(closes, EMA_LONG_PERIOD);
  const e9 = ema9[n - 1];
  const e21 = ema21[n - 1];
  const e9p = ema9[n - 2];
  const e21p = ema21[n - 2];
  const currentClose = closes[n - 1];

  if (Number.isNaN(e9) || Number.isNaN(e21)) {
    return { shortSignal: false, longSignal: false, signalPrice: 0, diag: { ...diag, reason: 'ema_nan' } };
  }

  const rsiVals = rsi(closes, RSI_PERIOD);
  const currentRsi = rsiVals[n - 1];
  if (Number.isNaN(currentRsi)) {
    return { shortSignal: false, longSignal: false, signalPrice: 0, diag: { ...diag, reason: 'rsi_nan' } };
  }

  const avgVolume = volumes.reduce((a, b) => a + b, 0) / Math.max(volumes.length, 1);
  const candleVol = volumes[n - 1];
  const volumeSpike = candleVol > avgVolume * VOLUME_SPIKE_MULTIPLIER;

  const atrVal = calculateAtr(closes, highs, lows);
  const expectedMove = atrVal * 2.5;

  const bullishCrossover = e9p <= e21p && e9 > e21;
  const bearishCrossover = e9p >= e21p && e9 < e21;
  const priceAboveEma21 = currentClose > e21;
  const priceBelowEma21 = currentClose < e21;

  const longGate =
    bullishCrossover &&
    priceAboveEma21 &&
    currentRsi >= RSI_LONG_THRESHOLD &&
    volumeSpike &&
    expectedMove >= MIN_EXPECTED_MOVE;

  const shortGate =
    bearishCrossover &&
    priceBelowEma21 &&
    currentRsi <= RSI_SHORT_THRESHOLD &&
    volumeSpike &&
    expectedMove >= MIN_EXPECTED_MOVE;

  const bullishBias = e9 > e21;
  const bearishBias = e9 < e21;

  const jupiterV4Gates = {
    schema: 'jupiter_v4_gates_v1',
    rows: [
      {
        id: 'bias',
        label: 'EMA bias (9/21 + close vs 21)',
        long_ok: bullishBias && priceAboveEma21,
        short_ok: bearishBias && priceBelowEma21,
      },
      {
        id: 'rsi',
        label: `RSI (long ≥ ${RSI_LONG_THRESHOLD}, short ≤ ${RSI_SHORT_THRESHOLD})`,
        long_ok: currentRsi >= RSI_LONG_THRESHOLD,
        short_ok: currentRsi <= RSI_SHORT_THRESHOLD,
      },
      {
        id: 'volume_spike',
        label: `Volume spike (>${VOLUME_SPIKE_MULTIPLIER}× avg)`,
        long_ok: volumeSpike,
        short_ok: volumeSpike,
      },
      {
        id: 'crossover',
        label: 'EMA9/21 crossover',
        long_ok: bullishCrossover,
        short_ok: bearishCrossover,
      },
      {
        id: 'expected_move',
        label: `Expected move ≥ ${MIN_EXPECTED_MOVE} (ATR×2.5)`,
        long_ok: expectedMove >= MIN_EXPECTED_MOVE,
        short_ok: expectedMove >= MIN_EXPECTED_MOVE,
      },
    ],
    long: { all_ok: longGate },
    short: { all_ok: shortGate },
  };

  Object.assign(diag, {
    ema9: e9,
    ema21: e21,
    bullish_crossover: bullishCrossover,
    bearish_crossover: bearishCrossover,
    bullish_bias: bullishBias,
    bearish_bias: bearishBias,
    current_rsi: currentRsi,
    atr: atrVal,
    expected_move: expectedMove,
    avg_volume: avgVolume,
    candle_volume: candleVol,
    volume_spike: volumeSpike,
    long_gate: longGate,
    short_gate: shortGate,
    jupiter_v4_gates: jupiterV4Gates,
    short_signal_core: shortGate,
    long_signal_core: longGate,
  });

  return {
    shortSignal: shortGate,
    longSignal: longGate,
    signalPrice: currentClose,
    diag,
  };
}

/** Short wins when both fire (matches Python / v3). */
export function resolveEntrySide(shortSignal, longSignal) {
  if (shortSignal && longSignal) return 'short';
  if (shortSignal) return 'short';
  if (longSignal) return 'long';
  return null;
}
