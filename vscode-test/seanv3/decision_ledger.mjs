/**
 * Jupiter bar decision ledger — one row per completed flat-bar evaluation (TRADE_OPEN | NO_TRADE).
 */

/** @param {Record<string, unknown>} diag */
export function indicatorValuesFromDiag(sig) {
  const d = sig.diag && typeof sig.diag === 'object' ? sig.diag : {};
  const o = {
    policy_engine: d.policy_engine,
    catalog_id: d.catalog_id,
    signal_price: sig.signalPrice,
    ema9: d.ema9,
    ema21: d.ema21,
    rsi: d.current_rsi,
    atr: d.atr,
    expected_move: d.expected_move,
    avg_volume: d.avg_volume,
    candle_volume: d.candle_volume,
    volume_spike: d.volume_spike,
    volume_spike_multiplier_effective: d.volume_spike_multiplier_effective,
    bullish_crossover: d.bullish_crossover,
    bearish_crossover: d.bearish_crossover,
    bullish_bias: d.bullish_bias,
    bearish_bias: d.bearish_bias,
    long_gate: d.long_gate,
    short_gate: d.short_gate,
    long_signal_core: d.long_signal_core,
    short_signal_core: d.short_signal_core,
  };
  return JSON.stringify(o);
}

/**
 * @param {Record<string, unknown>} diag
 * @param {{ ok: boolean, reason: string, detail: string } | null} fundingGate
 */
export function gateResultsJson(diag, fundingGate) {
  const strategy = diag && typeof diag.jupiter_v4_gates === 'object' ? diag.jupiter_v4_gates : null;
  return JSON.stringify({
    strategy,
    funding_gate: fundingGate,
  });
}

export const REASON = {
  NO_CANDIDATE_SIDE: 'no_candidate_side',
  ATR_INVALID: 'atr_invalid',
  FUNDING_GATE_BLOCKED: 'funding_gate_blocked',
  TRADE_OPEN_OK: 'trade_open_ok',
};
