/**
 * Minimal self-contained policy for intake tests (DV-ARCH-KITCHEN-POLICY-INTAKE-048).
 */
export const MIN_BARS = 2;
export const policy_id = 'fixture_minimal_direction_v1';

export function generateSignalFromOhlc(
  closes: number[],
  _highs: number[],
  _lows: number[],
  _volumes: number[],
): { shortSignal: boolean; longSignal: boolean; signalPrice: number; diag?: Record<string, unknown> } {
  const n = closes.length;
  if (n < MIN_BARS) {
    return { shortSignal: false, longSignal: false, signalPrice: 0 };
  }
  const c = closes[n - 1];
  const p = closes[n - 2];
  return {
    shortSignal: c < p,
    longSignal: c > p,
    signalPrice: c,
    diag: { reason: 'fixture' },
  };
}
