/**
 * Deterministic indicator series for intake harness (DV-ARCH-INDICATOR-MECHANICS-064).
 * Keep formulas aligned with Python validation params in indicators_v1.py.
 *
 * Each declaration produces either number[] (per bar) or { key: number[] } for composites.
 */
export function buildSeriesByDeclarationId(declarations, closes, highs, lows, vols) {
  const byId = {};
  if (!Array.isArray(declarations)) return byId;
  for (const decl of declarations) {
    if (!decl || typeof decl !== 'object') continue;
    const id = String(decl.id || '').trim();
    const kind = String(decl.kind || '').trim().toLowerCase();
    if (!id || !kind) continue;
    try {
      byId[id] = computeOne(kind, decl.params || {}, closes, highs, lows, vols);
    } catch (e) {
      byId[id] = { _error: String(e && e.message ? e.message : e) };
    }
  }
  return byId;
}

export function indicatorsAtBar(seriesById, barIndex) {
  const indicators = {};
  for (const [id, ser] of Object.entries(seriesById)) {
    if (ser && typeof ser === 'object' && !Array.isArray(ser) && ser._error) {
      indicators[id] = null;
      continue;
    }
    if (Array.isArray(ser)) {
      const v = ser[barIndex];
      indicators[id] = Number.isFinite(v) ? v : null;
    } else if (ser && typeof ser === 'object') {
      const o = {};
      for (const [k, arr] of Object.entries(ser)) {
        if (Array.isArray(arr)) {
          const v = arr[barIndex];
          o[k] = Number.isFinite(v) ? v : null;
        }
      }
      indicators[id] = o;
    } else {
      indicators[id] = null;
    }
  }
  return indicators;
}

function computeOne(kind, p, closes, highs, lows, vols) {
  const n = closes.length;
  switch (kind) {
    case 'ema':
      return ema(closes, intParam(p, 'period'));
    case 'sma':
      return sma(closes, intParam(p, 'period'));
    case 'rsi':
      return rsi(closes, intParam(p, 'period'));
    case 'atr':
      return atr(highs, lows, closes, intParam(p, 'period'));
    case 'macd': {
      const fast = intParam(p, 'fast_period');
      const slow = intParam(p, 'slow_period');
      const sig = intParam(p, 'signal_period');
      const emaF = ema(closes, fast);
      const emaS = ema(closes, slow);
      const line = new Array(n).fill(NaN);
      for (let i = 0; i < n; i++) {
        if (Number.isFinite(emaF[i]) && Number.isFinite(emaS[i])) line[i] = emaF[i] - emaS[i];
      }
      const signal = ema(
        line.map((x) => (Number.isFinite(x) ? x : 0)),
        sig,
      );
      const hist = new Array(n).fill(NaN);
      for (let i = 0; i < n; i++) {
        if (Number.isFinite(line[i]) && Number.isFinite(signal[i])) hist[i] = line[i] - signal[i];
      }
      return { macd: line, signal, histogram: hist };
    }
    case 'bollinger_bands': {
      const period = intParam(p, 'period');
      const stdDev = numParam(p, 'std_dev');
      const mid = sma(closes, period);
      const upper = new Array(n).fill(NaN);
      const lower = new Array(n).fill(NaN);
      for (let i = period - 1; i < n; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
          const d = closes[i - j] - mid[i];
          sum += d * d;
        }
        const sd = Math.sqrt(sum / period);
        upper[i] = mid[i] + stdDev * sd;
        lower[i] = mid[i] - stdDev * sd;
      }
      return { middle: mid, upper, lower };
    }
    case 'vwap':
      return vwapSeries(closes, highs, lows, vols);
    case 'supertrend':
      return supertrend(highs, lows, closes, intParam(p, 'period'), numParam(p, 'multiplier'));
    case 'stochastic': {
      const kp = intParam(p, 'k_period');
      const dp = intParam(p, 'd_period');
      const rawK = stochK(closes, highs, lows, kp);
      const kArr = sma(rawK.map((x) => (Number.isFinite(x) ? x : 0)), 3);
      const dArr = sma(kArr.map((x) => (Number.isFinite(x) ? x : 0)), dp);
      return { k: kArr, d: dArr };
    }
    case 'adx':
      return adx(highs, lows, closes, intParam(p, 'period'));
    case 'cci':
      return cci(closes, highs, lows, intParam(p, 'period'));
    case 'williams_r':
      return williamsR(closes, highs, lows, intParam(p, 'period'));
    case 'mfi':
      return mfi(closes, highs, lows, vols, intParam(p, 'period'));
    case 'obv':
      return obv(closes, vols);
    case 'parabolic_sar':
      return parabolicSar(highs, lows, closes, numParam(p, 'step'), numParam(p, 'max_step'));
    case 'ichimoku': {
      const ten = intParam(p, 'tenkan');
      const kij = intParam(p, 'kijun');
      const sen = intParam(p, 'senkou_b');
      return {
        tenkan: midline(highs, lows, ten),
        kijun: midline(highs, lows, kij),
        senkou_b: midline(highs, lows, sen),
      };
    }
    case 'donchian': {
      const period = intParam(p, 'period');
      const upper = new Array(n).fill(NaN);
      const lower = new Array(n).fill(NaN);
      for (let i = period - 1; i < n; i++) {
        let hi = -Infinity;
        let lo = Infinity;
        for (let j = 0; j < period; j++) {
          hi = Math.max(hi, highs[i - j]);
          lo = Math.min(lo, lows[i - j]);
        }
        upper[i] = hi;
        lower[i] = lo;
      }
      const mid = new Array(n).fill(NaN);
      for (let i = 0; i < n; i++) {
        if (Number.isFinite(upper[i]) && Number.isFinite(lower[i])) mid[i] = (upper[i] + lower[i]) / 2;
      }
      return { upper, lower, middle: mid };
    }
    case 'volume_filter':
      return volumeFilter(closes, highs, lows, vols, p);
    case 'body_measurement':
      return bodyMeasurement(closes, highs, lows, p);
    case 'fixed_threshold': {
      const v = numParam(p, 'value');
      return new Array(n).fill(v);
    }
    default:
      return new Array(n).fill(NaN);
  }
}

