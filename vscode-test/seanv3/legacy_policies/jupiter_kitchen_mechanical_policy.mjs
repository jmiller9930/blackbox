/**
 * DV-067 — Deterministic Kitchen proof policy for Jupiter runtime.
 * Always long after MIN_BARS (unmistakable signal for parity with Kitchen intake fixture).
 */
export const MIN_BARS = 2;
export const ENGINE_ID = 'kitchen_mechanical_always_long_engine_v1';
export const CATALOG_ID = 'kitchen_mechanical_always_long';
export const POLICY_ENGINE_ID = 'kitchen_mechanical_always_long';

export function generateSignalFromOhlcKitchenMechanical(closes, highs, lows, volumes, ctx) {
  void highs;
  void lows;
  void volumes;
  void ctx;
  const n = closes.length;
  if (n < MIN_BARS) {
    return {
      longSignal: false,
      shortSignal: false,
      signalPrice: 0,
      diag: { kitchen_mechanical: true, ready: false },
    };
  }
  const c = closes[n - 1];
  return {
    longSignal: true,
    shortSignal: false,
    signalPrice: c,
    diag: {
      kitchen_mechanical: 'always_long',
      policy_engine_tag: ENGINE_ID,
      catalog_id: CATALOG_ID,
    },
  };
}

export function resolveEntrySide(shortSignal, longSignal) {
  if (longSignal) return 'long';
  if (shortSignal) return 'short';
  return null;
}
