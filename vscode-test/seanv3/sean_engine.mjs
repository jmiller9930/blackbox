/**
 * SeanV3 paper engine: Jupiter_3 entry (jupiter_3_sean_policy.mjs) + ATR lifecycle exits (sean_lifecycle.mjs).
 */

import { getMeta, setMeta } from './paper_analog.mjs';
import {
  getPaperPosition,
  openPaperPosition,
  updatePositionLifecycle,
  writeClosedTradeAndFlat,
} from './sean_ledger.mjs';
import {
  generateSignalFromOhlcV3,
  resolveEntrySide,
  MIN_BARS,
  ENGINE_ID as POLICY_ENGINE_TAG,
} from './jupiter_3_sean_policy.mjs';
import {
  initialSlTp,
  computePnlUsd,
  applyBreakeven,
  applyTrailingMonotonic,
  evaluateExitOhlc,
  atrFromBarWindow,
} from './sean_lifecycle.mjs';
import { assertCanOpenPosition } from './funding_guards.mjs';

export const SEAN_ENGINE_ID = 'sean_jupiter3_engine_v1';

function envSize() {
  const v = parseFloat(process.env.SEAN_ENGINE_SIZE_NOTIONAL_SOL || '1');
  return Number.isFinite(v) ? v : 1;
}

/** @param {import('node:sqlite').DatabaseSync} db */
export function loadCanonicalBars(db) {
  const sql = `
    SELECT p.market_event_id AS mid, p.candle_open_ms AS oms, p.open_px AS o, p.high_px AS h,
           p.low_px AS l, p.close_px AS c, p.volume_base AS v
    FROM sean_binance_kline_poll p
    INNER JOIN (
      SELECT market_event_id AS gmid, MAX(id) AS mx FROM sean_binance_kline_poll GROUP BY market_event_id
    ) t ON p.market_event_id = t.gmid AND p.id = t.mx
    ORDER BY p.candle_open_ms ASC
  `;
  return db.prepare(sql).all();
}

function parseFloatPx(x) {
  if (x == null || x === '') return NaN;
  return parseFloat(String(x));
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {{ marketEventId: string, kline: { openTime?: number, open?: string, high?: string, low?: string, close?: string, volume?: string } }} ctx
 */
export function processSeanEngine(db, { marketEventId, kline }) {
  const lastMid = getMeta(db, 'sean_engine_last_bar_mid');
  if (lastMid === marketEventId) return;
  setMeta(db, 'sean_engine_last_bar_mid', marketEventId);

  const rows = loadCanonicalBars(db);
  if (rows.length < MIN_BARS) return;

  const o = parseFloatPx(kline?.open);
  const h = parseFloatPx(kline?.high);
  const l = parseFloatPx(kline?.low);
  const c = parseFloatPx(kline?.close);
  const kv = parseFloatPx(kline?.volume);
  const vol = Number.isFinite(kv) ? kv : 0;
  if (![o, h, l, c].every(Number.isFinite)) return;

  const patched = rows.map((r) => ({
    mid: String(r.mid),
    oms: Number(r.oms),
    o: parseFloatPx(r.o),
    h: parseFloatPx(r.h),
    l: parseFloatPx(r.l),
    c: parseFloatPx(r.c),
    v: parseFloatPx(r.v) || 0,
  }));

  const last = patched[patched.length - 1];
  if (last.mid !== marketEventId) {
    console.error(`[seanv3] engine: last bar ${last.mid} != current ${marketEventId}`);
    return;
  }
  last.o = o;
  last.h = h;
  last.l = l;
  last.c = c;
  last.v = vol;

  const closes = patched.map((x) => x.c);
  const highs = patched.map((x) => x.h);
  const lows = patched.map((x) => x.l);
  const vols = patched.map((x) => x.v);

  const pos = getPaperPosition(db);
  const exitTimeUtc = new Date().toISOString();

  if (pos.side !== 'flat') {
    if (marketEventId === pos.entry_market_event_id) {
      return;
    }

    let sl = pos.stop_loss;
    let tp = pos.take_profit;
    let br = pos.breakeven_applied;
    if (sl == null || tp == null) return;

    const atrT = atrFromBarWindow(closes, highs, lows);
    const be = applyBreakeven(pos.side, pos.entry_price, sl, h, l, br);
    sl = be.stopLoss;
    br = be.breakevenApplied;
    sl = applyTrailingMonotonic(pos.side, sl, c, atrT);

    const ex = evaluateExitOhlc(pos.side, sl, tp, o, h, l, c);
    if (ex) {
      const gross = computePnlUsd(pos.entry_price, ex.fill, pos.size_notional_sol, pos.side);
      writeClosedTradeAndFlat(db, {
        engineId: SEAN_ENGINE_ID,
        side: pos.side,
        entryMarketEventId: pos.entry_market_event_id || marketEventId,
        exitMarketEventId: marketEventId,
        entryTimeUtc: pos.opened_at_utc || exitTimeUtc,
        exitTimeUtc,
        entryPrice: pos.entry_price,
        exitPrice: ex.fill,
        sizeNotionalSol: pos.size_notional_sol,
        grossPnlUsd: gross,
        metadataJson: JSON.stringify({
          policy_engine: POLICY_ENGINE_TAG,
          exit_reason: ex.reason,
          atr_t: atrT,
        }),
      });
      console.error(`[seanv3] ${SEAN_ENGINE_ID} closed ${pos.side} gross_pnl=${gross.toFixed(4)} ${ex.reason}`);
      return;
    }

    updatePositionLifecycle(db, {
      stopLoss: sl,
      takeProfit: tp,
      breakevenApplied: br,
      lastProcessedMarketEventId: marketEventId,
    });
    return;
  }

  const sig = generateSignalFromOhlcV3(closes, highs, lows, vols);
  const side = resolveEntrySide(sig.shortSignal, sig.longSignal);
  if (!side) return;

  const atr = sig.diag.atr;
  if (typeof atr !== 'number' || !(atr > 0)) return;

  const entry = closes[closes.length - 1];
  const lv = initialSlTp(entry, atr, side);

  const gate = assertCanOpenPosition(db, {
    markUsd: c,
    closePx: c,
    sizeNotionalSol: envSize(),
  });
  if (!gate.ok) {
    console.error(`[seanv3] open blocked: ${gate.reason} — ${gate.detail}`);
    return;
  }

  openPaperPosition(db, {
    side,
    marketEventId,
    candleOpenMs: last.oms,
    entryPrice: entry,
    sizeNotionalSol: envSize(),
    metadata: { policy_engine: POLICY_ENGINE_TAG, signal: sig.diag },
    stopLoss: lv.stopLoss,
    takeProfit: lv.takeProfit,
    initialStopLoss: lv.stopLoss,
    initialTakeProfit: lv.takeProfit,
    atrEntry: atr,
    lastProcessedMarketEventId: marketEventId,
  });
  console.error(`[seanv3] ${SEAN_ENGINE_ID} opened ${side} @ ${entry} mid=${marketEventId}`);
}
