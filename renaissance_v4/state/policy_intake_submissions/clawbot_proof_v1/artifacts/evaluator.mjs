/**
 * Minimal Kitchen-built evaluator for clawbot positive-path proof (manifest-bound).
 * Policy id: jup_clawbot_proof_v1 · submission clawbot_proof_v1
 */
export const MIN_BARS = 2;
export const POLICY_ENGINE_TAG = 'clawbot_proof_v1';

export function generateSignalFromOhlc(_closes, _highs, _lows, _vols) {
  return { longSignal: false, shortSignal: false, signalPrice: 1, diag: { proof: 'clawbot_standby_no_trade' } };
}
