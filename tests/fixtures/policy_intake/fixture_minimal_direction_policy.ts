/**
 * Kitchen upload fixture — same intent as the older `PolicyInput` + `candles[]` prototype,
 * but the deterministic harness calls the **OHLC-array** contract only:
 *
 *   generateSignalFromOhlc(closes, highs, lows, volumes, ctx?)
 *
 * A policy that only accepts `{ candles: Candle[] }` will see `closes` as the first
 * argument and **must not** read `input.candles` — that shape fails intake with
 * zero signals (no_signals_generated_in_test_window).
 *
 * DV-064: embedded indicators block for PolicySpecV1 alignment with synthetic bars.
 */
/* RV4_POLICY_INDICATORS
{"schema_version":"policy_indicators_v1","declarations":[{"id":"rsi_main","kind":"rsi","params":{"period":14}}],"gates":[]}
*/

export const POLICY_META = {
  policy_id: "fixture_minimal_direction_v1",
  name: "Fixture Minimal Direction Policy",
  version: "1.0.0",
  timeframe: "15m",
  author: "OpenAI",
  policy_class: "candidate",
  promotion_eligible: false,
  target_systems: ["jupiter", "blackbox"],
  description:
    "Minimal self-contained test policy for Kitchen intake. Signals long on higher close, short on lower close.",
};

export const MIN_BARS = 2;
export const policy_id = "fixture_minimal_direction_v1";

export function generateSignalFromOhlc(
  closes: number[],
  _highs: number[],
  _lows: number[],
  _volumes: number[],
  ctx?: { schemaVersion?: string; indicators?: Record<string, number | null | Record<string, unknown>> },
): {
  longSignal: boolean;
  shortSignal: boolean;
  signalPrice: number;
  diag?: Record<string, unknown>;
} {
  const n = closes.length;
  if (n < MIN_BARS) {
    return { shortSignal: false, longSignal: false, signalPrice: 0, diag: { reason: "insufficient_bars" } };
  }
  const latest = closes[n - 1];
  const previous = closes[n - 2];
  const rsi = ctx?.indicators?.rsi_main;
  const diag: Record<string, unknown> = {
    reason: "harness_ohlc_arrays",
    latest_close: latest,
    previous_close: previous,
  };
  if (typeof rsi === "number" && Number.isFinite(rsi)) {
    diag.rsi_at_bar = rsi;
  }
  const longSignal = latest > previous;
  const shortSignal = latest < previous;
  return {
    longSignal,
    shortSignal,
    signalPrice: latest,
    diag,
  };
}
