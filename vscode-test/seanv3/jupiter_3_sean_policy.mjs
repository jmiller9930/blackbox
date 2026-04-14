/**
 * Jupiter_3 Sean conviction/BOS baseline — SeanV3-native port (no Python).
 * Matches modules/anna_training/jupiter_3_sean_policy.py numerics for OHLCV inputs.
 */

export const EMA_SHORT_PERIOD = 9;
export const EMA_LONG_PERIOD = 21;
export const RSI_PERIOD = 14;
export const RSI_LONG_THRESHOLD = 55.0;
export const RSI_SHORT_THRESHOLD = 45.0;
export const VOLUME_SPIKE_MULTIPLIER = 1.5;
export const BOS_LOOKBACK_CANDLES = 5;
export const MIN_EXPECTED_MOVE = 0.8;
export const ATR_PERIOD = 14;
export const MIN_BARS = EMA_LONG_PERIOD + ATR_PERIOD + 10;
export const CATALOG_ID = 'jupiter_3_sean_perps_v1';
export const ENGINE_ID = 'jupiter_3_sean_policy_mjs_v1';

export function calculateAtr(closes, highs, lows) {
  if (closes.length < ATR_PERIOD + 1) return 0.25;
  const h = highs ?? closes;
  const l = lows ?? closes;
  let trSum = 0;
  for (let i = 1; i <= ATR_PERIOD; i++) {
    const high = h[h.length - i];
    const low = l[l.length - i];
    const prevClose = closes[closes.length - i - 1];
    const tr1 = high - low;
    const tr2 = Math.abs(high - prevClose);
    const tr3 = Math.abs(low - prevClose);
    trSum += Math.max(tr1, tr2, tr3);
  }
  return trSum / ATR_PERIOD;
}

export function emaSeries(series, period) {
  const n = series.length;
  if (n < period) return Array(n).fill(NaN);
  const out = Array(n).fill(NaN);
  let s = 0;
  for (let i = 0; i < period; i++) s += series[i];
  out[period - 1] = s / period;
  const alpha = 2 / (period + 1);
  for (let i = period; i < n; i++) {
    out[i] = series[i] * alpha + out[i - 1] * (1 - alpha);
  }
  return out;
}

export function rsi(series, period = RSI_PERIOD) {
  const n = series.length;
  if (n < period + 1) return Array(n).fill(NaN);
  const out = Array(n).fill(NaN);
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = series[i] - series[i - 1];
    if (d > 0) gain += d;
    else loss -= d;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  if (avgGain === 0 && avgLoss === 0) {
    avgGain = 0.001;
    avgLoss = 0.001;
  }
  let rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
  out[period] = 100 - 100 / (1 + rs);
  for (let i = period + 1; i < n; i++) {
    const d = series[i] - series[i - 1];
    const curGain = d > 0 ? d : 0;
    const curLoss = d < 0 ? -d : 0;
    avgGain = (avgGain * (period - 1) + curGain) / period;
    avgLoss = (avgLoss * (period - 1) + curLoss) / period;
    rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
    out[i] = 100 - 100 / (1 + rs);
  }
  return out;
}

function priorSwingLevels(highs, lows) {
  if (highs.length < BOS_LOOKBACK_CANDLES + 1 || lows.length < BOS_LOOKBACK_CANDLES + 1) {
    return { priorHigh: null, priorLow: null };
  }
  const ph = highs.slice(-(BOS_LOOKBACK_CANDLES + 1), -1);
  const pl = lows.slice(-(BOS_LOOKBACK_CANDLES + 1), -1);
  return { priorHigh: Math.max(...ph), priorLow: Math.min(...pl) };
}

/**
 * @param {number[]} closes
 * @param {number[]} highs
 * @param {number[]} lows
 * @param {number[]} volumes
 * @returns {{ shortSignal: boolean, longSignal: boolean, signalPrice: number, diag: Record<string, unknown> }}
 */
export function generateSignalFromOhlcV3(closes, highs, lows, volumes) {
  const diag = { policy_engine: ENGINE_ID, catalog_id: CATALOG_ID };
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
  const currentClose = closes[n - 1];
  if (Number.isNaN(e9) || Number.isNaN(e21)) {
    return { shortSignal: false, longSignal: false, signalPrice: 0, diag: { ...diag, reason: 'ema_nan' } };
  }

  const rsiVals = rsi(closes);
  const currentRsi = rsiVals[n - 1];
  if (Number.isNaN(currentRsi)) {
    return { shortSignal: false, longSignal: false, signalPrice: 0, diag: { ...diag, reason: 'rsi_nan' } };
  }

  const avgVolume = volumes.reduce((a, b) => a + b, 0) / Math.max(volumes.length, 1);
  const candleVol = volumes[n - 1];
  const volumeSpike = candleVol > avgVolume * VOLUME_SPIKE_MULTIPLIER;

  const bullishBias = e9 > e21 && currentClose > e21;
  const bearishBias = e9 < e21 && currentClose < e21;

  const atr = calculateAtr(closes, highs, lows);
  const expectedMove = atr * 2.5;

  const { priorHigh, priorLow } = priorSwingLevels(highs, lows);
  if (priorHigh == null || priorLow == null) {
    return {
      shortSignal: false,
      longSignal: false,
      signalPrice: 0,
      diag: { ...diag, reason: 'insufficient_bos_window' },
    };
  }

  const longBos = currentClose > priorHigh;
  const shortBos = currentClose < priorLow;

  const longSignal =
    bullishBias &&
    currentRsi >= RSI_LONG_THRESHOLD &&
    volumeSpike &&
    longBos &&
    expectedMove >= MIN_EXPECTED_MOVE;

  const shortSignal =
    bearishBias &&
    currentRsi <= RSI_SHORT_THRESHOLD &&
    volumeSpike &&
    shortBos &&
    expectedMove >= MIN_EXPECTED_MOVE;

  Object.assign(diag, {
    ema9: e9,
    ema21: e21,
    bullish_bias: bullishBias,
    bearish_bias: bearishBias,
    current_rsi: currentRsi,
    atr,
    expected_move: expectedMove,
    volume_spike: volumeSpike,
    prior_swing_high: priorHigh,
    prior_swing_low: priorLow,
    long_bos: longBos,
    short_bos: shortBos,
    long_signal_core: longSignal,
    short_signal_core: shortSignal,
  });

  return { shortSignal, longSignal, signalPrice: currentClose, diag };
}

/**
 * Resolve entry side when both fire (short over long — matches Python).
 */
export function resolveEntrySide(shortSignal, longSignal) {
  if (shortSignal && longSignal) return 'short';
  if (shortSignal) return 'short';
  if (longSignal) return 'long';
  return null;
}
