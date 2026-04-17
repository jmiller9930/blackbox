/**
 * Paper lifecycle — SL/TP, breakeven, monotonic trailing (port of jupiter_2_baseline_lifecycle exit mechanics).
 */

import { calculateAtr } from './engine/atr_math.mjs';

export const SL_ATR_MULT = 1.6;
export const TP_ATR_MULT = 4.0;
export const BREAKEVEN_MOVE_PCT = 0.002;

export function initialSlTp(entry, atrEntry, side) {
  const sd = String(side).toLowerCase();
  const slDist = SL_ATR_MULT * atrEntry;
  const tpDist = TP_ATR_MULT * atrEntry;
  const ep = entry;
  if (sd === 'long') {
    return { stopLoss: ep - slDist, takeProfit: ep + tpDist };
  }
  if (sd === 'short') {
    return { stopLoss: ep + slDist, takeProfit: ep - tpDist };
  }
  throw new Error('side must be long or short');
}

export function computePnlUsd(entry, exit, size, side) {
  const sd = String(side).toLowerCase();
  if (sd === 'long') return (exit - entry) * size;
  if (sd === 'short') return (entry - exit) * size;
  return 0;
}

export function applyBreakeven(side, entry, stopLoss, high, low, breakevenApplied) {
  if (breakevenApplied) return { stopLoss, breakevenApplied: true, justFired: false };
  const ep = entry;
  const sl = stopLoss;
  const sd = String(side).toLowerCase();
  if (sd === 'long') {
    if (ep > 0 && (high - ep) / ep >= BREAKEVEN_MOVE_PCT) {
      return { stopLoss: Math.max(sl, ep), breakevenApplied: true, justFired: true };
    }
  } else if (sd === 'short') {
    if (ep > 0 && (ep - low) / ep >= BREAKEVEN_MOVE_PCT) {
      return { stopLoss: Math.min(sl, ep), breakevenApplied: true, justFired: true };
    }
  }
  return { stopLoss: sl, breakevenApplied, justFired: false };
}

export function applyTrailingMonotonic(side, prevStop, close, atrT) {
  const dist = SL_ATR_MULT * atrT;
  const sd = String(side).toLowerCase();
  if (sd === 'long') {
    const cand = close - dist;
    return Math.max(prevStop, cand);
  }
  if (sd === 'short') {
    const cand = close + dist;
    return Math.min(prevStop, cand);
  }
  throw new Error('side must be long or short');
}

/**
 * @returns {{ reason: 'STOP_LOSS' | 'TAKE_PROFIT', fill: number } | null}
 */
export function evaluateExitOhlc(side, stopLoss, takeProfit, open_, high, low, close) {
  const sd = String(side).toLowerCase();
  const sl = stopLoss;
  const tp = takeProfit;
  const o = open_;
  const h = high;
  const l = low;
  const c = close;

  if (sd === 'long') {
    const hitSl = l <= sl;
    const hitTp = h >= tp;
    if (hitSl && hitTp) return { reason: 'STOP_LOSS', fill: sl };
    if (hitSl) return { reason: 'STOP_LOSS', fill: sl };
    if (hitTp) return { reason: 'TAKE_PROFIT', fill: tp };
    return null;
  }
  if (sd === 'short') {
    const hitSl = h >= sl;
    const hitTp = l <= tp;
    if (hitSl && hitTp) return { reason: 'STOP_LOSS', fill: sl };
    if (hitSl) return { reason: 'STOP_LOSS', fill: sl };
    if (hitTp) return { reason: 'TAKE_PROFIT', fill: tp };
    return null;
  }
  throw new Error('side must be long or short');
}

export function atrFromBarWindow(closes, highs, lows) {
  return calculateAtr(closes, highs, lows);
}
