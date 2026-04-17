/**
 * SeanV3 paper engine — execution layer only (bars, lifecycle, risk gates, ledger).
 * Policy is loaded via `loadActivePolicyContext` → Kitchen artifact `evaluator.mjs`; do not import quarantined strategy modules (see demarcation doc).
 * @see docs/architect/engine_policy_demarcation_v1.md
 * DV-ARCH-JUPITER-POLICY-SWITCH-037 — policy evaluated fresh each cycle; entries use active policy;
 * exits use entry-time engine ids from position metadata (lifecycle unchanged by policy switch).
 */

import { getMeta, setMeta } from './paper_analog.mjs';
import {
  getPaperPosition,
  openPaperPosition,
  updatePositionLifecycle,
  writeClosedTradeAndFlat,
  insertBarDecision,
} from './sean_ledger.mjs';
import { indicatorValuesFromDiag, gateResultsJson, REASON } from './decision_ledger.mjs';
import { loadActivePolicyContext } from './jupiter_policy_runtime.mjs';
import {
  initialSlTp,
  computePnlUsd,
  applyBreakeven,
  applyTrailingMonotonic,
  evaluateExitOhlc,
  atrFromBarWindow,
} from './sean_lifecycle.mjs';
import { assertCanOpenPosition } from './funding_guards.mjs';

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

/** @returns {{ entryEngineId: string, entryPolicyTag: string }} */
function entryIdsFromPositionMetadata(pos) {
  let entryEngineId = 'sean_jupiter4_engine_v1';
  let entryPolicyTag = '';
  try {
    if (pos.metadata_json) {
      const m = JSON.parse(String(pos.metadata_json));
      if (m.entry_sean_engine_id) entryEngineId = String(m.entry_sean_engine_id);
      if (m.entry_policy_engine) entryPolicyTag = String(m.entry_policy_engine);
    }
  } catch {
    /* */
  }
  return { entryEngineId, entryPolicyTag };
}