function intParam(p, k) {
  const v = p[k];
  if (!Number.isFinite(v) || v < 1) throw new Error(`missing_int:${k}`);
  return Math.floor(v);
}

function numParam(p, k) {
  const v = p[k];
  if (!Number.isFinite(v)) throw new Error(`missing_num:${k}`);
  return v;
}

function sma(arr, period) {
  const n = arr.length;
  const out = new Array(n).fill(NaN);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    sum += arr[i];
    if (i >= period) sum -= arr[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

function ema(arr, period) {
  const n = arr.length;
  const out = new Array(n).fill(NaN);
  const k = 2 / (period + 1);
  let sum = 0;
  for (let i = 0; i < period; i++) sum += arr[i];
  out[period - 1] = sum / period;
  for (let i = period; i < n; i++) {
    out[i] = (arr[i] - out[i - 1]) * k + out[i - 1];
  }
  return out;
}

function trueRange(highs, lows, closes) {
  const n = closes.length;
  const tr = new Array(n).fill(0);
  tr[0] = highs[0] - lows[0];
  for (let i = 1; i < n; i++) {
    const hl = highs[i] - lows[i];
    const hc = Math.abs(highs[i] - closes[i - 1]);
    const lc = Math.abs(lows[i] - closes[i - 1]);
    tr[i] = Math.max(hl, hc, lc);
  }
  return tr;
}

function wilderSmooth(arr, period) {
  const n = arr.length;
  const out = new Array(n).fill(NaN);
  let sum = 0;
  for (let i = 0; i < period; i++) sum += arr[i];
  out[period - 1] = sum / period;
  for (let i = period; i < n; i++) {
    out[i] = (out[i - 1] * (period - 1) + arr[i]) / period;
  }
  return out;
}

function rsi(closes, period) {
  const n = closes.length;
  const gains = new Array(n).fill(0);
  const losses = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    const ch = closes[i] - closes[i - 1];
    if (ch > 0) gains[i] = ch;
    else losses[i] = -ch;
  }
  const avgG = wilderSmooth(gains, period);
  const avgL = wilderSmooth(losses, period);
  const out = new Array(n).fill(NaN);
  for (let i = 0; i < n; i++) {
    if (!Number.isFinite(avgG[i]) || !Number.isFinite(avgL[i])) continue;
    if (avgL[i] === 0) out[i] = 100;
    else {
      const rs = avgG[i] / avgL[i];
      out[i] = 100 - 100 / (1 + rs);
    }
  }
  return out;
}

function atr(highs, lows, closes, period) {
  const tr = trueRange(highs, lows, closes);
  return wilderSmooth(tr, period);
}

function stochK(closes, highs, lows, period) {
  const n = closes.length;
  const out = new Array(n).fill(NaN);
  for (let i = period - 1; i < n; i++) {
    let hh = -Infinity;
    let ll = Infinity;
    for (let j = 0; j < period; j++) {
      hh = Math.max(hh, highs[i - j]);
      ll = Math.min(ll, lows[i - j]);
    }
    const denom = hh - ll;
    out[i] = denom === 0 ? 50 : ((closes[i] - ll) / denom) * 100;
  }
  return out;
}

function vwapSeries(closes, highs, lows, vols) {
  const n = closes.length;
  const out = new Array(n).fill(NaN);
  let cumPV = 0;
  let cumV = 0;
  for (let i = 0; i < n; i++) {
    const tp = (highs[i] + lows[i] + closes[i]) / 3;
    const v = Math.max(vols[i], 1e-12);
    cumPV += tp * v;
    cumV += v;
    out[i] = cumPV / cumV;
  }
  return out;
}

function supertrend(highs, lows, closes, period, mult) {
  const atrArr = atr(highs, lows, closes, period);
  const n = closes.length;
  const basicUpper = new Array(n).fill(NaN);
  const basicLower = new Array(n).fill(NaN);
  for (let i = 0; i < n; i++) {
    if (!Number.isFinite(atrArr[i])) continue;
    const hl2 = (highs[i] + lows[i]) / 2;
    basicUpper[i] = hl2 + mult * atrArr[i];
    basicLower[i] = hl2 - mult * atrArr[i];
  }
  return basicUpper.map((u, i) => (Number.isFinite(u) && Number.isFinite(basicLower[i]) ? (u + basicLower[i]) / 2 : NaN));
}

function adx(highs, lows, closes, period) {
  const n = closes.length;
  const tr = trueRange(highs, lows, closes);
  const plusDM = new Array(n).fill(0);
  const minusDM = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    const upMove = highs[i] - highs[i - 1];
    const downMove = lows[i - 1] - lows[i];
    if (upMove > downMove && upMove > 0) plusDM[i] = upMove;
    if (downMove > upMove && downMove > 0) minusDM[i] = downMove;
  }
  const atrArr = wilderSmooth(tr, period);
  const smPlus = wilderSmooth(plusDM, period);
  const smMinus = wilderSmooth(minusDM, period);
  const plusDI = new Array(n).fill(NaN);
  const minusDI = new Array(n).fill(NaN);
  const dx = new Array(n).fill(NaN);
  for (let i = 0; i < n; i++) {
    if (!Number.isFinite(atrArr[i]) || atrArr[i] === 0) continue;
    plusDI[i] = (100 * smPlus[i]) / atrArr[i];
    minusDI[i] = (100 * smMinus[i]) / atrArr[i];
    const s = plusDI[i] + minusDI[i];
    if (Number.isFinite(s) && s !== 0) dx[i] = (100 * Math.abs(plusDI[i] - minusDI[i])) / s;
  }
  return wilderSmooth(
    dx.map((x) => (Number.isFinite(x) ? x : 0)),
    period,
  );
}

