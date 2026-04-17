/**
 * Engine-shell math only — no trading policy logic.
 * Extracted from legacy Jupiter policy modules so lifecycle does not import policy code.
 */
export const ATR_PERIOD = 14;

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
