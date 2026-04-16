/**
 * Minimal self-contained policy for intake tests (DV-ARCH-KITCHEN-POLICY-INTAKE-048).
 * DV-064: Embed canonical indicators so browser-uploaded .ts files align with PolicySpecV1.
 */
/* RV4_POLICY_INDICATORS
{"schema_version":"policy_indicators_v1","declarations":[{"id":"rsi_main","kind":"rsi","params":{"period":14}}],"gates":[]}
*/

export const MIN_BARS = 2;
export const policy_id = 'fixture_minimal_direction_v1';

export function generateSignalFromOhlc(
  closes: number[],
  _highs: number[],
  _lows: number[],
  _volumes: number[],
  ctx?: { schemaVersion?: string; indicators?: Record<string, number | null | Record<string, unknown>> },
): { shortSignal: boolean; longSignal: boolean; signalPrice: number; diag?: Record<string, unknown> } {
  const n = closes.length;
  if (n < MIN_BARS) {
    return { shortSignal: false, longSignal: false, signalPrice: 0 };
  }
  const c = closes[n - 1];
  const p = closes[n - 2];
  const rsi = ctx?.indicators?.rsi_main;
  const diag: Record<string, unknown> = { reason: 'fixture' };
  if (typeof rsi === 'number' && Number.isFinite(rsi)) {
    diag.rsi_at_bar = rsi;
  }
  return {
    shortSignal: c < p,
    longSignal: c > p,
    signalPrice: c,
    diag,
  };
}