function cci(closes, highs, lows, period) {
  const n = closes.length;
  const tp = closes.map((c, i) => (highs[i] + lows[i] + c) / 3);
  const out = new Array(n).fill(NaN);
  for (let i = period - 1; i < n; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) sum += tp[i - j];
    const smaTp = sum / period;
    let md = 0;
    for (let j = 0; j < period; j++) md += Math.abs(tp[i - j] - smaTp);
    md /= period;
    out[i] = md === 0 ? 0 : (tp[i] - smaTp) / (0.015 * md);
  }
  return out;
}

function williamsR(closes, highs, lows, period) {
  const n = closes.length;
  const out = new Array(n).fill(NaN);
  for (let i = period - 1; i < n; i++) {
    let hh = -Infinity;
    let ll = Infinity;
    for (let j = 0; j < period; j++) {
      hh = Math.max(hh, highs[i - j]);
      ll = Math.min(ll, lows[i - j]);
    }
    const denom = hh - ll;
    out[i] = denom === 0 ? -50 : -100 * ((hh - closes[i]) / denom);
  }
  return out;
}

function mfi(closes, highs, lows, vols, period) {
  const n = closes.length;
  const tp = closes.map((c, i) => (highs[i] + lows[i] + c) / 3);
  const out = new Array(n).fill(NaN);
  for (let i = period; i < n; i++) {
    let pos = 0;
    let neg = 0;
    for (let j = 0; j < period; j++) {
      const idx = i - j;
      const raw = tp[idx] * vols[idx];
      if (idx > 0 && tp[idx] > tp[idx - 1]) pos += raw;
      else if (idx > 0 && tp[idx] < tp[idx - 1]) neg += raw;
    }
    if (neg === 0) out[i] = 100;
    else {
      const mfr = pos / neg;
      out[i] = 100 - 100 / (1 + mfr);
    }
  }
  return out;
}

