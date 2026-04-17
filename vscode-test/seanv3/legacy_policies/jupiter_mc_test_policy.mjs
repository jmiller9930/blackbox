/**
 * Jupiter MC test / pipeline validation — same OHLC numerics as JUPv4, distinct catalog for auditing.
 * Legacy reference only — `jup_mc_test` was removed from `kitchen_policy_registry_v1.json`; production uses manifest-bound `evaluator.mjs`.
 */

import {
  generateSignalFromOhlcV4,
  resolveEntrySide as resolveEntrySideV4,
  MIN_BARS,
} from './jupiter_4_sean_policy.mjs';

export const ENGINE_ID = 'jupiter_mc_test_policy_mjs_v1';
export const CATALOG_ID = 'jupiter_mc_test_perps_v1';
export const POLICY_ENGINE_ID = 'jupiter_mc_test';

export { MIN_BARS };

export function generateSignalFromOhlcMcTest(closes, highs, lows, volumes) {
  const r = generateSignalFromOhlcV4(closes, highs, lows, volumes);
  const diag = {
    ...r.diag,
    policy_engine: POLICY_ENGINE_ID,
    catalog_id: CATALOG_ID,
    mc_test_lane: true,
  };
  return { ...r, diag };
}

export function resolveEntrySide(shortSignal, longSignal) {
  return resolveEntrySideV4(shortSignal, longSignal);
}
