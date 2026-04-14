/**
 * First SeanV3-native paper engine slice: driven only from stored Binance klines + sean_ledger.
 * Not full jupiter_3_sean_policy parity — explicit placeholder rules to prove lifecycle + ledger.
 *
 * Rules (sean_engine_slice_v1):
 * - One position slot: flat | long.
 * - Open long when flat (first opportunity on a **new** 5m bar).
 * - While long: each new bar increments bars_held; exit if stop hit (close <= entry * (1 - STOP_FRAC))
 *   or bars_held >= MAX_HOLD_BARS (time stop).
 *
 * Dedup: caller must only invoke once per distinct market_event_id (see app.mjs meta).
 */

import { getMeta, setMeta } from './paper_analog.mjs';
import {
  getPaperPosition,
  incrementBarsHeld,
  openPaperLong,
  writeClosedTradeAndFlat,
} from './sean_ledger.mjs';

const ENGINE_ID = 'sean_engine_slice_v1';

function envNum(name, def) {
  const v = (process.env[name] || '').trim();
  if (!v) return def;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : def;
}

/** Read at each step so tests and runtime can set env before first bar. */
function params() {
  return {
    stopFrac: envNum('SEAN_ENGINE_STOP_FRAC', 0.02),
    maxHoldBars: Math.max(1, Math.floor(envNum('SEAN_ENGINE_MAX_HOLD_BARS', 48))),
    sizeSol: envNum('SEAN_ENGINE_SIZE_NOTIONAL_SOL', 1.0),
  };
}

function px(kline, key) {
  const v = kline?.[key];
  if (v == null) return NaN;
  const n = parseFloat(String(v));
  return Number.isFinite(n) ? n : NaN;
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {{ marketEventId: string, kline: { openTime?: number, close?: string, open?: string } }} ctx
 */
export function processSeanEngineSlice(db, { marketEventId, kline }) {
  const last = getMeta(db, 'sean_engine_last_bar_mid');
  if (last === marketEventId) return;
  setMeta(db, 'sean_engine_last_bar_mid', marketEventId);

  const close = px(kline, 'close');
  const openMs = kline?.openTime != null ? Number(kline.openTime) : 0;
  if (!Number.isFinite(close) || openMs <= 0) return;

  const { stopFrac, maxHoldBars, sizeSol } = params();
  const pos = getPaperPosition(db);
  const exitTimeUtc = new Date().toISOString();

  if (pos.side === 'long') {
    incrementBarsHeld(db);
    const p = getPaperPosition(db);
    const entry = p.entry_price;
    const stopLevel = entry * (1.0 - stopFrac);
    let exitReason = null;
    if (close <= stopLevel) exitReason = 'stop_loss';
    else if (p.bars_held >= maxHoldBars) exitReason = 'max_hold_bars';

    if (exitReason) {
      const gross = (close - entry) * p.size_notional_sol;
      writeClosedTradeAndFlat(db, {
        engineId: ENGINE_ID,
        side: 'long',
        entryMarketEventId: p.entry_market_event_id || marketEventId,
        exitMarketEventId: marketEventId,
        entryTimeUtc: p.opened_at_utc || exitTimeUtc,
        exitTimeUtc,
        entryPrice: entry,
        exitPrice: close,
        sizeNotionalSol: p.size_notional_sol,
        grossPnlUsd: gross,
        netPnlUsd: null,
        metadataJson: JSON.stringify({
          engine: ENGINE_ID,
          exit_reason: exitReason,
          bars_held: p.bars_held,
          stop_frac: stopFrac,
          max_hold_bars: maxHoldBars,
        }),
      });
      console.error(
        `[seanv3] ${ENGINE_ID} closed long gross_pnl=${gross.toFixed(4)} reason=${exitReason}`
      );
    }
    return;
  }

  if (pos.side === 'flat') {
    openPaperLong(db, {
      marketEventId,
      candleOpenMs: openMs,
      entryPrice: close,
      sizeNotionalSol: sizeSol,
      metadata: {
        engine: ENGINE_ID,
        open_rule: 'slice_v1_open_on_first_new_bar',
      },
    });
    console.error(`[seanv3] ${ENGINE_ID} opened long @ ${close} mid=${marketEventId}`);
  }
}
