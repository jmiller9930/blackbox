/**
 * DV-067 — Mechanical proof policy (intake). Parity intent with SeanV3 ``jup_kitchen_mechanical_v1``.
 * Always long after MIN_BARS (deterministic, no indicators).
 */
/* RV4_POLICY_INDICATORS
{"schema_version":"policy_indicators_v1","declarations":[{"id":"rsi_main","kind":"rsi","params":{"period":14}}],"gates":[]}
*/

export const MIN_BARS = 2;
export const policy_id = 'kitchen_mechanical_always_long_v1';

export function generateSignalFromOhlc(
  closes: number[],
  _highs: number[],
  _lows: number[],
  _volumes: number[],
  ctx?: { schemaVersion?: string; indicators?: Record<string, number | null | Record<string, unknown>> },
): { shortSignal: boolean; longSignal: boolean; signalPrice: number; diag?: Record<string, unknown> } {
  void ctx;
  const n = closes.length;
  if (n < MIN_BARS) {
    return { shortSignal: false, longSignal: false, signalPrice: 0 };
  }
  const c = closes[n - 1];
  return {
    longSignal: true,
    shortSignal: false,
    signalPrice: c,
    diag: { kitchen_mechanical: 'always_long' },
  };
}
