/**
 * Pipeline-proof policy — DV-ARCH-CANONICAL-POLICY-SPEC-046 §8.
 * Frequent directional entries from bar-to-bar close change; exits use standard Sean lifecycle.
 * policy_class=training, promotion_eligible=false, monte_carlo_bootstrap=true (metadata in diag).
 */

/** Minimum bars: need previous close for comparison. */
export const MIN_BARS = 2;

export const ENGINE_ID = 'jupiter_pipeline_proof_policy_mjs_v1';
export const CATALOG_ID = 'jupiter_pipeline_proof_perps_v1';
export const POLICY_ENGINE_ID = 'jupiter_pipeline_proof_v1';

/**
 * @param {number[]} closes
 * @param {number[]} highs
 * @param {number[]} lows
 * @param {number[]} volumes
 */
export function generateSignalFromOhlcPipelineProof(closes, highs, lows, volumes) {
  const diag = {
    policy_engine: POLICY_ENGINE_ID,
    catalog_id: CATALOG_ID,
    pipeline_proof_lane: true,
    policy_class: 'training',
    promotion_eligible: false,
    monte_carlo_bootstrap: true,
  };
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
  const currentClose = closes[n - 1];
  const prevClose = closes[n - 2];
  const longSignal = currentClose > prevClose;
  const shortSignal = currentClose < prevClose;

  Object.assign(diag, {
    prev_close: prevClose,
    current_close: currentClose,
    long_gate: longSignal,
    short_gate: shortSignal,
  });

  return {
    shortSignal,
    longSignal,
    signalPrice: currentClose,
    diag,
  };
}

/** Short wins if both true (should not occur for strict > / < ). */
export function resolveEntrySide(shortSignal, longSignal) {
  if (shortSignal && longSignal) return 'short';
  if (shortSignal) return 'short';
  if (longSignal) return 'long';
  return null;
}