function obv(closes, vols) {
  const n = closes.length;
  const out = new Array(n).fill(NaN);
  let acc = 0;
  out[0] = 0;
  for (let i = 1; i < n; i++) {
    if (closes[i] > closes[i - 1]) acc += vols[i];
    else if (closes[i] < closes[i - 1]) acc -= vols[i];
    out[i] = acc;
  }
  return out;
}

function parabolicSar(highs, lows, closes, step, maxStep) {
  const n = closes.length;
  const out = new Array(n).fill(NaN);
  if (n < 3) return out;
  let isLong = closes[1] > closes[0];
  let af = step;
  let ep = isLong ? highs[0] : lows[0];
  let sar = isLong ? lows[0] : highs[0];
  out[0] = sar;
  for (let i = 1; i < n; i++) {
    const prevSar = sar;
    sar = prevSar + af * (ep - prevSar);
    if (isLong) {
      sar = Math.min(sar, lows[i - 1], i > 1 ? lows[i - 2] : lows[i - 1]);
      if (closes[i] < sar) {
        isLong = false;
        sar = ep;
        ep = lows[i];
        af = step;
      } else {
        if (highs[i] > ep) {
          ep = highs[i];
          af = Math.min(maxStep, af + step);
        }
      }
    } else {
      sar = Math.max(sar, highs[i - 1], i > 1 ? highs[i - 2] : highs[i - 1]);
      if (closes[i] > sar) {
        isLong = true;
        sar = ep;
        ep = highs[i];
        af = step;
      } else {
        if (lows[i] < ep) {
          ep = lows[i];
          af = Math.min(maxStep, af + step);
        }
      }
    }
    out[i] = sar;
  }
  return out;
}

function midline(highs, lows, period) {
  const n = highs.length;
  const out = new Array(n).fill(NaN);
  for (let i = period - 1; i < n; i++) {
    let hh = -Infinity;
    let ll = Infinity;
    for (let j = 0; j < period; j++) {
      hh = Math.max(hh, highs[i - j]);
      ll = Math.min(ll, lows[i - j]);
    }
    out[i] = (hh + ll) / 2;
  }
  return out;
}

function volumeFilter(closes, highs, lows, vols, p) {
  const mode = String(p.mode || '');
  const n = closes.length;
  if (mode === 'relative_to_sma') {
    const period = intParam(p, 'period');
    const volSma = sma(vols, period);
    return vols.map((v, i) => (Number.isFinite(volSma[i]) && volSma[i] > 0 ? v / volSma[i] : NaN));
  }
  if (mode === 'min_quote_volume' || mode === 'min_raw_volume') {
    const minV = Number.isFinite(p.min_volume) ? p.min_volume : 0;
    return vols.map((v) => (v >= minV ? 1 : 0));
  }
  if (mode === 'session_compare') {
    return vols.map((v, i) => (i > 0 && v > vols[i - 1] ? 1 : 0));
  }
  return new Array(n).fill(NaN);
}

function bodyMeasurement(closes, highs, lows, p) {
  const mode = String(p.mode || '');
  const n = closes.length;
  const out = new Array(n).fill(NaN);
  for (let i = 0; i < n; i++) {
    const body = Math.abs(closes[i] - (i > 0 ? closes[i - 1] : closes[i]));
    const rng = highs[i] - lows[i];
    if (mode === 'body_to_range') out[i] = rng === 0 ? 0 : body / rng;
    else if (mode === 'body_pct_of_range') out[i] = rng === 0 ? 0 : (100 * body) / rng;
    else if (mode === 'candle_direction') out[i] = closes[i] >= (i > 0 ? closes[i - 1] : closes[i]) ? 1 : -1;
  }
  return out;
}
