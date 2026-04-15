/**
 * DV-ARCH-JUPITER-MC2-039 — MC2 test policy: JUP-MC-Test numerics + exactly one tunable delta.
 *
 * **Single change vs JUP-MC-Test:** `VOLUME_SPIKE_MULTIPLIER` uses **1.35** instead of Jupiter_4 default **1.2**
 * (JUP-MC-Test delegates to `generateSignalFromOhlcV4` with no overrides).
 * All other gates (RSI, MIN_EXPECTED_MOVE, crossover, etc.) unchanged from JUPv4/MC-Test path.
 */

import {
  generateSignalFromOhlcV4,
  resolveEntrySide as resolveEntrySideV4,
  MIN_BARS,
} from './jupiter_4_sean_policy.mjs';

/** Only behavioral delta for MC2 vs default V4 / MC-Test wrapper. */
export const MC2_VOLUME_SPIKE_MULTIPLIER = 1.35;

export const ENGINE_ID = 'jupiter_mc2_policy_mjs_v1';
export const CATALOG_ID = 'jupiter_mc2_perps_v1';
export const POLICY_ENGINE_ID = 'jup_mc2';

export { MIN_BARS };

export function generateSignalFromOhlcMc2(closes, highs, lows, volumes) {
  const r = generateSignalFromOhlcV4(closes, highs, lows, volumes, {
    volumeSpikeMultiplier: MC2_VOLUME_SPIKE_MULTIPLIER,
  });
  const diag = {
    ...r.diag,
    policy_engine: POLICY_ENGINE_ID,
    catalog_id: CATALOG_ID,
    mc2_lane: true,
    mc2_volume_spike_multiplier: MC2_VOLUME_SPIKE_MULTIPLIER,
  };
  return { ...r, diag };
}

export function resolveEntrySide(shortSignal, longSignal) {
  return resolveEntrySideV4(shortSignal, longSignal);
}