/** @param {import('node:sqlite').DatabaseSync} db */
function writeFlatBarDecision(db, policy, marketEventId, payload) {
  const sym = (process.env.SEANV3_CANONICAL_SYMBOL || process.env.CANONICAL_SYMBOL || 'SOL-PERP').trim() || 'SOL-PERP';
  const tf = (process.env.SEAN_BAR_TIMEFRAME || '5m').trim() || '5m';
  insertBarDecision(db, {
    outcome: payload.outcome,
    marketEventId,
    timestampUtc: new Date().toISOString(),
    symbol: sym,
    timeframe: tf,
    policyId: policy.policyId,
    policyEngineTag: policy.policyEngineTag,
    engineId: policy.engineId,
    policyResolutionSource: policy.source,
    signalMode: policy.policyId,
    candidateSide: payload.candidateSide,
    reasonCode: payload.reasonCode,
    indicatorValuesJson: payload.indicatorValuesJson,
    gateResultsJson: payload.gateResultsJson,
    featuresJson: payload.featuresJson,
    tradeId: payload.tradeId ?? null,
  });
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {{ marketEventId: string, kline: { openTime?: number, open?: string, high?: string, low?: string, close?: string, volume?: string } }} ctx
 */
export async function processSeanEngine(db, { marketEventId, kline }) {
  const policy = await loadActivePolicyContext(db);
  if (!policy.ok) {
    console.error(`[seanv3] policy: ${policy.error} ${policy.detail || ''}`);
    return;
  }
  const minBars = policy.minBars;

  const lastMid = getMeta(db, 'sean_engine_last_bar_mid');
  if (lastMid === marketEventId) return;
  setMeta(db, 'sean_engine_last_bar_mid', marketEventId);

  const rows = loadCanonicalBars(db);
  if (rows.length < minBars) return;

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
      const { entryEngineId, entryPolicyTag } = entryIdsFromPositionMetadata(pos);
      const polTag = entryPolicyTag || policy.policyEngineTag;
      let entrySnap = {};
      try {
        if (pos.metadata_json) entrySnap = JSON.parse(String(pos.metadata_json));
      } catch {
        /* */
      }
      writeClosedTradeAndFlat(db, {
        engineId: entryEngineId,
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
          schema: 'sean_paper_trade_snapshot_v1',
          entry_policy_id: entrySnap.entry_policy_id,
          entry_sean_engine_id: entrySnap.entry_sean_engine_id,
          entry_policy_engine: entrySnap.entry_policy_engine,
          signal: entrySnap.signal,
          position_at_exit: {
            initial_stop_loss: pos.initial_stop_loss,
            initial_take_profit: pos.initial_take_profit,
            stop_loss: sl,
            take_profit: tp,
            breakeven_applied: br,
            atr_entry: pos.atr_entry,
            bars_held: pos.bars_held,
          },
          exit: {
            reason: ex.reason,
            fill_price: ex.fill,
            atr_t: atrT,
            exit_market_event_id: marketEventId,
            exit_time_utc: exitTimeUtc,
          },
          policy_engine: polTag,
          exit_reason: ex.reason,
          atr_t: atrT,
        }),
      });
      console.error(`[seanv3] ${entryEngineId} closed ${pos.side} gross_pnl=${gross.toFixed(4)} ${ex.reason}`);
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

  const sig = await Promise.resolve(policy.generateEntrySignal(closes, highs, lows, vols));
  const diag = sig.diag && typeof sig.diag === 'object' ? sig.diag : {};
  const featuresJson = JSON.stringify(diag);
  const indJson = indicatorValuesFromDiag(sig);

  const side = policy.resolveEntrySide(sig.shortSignal, sig.longSignal);
  const candidateSide = side === 'long' ? 'long' : side === 'short' ? 'short' : 'none';

  if (!side) {
    writeFlatBarDecision(db, policy, marketEventId, {
      outcome: 'NO_TRADE',
      candidateSide: 'none',
      reasonCode: REASON.NO_CANDIDATE_SIDE,
      indicatorValuesJson: indJson,
      gateResultsJson: gateResultsJson(diag, null),
      featuresJson,
    });
    return;
  }

  const atr = sig.diag.atr;
  if (typeof atr !== 'number' || !(atr > 0)) {
    writeFlatBarDecision(db, policy, marketEventId, {
      outcome: 'NO_TRADE',
      candidateSide,
      reasonCode: REASON.ATR_INVALID,
      indicatorValuesJson: indJson,
      gateResultsJson: gateResultsJson(diag, null),
      featuresJson,
    });
    return;
  }

  const entry = closes[closes.length - 1];
  const lv = initialSlTp(entry, atr, side);

  const gate = assertCanOpenPosition(db, {
    markUsd: c,
    closePx: c,
    sizeNotionalSol: envSize(),
  });
  if (!gate.ok) {
    console.error(`[seanv3] open blocked: ${gate.reason} — ${gate.detail}`);
    writeFlatBarDecision(db, policy, marketEventId, {
      outcome: 'NO_TRADE',
      candidateSide,
      reasonCode: REASON.FUNDING_GATE_BLOCKED,
      indicatorValuesJson: indJson,
      gateResultsJson: gateResultsJson(diag, { ok: gate.ok, reason: gate.reason, detail: gate.detail }),
      featuresJson,
    });
    return;
  }

  openPaperPosition(db, {
    side,
    marketEventId,
    candleOpenMs: last.oms,
    entryPrice: entry,
    sizeNotionalSol: envSize(),
    metadata: {
      policy_engine: policy.policyEngineTag,
      entry_policy_id: policy.policyId,
      entry_sean_engine_id: policy.engineId,
      entry_policy_engine: policy.policyEngineTag,
      signal: sig.diag,
    },
    stopLoss: lv.stopLoss,
    takeProfit: lv.takeProfit,
    initialStopLoss: lv.stopLoss,
    initialTakeProfit: lv.takeProfit,
    atrEntry: atr,
    lastProcessedMarketEventId: marketEventId,
  });
  writeFlatBarDecision(db, policy, marketEventId, {
    outcome: 'TRADE_OPEN',
    candidateSide,
    reasonCode: REASON.TRADE_OPEN_OK,
    indicatorValuesJson: indJson,
    gateResultsJson: gateResultsJson(diag, { ok: gate.ok, reason: gate.reason, detail: gate.detail }),
    featuresJson,
    tradeId: null,
  });
  console.error(`[seanv3] ${policy.engineId} opened ${side} @ ${entry} mid=${marketEventId} policy=${policy.policyId}`);
}
