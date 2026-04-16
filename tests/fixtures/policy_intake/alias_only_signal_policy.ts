/**
 * DV-065: Same logic as minimal_direction but uses long/short aliases only (no longSignal/shortSignal).
 */
export const MIN_BARS = 2;
export const policy_id = 'fixture_alias_only_signal_v1';

export function generateSignalFromOhlc(
  closes: number[],
  _highs: number[],
  _lows: number[],
  _volumes: number[],
): { long: boolean; short: boolean; signalPrice: number } {
  const n = closes.length;
  if (n < MIN_BARS) {
    return { long: false, short: false, signalPrice: 0 };
  }
  const c = closes[n - 1];
  const p = closes[n - 2];
  return {
    short: c < p,
    long: c > p,
    signalPrice: c,
  };
}
