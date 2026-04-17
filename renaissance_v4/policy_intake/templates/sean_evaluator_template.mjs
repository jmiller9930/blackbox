/**
 * Template for Kitchen-built Sean evaluator artifacts.
 * Copy to: policy_intake_submissions/<submission_id>/artifacts/evaluator.mjs
 * Build pipeline must set artifacts/evaluator.sha256 (hex of evaluator.mjs) when SEAN_REQUIRE_ARTIFACT_SHA256=1.
 *
 * Export either:
 *   - evaluate(marketState) → { longSignal, shortSignal, signalPrice?, diag }
 *   - or generateSignalFromOhlc(closes, highs, lows, volumes) → same shape
 */
export const MIN_BARS = 2;
export const POLICY_ENGINE_TAG = 'kitchen_evaluator_template_v1';

export function generateSignalFromOhlc(closes, highs, lows, volumes) {
  void highs;
  void lows;
  void volumes;
  const n = closes.length;
  if (n < MIN_BARS) {
    return {
      longSignal: false,
      shortSignal: false,
      signalPrice: 0,
      diag: { reason: 'insufficient_bars', atr: 0.25 },
    };
  }
  const latest = closes[n - 1];
  const prev = closes[n - 2];
  return {
    longSignal: latest > prev,
    shortSignal: latest < prev,
    signalPrice: latest,
    diag: { atr: 0.5 },
  };
}
