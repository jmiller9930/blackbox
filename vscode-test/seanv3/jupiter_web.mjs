#!/usr/bin/env node
/**
 * Jupiter dashboard + JSON API. Browser gate: JUPITER_AUTH_MODE=none | basic | session (see README).
 * Session mode: /auth/login, cookie sessions, /auth/forgot + email reset (Resend) or stderr link.
 * JUPITER_WEB_READ_ONLY=1 blocks POST /api/operator/*; sole write: POST /api/v1/jupiter/active-policy (Bearer).
 *
 * Mount repo read-only at BLACKBOX_REPO_ROOT for policy registry + execution_ledger parity.
 * Default port 707. Lab: http://clawbot.a51.corp:707/ or WAN http://jupv3.greyllc.net:707/
 */
import { execSync } from 'child_process';
import { createHash, timingSafeEqual } from 'node:crypto';
import { existsSync, readFileSync } from 'fs';
import http from 'http';
import { DatabaseSync } from 'node:sqlite';
import { resolve, join } from 'path';
import { fileURLToPath } from 'url';

import { assertCanOpenPosition, getPaperEquityUsd } from './funding_guards.mjs';
import { setMeta, upsertPaperWallet } from './paper_analog.mjs';
import { PublicKey } from '@solana/web3.js';
import {
  loadAllowedDeploymentIdsFromManifest,
  JUPITER_ACTIVE_POLICY_KEY,
  isDeploymentIdInManifest,
  getActiveDeploymentSnapshot,
} from './jupiter_policy_runtime.mjs';
import {
  bootstrapJupiterAuthUserIfNeeded,
  ensureJupiterWebAuthSchema,
  getSessionSecret,
  handleJupiterAuthHttp,
  requireJupiterSession,
} from './jupiter_web_auth.mjs';
import { tradeSurfacePolicyKitchenHandshake } from './jupiter_kitchen_checkin.mjs';

/** GET /api/v1/jupiter/policy — observability only. */
const JUPITER_POLICY_OBSERVABILITY_CONTRACT = 'jupiter_policy_observability_v1';
/**
 * Sole write: select a deployment id from kitchen_policy_deployment_manifest_v1 (Jupiter entries).
 * Records analog_meta.jupiter_active_policy; engine applies on next cycle. Does not mutate trades/bars.
 */
const JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT = 'jupiter_active_policy_switch_v1';

/** Operator-facing engine label (not policy). Internal runtime id remains sean_artifact_engine_v1 in metadata. */
function jupiterEngineDisplayId() {
  return (process.env.SEAN_ENGINE_DISPLAY_ID || 'BBT_v1').trim();
}

/** Sean execution loop enabled (separate from which deployment id is assigned). */
function jupiterEngineSliceEnabled() {
  return !['0', 'false', 'no'].includes(String(process.env.SEAN_ENGINE_SLICE ?? '1').trim().toLowerCase());
}

function parseSolanaPubkeyBase58(raw) {
  const s = String(raw ?? '').trim();
  if (!s) return null;
  try {
    const pk = new PublicKey(s);
    return pk.toBase58();
  } catch {
    return null;
  }
}

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const FRONT_DOOR_PNG = join(__dirname, 'static', 'jupiter_front_door.png');

const BB_LANE = 'baseline';
const BB_STRATEGY = 'baseline';
const PARITY_PRICE_REL_TOL = 0.005;
const DEFAULT_PYTH_FEED = 'ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d';

function dbPath() {
  const env = (process.env.SQLITE_PATH || process.env.SEAN_SQLITE_PATH || '').trim();
  if (env) return resolve(env);
  return resolve(__dirname, 'capture', 'sean_parity.db');
}

function repoRoot() {
  const raw = (process.env.BLACKBOX_REPO_ROOT || '').trim();
  if (raw) return resolve(raw);
  return resolve(__dirname, '..', '..');
}

function executionLedgerPath() {
  const raw = (process.env.BLACKBOX_EXECUTION_LEDGER_PATH || '').trim();
  if (raw) return resolve(raw);
  return resolve(repoRoot(), 'data', 'sqlite', 'execution_ledger.db');
}

function binanceOrigin() {
  return (process.env.BINANCE_API_BASE_URL || process.env.BINANCE_REST_BASE_URL || 'https://api.binance.com').replace(
    /\/$/,
    ''
  );
}

function hermesOrigin() {
  return (process.env.PYTH_HERMES_BASE_URL || process.env.HERMES_PYTH_BASE_URL || 'https://hermes.pyth.network').replace(
    /\/$/,
    ''
  );
}

function binancePingUrl() {
  return `${binanceOrigin()}/api/v3/ping`;
}

function binanceKlinesUrl() {
  const sym = (process.env.BLACKBOX_BINANCE_KLINE_SYMBOL || process.env.BINANCE_SYMBOL || 'SOLUSDT').trim().toUpperCase() || 'SOLUSDT';
  return `${binanceOrigin()}/api/v3/klines?symbol=${sym}&interval=5m&limit=1`;
}

function hermesLatestUrl() {
  const fid = (process.env.PYTH_SOL_USD_FEED_ID || DEFAULT_PYTH_FEED).trim();
  return `${hermesOrigin()}/v2/updates/price/latest?ids[]=${encodeURIComponent(fid)}&parsed=true`;
}

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** When true, POST /api/operator/* returns 403; POST /api/v1/jupiter/active-policy (alias set-policy) still works with Bearer. */
function jupiterWebReadOnly() {
  return ['1', 'true', 'yes'].includes((process.env.JUPITER_WEB_READ_ONLY || '').trim().toLowerCase());
}

function formatIsoUtcShort(iso) {
  if (!iso) return '—';
  try {
    const s = String(iso).trim().replace('Z', '+00:00');
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 22);
    return d.toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
  } catch {
    return String(iso).slice(0, 22);
  }
}

function truncateMid(s, n = 32) {
  if (s == null || s === '') return '—';
  const t = String(s).trim();
  return t.length <= n ? t : `${t.slice(0, n - 1)}…`;
}

/** Short base58 hint for status strip (no new backend). */
function shortPubkeyBase58(pk) {
  if (!pk) return '';
  const s = String(pk).trim();
  if (s.length <= 10) return s;
  return `${s.slice(0, 4)}…${s.slice(-4)}`;
}

/**
 * Operator status strip model — shallow UI only; mirrors preflight thresholds where present
 * (e.g. SQLite market_ticks stale ≥120s in runPreflight path; Hermes wall age for Pyth freshness).
 * @param {Record<string, unknown>} v View payload (same shape as htmlPage / summary.json)
 */
function computeStatusStrip(v) {
  const w = v.wallet;
  const op = v.operator || {};
  const opErr = Boolean(op.error);
  const pf = v.preflight || {};
  const checks = pf.checks || [];
  const hermesChk = checks.find((c) => /hermes|pyth/i.test(String(c?.name || '')));
  const binPing = checks.find((c) => /binance.*ping/i.test(String(c?.name || '').toLowerCase()));
  const binKl = checks.find((c) => /binance klines/i.test(String(c?.name || '').toLowerCase()));
  const o = pf.oracle;
  const wallAge = pf.wall_age_s;

  let pythLabel = 'Unknown';
  let pythCls = 'jw-st-muted';
  if (!hermesChk?.ok || o?.price == null) {
    pythLabel = 'Down';
    pythCls = 'jw-st-bad';
  } else if (wallAge != null && Number.isFinite(Number(wallAge)) && Number(wallAge) > 120) {
    pythLabel = 'Stale';
    pythCls = 'jw-st-warn';
  } else {
    pythLabel = 'Live';
    pythCls = 'jw-st-ok';
  }

  const kl = v.last_kline;
  let bnLabel = 'Unknown';
  let bnCls = 'jw-st-muted';
  if (!binPing?.ok || !binKl?.ok) {
    bnLabel = 'Down';
    bnCls = 'jw-st-bad';
  } else {
    let ageSec = null;
    if (kl?.polled_at_utc) {
      try {
        const t = new Date(String(kl.polled_at_utc).trim()).getTime();
        if (!Number.isNaN(t)) ageSec = (Date.now() - t) / 1000;
      } catch {
        /* */
      }
    }
    if (ageSec != null && ageSec > 600) {
      bnLabel = 'Stale';
      bnCls = 'jw-st-warn';
    } else {
      bnLabel = 'Live';
      bnCls = 'jw-st-ok';
    }
  }

  const walletConnected = Boolean(w?.pubkey_base58);
  const walletMain = walletConnected ? 'Connected' : 'Disconnected';
  const walletCls = walletConnected ? 'jw-st-ok' : 'jw-st-bad';
  const walletSub = walletConnected ? shortPubkeyBase58(w.pubkey_base58) : '';

  const readOnly = Boolean(v.read_only_except_policy);
  const gate = op.next_open_gate || {};
  let trgLabel = 'Enabled';
  let trgCls = 'jw-st-ok';
  if (opErr) {
    trgLabel = 'Unknown';
    trgCls = 'jw-st-muted';
  } else if (readOnly) {
    trgLabel = 'Read-only';
    trgCls = 'jw-st-warn';
  } else if (gate.ok !== true) {
    trgLabel = 'Blocked';
    trgCls = 'jw-st-bad';
  }

  const tm = v.trading_mode || {};
  const modeLabel = tm.actual_banner ? 'Live' : 'Paper';
  const modeCls = tm.actual_banner ? 'jw-st-warn' : 'jw-st-ok';

  const jr = tm.jupiter_runtime || {};
  /** Deployment id from analog_meta (Kitchen manifest row), not the engine. */
  const deploymentId = jr.active_policy ? String(jr.active_policy) : '—';
  /** Treat missing as online (older summary.json) — only explicit false turns engine off. */
  const engineOn = jr.engine_online !== false;
  const eid = String(jr.engine_display_id || jupiterEngineDisplayId()).trim();
  const engineLabel = engineOn ? `${eid} · Online` : `${eid} · Off`;
  const engineCls = engineOn ? 'jw-st-engine-on' : 'jw-st-muted';

  const pq = op.paper_equity_usd || {};
  let eqStr = '—';
  let eqCls = 'jw-st-muted';
  if (!opErr && pq.equity_usd != null && Number.isFinite(Number(pq.equity_usd))) {
    eqStr = Number(pq.equity_usd).toFixed(2);
    eqCls = 'jw-st-ok';
  }

  const pos = v.position;
  let posLabel = '—';
  let posCls = 'jw-st-muted';
  if (pos && String(pos.side) !== 'flat') {
    const s = String(pos.side).toLowerCase();
    if (s === 'long') {
      posLabel = 'Long';
      posCls = 'jw-st-warn';
    } else if (s === 'short') {
      posLabel = 'Short';
      posCls = 'jw-st-warn';
    } else {
      posLabel = String(pos.side);
      posCls = 'jw-st-ok';
    }
  } else {
    posLabel = 'Flat';
    posCls = 'jw-st-ok';
  }

  let updLabel = '—';
  let updCls = 'jw-st-muted';
  if (kl?.polled_at_utc) {
    try {
      const t = new Date(String(kl.polled_at_utc).trim()).getTime();
      if (!Number.isNaN(t)) {
        const sec = (Date.now() - t) / 1000;
        if (sec >= 0 && sec < 120) {
          updLabel = `${Math.round(sec)}s`;
          updCls = 'jw-st-ok';
        } else if (sec >= 120 && sec < 900) {
          updLabel = `${Math.round(sec / 60)}m`;
          updCls = 'jw-st-warn';
        } else if (sec >= 900) {
          updLabel = `${Math.round(sec / 60)}m`;
          updCls = 'jw-st-bad';
        }
      }
    } catch {
      /* */
    }
  } else if (wallAge != null && Number.isFinite(Number(wallAge))) {
    updLabel = `Pyth ~${Math.round(Number(wallAge))}s`;
    updCls = Number(wallAge) > 120 ? 'jw-st-warn' : 'jw-st-ok';
  }

  return {
    walletMain,
    walletSub,
    walletCls,
    pythLabel,
    pythCls,
    bnLabel,
    bnCls,
    trgLabel,
    trgCls,
    modeLabel,
    modeCls,
    engineLabel,
    engineCls,
    deploymentId,
    eqStr,
    eqCls,
    posLabel,
    posCls,
    updLabel,
    updCls,
  };
}

function statusStripHtml(s, sessionChrome = false) {
  const stripCls = `jw-status-strip${sessionChrome ? ' jw-status-strip--session' : ''}`;
  const wSub =
    s.walletSub &&
    `<span class="jw-st-sub" id="jw-st-wallet-sub">${esc(s.walletSub)}</span>`;
  return `<div id="jw-status-strip" class="${stripCls}" role="region" aria-label="Operator status">
    <div class="jw-st-item"><span class="jw-st-k">Wallet</span><span class="jw-st-v ${s.walletCls}" id="jw-st-wallet"><span id="jw-st-wallet-main">${esc(s.walletMain)}</span>${wSub ? ` ${wSub}` : ''}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Pyth</span><span class="jw-st-v ${s.pythCls}" id="jw-st-pyth">${esc(s.pythLabel)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Binance</span><span class="jw-st-v ${s.bnCls}" id="jw-st-binance">${esc(s.bnLabel)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Trading</span><span class="jw-st-v ${s.trgCls}" id="jw-st-trading">${esc(s.trgLabel)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Mode</span><span class="jw-st-v ${s.modeCls}" id="jw-st-mode">${esc(s.modeLabel)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Engine</span><span class="jw-st-v ${s.engineCls}" id="jw-st-engine">${esc(s.engineLabel)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Deployment</span><span class="jw-st-v jw-st-deployment" id="jw-st-deployment">${esc(s.deploymentId)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Equity</span><span class="jw-st-v ${s.eqCls}" id="jw-st-equity">${esc(s.eqStr)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Position</span><span class="jw-st-v ${s.posCls}" id="jw-st-position">${esc(s.posLabel)}</span></div>
    <div class="jw-st-item"><span class="jw-st-k">Updated</span><span class="jw-st-v ${s.updCls}" id="jw-st-updated">${esc(s.updLabel)}</span></div>
  </div>`;
}

function exitReasonFromMeta(metaJson) {
  if (!metaJson) return '—';
  try {
    const o = JSON.parse(String(metaJson));
    if (o && typeof o === 'object') {
      const r = o.exit?.reason ?? o.exit_reason ?? o.exitReason;
      if (r) return String(r).slice(0, 48);
    }
  } catch {
    /* */
  }
  return '—';
}

function csvEscapeCell(val) {
  const s = val == null ? '' : String(val);
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

/** @param {import('node:sqlite').DatabaseSync} db */
function buildSeanTradesCsv(db) {
  const sym =
    (process.env.SEANV3_CANONICAL_SYMBOL || process.env.CANONICAL_SYMBOL || 'SOL-PERP').trim() || 'SOL-PERP';
  const max = Math.min(10000, Math.max(1, parseInt(process.env.SEANV3_TRADE_CSV_MAX || '5000', 10) || 5000));
  const rows = db
    .prepare(
      `SELECT id, engine_id, side, entry_market_event_id, exit_market_event_id,
              entry_time_utc, exit_time_utc, entry_price, exit_price, size_notional_sol,
              gross_pnl_usd, net_pnl_usd, result_class, metadata_json
       FROM sean_paper_trades ORDER BY id ASC LIMIT ?`
    )
    .all(max);
  const headers = [
    'trade_id',
    'id',
    'symbol',
    'engine_id',
    'side',
    'entry_market_event_id',
    'exit_market_event_id',
    'entry_time_utc',
    'exit_time_utc',
    'entry_price',
    'exit_price',
    'size_notional_sol',
    'notional_usd_entry_approx',
    'gross_pnl_usd',
    'net_pnl_usd',
    'result_class',
    'exit_reason_flat',
    'policy_engine_flat',
    'metadata_json',
  ];
  const lines = [headers.join(',')];
  for (const r of rows) {
    const ep = Number(r.entry_price);
    const sz = Number(r.size_notional_sol);
    const nom = Number.isFinite(ep) && Number.isFinite(sz) ? ep * sz : '';
    const meta = r.metadata_json != null ? String(r.metadata_json) : '';
    let exitReason = '';
    let polEng = '';
    try {
      const o = JSON.parse(meta || '{}');
      exitReason = String(o.exit?.reason ?? o.exit_reason ?? '');
      polEng = String(o.policy_engine ?? o.entry_policy_engine ?? '');
    } catch {
      /* */
    }
    lines.push(
      [
        csvEscapeCell(`sean_${r.id}`),
        csvEscapeCell(r.id),
        csvEscapeCell(sym),
        csvEscapeCell(r.engine_id),
        csvEscapeCell(r.side),
        csvEscapeCell(r.entry_market_event_id),
        csvEscapeCell(r.exit_market_event_id),
        csvEscapeCell(r.entry_time_utc),
        csvEscapeCell(r.exit_time_utc),
        csvEscapeCell(r.entry_price),
        csvEscapeCell(r.exit_price),
        csvEscapeCell(r.size_notional_sol),
        csvEscapeCell(nom),
        csvEscapeCell(r.gross_pnl_usd),
        csvEscapeCell(r.net_pnl_usd),
        csvEscapeCell(r.result_class),
        csvEscapeCell(exitReason),
        csvEscapeCell(polEng),
        csvEscapeCell(meta),
      ].join(',')
    );
  }
  return lines.join('\r\n');
}

/** Max rows for bar-decision CSV exports (NO_TRADE and TRADE_OPEN). */
function barDecisionsCsvMaxRows() {
  return Math.min(
    5000,
    Math.max(
      1,
      parseInt(
        process.env.SEANV3_BAR_DECISION_EXPORT_MAX ||
          process.env.SEANV3_NO_TRADE_EXPORT_MAX ||
          process.env.SEANV3_TUI_NO_TRADE_ROWS ||
          '500',
        10
      ) || 500
    )
  );
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {'NO_TRADE' | 'TRADE_OPEN'} outcome
 */
function buildBarDecisionsCsv(db, outcome) {
  const max = barDecisionsCsvMaxRows();
  const rows = db
    .prepare(
      `SELECT id, outcome, market_event_id, timestamp_utc, symbol, timeframe, policy_id, policy_engine_tag, engine_id,
              policy_resolution_source, signal_mode, candidate_side, reason_code,
              indicator_values_json, gate_results_json, features_json, trade_id, schema_version
       FROM sean_bar_decisions WHERE outcome = ? ORDER BY id DESC LIMIT ?`
    )
    .all(outcome, max);
  const headers = [
    'id',
    'outcome',
    'market_event_id',
    'timestamp_utc',
    'symbol',
    'timeframe',
    'policy_id',
    'policy_engine_tag',
    'engine_id',
    'policy_resolution_source',
    'signal_mode',
    'candidate_side',
    'reason_code',
    'indicator_values_json',
    'gate_results_json',
    'features_json',
    'trade_id',
    'schema_version',
  ];
  const lines = [headers.join(',')];
  for (const r of rows) {
    lines.push(
      [
        csvEscapeCell(r.id),
        csvEscapeCell(r.outcome),
        csvEscapeCell(r.market_event_id),
        csvEscapeCell(r.timestamp_utc),
        csvEscapeCell(r.symbol),
        csvEscapeCell(r.timeframe),
        csvEscapeCell(r.policy_id),
        csvEscapeCell(r.policy_engine_tag),
        csvEscapeCell(r.engine_id),
        csvEscapeCell(r.policy_resolution_source),
        csvEscapeCell(r.signal_mode),
        csvEscapeCell(r.candidate_side),
        csvEscapeCell(r.reason_code),
        csvEscapeCell(r.indicator_values_json),
        csvEscapeCell(r.gate_results_json),
        csvEscapeCell(r.features_json),
        csvEscapeCell(r.trade_id),
        csvEscapeCell(r.schema_version),
      ].join(',')
    );
  }
  return lines.join('\r\n');
}

/** @param {import('node:sqlite').DatabaseSync} db */
function buildNoTradeDecisionsCsv(db) {
  return buildBarDecisionsCsv(db, 'NO_TRADE');
}

/** @param {import('node:sqlite').DatabaseSync} db */
function buildTradeOpenDecisionsCsv(db) {
  return buildBarDecisionsCsv(db, 'TRADE_OPEN');
}

/**
 * @param {Record<string, unknown>} row
 * @returns {Record<string, unknown>}
 */
function barDecisionDetailPayload(row) {
  /** @param {unknown} j */
  const parse = (j) => {
    if (j == null || j === '') return null;
    try {
      return JSON.parse(String(j));
    } catch {
      return { _parse_error: true, raw: String(j).slice(0, 2000) };
    }
  };
  return {
    schema: 'jupiter_sean_bar_decision_detail_v1',
    id: row.id,
    outcome: row.outcome,
    market_event_id: row.market_event_id,
    timestamp_utc: row.timestamp_utc,
    symbol: row.symbol,
    timeframe: row.timeframe,
    policy_id: row.policy_id,
    policy_engine_tag: row.policy_engine_tag,
    engine_id: row.engine_id,
    policy_resolution_source: row.policy_resolution_source,
    signal_mode: row.signal_mode,
    candidate_side: row.candidate_side,
    reason_code: row.reason_code,
    trade_id: row.trade_id,
    schema_version: row.schema_version,
    indicator_values: parse(row.indicator_values_json),
    gate_results: parse(row.gate_results_json),
    features: parse(row.features_json),
    indicator_values_json: row.indicator_values_json != null ? String(row.indicator_values_json) : null,
    gate_results_json: row.gate_results_json != null ? String(row.gate_results_json) : null,
    features_json: row.features_json != null ? String(row.features_json) : null,
  };
}

/**
 * Adds optional `sean_paper_trades` snapshot when `trade_id` is set (TRADE_OPEN path).
 *
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {Record<string, unknown>} payload from {@link barDecisionDetailPayload}
 */
function augmentBarDecisionDetail(db, payload) {
  const tid = payload.trade_id;
  if (tid == null || tid === '') {
    return payload;
  }
  const id = Number(tid);
  if (!Number.isFinite(id)) {
    return { ...payload, paper_trade_link: { trade_id: tid, note: 'trade_id is not numeric' } };
  }
  try {
    const pt = db
      .prepare(
        `SELECT id, engine_id, side, entry_market_event_id, exit_market_event_id,
                entry_time_utc, exit_time_utc, entry_price, exit_price, size_notional_sol,
                gross_pnl_usd, net_pnl_usd, result_class, metadata_json
         FROM sean_paper_trades WHERE id = ?`
      )
      .get(id);
    if (!pt) {
      return {
        ...payload,
        paper_trade_link: { trade_id: id, note: 'no matching row in sean_paper_trades (lifecycle table)' },
      };
    }
    return {
      ...payload,
      paper_trade_snapshot: {
        schema: 'jupiter_sean_paper_trade_snapshot_v1',
        id: pt.id,
        trade_id_label: `sean_${pt.id}`,
        engine_id: pt.engine_id != null ? String(pt.engine_id) : null,
        side: pt.side != null ? String(pt.side) : null,
        entry_market_event_id: pt.entry_market_event_id != null ? String(pt.entry_market_event_id) : null,
        exit_market_event_id: pt.exit_market_event_id != null ? String(pt.exit_market_event_id) : null,
        entry_time_utc: pt.entry_time_utc != null ? String(pt.entry_time_utc) : null,
        exit_time_utc: pt.exit_time_utc != null ? String(pt.exit_time_utc) : null,
        entry_price: pt.entry_price,
        exit_price: pt.exit_price,
        size_notional_sol: pt.size_notional_sol,
        gross_pnl_usd: pt.gross_pnl_usd,
        net_pnl_usd: pt.net_pnl_usd,
        result_class: pt.result_class != null ? String(pt.result_class) : null,
        metadata_json: pt.metadata_json != null ? String(pt.metadata_json) : null,
      },
    };
  } catch {
    return payload;
  }
}

function parseTsSort(iso) {
  if (!iso) return 0;
  try {
    const d = new Date(String(iso).trim().replace('Z', '+00:00'));
    return d.getTime() / 1000;
  } catch {
    return 0;
  }
}

function sideNorm(s) {
  return String(s || '')
    .trim()
    .toLowerCase();
}

function priceDriftOk(a, b) {
  try {
    const fa = Number(a);
    const fb = Number(b);
    if (!Number.isFinite(fa) || !Number.isFinite(fb)) return true;
    if (fa <= 0 || fb <= 0) return Math.abs(fa - fb) < 1e-9;
    return Math.abs(fa - fb) / Math.max(fa, fb) <= PARITY_PRICE_REL_TOL;
  } catch {
    return true;
  }
}

function parsePythPrice(parsed) {
  if (!Array.isArray(parsed) || !parsed[0]) return null;
  const p0 = parsed[0];
  const pr = p0.price || {};
  try {
    const price_i = Number(pr.price);
    const conf_i = Number(pr.conf);
    const expo = Number(pr.expo);
    const pub = Number(pr.publish_time);
    const scale = 10 ** expo;
    return {
      price: price_i * scale,
      conf: conf_i * scale,
      publish_time: pub,
      feed_id: String(p0.id || ''),
    };
  } catch {
    return null;
  }
}

function unrealizedUsd(entry, mark, size, side) {
  const sd = sideNorm(side);
  if (sd === 'long') return (mark - entry) * size;
  if (sd === 'short') return (entry - mark) * size;
  return 0;
}

async function fetchHttp(url, timeoutMs = 12000) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      signal: ac.signal,
      headers: { 'User-Agent': 'jupiter-web/tui-parity' },
    });
    const text = await r.text();
    return { ok: r.ok, status: r.status, text };
  } catch (e) {
    return { ok: false, status: 0, text: '', error: e instanceof Error ? e.message : String(e) };
  } finally {
    clearTimeout(t);
  }
}

function dockerSeanv3Check() {
  try {
    const out = execSync('docker inspect -f "{{.State.Running}}" seanv3', {
      encoding: 'utf8',
      timeout: 5000,
    }).trim();
    if (out.toLowerCase() === 'true') {
      return { name: 'Docker seanv3', ok: true, detail: 'Running' };
    }
    return { name: 'Docker seanv3 (optional)', ok: true, detail: 'not running — skipped' };
  } catch {
    return { name: 'Docker seanv3 (optional)', ok: true, detail: 'container absent — skipped' };
  }
}

function marketDbTickCheck() {
  const raw = (process.env.SEAN_MARKET_DATA_PATH || process.env.BLACKBOX_MARKET_DATA_PATH || '').trim();
  const sym = (process.env.MARKET_TICK_SYMBOL || 'SOL-USD').trim() || 'SOL-USD';
  if (!raw) {
    return { name: 'SQLite market_ticks (optional)', ok: true, detail: 'SEAN_MARKET_DATA_PATH unset — skipped' };
  }
  const p = resolve(raw);
  if (!existsSync(p)) {
    return { name: 'SQLite market_ticks (optional)', ok: true, detail: `no file ${p} — skipped` };
  }
  let db;
  try {
    db = new DatabaseSync(p, { readOnly: true });
    const row = db
      .prepare(
        `SELECT primary_price, primary_publish_time, inserted_at FROM market_ticks
         WHERE symbol = ? ORDER BY inserted_at DESC, id DESC LIMIT 1`
      )
      .get(sym);
    db.close();
    if (!row) {
      return { name: 'SQLite market_ticks', ok: false, detail: `no rows for ${sym}` };
    }
    const pub = row.primary_publish_time;
    let age = null;
    if (pub != null) {
      try {
        age = Date.now() / 1000 - Number(pub);
      } catch {
        /* */
      }
    }
    const ageS = age != null ? `publish_age ~${Math.round(age)}s` : 'publish_age n/a';
    const stale = age != null && age >= 120;
    return {
      name: 'SQLite market_ticks (latest)',
      ok: !stale,
      detail: `${sym} price=${row.primary_price}  ${ageS}` + (stale ? '  (stale?)' : ''),
    };
  } catch (e) {
    try {
      db?.close();
    } catch {
      /* */
    }
    return { name: 'SQLite market_ticks', ok: false, detail: e instanceof Error ? e.message : String(e) };
  }
}

async function runPreflight() {
  const checks = [];

  const ping = await fetchHttp(binancePingUrl());
  checks.push({
    name: 'Binance /api/v3/ping',
    ok: ping.status === 200,
    detail: ping.status ? `HTTP ${ping.status}` : ping.error || 'request failed',
  });

  const kl = await fetchHttp(binanceKlinesUrl());
  const kbodyOk = kl.status === 200 && kl.text.trim().startsWith('[');
  checks.push({
    name: `Binance klines ${(process.env.BLACKBOX_BINANCE_KLINE_SYMBOL || 'SOLUSDT').toUpperCase()} 5m`,
    ok: kl.status === 200 && kbodyOk,
    detail: kl.status === 200 ? (kbodyOk ? 'JSON array' : 'not a JSON array') : `HTTP ${kl.status}`,
  });

  const hermes = await fetchHttp(hermesLatestUrl());
  let parsed = null;
  try {
    if (hermes.status === 200 && hermes.text) {
      const j = JSON.parse(hermes.text);
      parsed = Array.isArray(j?.parsed) ? j.parsed : null;
    }
  } catch {
    /* */
  }
  checks.push({
    name: 'Hermes Pyth latest (parsed)',
    ok: !!(parsed && parsed.length),
    detail: parsed && parsed.length ? 'OK' : hermes.error || 'empty parsed[]',
  });

  checks.push(marketDbTickCheck());
  checks.push(dockerSeanv3Check());

  const oracle = parsePythPrice(parsed || []);
  const nowTs = Date.now() / 1000;
  let wallAge = null;
  if (oracle?.publish_time != null) {
    wallAge = nowTs - oracle.publish_time;
  }

  const strictOk = checks.every((c) => {
    if (!c.ok && c.name.toLowerCase().includes('optional') && c.detail.toLowerCase().includes('skipped')) {
      return true;
    }
    return c.ok;
  });

  return {
    checks,
    oracle,
    parsed,
    wall_age_s: wallAge,
    degraded: !strictOk,
  };
}

function paperStartingUsd(db) {
  try {
    const row = db.prepare(`SELECT v FROM analog_meta WHERE k = ?`).get('paper_starting_balance_usd');
    if (row?.v) {
      const v = parseFloat(String(row.v).trim());
      if (v > 0) return v;
    }
  } catch {
    /* */
  }
  const raw = (process.env.SEAN_PAPER_STARTING_BALANCE_USD || '1000').trim();
  const v = parseFloat(raw);
  return v > 0 ? v : 1000;
}

function loadPolicyPanel(repo) {
  const regPath = (process.env.SEANV3_POLICY_REGISTRY || process.env.BLACKBOX_POLICY_REGISTRY || '').trim()
    ? resolve(process.env.SEANV3_POLICY_REGISTRY || process.env.BLACKBOX_POLICY_REGISTRY)
    : join(repo, 'scripts', 'operator', 'policy_registry.json');
  if (!existsSync(regPath)) {
    return {
      error: `Policy registry not found (${regPath}). Mount repo at BLACKBOX_REPO_ROOT or set SEANV3_POLICY_REGISTRY.`,
    };
  }
  let reg;
  try {
    reg = JSON.parse(readFileSync(regPath, 'utf8'));
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
  const policies = (reg.policies || []).filter((x) => x && x.id);
  const envPol =
    (process.env.SEANV3_ACTIVE_POLICY_ID || process.env.BLACKBOX_ACTIVE_POLICY_ID || '').trim() ||
    (policies[0] ? String(policies[0].id) : '');
  const current = policies.find((p) => String(p.id) === String(envPol)) || policies[0];
  if (!current) {
    return { error: 'Empty policies in registry' };
  }
  const ds = current.dataset && typeof current.dataset === 'object' ? current.dataset : {};
  const mode = (ds.mode || '?').toString();
  let effectiveDb = null;
  if (mode === 'isolated' && ds.sqlite_relative) {
    effectiveDb = resolve(repo, String(ds.sqlite_relative).trim());
  } else {
    const envMd = (process.env.SEAN_MARKET_DATA_PATH || process.env.BLACKBOX_MARKET_DATA_PATH || '').trim();
    effectiveDb = envMd ? resolve(envMd) : null;
  }
  let entryPath = null;
  if (current.entry && String(current.entry).trim()) {
    entryPath = resolve(repo, String(current.entry).trim());
  }
  return {
    id: String(current.id),
    label: String(current.label || current.id),
    kind: String(current.kind || 'builtin'),
    dataset_mode: mode,
    effective_db: effectiveDb,
    entry_path: entryPath,
    registry_path: regPath,
  };
}

function fmtParityCell(rec) {
  if (!rec) return '—';
  const side = sideNorm(rec.side);
  let px = '?';
  try {
    px = rec.entry_price != null ? Number(rec.entry_price).toFixed(4) : '?';
  } catch {
    /* */
  }
  const tshort = formatIsoUtcShort(rec.entry_time);
  const tag = rec.kind === 'open' ? ' open' : '';
  return `${side || '?'} @ ${px} · ${tshort}${tag}`;
}

/**
 * @param {boolean} policyAligned When false (Jupiter policy ≠ JUPITER_PARITY_ALIGNED_POLICY), parity column is blank — baseline compare not meaningful.
 */
function parityMatchText(sean, bb, policyAligned) {
  if (!policyAligned) {
    return { text: '—', cls: 'dim' };
  }
  if (sean && bb) {
    if (sideNorm(sean.side) !== sideNorm(bb.side)) return { text: 'SIDE mismatch', cls: 'bad' };
    if (!priceDriftOk(sean.entry_price, bb.entry_price)) return { text: 'MATCH (entry px drift)', cls: 'warn' };
    return { text: 'MATCH', cls: 'ok' };
  }
  if (sean && !bb) return { text: 'Jupiter only — no BlackBox row', cls: 'bad' };
  if (bb && !sean) return { text: 'BlackBox only — no Jupiter row', cls: 'bad' };
  return { text: '—', cls: 'dim' };
}

function buildParityRows(seanDbPath, ledgerPath, maxRows) {
  const out = { rows: [], error: null, sean_db: seanDbPath, ledger_db: ledgerPath };
  if (!existsSync(seanDbPath)) {
    out.error = 'Sean DB missing';
    return out;
  }
  let policyAligned = true;
  let alignNote = '';
  try {
    const dba = new DatabaseSync(seanDbPath, { readOnly: true });
    const alignTarget = String(process.env.JUPITER_PARITY_ALIGNED_POLICY || '').trim();
    const active = getActiveDeploymentSnapshot(dba).policyId;
    policyAligned = active === alignTarget;
    alignNote = policyAligned
      ? `aligned policy ${active} (compare vs BlackBox baseline)`
      : `Jupiter policy ${active} ≠ compare target ${alignTarget || '(unset)'} — parity column blank (set JUPITER_PARITY_ALIGNED_POLICY on jupiter-web to match)`;
    dba.close();
  } catch {
    policyAligned = true;
  }
  out.parity_policy_aligned = policyAligned;
  out.parity_align_note = alignNote;

  const maxFetch = Math.max(maxRows * 3, 48);
  let seanDb;
  const seanMap = new Map();
  try {
    seanDb = new DatabaseSync(seanDbPath, { readOnly: true });
    const all = seanDb
      .prepare(
        `SELECT entry_market_event_id, side, entry_time_utc, entry_price, size_notional_sol, id, exit_time_utc
         FROM sean_paper_trades ORDER BY id DESC`
      )
      .all();
    for (const r of all) {
      const mid = String(r.entry_market_event_id || '').trim();
      if (!mid || seanMap.has(mid)) continue;
      seanMap.set(mid, {
        kind: 'closed',
        side: r.side,
        entry_time: r.entry_time_utc,
        entry_price: r.entry_price,
        size: r.size_notional_sol,
        sean_id: r.id,
        exit_time: r.exit_time_utc,
      });
      if (seanMap.size >= maxFetch * 2) break;
    }
    const pos = seanDb.prepare('SELECT side, entry_market_event_id, opened_at_utc, entry_price, size_notional_sol FROM sean_paper_position WHERE id=1').get();
    if (pos && sideNorm(pos.side) !== '' && sideNorm(pos.side) !== 'flat' && String(pos.entry_market_event_id || '').trim()) {
      const omid = String(pos.entry_market_event_id).trim();
      seanMap.set(omid, {
        kind: 'open',
        side: pos.side,
        entry_time: pos.opened_at_utc,
        entry_price: pos.entry_price,
        size: pos.size_notional_sol,
        entry_market_event_id: omid,
      });
    }
    seanDb.close();
  } catch (e) {
    try {
      seanDb?.close();
    } catch {
      /* */
    }
    out.error = e instanceof Error ? e.message : String(e);
    return out;
  }

  const bbMap = new Map();
  if (existsSync(ledgerPath)) {
    let ldb;
    try {
      ldb = new DatabaseSync(ledgerPath, { readOnly: true });
      const cur = ldb
        .prepare(
          `SELECT market_event_id, side, entry_time, entry_price, size, trade_id, exit_time, created_at_utc
           FROM execution_trades WHERE lane = ? AND strategy_id = ? ORDER BY created_at_utc DESC`
        )
        .all(BB_LANE, BB_STRATEGY);
      for (const row of cur) {
        const mid = String(row.market_event_id || '').trim();
        if (!mid || bbMap.has(mid)) continue;
        bbMap.set(mid, {
          side: row.side,
          entry_time: row.entry_time,
          entry_price: row.entry_price,
          size: row.size,
          trade_id: row.trade_id,
          exit_time: row.exit_time,
          created_at_utc: row.created_at_utc,
        });
        if (bbMap.size >= maxFetch) break;
      }
      ldb.close();
    } catch {
      try {
        ldb?.close();
      } catch {
        /* */
      }
    }
  }

  const allMids = new Set([...seanMap.keys(), ...bbMap.keys()]);
  if (allMids.size === 0) {
    out.error = null;
    return out;
  }

  const ordered = [...allMids].sort((a, b) => {
    const sa = seanMap.get(a);
    const sb = seanMap.get(b);
    const ba = bbMap.get(a);
    const bb = bbMap.get(b);
    let ts = 0;
    if (sa) ts = Math.max(ts, parseTsSort(sa.entry_time));
    if (sb) ts = Math.max(ts, parseTsSort(sb.entry_time));
    if (ba) ts = Math.max(ts, parseTsSort(ba.entry_time || ba.created_at_utc));
    if (bb) ts = Math.max(ts, parseTsSort(bb.entry_time || bb.created_at_utc));
    return ts;
  });
  const slice = ordered.slice(0, maxRows);

  for (const mid of slice) {
    const s = seanMap.get(mid);
    const b = bbMap.get(mid);
    const pm = parityMatchText(s, b, policyAligned);
    out.rows.push({
      market_event_id: mid,
      sean_cell: fmtParityCell(s),
      bb_cell: b ? fmtParityCell(b) : '—',
      parity: pm.text,
      parity_cls: pm.cls,
    });
  }
  return out;
}

function buildSummary(db) {
  const keypairEnv =
    (process.env.KEYPAIR_PATH || process.env.SEANV3_KEYPAIR_PATH || process.env.BLACKBOX_SOLANA_KEYPAIR_PATH || '').trim();

  const out = {
    wallet: null,
    wallet_status: null,
    position: null,
    recent_trades: [],
    recent_no_trades: [],
    recent_trade_opens: [],
    all_trades_dropdown: [],
    last_kline: null,
    error: null,
    keypair_env: keypairEnv || null,
  };

  try {
    const st = db.prepare(`SELECT v FROM analog_meta WHERE k = 'wallet_status'`).get();
    if (st?.v) out.wallet_status = String(st.v);
  } catch {
    /* */
  }

  try {
    const w = db.prepare(`SELECT pubkey_base58, keypair_path FROM paper_wallet WHERE id=1`).get();
    if (w?.pubkey_base58) {
      out.wallet = {
        pubkey_base58: String(w.pubkey_base58),
        keypair_path_suffix: w.keypair_path ? String(w.keypair_path).slice(-48) : null,
      };
    }
  } catch {
    /* */
  }

  try {
    const p = db
      .prepare(
        `SELECT side, entry_price, size_notional_sol, entry_market_event_id, opened_at_utc, bars_held
         FROM sean_paper_position WHERE id=1`
      )
      .get();
    if (p) {
      out.position = {
        side: p.side != null ? String(p.side) : null,
        entry_price: p.entry_price,
        size_notional_sol: p.size_notional_sol,
        entry_market_event_id: p.entry_market_event_id != null ? String(p.entry_market_event_id) : null,
        opened_at_utc: p.opened_at_utc != null ? String(p.opened_at_utc) : null,
        bars_held: p.bars_held,
      };
    }
  } catch {
    /* */
  }

  const tradeLimit = Math.min(50, Math.max(1, parseInt(process.env.SEANV3_TUI_TRADE_ROWS || '20', 10) || 20));
  const dropLimit = Math.min(500, Math.max(10, parseInt(process.env.SEANV3_TRADE_DROPDOWN_MAX || '200', 10) || 200));
  try {
    const rows = db
      .prepare(
        `SELECT id, engine_id, side, entry_time_utc, exit_time_utc, entry_price, exit_price,
                size_notional_sol, gross_pnl_usd, result_class, entry_market_event_id, exit_market_event_id, metadata_json
         FROM sean_paper_trades ORDER BY id DESC LIMIT ?`
      )
      .all(tradeLimit);
    const sym = (process.env.SEANV3_CANONICAL_SYMBOL || process.env.CANONICAL_SYMBOL || 'SOL-PERP').trim() || 'SOL-PERP';
    out.recent_trades = rows.map((r) => ({
      id: r.id,
      trade_id: `sean_${r.id}`,
      engine_id: r.engine_id != null ? String(r.engine_id) : null,
      side: r.side != null ? String(r.side) : null,
      entry_time_utc: r.entry_time_utc != null ? String(r.entry_time_utc) : null,
      exit_time_utc: r.exit_time_utc != null ? String(r.exit_time_utc) : null,
      entry_price: r.entry_price,
      exit_price: r.exit_price,
      size_notional_sol: r.size_notional_sol,
      gross_pnl_usd: r.gross_pnl_usd,
      result_class: r.result_class != null ? String(r.result_class) : null,
      entry_market_event_id: r.entry_market_event_id != null ? String(r.entry_market_event_id) : null,
      exit_market_event_id: r.exit_market_event_id != null ? String(r.exit_market_event_id) : null,
      exit_reason: exitReasonFromMeta(r.metadata_json),
      symbol: sym,
    }));
    const drows = db
      .prepare(
        `SELECT id, side, exit_time_utc, gross_pnl_usd FROM sean_paper_trades ORDER BY id DESC LIMIT ?`
      )
      .all(dropLimit);
    out.all_trades_dropdown = drows.map((r) => ({
      id: r.id,
      trade_id: `sean_${r.id}`,
      label: `#${r.id} ${String(r.side)} · ${formatIsoUtcShort(r.exit_time_utc)} · ${Number(r.gross_pnl_usd).toFixed(4)} USD`,
    }));
  } catch {
    /* */
  }

  const noTradeLimit = Math.min(50, Math.max(1, parseInt(process.env.SEANV3_TUI_NO_TRADE_ROWS || '30', 10) || 30));
  try {
    const nrows = db
      .prepare(
        `SELECT id, timestamp_utc AS at_utc, market_event_id, policy_id, reason_code
         FROM sean_bar_decisions WHERE outcome = 'NO_TRADE' ORDER BY id DESC LIMIT ?`
      )
      .all(noTradeLimit);
    out.recent_no_trades = nrows.map((r) => ({
      id: r.id,
      at_utc: r.at_utc != null ? String(r.at_utc) : null,
      market_event_id: r.market_event_id != null ? String(r.market_event_id) : null,
      policy_id: r.policy_id != null ? String(r.policy_id) : null,
      reason_code: r.reason_code != null ? String(r.reason_code) : null,
    }));
  } catch {
    /* table missing on legacy DB until migrate */
  }

  const tradeOpenLimit = Math.min(50, Math.max(1, parseInt(process.env.SEANV3_TUI_TRADE_OPEN_ROWS || '30', 10) || 30));
  try {
    const trows = db
      .prepare(
        `SELECT id, timestamp_utc AS at_utc, market_event_id, policy_id, candidate_side, reason_code, trade_id
         FROM sean_bar_decisions WHERE outcome = 'TRADE_OPEN' ORDER BY id DESC LIMIT ?`
      )
      .all(tradeOpenLimit);
    out.recent_trade_opens = trows.map((r) => ({
      id: r.id,
      at_utc: r.at_utc != null ? String(r.at_utc) : null,
      market_event_id: r.market_event_id != null ? String(r.market_event_id) : null,
      policy_id: r.policy_id != null ? String(r.policy_id) : null,
      candidate_side: r.candidate_side != null ? String(r.candidate_side) : null,
      reason_code: r.reason_code != null ? String(r.reason_code) : null,
      trade_id: r.trade_id != null ? Number(r.trade_id) : null,
    }));
  } catch {
    /* */
  }

  try {
    const k = db
      .prepare(
        `SELECT market_event_id, close_px, polled_at_utc FROM sean_binance_kline_poll
         ORDER BY id DESC LIMIT 1`
      )
      .get();
    if (k) {
      out.last_kline = {
        market_event_id: k.market_event_id != null ? String(k.market_event_id) : null,
        close_px: k.close_px,
        polled_at_utc: k.polled_at_utc != null ? String(k.polled_at_utc) : null,
      };
    }
  } catch {
    /* */
  }

  return out;
}

function computePaperLedger(markUsd) {
  const keypairEnv =
    (process.env.KEYPAIR_PATH || process.env.SEANV3_KEYPAIR_PATH || process.env.BLACKBOX_SOLANA_KEYPAIR_PATH || '').trim();
  let db;
  try {
    db = new DatabaseSync(dbPath(), { readOnly: true });
    const starting = paperStartingUsd(db);
    const n = Number(db.prepare('SELECT COUNT(*) AS c FROM sean_paper_trades').get().c || 0);
    const totalRow = db.prepare('SELECT COALESCE(SUM(gross_pnl_usd),0) AS s FROM sean_paper_trades').get();
    const realized = Number(totalRow?.s || 0);
    const last = db
      .prepare('SELECT gross_pnl_usd, result_class, side FROM sean_paper_trades ORDER BY id DESC LIMIT 1')
      .get();
    const pos = db.prepare('SELECT side, entry_price, size_notional_sol FROM sean_paper_position WHERE id=1').get();
    let unreal = 0;
    let openLine = 'Open: flat';
    const mark = markUsd != null && Number.isFinite(Number(markUsd)) ? Number(markUsd) : null;
    if (pos && pos[0] && sideNorm(pos[0]) !== 'flat') {
      if (mark != null) {
        try {
          const entry = Number(pos[1]);
          const size = Number(pos[2] || 1);
          unreal = unrealizedUsd(entry, mark, size, String(pos[0]));
          openLine = `Open: ${pos[0]} @ ${pos[1]}  notional_sol≈${size}  mtm≈${unreal.toFixed(4)} USD (Hermes mark)`;
        } catch {
          openLine = `Open: ${pos[0]} @ ${pos[1]}`;
        }
      } else {
        openLine = `Open: ${pos[0]} @ ${pos[1]}  (set Hermes OK for mtm)`;
      }
    }
    return {
      starting_balance_usd: starting,
      realized_pnl_usd: realized,
      closed_trade_count: n,
      equity_est_usd: starting + realized + unreal,
      last_closed: last
        ? { side: last.side, result_class: last.result_class, gross_pnl_usd: last.gross_pnl_usd }
        : null,
      open_line: openLine,
      keypair_env: keypairEnv || null,
    };
  } catch {
    return null;
  } finally {
    try {
      db?.close();
    } catch {
      /* */
    }
  }
}

/**
 * Operator-facing funding snapshot + next-open gate (same rules as sean_engine + funding_guards).
 * @param {string} seanPath
 * @param {number | null} markUsd Hermes SOL/USD when available
 * @param {Record<string, unknown>} base buildSummary output (needs last_kline for close)
 */
function buildOperatorPayload(seanPath, markUsd, base) {
  const paperEnv = (process.env.PAPER_TRADING || '1').trim();
  const paperEnvOn = paperEnv !== '0' && paperEnv !== 'false';
  const tokenConfigured = Boolean((process.env.JUPITER_OPERATOR_TOKEN || '').trim());
  const stakeEdit = ['1', 'true', 'yes'].includes((process.env.SEAN_ALLOW_PAPER_STAKE_EDIT || '').trim().toLowerCase());
  let db;
  try {
    db = new DatabaseSync(seanPath, { readOnly: true });
    const modeRow = db.prepare(`SELECT v FROM analog_meta WHERE k = 'sean_funding_mode'`).get();
    const mode = modeRow?.v != null ? String(modeRow.v).trim() : 'paper';
    const lamRow = db.prepare(`SELECT v FROM analog_meta WHERE k = 'chain_sol_balance_lamports'`).get();
    const lamAtRow = db.prepare(`SELECT v FROM analog_meta WHERE k = 'chain_sol_balance_updated_utc'`).get();
    const chErrRow = db.prepare(`SELECT v FROM analog_meta WHERE k = 'chain_balance_error'`).get();
    const closeRaw = base?.last_kline?.close_px;
    const closePx = closeRaw != null ? parseFloat(String(closeRaw)) : NaN;
    const m = Number.isFinite(Number(markUsd)) ? Number(markUsd) : Number.isFinite(closePx) ? closePx : NaN;
    const sizeSol = parseFloat(process.env.SEAN_ENGINE_SIZE_NOTIONAL_SOL || '1') || 1;
    const eq = getPaperEquityUsd(db, m);
    const gate = assertCanOpenPosition(db, {
      markUsd: m,
      closePx: Number.isFinite(closePx) ? closePx : m,
      sizeNotionalSol: sizeSol,
    });
    return {
      schema: 'jupiter_operator_state_v1',
      sean_funding_mode: mode,
      paper_trading_env: paperEnvOn,
      chain_sol_balance_lamports: lamRow?.v != null ? String(lamRow.v) : null,
      chain_balance_updated_utc: lamAtRow?.v != null ? String(lamAtRow.v) : null,
      chain_balance_error: chErrRow?.v != null ? String(chErrRow.v) : null,
      paper_equity_usd: eq,
      next_open_gate: gate,
      operator_controls: {
        post_token_configured: tokenConfigured,
        paper_stake_edit_allowed: stakeEdit,
        wallet_operator_writes_allowed: !jupiterWebReadOnly(),
        read_only_except_policy: jupiterWebReadOnly(),
      },
    };
  } catch (e) {
    return { schema: 'jupiter_operator_state_v1', error: e instanceof Error ? e.message : String(e) };
  } finally {
    try {
      db?.close();
    } catch {
      /* */
    }
  }
}

function frontDoorHtml() {
  const mode = jupiterAuthMode();
  const loginNote =
    mode === 'session'
      ? `<p class="note">Browser login: <strong><a href="/auth/login">Sign in</a></strong> (session). Forgot password uses email reset. Operator <strong>Bearer</strong> for API POSTs is separate.</p>`
      : mode === 'basic'
        ? `<p class="note">Browser login is <strong>HTTP Basic Auth</strong> (<code>JUPITER_WEB_LOGIN_*</code>). Operator <strong>Bearer</strong> for API POSTs is separate.</p>`
        : `<p class="note">No browser login configured — restrict with VPN/firewall. Operator Bearer token required for policy POST when read-only.</p>`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Jupiter — lab</title>
  <style>
    body { margin:0; min-height:100vh; background:#050508; color:#e6edf3; font-family: system-ui, Segoe UI, sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:1.5rem; }
    .hero { max-width:min(920px, 96vw); text-align:center; }
    img { max-width:100%; height:auto; border-radius:4px; border:1px solid #30363d; }
    h1 { font-size:1.15rem; font-weight:600; margin:1rem 0 0.5rem; }
    p { color:#8b949e; font-size:0.9rem; max-width: 56ch; margin: 0.5rem auto; line-height:1.45; }
    a.btn { display:inline-block; margin-top:1rem; padding:0.55rem 1.25rem; background:#21262d; color:#58a6ff; border:1px solid #30363d; border-radius:4px; text-decoration:none; font-weight:600; }
    a.btn:hover { background:#30363d; }
    .note { color:#d29922; font-size:0.82rem; margin-top:1.1rem; }
    code { background:#1e1e1e; padding:0.1rem 0.35rem; border-radius:2px; }
  </style>
</head>
<body>
  <div class="hero">
    <img src="/static/jupiter_front_door.png" alt="Jupiter — financial rings" width="920" height="auto"/>
    <h1>Jupiter — operator lab</h1>
    <p>SeanV3 paper engine, parity vs BlackBox baseline. Dashboard is read-only for wallet/funding when <code>JUPITER_WEB_READ_ONLY=1</code>; sole write is <strong>set active Jupiter policy</strong> — <code>POST /api/v1/jupiter/active-policy</code> (Bearer).</p>
    <a class="btn" href="/dashboard">Open dashboard</a>
    ${loginNote}
  </div>
</body>
</html>`;
}

async function buildFullView() {
  const rr = repoRoot();
  const seanPath = dbPath();
  const parityMax = Math.min(40, Math.max(3, parseInt(process.env.SEANV3_TUI_PARITY_ROWS || '18', 10) || 18));

  const base = {
    schema: 'jupiter_web_tui_view_v1',
    application: 'Jupiter',
    sqlite_path: seanPath,
    repo_root: rr,
    error: null,
  };

  let jupiterRuntime = {
    active_policy: '',
    source: 'unset',
    engine_display_id: jupiterEngineDisplayId(),
    engine_online: jupiterEngineSliceEnabled(),
  };
  let db;
  try {
    db = new DatabaseSync(seanPath, { readOnly: true });
    Object.assign(base, buildSummary(db));
    const rp = getActiveDeploymentSnapshot(db);
    jupiterRuntime = {
      active_policy: rp.policyId,
      source: rp.source,
      engine_display_id: jupiterEngineDisplayId(),
      engine_online: jupiterEngineSliceEnabled(),
    };
  } catch (e) {
    base.error = e instanceof Error ? e.message : String(e);
  } finally {
    try {
      db?.close();
    } catch {
      /* */
    }
  }

  const tradingMode = {
    actual_banner: ['1', 'true', 'yes'].includes((process.env.SEANV3_TUI_ACTUAL || '').trim().toLowerCase()),
    paper_trading: (process.env.PAPER_TRADING || '1').trim() !== '0',
    sean_jupiter_policy: (process.env.SEAN_JUPITER_POLICY || 'jupiter_4').trim(),
    jupiter_runtime: jupiterRuntime,
    post_token_configured: Boolean((process.env.JUPITER_OPERATOR_TOKEN || '').trim()),
    read_only_except_policy: jupiterWebReadOnly(),
  };

  const policy = loadPolicyPanel(rr);
  const preflight = await runPreflight();
  const mark = preflight.oracle?.price != null ? Number(preflight.oracle.price) : null;
  const paperLedger = computePaperLedger(mark);
  const operator = buildOperatorPayload(seanPath, mark, base);

  let parity = { rows: [], error: null, sean_db: seanPath, ledger_db: executionLedgerPath() };
  try {
    parity = buildParityRows(seanPath, executionLedgerPath(), parityMax);
  } catch (e) {
    parity.error = e instanceof Error ? e.message : String(e);
  }

  return {
    ...base,
    paper_ledger: paperLedger,
    trading_mode: tradingMode,
    read_only_except_policy: jupiterWebReadOnly(),
    policy,
    preflight,
    parity,
    operator,
    refresh_sec: Math.max(0, parseFloat(process.env.JUPITER_WEB_REFRESH_SEC || '3') || 3),
  };
}

/**
 * Client-side polling via fetch(/api/summary.json) — avoids &lt;meta refresh&gt; full-page flicker.
 * (WebSocket would add a dependency; SSE is an alternative later.)
 */
function jwLivePollScript(refreshSec) {
  const ms = Math.max(2000, Math.floor((Number(refreshSec) || 3) * 1000));
  return `<script>
(function(){
  var POLL_MS=${ms};
  function E(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function T(s,n){s=String(s||'');return s.length<=n?s:s.slice(0,n-1)+'\\u2026';}
  function isoUtc(s){if(!s)return'\\u2014';try{var d=new Date(String(s).trim().replace('Z','+00:00'));return isNaN(d.getTime())?String(s).slice(0,22):d.toISOString().slice(0,16).replace('T',' ')+' UTC';}catch(e){return String(s).slice(0,22);}}
  function trCls(rc){var x=String(rc||'').toLowerCase();if(x==='win')return'trade-win';if(x==='loss')return'trade-loss';return'trade-flat';}
  function ntCls(rc){var x=String(rc||'').toLowerCase();if(x==='open_blocked'||x==='funding_gate_blocked')return'nt-blocked';if(x==='no_atr'||x==='atr_invalid')return'nt-warn';if(x==='no_entry_signal'||x==='no_candidate_side')return'nt-signal';return'nt-dim';}
  function setSt(id, text, cls){
    var el=document.getElementById(id);
    if(!el)return;
    el.textContent=text;
    el.className='jw-st-v '+cls+(id==='jw-st-deployment'?' jw-st-deployment':'');
  }
  /** Mirrors server computeStatusStrip — shallow UI only. */
  function applyStatusStrip(j){
    var w=j.wallet||{};
    var op=j.operator||{};
    var opErr=!!op.error;
    var pf=j.preflight||{};
    var checks=pf.checks||[];
    var hermesChk=null, binPing=null, binKl=null;
    for(var i=0;i<checks.length;i++){
      var c=checks[i], n=String(c&&c.name||'');
      if(/hermes|pyth/i.test(n))hermesChk=c;
      if(/binance.*ping/i.test(n.toLowerCase()))binPing=c;
      if(/binance klines/i.test(n.toLowerCase()))binKl=c;
    }
    var o=pf.oracle;
    var wallAge=pf.wall_age_s;
    var pythLabel='Unknown', pythCls='jw-st-muted';
    if(!hermesChk||!hermesChk.ok||!o||o.price==null){pythLabel='Down';pythCls='jw-st-bad';}
    else if(wallAge!=null&&isFinite(Number(wallAge))&&Number(wallAge)>120){pythLabel='Stale';pythCls='jw-st-warn';}
    else{pythLabel='Live';pythCls='jw-st-ok';}
    var kl=j.last_kline;
    var bnLabel='Unknown', bnCls='jw-st-muted';
    if(!binPing||!binPing.ok||!binKl||!binKl.ok){bnLabel='Down';bnCls='jw-st-bad';}
    else{
      var ageSec=null;
      if(kl&&kl.polled_at_utc){
        try{var ts=new Date(String(kl.polled_at_utc).trim()).getTime();if(!isNaN(ts))ageSec=(Date.now()-ts)/1000;}catch(e){}
      }
      if(ageSec!=null&&ageSec>600){bnLabel='Stale';bnCls='jw-st-warn';}
      else{bnLabel='Live';bnCls='jw-st-ok';}
    }
    var walletConnected=!!w.pubkey_base58;
    var wm=document.getElementById('jw-st-wallet-main');
    if(wm)wm.textContent=walletConnected?'Connected':'Disconnected';
    var ws=document.getElementById('jw-st-wallet-sub');
    if(ws){
      var pk=String(w.pubkey_base58||'').trim();
      if(pk.length>10)ws.textContent=pk.slice(0,4)+'\\u2026'+pk.slice(-4);
      else ws.textContent=pk;
      ws.style.display=pk?'inline':'none';
    }
    var wwrap=document.getElementById('jw-st-wallet');
    if(wwrap)wwrap.className='jw-st-v '+(walletConnected?'jw-st-ok':'jw-st-bad');
    setSt('jw-st-pyth',pythLabel,pythCls);
    setSt('jw-st-binance',bnLabel,bnCls);
    var readOnly=!!j.read_only_except_policy;
    var gate=op.next_open_gate||{};
    var trgLabel='Enabled', trgCls='jw-st-ok';
    if(opErr){trgLabel='Unknown';trgCls='jw-st-muted';}
    else if(readOnly){trgLabel='Read-only';trgCls='jw-st-warn';}
    else if(gate.ok!==true){trgLabel='Blocked';trgCls='jw-st-bad';}
    setSt('jw-st-trading',trgLabel,trgCls);
    var tm=j.trading_mode||{};
    var modeLabel=tm.actual_banner?'Live':'Paper';
    var modeCls=tm.actual_banner?'jw-st-warn':'jw-st-ok';
    setSt('jw-st-mode',modeLabel,modeCls);
    var jr=tm.jupiter_runtime||{};
    var engOn=jr.engine_online!==false;
    var eid=String(jr.engine_display_id||'BBT_v1').trim();
    var engLabel=engOn?eid+' \\u00b7 Online':eid+' \\u00b7 Off';
    var engCls=engOn?'jw-st-engine-on':'jw-st-muted';
    setSt('jw-st-engine',engLabel,engCls);
    var depEl=document.getElementById('jw-st-deployment');
    if(depEl){depEl.textContent=jr.active_policy||'\\u2014';depEl.className='jw-st-v jw-st-deployment';}
    var pq=op.paper_equity_usd||{};
    var eqStr='\\u2014', eqCls='jw-st-muted';
    if(!opErr&&pq.equity_usd!=null&&isFinite(Number(pq.equity_usd))){eqStr=Number(pq.equity_usd).toFixed(2);eqCls='jw-st-ok';}
    setSt('jw-st-equity',eqStr,eqCls);
    var pos=j.position;
    var posLabel='\\u2014', posCls='jw-st-muted';
    if(pos&&String(pos.side)!=='flat'){
      var sd=String(pos.side).toLowerCase();
      if(sd==='long'){posLabel='Long';posCls='jw-st-warn';}
      else if(sd==='short'){posLabel='Short';posCls='jw-st-warn';}
      else{posLabel=String(pos.side);posCls='jw-st-ok';}
    }else{posLabel='Flat';posCls='jw-st-ok';}
    setSt('jw-st-position',posLabel,posCls);
    var updLabel='\\u2014', updCls='jw-st-muted';
    if(kl&&kl.polled_at_utc){
      try{
        var t0=new Date(String(kl.polled_at_utc).trim()).getTime();
        if(!isNaN(t0)){
          var sec=(Date.now()-t0)/1000;
          if(sec>=0&&sec<120){updLabel=Math.round(sec)+'s';updCls='jw-st-ok';}
          else if(sec>=120&&sec<900){updLabel=Math.round(sec/60)+'m';updCls='jw-st-warn';}
          else if(sec>=900){updLabel=Math.round(sec/60)+'m';updCls='jw-st-bad';}
        }
      }catch(e){}
    }else if(wallAge!=null&&isFinite(Number(wallAge))){
      updLabel='Pyth ~'+Math.round(Number(wallAge))+'s';
      updCls=Number(wallAge)>120?'jw-st-warn':'jw-st-ok';
    }
    setSt('jw-st-updated',updLabel,updCls);
  }
  function apply(j){
    if(!j||j.error)return;
    applyStatusStrip(j);
    var tm=j.trading_mode||{}, jr=tm.jupiter_runtime||{};
    var a=document.getElementById('jw-ap-code'); if(a)a.textContent=jr.active_policy||'';
    a=document.getElementById('jw-ap-src'); if(a)a.textContent=jr.source||'';
    var sel=document.getElementById('jw-jupiter-policy'); if(sel&&jr.active_policy)sel.value=jr.active_policy;
    var op=j.operator||{};
    if(op.error)return;
    var pq=op.paper_equity_usd||{}, gate=op.next_open_gate||{};
    var pf=j.preflight||{}, o=pf.oracle, kl=j.last_kline;
    var kc=kl&&kl.close_px!=null?E(kl.close_px):'\\u2014';
    var hp=o&&o.price!=null?E(Number(o.price).toFixed(4)):'\\u2014';
    var ls=document.getElementById('jw-live-strip');
    if(ls){ls.innerHTML='<p><strong>Binance kline close</strong> '+kc+' \\u00b7 <strong>Hermes SOL/USD</strong> '+hp+' \\u00b7 <strong>poll</strong> '+E(kl&&kl.polled_at_utc||'\\u2014')+'</p>';ls.classList.add('jw-pulse');setTimeout(function(){ls.classList.remove('jw-pulse');},200);}
    var ev=document.getElementById('jw-op-eq-val'); if(ev){var eq=pq.equity_usd!=null&&isFinite(Number(pq.equity_usd))?Number(pq.equity_usd).toFixed(4):'\\u2014';ev.textContent=eq;}
    var eb=document.getElementById('jw-op-eq-brk'); if(eb)eb.textContent='(start '+E(pq.starting_usd!=null?pq.starting_usd:'\\u2014')+' + realized '+E(pq.realized_pnl_usd!=null?pq.realized_pnl_usd:'\\u2014')+' + unreal '+E(pq.unrealized_usd!=null?pq.unrealized_usd:'\\u2014')+')';
    var cl=document.getElementById('jw-chain-lam'); if(cl)cl.textContent=op.chain_sol_balance_lamports||'\\u2014';
    var ca=document.getElementById('jw-chain-at'); if(ca)ca.textContent=op.chain_balance_updated_utc||'';
    var gl=document.getElementById('jw-gate-line'); if(gl){var gOk=gate.ok===true;gl.innerHTML='<strong>Next engine open</strong> '+(gOk?'<span class="ok">allowed</span>':'<span class="bad">blocked</span>')+' \\u2014 '+E(gate.reason||'\\u2014')+' <span class="muted">'+E(gate.detail||'')+'</span>';}
    var wv=document.getElementById('jw-wallet-eq-val'); if(wv){var eq2=pq.equity_usd!=null&&isFinite(Number(pq.equity_usd))?Number(pq.equity_usd).toFixed(4):'\\u2014';wv.textContent=eq2;}
    var wb=document.getElementById('jw-wallet-eq-brk'); if(wb)wb.textContent='= bankroll '+E(pq.starting_usd!=null?pq.starting_usd:'\\u2014')+' + realized '+E(pq.realized_pnl_usd!=null?pq.realized_pnl_usd:'\\u2014')+' + unreal '+E(pq.unrealized_usd!=null?pq.unrealized_usd:'\\u2014');
    var pl=j.paper_ledger, lb=document.getElementById('jw-ledger-block');
    if(lb&&pl)lb.innerHTML='<p><strong>Paper ledger</strong> \\u2014 starting '+E(pl.starting_balance_usd)+' USD \\u00b7 realized '+E(pl.realized_pnl_usd)+' \\u00b7 equity ~'+E(pl.equity_est_usd!=null&&isFinite(Number(pl.equity_est_usd))?Number(pl.equity_est_usd).toFixed(4):pl.equity_est_usd)+' USD</p><p class="muted">Same figures as <strong>Wallet &amp; funding</strong>; trade list below.</p>';
    var pos=j.position, pkb=document.getElementById('jw-pos-kl-block');
    if(pkb){var posHtml=(pos&&String(pos.side)!=='flat')?('<p><strong>Open</strong> '+E(pos.side)+' @ '+E(pos.entry_price)+' \\u00b7 mid '+E(pos.entry_market_event_id)+'</p>'):'<p class="muted">Position: flat</p>';var klHtml=kl?('<p class="muted">Last kline poll: '+E(kl.market_event_id)+' \\u00b7 close '+E(kl.close_px)+' \\u00b7 '+E(kl.polled_at_utc)+'</p>'):'';pkb.innerHTML=posHtml+klHtml;}
    var pfb=document.getElementById('jw-preflight-banner'); if(pfb)pfb.innerHTML=pf.degraded?'<p class="bad"><strong>DEGRADED</strong> \\u2014 fix failing checks before relying on runtime.</p>':'<p class="ok"><strong>ALL ACTIVE</strong> \\u2014 checks passing</p>';
    var pft=document.getElementById('jw-preflight-tbody'); if(pft&&pf.checks){pft.innerHTML=pf.checks.map(function(c){var st=c.ok?'<span class="ok">OK</span>':'<span class="bad">FAIL</span>';return'<tr><td>'+E(c.name)+'</td><td>'+st+'</td><td>'+E(c.detail)+'</td></tr>';}).join('');}
    var ob=document.getElementById('jw-oracle-block');
    if(ob){if(o){var rel=o.price?Number(o.conf)/Number(o.price)*100:0;ob.innerHTML='<p><strong>SOL/USD</strong> '+E(Number(o.price).toFixed(4))+' USD</p><p class="muted">Confidence \\u00b1'+E(Number(o.conf).toFixed(6))+' ('+E(rel.toFixed(4))+'% of price)</p><p class="muted">Publish unix: '+E(String(o.publish_time))+' '+(pf.wall_age_s!=null?'wall age ~'+Number(pf.wall_age_s).toFixed(1)+'s':'')+'</p><p class="muted">Feed: '+E(T(o.feed_id,20))+'</p>';}else ob.innerHTML='<p class="muted">No Hermes parsed payload yet.</p>';}
    var pt=document.getElementById('jw-parity-tbody'); if(pt&&j.parity){var pr=j.parity;if(pr.error&&!(pr.rows&&pr.rows.length))pt.innerHTML='<tr><td colspan="4" class="muted">'+E(pr.error)+'</td></tr>';else if(!pr.rows||!pr.rows.length)pt.innerHTML='<tr><td colspan="4" class="muted">No parity rows yet (need trades with market_event_id + optional execution_ledger.db).</td></tr>';else pt.innerHTML=pr.rows.map(function(r){var pc=r.parity_cls==='ok'?'p-ok':r.parity_cls==='warn'?'p-warn':r.parity_cls==='bad'?'p-bad':'p-dim';return'<tr><td>'+E(T(r.market_event_id,44))+'</td><td>'+E(r.sean_cell)+'</td><td>'+E(r.bb_cell)+'</td><td class="'+pc+'">'+E(r.parity)+'</td></tr>';}).join('');}
    var tt=document.getElementById('jw-trades-tbody'); if(tt&&j.recent_trades){var rt=j.recent_trades;tt.innerHTML=rt.length?rt.map(function(t){return'<tr class="trade-row '+trCls(t.result_class)+'" data-trade-id="'+E(String(t.id))+'"><td>'+E(t.trade_id)+'</td><td>'+E(isoUtc(t.exit_time_utc))+'</td><td>'+E(isoUtc(t.entry_time_utc))+'</td><td>'+E(t.symbol)+'</td><td>'+E(t.side)+'</td><td>'+E(t.entry_price)+'</td><td>'+E(t.exit_price)+'</td><td>'+E(t.size_notional_sol)+'</td><td>'+E(t.gross_pnl_usd)+'</td><td>'+E(t.result_class)+'</td><td>'+E(t.exit_reason)+'</td><td>'+E(T(t.entry_market_event_id,40))+'</td><td>'+E(T(t.exit_market_event_id,40))+'</td></tr>';}).join(''):'<tr><td colspan="13" class="muted">No closed trades yet</td></tr>';jwWireTrades();}
    var nt=document.getElementById('jw-no-trade-tbody'); if(nt&&j.recent_no_trades){var rn=j.recent_no_trades;nt.innerHTML=rn.length?rn.map(function(n){var mid=String(n.market_event_id||'');return'<tr class="'+ntCls(n.reason_code)+'"><td>'+E(isoUtc(n.at_utc))+'</td><td title="'+E(mid)+'">'+E(T(mid,44))+'</td><td>'+E(n.policy_id||'\\u2014')+'</td><td>'+E(n.reason_code)+'</td><td><button type="button" class="fund-btn jw-bar-decision-view" data-decision-id="'+E(String(n.id))+'">View</button></td></tr>';}).join(''):'<tr><td colspan="5" class="muted">No NO_TRADE decisions yet</td></tr>';}
    var to=document.getElementById('jw-trade-open-tbody'); if(to&&j.recent_trade_opens){var ro=j.recent_trade_opens;to.innerHTML=ro.length?ro.map(function(n){var mid=String(n.market_event_id||'');var side=String(n.candidate_side||'\\u2014');return'<tr class="to-open"><td>'+E(isoUtc(n.at_utc))+'</td><td title="'+E(mid)+'">'+E(T(mid,44))+'</td><td>'+E(n.policy_id||'\\u2014')+'</td><td>'+E(side)+'</td><td>'+E(n.reason_code)+'</td><td><button type="button" class="fund-btn jw-bar-decision-view" data-decision-id="'+E(String(n.id))+'">View</button></td></tr>';}).join(''):'<tr><td colspan="6" class="muted">No TRADE_OPEN decisions yet</td></tr>';}
    var dj=document.getElementById('jw-trade-jump'); if(dj&&j.all_trades_dropdown){var cur=dj.value, opts=j.all_trades_dropdown.length?('<option value="">All trades \\u2014 pick to jump + detail ('+j.all_trades_dropdown.length+')</option>'+j.all_trades_dropdown.map(function(d){return'<option value="'+E(String(d.id))+'">'+E(d.label)+'</option>';})).join(''):'<option value="">No closed trades</option>';dj.innerHTML=opts; if(cur)try{dj.value=cur;}catch(e){}}
    var clk=document.getElementById('jw-live-clock'); if(clk)clk.textContent='Last update '+new Date().toISOString().slice(11,19)+' UTC';
    if(typeof window.jwPolicySyncVisual==='function')window.jwPolicySyncVisual();
  }
  function jwWireTrades(){var sel=document.getElementById('jw-trade-jump');var pre=document.getElementById('jw-trade-detail');document.querySelectorAll('#jw-trades-tbody tr.trade-row').forEach(function(tr){tr.onclick=function(){var id=tr.getAttribute('data-trade-id');if(!id)return;if(sel)sel.value=id;if(pre)fetch('/api/v1/sean/trade/'+id+'.json').then(function(r){return r.text();}).then(function(t){pre.textContent=t;}).catch(function(e){pre.textContent=String(e);});};});}
  function sumFetch(){return fetch('/api/summary.json').then(function(r){if(r.status===401){location.href='/auth/login';return Promise.reject();}return r.json();});}
  window.jwLiveRefresh=function(){return sumFetch().then(apply);};
  sumFetch().then(apply).catch(function(){});
  setInterval(function(){sumFetch().then(apply).catch(function(){});},POLL_MS);
})();
<\/script>`;
}

/** Display label for deployment id — raw id only (Kitchen manifest truth; no legacy marketing names). */
function jupiterPolicyOptionLabel(id) {
  return String(id || '').trim() || '—';
}

function htmlJupiterPolicySelectOptions(selectedAp) {
  const ids = loadAllowedDeploymentIdsFromManifest();
  if (ids.length === 0) {
    return '<option value="" selected>none</option>';
  }
  return ids
    .map(
      (id) =>
        `<option value="${esc(id)}"${selectedAp === id ? ' selected' : ''}>${esc(jupiterPolicyOptionLabel(id))}</option>`
    )
    .join('');
}

function htmlPage(v) {
  const readOnly = Boolean(v.read_only_except_policy);
  const useLivePoll = !['0', 'false', 'no'].includes((process.env.JUPITER_WEB_LIVE_POLL || '1').trim().toLowerCase());
  const refresh =
    !useLivePoll && v.refresh_sec > 0
      ? `<meta http-equiv="refresh" content="${esc(String(v.refresh_sec))}"/>`
      : '';
  const tm = v.trading_mode || {};
  const actual = tm.actual_banner;
  const jr = tm.jupiter_runtime || {};
  const allowed = loadAllowedDeploymentIdsFromManifest();
  const ap = jr.active_policy || allowed[0] || '';
  const src = jr.source || 'default';
  const postOk = Boolean(tm.post_token_configured);
  const policyOptionsHtml = htmlJupiterPolicySelectOptions(ap);
  const policyLabelsJson = JSON.stringify(
    Object.fromEntries(allowed.map((id) => [id, jupiterPolicyOptionLabel(id)]))
  );
  const policySel = `
    <p><strong>Assigned deployment</strong> (policy artifact bound in manifest — applies next bar; does not close or force-open positions)</p>
    <p class="muted"><strong>Engine</strong> is separate — status strip shows <code>${esc(jupiterEngineDisplayId())}</code> · Online when the execution loop is enabled. Active deployment: <code id="jw-ap-code">${esc(ap)}</code> · source <code id="jw-ap-src">${esc(src)}</code> · meta <code>${esc(JUPITER_ACTIVE_POLICY_KEY)}</code></p>
    <div id="jw-policy-control" class="jw-policy-box jw-policy-idle">
      <p class="op-row" style="margin-top:0"><label>Deployment id <select id="jw-jupiter-policy" ${postOk ? '' : 'disabled'}>${policyOptionsHtml}</select></label>
    <button type="button" id="jw-apply-policy" class="fund-btn" ${postOk ? '' : 'disabled'}>Set active deployment</button></p>
      <p id="jw-policy-status" class="jw-policy-status small"></p>
      ${
        postOk
          ? ''
          : `<p class="warn" id="jw-policy-token-warn"><strong>Deployment switch unavailable</strong> — <code>JUPITER_OPERATOR_TOKEN</code> is not set on this server. Dropdown lists manifest deployment ids; enable token and restart to apply.</p>`
      }
    </div>
    ${postOk ? `<p class="muted">Uses Bearer token in <strong>Operator token</strong> panel above. Options stay aligned with <code>GET /api/v1/jupiter/policy</code> · <code>allowed_policies</code>.</p>
    <script>
    (function(){
      var LABELS=${policyLabelsJson};
      function jwRebuildPolicySelectFromApi(j){
        var s=document.getElementById('jw-jupiter-policy');
        if(!s||!j)return;
        var allowed=Array.isArray(j.allowed_policies)?j.allowed_policies:[];
        s.innerHTML='';
        if(allowed.length===0){
          var o0=document.createElement('option');
          o0.value='';
          o0.textContent='none';
          o0.selected=true;
          s.appendChild(o0);
          return;
        }
        allowed.forEach(function(id){
          var o=document.createElement('option');
          o.value=id;
          o.textContent=LABELS[id]||id;
          s.appendChild(o);
        });
        var pick=String(j.active_policy||'').trim();
        if(pick&&allowed.indexOf(pick)>=0)s.value=pick;
        else s.value=allowed[0];
      }
      function jwPolicySyncVisual(){
        var box=document.getElementById('jw-policy-control');
        var sel=document.getElementById('jw-jupiter-policy');
        var code=document.getElementById('jw-ap-code');
        var st=document.getElementById('jw-policy-status');
        if(!box||!sel||!code)return;
        var err=box.getAttribute('data-policy-error');
        box.classList.remove('jw-policy-idle','jw-policy-active','jw-policy-error');
        if(err){
          box.classList.add('jw-policy-error');
          if(st){ st.textContent=err; }
          return;
        }
        var active=String(code.textContent||'').trim();
        var selv=String(sel.value||'').trim();
        if(!selv){
          box.classList.add('jw-policy-idle');
          if(st){ st.textContent='No deployment ids in manifest — dropdown shows none.'; }
          return;
        }
        if(active&&selv===active){
          box.classList.add('jw-policy-active');
          if(st){ st.textContent='Deployment is set and active — '+selv+' (SQLite jupiter_active_policy; engine loads evaluator on the next eligible cycle).'; }
        }else{
          box.classList.add('jw-policy-idle');
          if(st){ st.textContent='Selection not applied or differs from Active above — choose a deployment id and click Set active deployment.'; }
        }
      }
      window.jwPolicySyncVisual=jwPolicySyncVisual;
      fetch('/api/v1/jupiter/policy').then(function(r){return r.json();}).then(function(j){
        jwRebuildPolicySelectFromApi(j);
        jwPolicySyncVisual();
      }).catch(function(){ jwPolicySyncVisual(); });
      document.getElementById('jw-jupiter-policy')?.addEventListener('change',function(){
        document.getElementById('jw-policy-control')?.removeAttribute('data-policy-error');
        jwPolicySyncVisual();
      });
      document.getElementById('jw-apply-policy')?.addEventListener('click', async function(){
        var box=document.getElementById('jw-policy-control');
        var pol=String((document.getElementById('jw-jupiter-policy')||{}).value||'').trim();
        var tok=String((document.getElementById('jw-op-token')||{}).value||'').trim();
        if(!tok){
          alert('Enter the operator Bearer token in the Operator token panel (must match JUPITER_OPERATOR_TOKEN on the server).');
          return;
        }
        if(!pol){
          alert('No deployment id selected — if the dropdown shows \u201cnone\u201d, add Jupiter entries to kitchen_policy_deployment_manifest_v1.json (repo) and reload.');
          return;
        }
        if(box)box.removeAttribute('data-policy-error');
        jwPolicySyncVisual();
        var r=await fetch('/api/v1/jupiter/active-policy',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+tok},body:JSON.stringify({policy:pol})});
        var t=await r.text();
        if(!r.ok){
          var msg='Could not set policy — HTTP '+r.status+'. '+t.slice(0,220);
          if(box)box.setAttribute('data-policy-error',msg);
          jwPolicySyncVisual();
          alert(msg);
          return;
        }
        if(typeof window.jwLiveRefresh==='function')await window.jwLiveRefresh();
        else location.reload();
        jwPolicySyncVisual();
      });
    })();
    </script>` : '<p class="muted">Set <code>JUPITER_OPERATOR_TOKEN</code> on jupiter-web and restart to enable deployment changes (dropdown lists ids from <code>kitchen_policy_deployment_manifest_v1</code>).</p>'}`;
  const tradingBlock = actual
    ? `<p class="warn"><strong>ACTUAL</strong> — Live-capital intent. Deploy with PAPER_TRADING=0 when leaving paper; this banner does not change Docker.</p>
      ${policySel}
      <p class="muted small"><strong>Deployment id</strong> selects which manifest-bound policy artifact runs — not the engine (<code>${esc(jupiterEngineDisplayId())}</code>). Not the BlackBox <code>policy_registry.json</code> strategy line.</p>
      ${
        readOnly
          ? '<p class="muted small">Read-only API: wallet/funding POSTs are off. Other apps may <strong>set active Jupiter policy</strong> via <code>POST /api/v1/jupiter/active-policy</code> (Bearer).</p>'
          : ''
      }`
    : `<p><strong>PAPER</strong> — Simulated ledger (default). SEANV3_TUI_ACTUAL=1 for live-intent banner.</p>
      ${policySel}
      <p class="muted small"><strong>Deployment id</strong> — manifest-bound artifact only. Ignores BlackBox registry “strategy entry” elsewhere.</p>
      ${
        readOnly
          ? '<p class="muted small">Read-only API: wallet/funding POSTs are off. Other apps may <strong>set active Jupiter policy</strong> via <code>POST /api/v1/jupiter/active-policy</code> (Bearer).</p>'
          : ''
      }`;

  const w = v.wallet;
  const keypairEnv = v.paper_ledger?.keypair_env || v.keypair_env || '';
  const pl = v.paper_ledger;

  const op = v.operator || {};
  const gate = op.next_open_gate || {};
  const gOk = gate.ok === true;
  const pq = op.paper_equity_usd || {};
  const modeCur = String(op.sean_funding_mode || 'paper').trim();
  const stakeNum =
    pq.starting_usd != null && Number.isFinite(Number(pq.starting_usd)) ? Number(pq.starting_usd) : 1000;
  const pkPref = w?.pubkey_base58 ? String(w.pubkey_base58) : '';
  const eqStr =
    pq.equity_usd != null && typeof pq.equity_usd === 'number' && Number.isFinite(pq.equity_usd)
      ? pq.equity_usd.toFixed(4)
      : '—';
  const opPostOk = Boolean(op.operator_controls?.post_token_configured);
  const stakeOk = Boolean(op.operator_controls?.paper_stake_edit_allowed);
  const paperModeOn = modeCur === 'paper';
  const chainModeOn = modeCur === 'chain' || modeCur === 'live';

  let walletFundingBlock = '<p class="muted">Operator state unavailable.</p>';
  if (!op.error) {
    if (readOnly) {
      walletFundingBlock = `
      <p class="warn"><strong>Read-only HTTP API</strong> — <code>JUPITER_WEB_READ_ONLY=1</code>. Wallet, funding mode, and paper stake cannot be changed via <code>POST /api/operator/*</code>. Use <code>KEYPAIR_PATH</code> on <strong>seanv3</strong> or SQLite for wallet state, or set <code>JUPITER_WEB_READ_ONLY=0</code> to re-enable dashboard writes.</p>
      <p class="muted"><strong>Paper wallet</strong> — <strong>Equity = bankroll + realized PnL + unrealized</strong>.</p>
      <p><strong>Paper PnL (live)</strong> — equity ~<strong id="jw-wallet-eq-val">${esc(eqStr)}</strong> USD
        <span class="muted" id="jw-wallet-eq-brk">= bankroll ${esc(String(pq.starting_usd ?? '—'))} + realized ${esc(String(pq.realized_pnl_usd ?? '—'))} + unreal ${esc(String(pq.unrealized_usd ?? '—'))}</span>
        ${pl ? ` · closed: ${esc(String(pl.closed_trade_count))}` : ''}</p>
      ${pl?.open_line ? `<p class="muted" id="jw-wallet-openline">${esc(pl.open_line)}</p>` : ''}
      <p class="muted">Stored funding mode: <code>${esc(modeCur)}</code> · PAPER_TRADING: ${
        op.paper_trading_env ? `<span class="ok">on</span>` : `<span class="warn">off</span>`
      }</p>
      ${
        w?.pubkey_base58
          ? `<p class="ok">Pubkey in DB — <code>${esc(w.pubkey_base58)}</code> · ${esc(v.wallet_status || '—')}</p>`
          : `<p class="warn">No pubkey in DB — use <code>KEYPAIR_PATH</code> on seanv3 or temporarily set <code>JUPITER_WEB_READ_ONLY=0</code> to register via UI.</p>`
      }
      <p class="muted small"><strong>Set active deployment (sole write):</strong> <code>POST /api/v1/jupiter/active-policy</code> · <code>Authorization: Bearer &lt;token&gt;</code> · body <code>{"policy":"&lt;deployed_runtime_policy_id&gt;"}</code> where the id is listed under Jupiter in <code>kitchen_policy_deployment_manifest_v1.json</code>. Alias: <code>/api/v1/jupiter/set-policy</code>.</p>`;
    } else {
      walletFundingBlock = `
      <p class="muted"><strong>Paper wallet</strong> — <strong>Equity = bankroll + realized PnL + unrealized</strong> (same numbers the engine uses). Raising “Add paper funds” increases <strong>bankroll</strong> immediately after save + reload. <strong>Chain wallet</strong> switches the gate to cached SOL; live fills still need <code>PAPER_TRADING=0</code> on seanv3 + restart.</p>
      <p><strong>Paper PnL (live)</strong> — equity ~<strong id="jw-wallet-eq-val">${esc(eqStr)}</strong> USD
        <span class="muted" id="jw-wallet-eq-brk">= bankroll ${esc(String(pq.starting_usd ?? '—'))} + realized ${esc(String(pq.realized_pnl_usd ?? '—'))} + unreal ${esc(String(pq.unrealized_usd ?? '—'))}</span>
        ${pl ? ` · closed: ${esc(String(pl.closed_trade_count))}` : ''}</p>
      ${pl?.open_line ? `<p class="muted" id="jw-wallet-openline">${esc(pl.open_line)}</p>` : ''}
      <div class="fund-toggle" role="group" aria-label="Paper vs chain funding gate">
        <button type="button" class="fund-btn ${paperModeOn ? 'selected' : ''}" id="jw-fund-paper">Paper wallet (simulated)</button>
        <button type="button" class="fund-btn ${chainModeOn ? 'selected' : ''}" id="jw-fund-chain">Chain wallet (live balance)</button>
      </div>
      <p class="muted small">Stored mode: <code>${esc(modeCur)}</code> · PAPER_TRADING: ${
        op.paper_trading_env ? `<span class="ok">on</span> (paper path)` : `<span class="warn">off</span>`
      }</p>
      ${
        w?.pubkey_base58
          ? `<p class="ok">Pubkey registered — <code>${esc(w.pubkey_base58)}</code> · ${esc(v.wallet_status || '—')}</p>`
          : `<p class="bad"><strong>Register a pubkey below</strong> to clear <code>wallet_not_connected</code> (no KEYPAIR file required).</p>`
      }
      ${
        opPostOk
          ? `<div class="op-box">
        <p class="op-row"><label>Solana pubkey <input type="text" id="jw-pubkey" size="52" value="${esc(pkPref)}" placeholder="base58" spellcheck="false" autocomplete="off"/></label>
          <button type="button" id="jw-save-wallet">Register pubkey</button></p>
        ${
          stakeOk
            ? `<p class="op-row"><label>Add paper funds (USD bankroll) <input type="number" step="0.01" min="0" id="jw-stake" size="16" value="${esc(String(stakeNum))}"/></label>
          <button type="button" class="fund-btn" id="jw-save-stake">Apply to bankroll &amp; PnL</button></p>
          <p class="muted small">Writes <code>paper_starting_balance_usd</code> in SQLite — no manual DB edit. Page reload refreshes equity everywhere below.</p>`
            : '<p class="muted">Paper bankroll edit disabled on server (SEAN_ALLOW_PAPER_STAKE_EDIT).</p>'
        }
      </div>
      <script>
      (function(){
        function tok(){ return (document.getElementById('jw-op-token')||{}).value||''; }
        async function postMode(mode){
          const r = await fetch('/api/operator/funding-mode', { method:'POST', headers:{'Authorization':'Bearer '+tok(),'Content-Type':'application/json'}, body: JSON.stringify({mode}) });
          alert(r.ok ? await r.text() : 'HTTP '+r.status+' '+await r.text());
          if(r.ok){ if(typeof window.jwLiveRefresh==='function') window.jwLiveRefresh(); else location.reload(); }
        }
        document.getElementById('jw-fund-paper')?.addEventListener('click', function(){ postMode('paper'); });
        document.getElementById('jw-fund-chain')?.addEventListener('click', function(){ postMode('chain'); });
        document.getElementById('jw-save-wallet')?.addEventListener('click', async function(){
          const pubkey_base58 = (document.getElementById('jw-pubkey')||{}).value||'';
          const r = await fetch('/api/operator/paper-wallet', { method:'POST', headers:{'Authorization':'Bearer '+tok(),'Content-Type':'application/json'}, body: JSON.stringify({pubkey_base58}) });
          alert(r.ok ? await r.text() : 'HTTP '+r.status+' '+await r.text());
          if(r.ok){ if(typeof window.jwLiveRefresh==='function') window.jwLiveRefresh(); else location.reload(); }
        });
        document.getElementById('jw-save-stake')?.addEventListener('click', async function(){
          const usd = parseFloat((document.getElementById('jw-stake')||{}).value||'');
          const r = await fetch('/api/operator/paper-stake', { method:'POST', headers:{'Authorization':'Bearer '+tok(),'Content-Type':'application/json'}, body: JSON.stringify({usd}) });
          alert(r.ok ? await r.text() : 'HTTP '+r.status+' '+await r.text());
          if(r.ok){ if(typeof window.jwLiveRefresh==='function') window.jwLiveRefresh(); else location.reload(); }
        });
      })();
      </script>`
          : `<p class="warn">Set <code>JUPITER_OPERATOR_TOKEN</code> on jupiter-web to enable Register / stake / Paper↔Chain.</p>`
      }`;
    }
  } else {
    walletFundingBlock = `<p class="warn">${esc(op.error)}</p>`;
  }

  let walletBlock = '';
  if (w?.pubkey_base58) {
    walletBlock = `<p class="muted">Pubkey also listed in <strong>Wallet &amp; funding</strong> above.</p>`;
  } else {
    walletBlock = readOnly
      ? `<p class="warn">No pubkey in DB — see <strong>Wallet &amp; funding</strong> for options (<code>KEYPAIR_PATH</code> or disable read-only).</p>`
      : `<p class="warn">No pubkey — complete <strong>Wallet &amp; funding</strong> above.</p>`;
    if (keypairEnv) {
      walletBlock += `<p class="muted">Optional file path on seanv3: <code>${esc(keypairEnv)}</code></p>`;
    }
  }

  let ledgerBlock =
    '<div id="jw-ledger-block"><p class="muted">—</p></div>';
  if (pl) {
    ledgerBlock = `<div id="jw-ledger-block"><p><strong>Paper ledger</strong> — starting ${esc(String(pl.starting_balance_usd))} USD · realized ${esc(String(pl.realized_pnl_usd))} · equity ~${esc(String(pl.equity_est_usd?.toFixed ? pl.equity_est_usd.toFixed(4) : pl.equity_est_usd))} USD</p>
      <p class="muted">Same figures as <strong>Wallet &amp; funding</strong>; trade list below.</p></div>`;
  }

  let parityRows = '';
  if (v.parity?.error && !v.parity.rows?.length) {
    parityRows = `<tr><td colspan="4" class="muted">${esc(v.parity.error)}</td></tr>`;
  } else if (!v.parity?.rows?.length) {
    parityRows = `<tr><td colspan="4" class="muted">No parity rows yet (need trades with market_event_id + optional execution_ledger.db).</td></tr>`;
  } else {
    parityRows = v.parity.rows
      .map((r) => {
        const pc = r.parity_cls === 'ok' ? 'p-ok' : r.parity_cls === 'warn' ? 'p-warn' : r.parity_cls === 'bad' ? 'p-bad' : 'p-dim';
        return `<tr><td>${esc(truncateMid(r.market_event_id, 44))}</td><td>${esc(r.sean_cell)}</td><td>${esc(r.bb_cell)}</td><td class="${pc}">${esc(r.parity)}</td></tr>`;
      })
      .join('');
  }

  const pf = v.preflight || {};
  const o = pf.oracle;
  const chkRows = (pf.checks || [])
    .map((c) => {
      const st = c.ok ? '<span class="ok">OK</span>' : '<span class="bad">FAIL</span>';
      return `<tr><td>${esc(c.name)}</td><td>${st}</td><td>${esc(c.detail)}</td></tr>`;
    })
    .join('');
  const banner = pf.degraded
    ? '<p class="bad"><strong>DEGRADED</strong> — fix failing checks before relying on runtime.</p>'
    : '<p class="ok"><strong>ALL ACTIVE</strong> — checks passing</p>';

  let oracleBlock = '<p class="muted">No Hermes parsed payload yet.</p>';
  if (o) {
    const rel = o.price ? (o.conf / o.price) * 100 : 0;
    const wa = pf.wall_age_s != null ? `wall age ~${pf.wall_age_s.toFixed(1)}s` : '';
    oracleBlock = `<p><strong>SOL/USD</strong> ${esc(o.price.toFixed(4))} USD</p>
      <p class="muted">Confidence ±${esc(o.conf.toFixed(6))} (${esc(rel.toFixed(4))}% of price)</p>
      <p class="muted">Publish unix: ${esc(String(o.publish_time))} ${wa}</p>
      <p class="muted">Feed: ${esc(truncateMid(o.feed_id, 20))}</p>`;
  }

  const trades = v.recent_trades || [];
  const drop = v.all_trades_dropdown || [];
  const tradeJumpOpts = drop.length
    ? `<option value="">All trades — pick to jump + detail (${drop.length})</option>${drop
        .map((d) => `<option value="${esc(String(d.id))}">${esc(d.label)}</option>`)
        .join('')}`
    : '<option value="">No closed trades</option>';
  const trCls = (rc) => {
    const s = String(rc || '').toLowerCase();
    if (s === 'win') return 'trade-win';
    if (s === 'loss') return 'trade-loss';
    return 'trade-flat';
  };
  const tradeRows = trades.length
    ? trades
        .map(
          (t) =>
            `<tr class="trade-row ${trCls(t.result_class)}" data-trade-id="${esc(String(t.id))}"><td>${esc(t.trade_id)}</td><td>${esc(formatIsoUtcShort(t.exit_time_utc))}</td><td>${esc(formatIsoUtcShort(t.entry_time_utc))}</td><td>${esc(t.symbol)}</td><td>${esc(t.side)}</td><td>${esc(t.entry_price)}</td><td>${esc(t.exit_price)}</td><td>${esc(t.size_notional_sol)}</td><td>${esc(t.gross_pnl_usd)}</td><td>${esc(t.result_class)}</td><td>${esc(t.exit_reason)}</td><td>${esc(truncateMid(t.entry_market_event_id, 40))}</td><td>${esc(truncateMid(t.exit_market_event_id, 40))}</td></tr>`
        )
        .join('')
    : '<tr><td colspan="13" class="muted">No closed trades yet</td></tr>';

  const noTrades = v.recent_no_trades || [];
  const ntCls = (rc) => {
    const s = String(rc || '').toLowerCase();
    if (s === 'open_blocked' || s === 'funding_gate_blocked') return 'nt-blocked';
    if (s === 'no_atr' || s === 'atr_invalid') return 'nt-warn';
    if (s === 'no_entry_signal' || s === 'no_candidate_side') return 'nt-signal';
    return 'nt-dim';
  };
  const noTradeRows = noTrades.length
    ? noTrades
        .map((n) => {
          const mid = n.market_event_id != null ? String(n.market_event_id) : '';
          return `<tr class="${ntCls(n.reason_code)}"><td>${esc(formatIsoUtcShort(n.at_utc))}</td><td title="${esc(mid)}">${esc(truncateMid(mid, 44))}</td><td>${esc(n.policy_id || '—')}</td><td>${esc(n.reason_code)}</td><td><button type="button" class="fund-btn jw-bar-decision-view" data-decision-id="${esc(String(n.id))}">View</button></td></tr>`;
        })
        .join('')
    : '<tr><td colspan="5" class="muted">No NO_TRADE decisions yet</td></tr>';

  const tradeOpens = v.recent_trade_opens || [];
  const toCls = () => 'to-open';
  const tradeOpenRows = tradeOpens.length
    ? tradeOpens
        .map((n) => {
          const mid = n.market_event_id != null ? String(n.market_event_id) : '';
          const side = n.candidate_side != null ? String(n.candidate_side) : '—';
          return `<tr class="${toCls()}"><td>${esc(formatIsoUtcShort(n.at_utc))}</td><td title="${esc(mid)}">${esc(truncateMid(mid, 44))}</td><td>${esc(n.policy_id || '—')}</td><td>${esc(side)}</td><td>${esc(n.reason_code)}</td><td><button type="button" class="fund-btn jw-bar-decision-view" data-decision-id="${esc(String(n.id))}">View</button></td></tr>`;
        })
        .join('')
    : '<tr><td colspan="6" class="muted">No TRADE_OPEN decisions yet</td></tr>';

  const kl = v.last_kline;
  const klBlock = kl
    ? `<p class="muted">Last kline poll: ${esc(kl.market_event_id)} · close ${esc(kl.close_px)} · ${esc(kl.polled_at_utc)}</p>`
    : '';

  const pos = v.position;
  const posBlock =
    pos && String(pos.side) !== 'flat'
      ? `<p><strong>Open</strong> ${esc(pos.side)} @ ${esc(pos.entry_price)} · mid ${esc(pos.entry_market_event_id)}</p>`
      : '<p class="muted">Position: flat</p>';

  const liveStrip = (() => {
    const kc = kl?.close_px != null ? esc(kl.close_px) : '—';
    const hp = o?.price != null ? esc(o.price.toFixed(4)) : '—';
    return `<p><strong>Binance kline close</strong> ${kc} · <strong>Hermes SOL/USD</strong> ${hp} · <strong>poll</strong> ${esc(kl?.polled_at_utc || '—')}</p>`;
  })();

  let operatorBlock = '<p class="muted">Operator state unavailable.</p>';
  if (!op.error) {
    const operatorDetailsOnly = `
      <p><strong>Funding mode (SQLite)</strong> <code>${esc(op.sean_funding_mode || 'paper')}</code>
        · PAPER_TRADING env: ${
          op.paper_trading_env
            ? `<span class="ok">on (simulated)</span>`
            : `<span class="warn">off</span> (compose uses live path for chain gate)`
        }</p>
      <p><strong>Paper equity</strong> ~<span id="jw-op-eq-val">${esc(eqStr)}</span> USD
        <span class="muted" id="jw-op-eq-brk">(start ${esc(String(pq.starting_usd ?? '—'))} + realized ${esc(String(pq.realized_pnl_usd ?? '—'))} + unreal ${esc(String(pq.unrealized_usd ?? '—'))})</span></p>
      <p><strong>On-chain SOL</strong> (cached) <span id="jw-chain-lam">${esc(op.chain_sol_balance_lamports || '—')}</span> lamports
        <span class="muted" id="jw-chain-at">${esc(op.chain_balance_updated_utc || '')}</span></p>
      ${op.chain_balance_error ? `<p class="bad" id="jw-chain-err">${esc(op.chain_balance_error)}</p>` : ''}
      <p id="jw-gate-line"><strong>Next engine open</strong> ${gOk ? '<span class="ok">allowed</span>' : '<span class="bad">blocked</span>'} — ${esc(gate.reason || '—')}
        <span class="muted">${esc(gate.detail || '')}</span></p>
      <p class="muted">Controls: <strong>Wallet &amp; funding</strong> panel (above this section).</p>`;
    operatorBlock = `<div id="jw-live-strip">${liveStrip}</div><div id="jw-operator-details">${operatorDetailsOnly}</div>`;
  } else {
    operatorBlock = `<p class="warn">${esc(op.error)}</p>`;
  }

  const opTokEnv = (process.env.JUPITER_OPERATOR_TOKEN || '').trim();
  const prefillBearer =
    ['1', 'true', 'yes'].includes((process.env.JUPITER_WEB_PREFILL_BEARER || '').trim().toLowerCase()) && opTokEnv
      ? opTokEnv
      : '';
  const bearerInputType = prefillBearer ? 'text' : 'password';
  const tokenPanel = postOk
    ? `<section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-token"><span class="jw-caret" aria-hidden="true">▶</span> Operator token</button></h2>
      <div class="jw-panel-body" id="jw-pan-token" hidden>
      <p class="muted">Same secret as <code>JUPITER_OPERATOR_TOKEN</code> on jupiter-web (see <code>lab_operator_token.env</code> in this stack). ${
        readOnly
          ? '<strong>Read-only mode:</strong> use Bearer only for <strong>Set active deployment</strong> below — wallet/funding POSTs are disabled.'
          : 'Used for policy switch, paper wallet, funding mode, and paper stake'
      } — <em>not</em> your Solana wallet.</p>
      <p><label>Bearer <input type="${bearerInputType}" id="jw-op-token" size="44" value="${esc(prefillBearer)}" autocomplete="off" spellcheck="false"/></label></p>
      ${
        prefillBearer
          ? '<p class="muted small">Prefilled while <code>JUPITER_WEB_PREFILL_BEARER=1</code>. Set to <code>0</code> in <code>lab_operator_token.env</code> to hide.</p>'
          : ''
      }
    </div></section>`
    : `<section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-token"><span class="jw-caret" aria-hidden="true">▶</span> Operator token</button></h2>
      <div class="jw-panel-body" id="jw-pan-token" hidden>
      <p class="warn">POST actions are off until you set <code>JUPITER_OPERATOR_TOKEN</code> on jupiter-web and restart the container.</p>
    </div></section>`;

  const sessionChrome = jupiterAuthMode() === 'session';
  const statusStripMarkup = statusStripHtml(computeStatusStrip(v), sessionChrome);

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  ${refresh}
  <title>Jupiter — TUI parity</title>
  <style>
    * { box-sizing: border-box; }
    :root { --jw-text-scale: 1; }
    html { font-size: calc(16px * var(--jw-text-scale)); }
    body { font-family: ui-monospace, Menlo, Consolas, monospace; background: #0c0c0c; color: #e6edf3; margin: 0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 1rem; position: relative; isolation: isolate; }
    body::before {
      content: '';
      position: fixed;
      inset: 0;
      z-index: 0;
      background: url(/static/jupiter_front_door.png) center center / cover no-repeat;
      opacity: 0.15;
      pointer-events: none;
    }
    .wrap { width: 100%; max-width: 120ch; position: relative; z-index: 1; }
    .panel { border: 1px solid #3d3d3d; border-radius: 2px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; background: #121212; }
    .panel h2.jw-panel-head {
      font-family: ui-monospace, Menlo, Consolas, monospace;
      font-size: 0.7rem;
      font-weight: 600;
      line-height: 1.3;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #8b949e;
      margin: 0 0 0.5rem 0;
      border-bottom: 1px solid #30363d;
      padding-bottom: 0.35rem;
    }
    .jw-panel-toggle {
      all: unset;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      cursor: pointer;
      width: 100%;
      box-sizing: border-box;
      font-family: ui-monospace, Menlo, Consolas, monospace;
      font-size: 0.7rem;
      font-weight: 600;
      line-height: 1.3;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #8b949e;
    }
    .jw-panel-toggle:hover { color: #c9d1d9; }
    .jw-caret {
      display: inline-block;
      min-width: 1em;
      text-align: center;
      color: #58a6ff;
      font-family: ui-monospace, Menlo, Consolas, monospace;
      font-size: 0.7rem;
      font-weight: 600;
      line-height: 1.3;
    }
    .jw-policy-box { border-radius: 4px; padding: 0.5rem 0.65rem; margin: 0.35rem 0; border: 1px solid #30363d; transition: background 0.15s, border-color 0.15s; }
    .jw-policy-idle { background: #f6f8fa; color: #0d1117; border-color: #d0d7de; }
    .jw-policy-idle select, .jw-policy-idle .fund-btn { background: #ffffff; color: #0d1117; border-color: #d0d7de; }
    .jw-policy-idle .jw-policy-status { color: #57606a; }
    .jw-policy-active { background: rgba(88, 166, 255, 0.22); border-color: rgba(88, 166, 255, 0.55); color: #e6edf3; }
    .jw-policy-active select, .jw-policy-active .fund-btn { background: rgba(200, 230, 255, 0.95); color: #0d1117; border-color: #58a6ff; }
    .jw-policy-active .jw-policy-status { color: #c9d1d9; }
    .jw-policy-error { background: rgba(248, 81, 73, 0.18); border-color: rgba(248, 81, 73, 0.55); }
    .jw-policy-error select, .jw-policy-error .fund-btn { background: #ffeef0; color: #0d1117; border-color: #f85149; }
    .jw-policy-error .jw-policy-status { color: #ffb1ab; }
    .jw-policy-status { margin: 0.35rem 0 0 0; }
    h1 { font-size: 1.1rem; margin: 0 0 0.35rem 0; }
    code { background: #1e1e1e; padding: 0.1rem 0.35rem; border: 1px solid #333; }
    table { border-collapse: collapse; width: 100%; font-size: 0.72rem; }
    th, td { border: 1px solid #30363d; padding: 0.3rem 0.4rem; text-align: left; vertical-align: top; }
    th { background: #161b22; }
    .muted { color: #8b949e; font-size: 0.85rem; }
    .warn { color: #d29922; }
    .ok { color: #3fb950; }
    .bad { color: #f85149; }
    .p-ok { color: #3fb950; font-weight: 600; }
    .p-warn { color: #d29922; font-weight: 600; }
    .p-bad { color: #f85149; font-weight: 600; }
    .p-dim { color: #8b949e; }
    a { color: #58a6ff; }
    .scroll { overflow-x: auto; }
    p { margin: 0.35rem 0; }
    .op-box { border: 1px dashed #30363d; padding: 0.6rem 0.75rem; margin-top: 0.5rem; border-radius: 2px; background: #0e0e10; }
    .op-row { margin: 0.45rem 0; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
    .small { font-size: 0.78rem; }
    .fund-toggle { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.65rem 0; }
    .fund-btn { font: inherit; padding: 0.4rem 0.85rem; border-radius: 2px; border: 1px solid #30363d; background: #1a1a1c; color: #e6edf3; cursor: pointer; }
    .fund-btn:hover { border-color: #58a6ff; }
    .fund-btn.selected { border-color: #3fb950; background: rgba(63, 185, 80, 0.12); }
    .pubkey-banner { font-size: 0.85rem; padding: 0.5rem 0.65rem; border-radius: 2px; border: 1px solid #30363d; background: #0d1117; margin-top: 0.5rem; word-break: break-all; }
    .pubkey-banner code { font-size: 0.8rem; }
    .trade-row { cursor: pointer; }
    .trade-win { background: rgba(63, 185, 80, 0.14); }
    .trade-loss { background: rgba(248, 81, 73, 0.1); }
    .trade-flat { background: transparent; }
    .nt-blocked { background: rgba(248, 81, 73, 0.08); }
    .nt-warn { background: rgba(210, 153, 34, 0.1); }
    .nt-signal { background: rgba(139, 148, 158, 0.08); }
    .nt-dim { background: transparent; }
    #jw-no-trade-scroll { max-height: min(40vh, 28rem); overflow-y: auto; overflow-x: auto; }
    #jw-no-trade-scroll thead th { position: sticky; top: 0; z-index: 1; }
    .to-open { background: rgba(88, 166, 255, 0.1); }
    #jw-trade-open-scroll { max-height: min(40vh, 28rem); overflow-y: auto; overflow-x: auto; }
    #jw-trade-open-scroll thead th { position: sticky; top: 0; z-index: 1; }
    .jw-nt-drawer-backdrop { position: fixed; inset: 0; z-index: 2000; background: rgba(5, 5, 8, 0.72); display: none; align-items: stretch; justify-content: flex-end; }
    .jw-nt-drawer-backdrop.jw-nt-open { display: flex; }
    .jw-nt-drawer { width: min(42rem, 96vw); max-width: 100%; background: #121212; border-left: 1px solid #30363d; overflow-y: auto; box-sizing: border-box; padding: 0.75rem 1rem 1.25rem; box-shadow: -4px 0 24px rgba(0,0,0,0.45); }
    .jw-nt-drawer-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.75rem; border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; }
    .jw-nt-drawer-head h3 { margin: 0; font-size: 0.95rem; font-weight: 600; }
    .jw-nt-h4 { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #8b949e; margin: 0.85rem 0 0.35rem 0; }
    .jw-nt-dl { margin: 0; display: grid; grid-template-columns: 11rem 1fr; gap: 0.25rem 0.75rem; font-size: 0.78rem; }
    .jw-nt-dl dt { color: #8b949e; margin: 0; }
    .jw-nt-dl dd { margin: 0; word-break: break-word; }
    .jw-nt-kv { width: 100%; font-size: 0.72rem; margin: 0.25rem 0 0.5rem 0; }
    .jw-nt-kv th { background: #161b22; }
    .jw-nt-pre { margin: 0.35rem 0 0 0; padding: 0.5rem 0.6rem; background: #0a0a0b; border: 1px solid #30363d; border-radius: 2px; font-size: 0.68rem; line-height: 1.35; white-space: pre-wrap; word-break: break-word; max-height: 40vh; overflow: auto; }
    a.csv-btn { display: inline-block; padding: 0.25rem 0.6rem; border: 1px solid #30363d; border-radius: 2px; color: #58a6ff; text-decoration: none; font-size: 0.85rem; }
    a.csv-btn:hover { background: #1f2428; }
    .trade-snap-h { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #8b949e; margin: 0.75rem 0 0.35rem 0; }
    pre.trade-detail { margin: 0; max-height: 42vh; overflow: auto; font-size: 0.68rem; line-height: 1.35; white-space: pre-wrap; word-break: break-word; background: #0a0a0b; border: 1px solid #30363d; padding: 0.5rem 0.6rem; border-radius: 2px; }
    #jw-live-strip.jw-pulse { outline: 1px solid rgba(88, 166, 255, 0.25); border-radius: 2px; }
    .jw-status-strip { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.35rem 0.9rem; width: 100%; max-width: 120ch; padding: 0.45rem 0.65rem; padding-right: 3.5rem; margin: 0 auto 0.65rem auto; border: 1px solid #30363d; border-radius: 2px; background: #161b22; font-size: 0.7rem; line-height: 1.35; box-sizing: border-box; z-index: 2; position: relative; }
    .jw-status-strip--session { padding-left: 3.5rem; }
    .jw-st-item { display: inline-flex; flex-wrap: nowrap; align-items: baseline; gap: 0.35rem; }
    .jw-st-k { color: #8b949e; font-size: 0.62rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }
    .jw-st-v { font-weight: 600; white-space: nowrap; }
    .jw-st-sub { font-weight: 500; color: #8b949e; font-size: 0.68rem; }
    .jw-st-deployment { color: #79c0ff; }
    .jw-st-engine-on { color: #79c0ff; }
    .jw-st-ok { color: #3fb950; }
    .jw-st-warn { color: #d29922; }
    .jw-st-bad { color: #f85149; }
    .jw-st-muted { color: #8b949e; }
    .jw-text-scale-float {
      position: fixed;
      top: max(8px, env(safe-area-inset-top, 0px));
      right: max(8px, env(safe-area-inset-right, 0px));
      z-index: 1500;
      display: flex;
      flex-direction: column;
      gap: 3px;
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      font-size: 11px;
      line-height: 1;
      pointer-events: auto;
    }
    .jw-logout-float {
      position: fixed;
      top: max(8px, env(safe-area-inset-top, 0px));
      left: max(8px, env(safe-area-inset-left, 0px));
      z-index: 1500;
      display: flex;
      flex-direction: column;
      gap: 3px;
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      font-size: 11px;
      line-height: 1;
      pointer-events: auto;
    }
    .jw-chrome-float-btn {
      all: unset;
      box-sizing: border-box;
      display: flex;
      align-items: center;
      justify-content: center;
      min-width: 34px;
      min-height: 26px;
      padding: 2px 8px;
      border: 1px solid #30363d;
      border-radius: 3px;
      background: rgba(22, 27, 34, 0.94);
      color: #c9d1d9;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: -0.02em;
      cursor: pointer;
      box-shadow: 0 1px 6px rgba(0, 0, 0, 0.45);
      white-space: nowrap;
      text-decoration: none;
    }
    a.jw-chrome-float-btn { cursor: pointer; }
    .jw-chrome-float-btn:hover { border-color: #58a6ff; color: #f0f6fc; }
    .jw-chrome-float-btn:focus-visible { outline: 2px solid #58a6ff; outline-offset: 2px; }
    .jw-chrome-float-btn:active { transform: scale(0.97); }
  </style>
  <script>
  (function(){
    try {
      var KEY = 'jw_dashboard_text_scale_v1';
      var STEPS = [0.8, 0.85, 0.9, 0.95, 1, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4];
      var raw = parseFloat(localStorage.getItem(KEY) || '1');
      if (!isFinite(raw)) raw = 1;
      var best = STEPS[0], bestDiff = 999;
      for (var i = 0; i < STEPS.length; i++) {
        var d = Math.abs(STEPS[i] - raw);
        if (d < bestDiff) { bestDiff = d; best = STEPS[i]; }
      }
      document.documentElement.style.setProperty('--jw-text-scale', String(best));
    } catch (e) { /* */ }
  })();
  </script>
</head>
<body>
  ${statusStripMarkup}
  ${
    sessionChrome
      ? `<div id="jw-logout-float" class="jw-logout-float" role="navigation" aria-label="Session"><a href="/auth/logout" class="jw-chrome-float-btn">Log out</a></div>`
      : ''
  }
  <div class="wrap">
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-wallet-fund"><span class="jw-caret" aria-hidden="true">▶</span> Wallet &amp; funding</button></h2><div class="jw-panel-body" id="jw-pan-wallet-fund" hidden>${walletFundingBlock}</div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="true" aria-controls="jw-pan-trades"><span class="jw-caret" aria-hidden="true">▼</span> Trade window (Sean paper trades)</button></h2><div class="jw-panel-body" id="jw-pan-trades">
      <p class="op-row">
        <label>Jump to trade <select id="jw-trade-jump">${tradeJumpOpts}</select></label>
        <a class="csv-btn" href="/api/v1/sean/trades.csv">Download all trades (CSV)</a>
      </p>
      <p class="muted small">Winning trades are tinted light green. This CSV is the <strong>lifecycle / closed-trade</strong> table (<code>sean_paper_trades</code>) — not the bar <code>decision_ledger</code>. For open-decision rows at the bar, use <strong>TRADE_OPEN decision log</strong> + <code>/api/v1/sean/trade-open-decisions.csv</code>.</p>
      <p class="muted small">CSV includes standard columns plus full <code>metadata_json</code> (entry <code>signal</code> + exit snapshot for closes written with the current engine). BlackBox baseline trade synthesis tiles use a different pipeline.</p>
      <p class="muted small jw-panel-sync-hint">Time sync: same <code>/api/summary.json</code> poll as the live strip (${esc(String(v.refresh_sec || 0))}s). This panel: <strong>closed</strong> paper trades only (<code>sean_paper_trades</code>).</p>
      <div class="scroll" id="jw-trades-scroll"><table><thead><tr><th>trade_id</th><th>exit UTC</th><th>entry UTC</th><th>sym</th><th>side</th><th>entry px</th><th>exit px</th><th>size</th><th>PnL</th><th>result</th><th>exit</th><th>entry MEI</th><th>exit MEI</th></tr></thead><tbody id="jw-trades-tbody">${tradeRows}</tbody></table></div>
      <h3 class="trade-snap-h">Trade snapshot (JSON)</h3>
      <pre id="jw-trade-detail" class="trade-detail">Select a trade from the dropdown, or click a row.</pre>
      <script>
      (function(){
        var pre = document.getElementById('jw-trade-detail');
        var sel = document.getElementById('jw-trade-jump');
        function loadDetail(id) {
          if (!pre || !id) return;
          fetch('/api/v1/sean/trade/'+id+'.json').then(function(r){ return r.text(); }).then(function(t){ pre.textContent = t; }).catch(function(e){ pre.textContent = String(e); });
        }
        if (sel) sel.addEventListener('change', function(){
          var id = this.value;
          if (!id) { if (pre) pre.textContent = 'Select a trade from the dropdown, or click a row.'; return; }
          var row = document.querySelector('tr[data-trade-id="'+id+'"]');
          if (row) row.scrollIntoView({ behavior:'smooth', block:'center' });
          loadDetail(id);
        });
        document.querySelectorAll('tr.trade-row').forEach(function(tr){
          tr.addEventListener('click', function(){
            var id = this.getAttribute('data-trade-id');
            if (!id) return;
            if (sel) sel.value = id;
            loadDetail(id);
          });
        });
      })();
      </script>
    </div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="true" aria-controls="jw-pan-no-trade"><span class="jw-caret" aria-hidden="true">▼</span> NO_TRADE decision log (flat bar, no open)</button></h2><div class="jw-panel-body" id="jw-pan-no-trade">
      <p class="op-row" style="margin-top:0;flex-wrap:wrap;align-items:center">
        <a class="csv-btn" href="/api/v1/sean/no-trade-decisions.csv">Export NO_TRADE decisions (CSV)</a>
        <span class="muted small">Same rows as this table — full <code>indicator_values_json</code>, <code>gate_results_json</code>, <code>features_json</code> for analysis.</span>
      </p>
      <p class="muted small jw-panel-sync-hint">Time sync: same <code>/api/summary.json</code> poll as the live strip (${esc(String(v.refresh_sec || 0))}s). Source: <code>sean_bar_decisions</code> where <code>outcome = NO_TRADE</code>.</p>
      <p class="muted small">Click <strong>View</strong> for full indicators, gates, and raw diagnostics (loaded from the ledger row, not the summary poll).</p>
      <div class="scroll" id="jw-no-trade-scroll"><table><thead><tr><th>Time (UTC)</th><th>market_event_id</th><th>policy</th><th>reason</th><th></th></tr></thead><tbody id="jw-no-trade-tbody">${noTradeRows}</tbody></table></div>
    </div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-wallet-st"><span class="jw-caret" aria-hidden="true">▶</span> Wallet status</button></h2><div class="jw-panel-body" id="jw-pan-wallet-st" hidden>${walletBlock}</div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-trading"><span class="jw-caret" aria-hidden="true">▶</span> Policy trade mode</button></h2><div class="jw-panel-body" id="jw-pan-trading" hidden>${tradingBlock}</div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-live"><span class="jw-caret" aria-hidden="true">▶</span> Live market &amp; gates</button></h2><div class="jw-panel-body" id="jw-pan-live" hidden>${operatorBlock}</div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-pos"><span class="jw-caret" aria-hidden="true">▶</span> Position &amp; last kline (Sean DB)</button></h2><div class="jw-panel-body" id="jw-pan-pos" hidden><div id="jw-pos-kl-block">${posBlock}${klBlock}</div></div></section>
    <section class="panel">
      <h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-overview"><span class="jw-caret" aria-hidden="true">▶</span> Dashboard overview</button></h2>
      <div class="jw-panel-body" id="jw-pan-overview" hidden>
      <h1>Jupiter — operator dashboard</h1>
      ${
        w?.pubkey_base58
          ? `<p class="pubkey-banner"><strong>Paper wallet pubkey (published)</strong><br/><code id="jw-pubkey-published">${esc(w.pubkey_base58)}</code>
        <button type="button" class="fund-btn" id="jw-copy-pk" style="margin-top:0.35rem">Copy pubkey</button></p>`
          : `<p class="pubkey-banner bad"><strong>No pubkey published yet</strong> — scroll to <strong>Wallet &amp; funding</strong>, paste your base58 address, click <strong>Register pubkey</strong> (requires operator token). Same flow as the VS Code SeanV3 path: stored in <code>paper_wallet</code>.</p>`
      }
      <p class="muted" id="jw-header-sub">SQLite + parity vs BlackBox baseline · ${
        useLivePoll
          ? `Live poll ${esc(String(v.refresh_sec || 0))}s (no full page reload)`
          : `Auto-refresh ${esc(String(v.refresh_sec || 0))}s`
      }</p>
      <p class="muted small" id="jw-live-clock" style="opacity:0.85"></p>
      <p class="muted">${esc(v.sqlite_path)} · repo: ${esc(v.repo_root)}</p>
      <p><a href="/">Front door</a> · <a href="https://jup.ag/perps/long/SOL-SOL" target="_blank" rel="noopener noreferrer">jup.ag SOL perps</a> · <a href="/api/summary.json">summary.json</a> · <a href="/api/operator/state.json">operator/state.json</a> · <a href="/api/live-market.json">live-market.json</a> · <a href="/health">health</a></p>
      <script>
      (function(){
        document.getElementById('jw-copy-pk')?.addEventListener('click', function(){
          var el = document.getElementById('jw-pubkey-published');
          if (!el) return;
          var t = el.textContent || '';
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(t).then(function(){ alert('Copied'); }).catch(function(){ prompt('Copy:', t); });
          } else { prompt('Copy:', t); }
        });
      })();
      </script>
    </div>
    </section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-ledger"><span class="jw-caret" aria-hidden="true">▶</span> SeanV3 paper ledger (testing)</button></h2><div class="jw-panel-body" id="jw-pan-ledger" hidden>${ledgerBlock}</div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-parity"><span class="jw-caret" aria-hidden="true">▶</span> Parity (Jupiter vs BlackBox baseline)</button></h2>
      <div class="jw-panel-body" id="jw-pan-parity" hidden>
      <p class="muted">Jupiter DB: ${esc(v.parity?.sean_db || '')} · baseline ledger: ${esc(v.parity?.ledger_db || '')}</p>
      ${v.parity?.parity_align_note ? `<p class="muted small">${esc(v.parity.parity_align_note)}</p>` : ''}
      <div class="scroll"><table><thead><tr><th>market_event_id</th><th>Jupiter</th><th>BlackBox</th><th>Parity</th></tr></thead><tbody id="jw-parity-tbody">${parityRows}</tbody></table></div>
    </div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-trade-open"><span class="jw-caret" aria-hidden="true">▶</span> TRADE_OPEN decision log (bar opened position)</button></h2><div class="jw-panel-body" id="jw-pan-trade-open" hidden>
      <p class="op-row" style="margin-top:0;flex-wrap:wrap;align-items:center">
        <a class="csv-btn" href="/api/v1/sean/trade-open-decisions.csv">Export TRADE_OPEN decisions (CSV)</a>
        <span class="muted small">Same rows as this table — full <code>indicator_values_json</code>, <code>gate_results_json</code>, <code>features_json</code>, <code>trade_id</code> (decision ledger).</span>
      </p>
      <p class="muted small jw-panel-sync-hint">Time sync: same <code>/api/summary.json</code> poll as the live strip (${esc(String(v.refresh_sec || 0))}s). Source: <code>sean_bar_decisions</code> where <code>outcome = TRADE_OPEN</code>.</p>
      <p class="muted small">Click <strong>View</strong> for full detail (same API as NO_TRADE — <code>/api/v1/sean/decision/:id.json</code>). When <code>trade_id</code> is set, the drawer includes a linked <code>sean_paper_trades</code> snapshot for lifecycle context.</p>
      <div class="scroll" id="jw-trade-open-scroll"><table><thead><tr><th>Time (UTC)</th><th>market_event_id</th><th>policy</th><th>side</th><th>reason</th><th></th></tr></thead><tbody id="jw-trade-open-tbody">${tradeOpenRows}</tbody></table></div>
    </div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-preflight"><span class="jw-caret" aria-hidden="true">▶</span> Preflight strip</button></h2><div class="jw-panel-body" id="jw-pan-preflight" hidden><div id="jw-preflight-banner">${banner}</div><div class="scroll"><table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody id="jw-preflight-tbody">${chkRows}</tbody></table></div></div></section>
    <section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-oracle"><span class="jw-caret" aria-hidden="true">▶</span> Trade / oracle window (Pyth SOL/USD)</button></h2><div class="jw-panel-body" id="jw-pan-oracle" hidden><div id="jw-oracle-block">${oracleBlock}</div></div></section>
    ${tokenPanel}
    ${v.error ? `<section class="panel"><h2 class="jw-panel-head"><button type="button" class="jw-panel-toggle" aria-expanded="false" aria-controls="jw-pan-err"><span class="jw-caret" aria-hidden="true">▶</span> Error</button></h2><div class="jw-panel-body" id="jw-pan-err" hidden><p class="warn">${esc(v.error)}</p></div></section>` : ''}
  </div>
  <div id="jw-nt-drawer-root" class="jw-nt-drawer-backdrop" hidden aria-hidden="true">
    <aside class="jw-nt-drawer" role="dialog" aria-modal="true" aria-labelledby="jw-nt-drawer-title" onclick="event.stopPropagation()">
      <div class="jw-nt-drawer-head">
        <h3 id="jw-nt-drawer-title">Bar decision</h3>
        <button type="button" class="fund-btn" id="jw-nt-drawer-close">Close</button>
      </div>
      <div id="jw-nt-drawer-body"><p class="muted">Select <strong>View</strong> on a row.</p></div>
    </aside>
  </div>
  <div id="jw-text-scale-float" class="jw-text-scale-float" role="toolbar" aria-label="Text size">
    <button type="button" class="jw-chrome-float-btn" id="jw-text-scale-up" title="Larger text" aria-label="Larger text">A+</button>
    <button type="button" class="jw-chrome-float-btn" id="jw-text-scale-down" title="Smaller text" aria-label="Smaller text">A\u2212</button>
  </div>
  <script>
  (function(){
    var KEY = 'jw_dashboard_text_scale_v1';
    var STEPS = [0.8, 0.85, 0.9, 0.95, 1, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4];
    function nearestStep(v) {
      var best = 0, bestDiff = 999;
      for (var i = 0; i < STEPS.length; i++) {
        var d = Math.abs(STEPS[i] - v);
        if (d < bestDiff) { bestDiff = d; best = i; }
      }
      return best;
    }
    function applyIdx(i) {
      var idx = i < 0 ? 0 : i >= STEPS.length ? STEPS.length - 1 : i;
      var s = STEPS[idx];
      document.documentElement.style.setProperty('--jw-text-scale', String(s));
      try { localStorage.setItem(KEY, String(s)); } catch (e) { /* */ }
      return idx;
    }
    var cur = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--jw-text-scale').trim() || '1'
    );
    var idx = nearestStep(isFinite(cur) ? cur : 1);
    idx = applyIdx(idx);
    document.getElementById('jw-text-scale-up')?.addEventListener('click', function () {
      idx = applyIdx(idx + 1);
    });
    document.getElementById('jw-text-scale-down')?.addEventListener('click', function () {
      idx = applyIdx(idx - 1);
    });
  })();
  </script>
  <script>
  (function(){
    function E(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
    function kvTable(obj){
      if(!obj||typeof obj!=='object'||Array.isArray(obj)) return '<p class="muted">—</p>';
      var keys = Object.keys(obj);
      if(!keys.length) return '<p class="muted">—</p>';
      var rows = keys.map(function(k){
        var v = obj[k];
        var cell = (v !== null && typeof v === 'object') ? JSON.stringify(v) : String(v);
        return '<tr><td>'+E(k)+'</td><td>'+E(cell.length>1200?cell.slice(0,1199)+'…':cell)+'</td></tr>';
      }).join('');
      return '<table class="jw-nt-kv"><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>'+rows+'</tbody></table>';
    }
    /** Display-only: omit strategy.schema from stringified gate JSON (does not mutate API object). */
    function strategyJsonForDisplay(strat){
      if(!strat||typeof strat!=='object') return '{}';
      var copy = {};
      for(var k in strat){
        if(!Object.prototype.hasOwnProperty.call(strat,k)) continue;
        if(k === 'schema') continue;
        copy[k] = strat[k];
      }
      return JSON.stringify(copy,null,2);
    }
    /** Display-only full gate_results fallback without strategy.schema leakage. */
    function gateResultsJsonForDisplay(g){
      if(!g||typeof g!=='object') return '{}';
      try {
        var o = JSON.parse(JSON.stringify(g));
        if(o.strategy && typeof o.strategy === 'object' && Object.prototype.hasOwnProperty.call(o.strategy,'schema')) delete o.strategy.schema;
        return JSON.stringify(o,null,2);
      } catch (err) {
        return JSON.stringify(g,null,2);
      }
    }
    function gateHtml(g){
      if(!g||typeof g!=='object') return '<p class="muted">—</p>';
      var h = '';
      if(g.funding_gate !== undefined){
        h += '<p class="muted small"><strong>Funding gate</strong></p>';
        h += kvTable(g.funding_gate === null ? { note: 'not evaluated on this path' } : (typeof g.funding_gate === 'object' && g.funding_gate ? g.funding_gate : { value: g.funding_gate }));
      }
      if(g.strategy && typeof g.strategy === 'object'){
        h += '<p class="muted small" style="margin-top:0.5rem"><strong>Policy Gates</strong></p>';
        var sr = g.strategy.rows;
        if(Array.isArray(sr)){
          h += '<table class="jw-nt-kv"><thead><tr><th>id</th><th>label</th><th>long_ok</th><th>short_ok</th></tr></thead><tbody>';
          sr.forEach(function(rw){
            h += '<tr><td>'+E(rw.id)+'</td><td>'+E(rw.label||'')+'</td><td>'+E(String(rw.long_ok))+'</td><td>'+E(String(rw.short_ok))+'</td></tr>';
          });
          h += '</tbody></table>';
          if(g.strategy.long) h += '<p class="muted small">long.all_ok: '+E(String(g.strategy.long.all_ok))+'</p>';
          if(g.strategy.short) h += '<p class="muted small">short.all_ok: '+E(String(g.strategy.short.all_ok))+'</p>';
        } else { h += '<pre class="jw-nt-pre">'+E(strategyJsonForDisplay(g.strategy))+'</pre>'; }
      }
      return h || '<pre class="jw-nt-pre">'+E(gateResultsJsonForDisplay(g))+'</pre>';
    }
    var root = document.getElementById('jw-nt-drawer-root');
    var body = document.getElementById('jw-nt-drawer-body');
    var title = document.getElementById('jw-nt-drawer-title');
    function closeNt(){
      if(!root) return;
      root.hidden = true;
      root.setAttribute('aria-hidden','true');
      root.classList.remove('jw-nt-open');
      document.body.style.overflow = '';
    }
    function openNt(id){
      if(!body||!title) return;
      body.innerHTML = '<p class="muted">Loading…</p>';
      if(root){ root.hidden = false; root.setAttribute('aria-hidden','false'); root.classList.add('jw-nt-open'); document.body.style.overflow = 'hidden'; }
      fetch('/api/v1/sean/decision/'+id+'.json').then(function(r){
        if(r.status===401){ location.href='/auth/login'; return Promise.reject(); }
        return r.json();
      }).then(function(d){
        if(d.error){ body.innerHTML = '<p class="warn">'+E(String(d.error))+'</p>'; return; }
        var polLabel = (d.policy_id != null && String(d.policy_id).trim() !== '') ? String(d.policy_id).trim() : 'Policy';
        title.textContent = polLabel + ' — ' + String(d.outcome || 'BAR') + ' #' + String(d.id) + ' — ' + String(d.reason_code || '');
        var html = '';
        html += '<h4 class="jw-nt-h4">Summary</h4><dl class="jw-nt-dl">';
        [['outcome', d.outcome],['market_event_id', d.market_event_id],['timestamp_utc', d.timestamp_utc],['symbol', d.symbol],['timeframe', d.timeframe],['policy_id', d.policy_id],['policy_engine_tag', d.policy_engine_tag],['engine_id', d.engine_id],['candidate_side', d.candidate_side],['reason_code', d.reason_code],['trade_id', d.trade_id]].forEach(function(p){
          html += '<dt>'+E(p[0])+'</dt><dd>'+E(p[1]!=null?String(p[1]):'—')+'</dd>';
        });
        html += '</dl>';
        if (d.paper_trade_snapshot && typeof d.paper_trade_snapshot === 'object') {
          var pts = d.paper_trade_snapshot;
          html += '<h4 class="jw-nt-h4">Linked paper trade (sean_paper_trades)</h4><dl class="jw-nt-dl">';
          [['trade_id_label', pts.trade_id_label],['engine_id', pts.engine_id],['side', pts.side],['entry_market_event_id', pts.entry_market_event_id],['exit_market_event_id', pts.exit_market_event_id],['entry_time_utc', pts.entry_time_utc],['exit_time_utc', pts.exit_time_utc],['entry_price', pts.entry_price],['exit_price', pts.exit_price],['size_notional_sol', pts.size_notional_sol],['gross_pnl_usd', pts.gross_pnl_usd],['net_pnl_usd', pts.net_pnl_usd],['result_class', pts.result_class]].forEach(function(p){
            html += '<dt>'+E(p[0])+'</dt><dd>'+E(p[1]!=null?String(p[1]):'—')+'</dd>';
          });
          html += '</dl>';
          if (pts.metadata_json) {
            html += '<p class="muted small">metadata_json (lifecycle)</p><pre class="jw-nt-pre">'+E(String(pts.metadata_json).length>6000?String(pts.metadata_json).slice(0,5999)+'…':String(pts.metadata_json))+'</pre>';
          }
        }
        if (d.paper_trade_link && d.paper_trade_link.note) {
          html += '<p class="muted small">'+E(String(d.paper_trade_link.note))+'</p>';
        }
        html += '<h4 class="jw-nt-h4">Indicators</h4>' + kvTable(d.indicator_values);
        html += '<h4 class="jw-nt-h4">Gates</h4>' + gateHtml(d.gate_results);
        html += '<h4 class="jw-nt-h4">Raw diagnostics (features)</h4>';
        body.innerHTML = html;
        var featObj = d.features;
        if (featObj == null && d.features_json) {
          try { featObj = JSON.parse(String(d.features_json)); } catch (err) { featObj = { _parse_error: true, raw: String(d.features_json).slice(0, 8000) }; }
        }
        if (featObj == null) featObj = {};
        var pre = document.createElement('pre');
        pre.className = 'jw-nt-pre';
        pre.textContent = JSON.stringify(featObj, null, 2);
        body.appendChild(pre);
      }).catch(function(e){ body.innerHTML = '<p class="warn">'+E(String(e))+'</p>'; });
    }
    document.getElementById('jw-nt-drawer-close')?.addEventListener('click', closeNt);
    root?.addEventListener('click', function(e){ if(e.target === root) closeNt(); });
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeNt(); });
    document.addEventListener('click', function(e){
      var btn = e.target && e.target.closest && e.target.closest('.jw-bar-decision-view');
      if(!btn) return;
      var did = btn.getAttribute('data-decision-id');
      if(!did) return;
      e.preventDefault();
      openNt(did);
    });
  })();
  </script>
  <script>
  (function(){
    function syncPanelFromAria(btn){
      var id = btn.getAttribute('aria-controls');
      var body = id ? document.getElementById(id) : null;
      if (!body) return;
      var exp = btn.getAttribute('aria-expanded') === 'true';
      body.hidden = !exp;
      var care = btn.querySelector('.jw-caret');
      if (care) care.textContent = exp ? '\\u25bc' : '\\u25b6';
    }
    document.querySelectorAll('.jw-panel-toggle').forEach(function(btn){
      syncPanelFromAria(btn);
      btn.addEventListener('click', function(){
        var id = btn.getAttribute('aria-controls');
        var body = id ? document.getElementById(id) : null;
        if (!body) return;
        var exp = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', exp ? 'false' : 'true');
        body.hidden = exp;
        var care = btn.querySelector('.jw-caret');
        if (care) care.textContent = exp ? '\\u25b6' : '\\u25bc';
      });
    });
  })();
  </script>
  ${useLivePoll ? jwLivePollScript(v.refresh_sec) : ''}
</body>
</html>`;
}

function readRequestBody(req, limit = 65536) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let n = 0;
    req.on('data', (c) => {
      n += c.length;
      if (n > limit) {
        reject(new Error('body too large'));
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

/**
 * @param {import('http').IncomingMessage} req
 * @param {import('http').ServerResponse} res
 * @param {string} pathname
 */
function handleJupiterPolicyGet(res) {
  const seanPath = dbPath();
  let db;
  try {
    db = new DatabaseSync(seanPath, { readOnly: true });
    const p = getActiveDeploymentSnapshot(db);
    const allowed = loadAllowedDeploymentIdsFromManifest();
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    const mb = p.manifestBinding;
    res.end(
      JSON.stringify({
        contract: JUPITER_POLICY_OBSERVABILITY_CONTRACT,
        active_policy: p.policyId,
        source: p.source,
        engine_display_id: jupiterEngineDisplayId(),
        engine_online: jupiterEngineSliceEnabled(),
        allowed_policies: allowed,
        submission_id: mb && mb.submission_id ? mb.submission_id : null,
        content_sha256: mb && mb.content_sha256 ? mb.content_sha256 : null,
        artifact_binding: mb ? 'manifest_v1' : 'legacy_unbound',
        api: {
          sole_write: 'POST /api/v1/jupiter/active-policy',
          sole_write_alias: 'POST /api/v1/jupiter/set-policy',
          body: { policy: 'deployed_runtime_policy_id from kitchen_policy_deployment_manifest_v1 (Jupiter)' },
          auth: 'Authorization: Bearer JUPITER_OPERATOR_TOKEN',
          effect:
            'Writes analog_meta.jupiter_active_policy only; engine loads evaluator.mjs from submission artifacts each cycle. Does not mutate trades, bars, or lifecycle state.',
        },
      })
    );
  } catch (e) {
    res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
  } finally {
    try {
      db?.close();
    } catch {
      /* */
    }
  }
}

async function handleJupiterActivePolicyPost(req, res) {
  const expected = (process.env.JUPITER_OPERATOR_TOKEN || '').trim();
  if (!expected) {
    res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'JUPITER_OPERATOR_TOKEN not set on server' }));
    return;
  }
  const auth = req.headers.authorization || '';
  const tok = auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
  if (tok !== expected) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'unauthorized' }));
    return;
  }
  let body;
  try {
    const raw = await readRequestBody(req);
    body = JSON.parse(raw || '{}');
  } catch (e) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
    return;
  }
  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        error: 'invalid_body',
        contract: JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT,
        message: 'Body must be a JSON object with exactly one property: "policy" (approved identifier).',
      })
    );
    return;
  }
  const keys = Object.keys(body);
  if (keys.length !== 1 || keys[0] !== 'policy') {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        error: 'invalid_body',
        contract: JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT,
        message:
          'Only {"policy":"<id>"} is accepted — no extra fields, scripts, or package paths. Approved ids only.',
        allowed_keys: ['policy'],
        allowed_policies: loadAllowedDeploymentIdsFromManifest(),
      })
    );
    return;
  }
  if (typeof body.policy !== 'string') {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        error: 'invalid_policy_type',
        message: 'policy must be a string (approved identifier)',
        allowed_policies: loadAllowedDeploymentIdsFromManifest(),
      })
    );
    return;
  }
  const nid = String(body.policy).trim();
  if (!nid || !isDeploymentIdInManifest(nid)) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        error: 'policy_not_in_approved_set',
        contract: JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT,
        message: 'Unknown deployment id — must exist in kitchen_policy_deployment_manifest_v1 for Jupiter.',
        allowed_policies: loadAllowedDeploymentIdsFromManifest(),
      })
    );
    return;
  }
  const seanPath = dbPath();
  const dbw = new DatabaseSync(seanPath);
  try {
    const before = getActiveDeploymentSnapshot(dbw).policyId;
    setMeta(dbw, JUPITER_ACTIVE_POLICY_KEY, nid);
    const after = getActiveDeploymentSnapshot(dbw).policyId;
    console.error(`[jupiter] set active Jupiter policy: ${before} → ${after}`);
    const strictKitchenAckRequired = ['1', 'true', 'yes'].includes(
      String(process.env.JUPITER_REQUIRE_KITCHEN_ACK || '')
        .trim()
        .toLowerCase()
    );
    let hs;
    try {
      /**
       * DV-077 hardening note:
       * - The local runtime write has already happened by the time we enter the reciprocal
       *   Kitchen handshake.
       * - We therefore treat unexpected handshake exceptions exactly like a failed ack instead
       *   of letting them fall through to the generic 500 handler below.
       * - That keeps strict mode honest: if Kitchen cannot be reached or the handshake code blows
       *   up unexpectedly, we still drive the rollback branch instead of leaving Jupiter changed
       *   while Kitchen stays behind.
       */
      hs = await tradeSurfacePolicyKitchenHandshake({
        beforePolicyId: before,
        afterPolicyId: after,
      });
    } catch (e) {
      const detail = `Kitchen check-in raised an unexpected exception: ${
        e instanceof Error ? e.message : String(e)
      }`;
      hs = {
        /**
         * Preserve the product contract even if the helper itself misbehaves:
         * - strict mode => treat this as an unacknowledged change and roll back
         * - relaxed mode => keep the local runtime change but surface a loud warning
         *
         * That mirrors the normal handshake result shape instead of silently upgrading
         * every exception into a rollback.
         */
        strictBlocked: strictKitchenAckRequired,
        kitchen_checkin: { ok: false, reason: 'unexpected_exception', detail },
        detail,
      };
      if (!strictKitchenAckRequired) {
        hs.kitchen_checkin_warning = `Kitchen did not acknowledge runtime policy change: ${String(detail).slice(0, 500)}`;
      }
    }
    if (hs.strictBlocked) {
      setMeta(dbw, JUPITER_ACTIVE_POLICY_KEY, before);
      const restored = getActiveDeploymentSnapshot(dbw).policyId;
      if (restored !== before) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(
          JSON.stringify({
            ok: false,
            error: 'kitchen_checkin_rollback_failed',
            attempted_policy: after,
            restored_policy: restored,
            detail: 'Rollback after failed Kitchen check-in could not restore previous policy.',
          })
        );
        return;
      }
      res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(
        JSON.stringify({
          ok: false,
          error: 'kitchen_checkin_failed_runtime_rolled_back',
          attempted_policy: after,
          restored_policy: before,
          detail: hs.detail || 'Kitchen did not acknowledge runtime policy change.',
          kitchen_checkin: hs.kitchen_checkin,
        })
      );
      return;
    }
    const payload = {
      ok: true,
      contract: JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT,
      operation: 'set_active_jupiter_policy',
      active_policy: after,
      previous_policy: before,
      source: 'runtime_config',
      applied_on_next_engine_cycle: true,
      does_not_mutate: ['trade_history', 'bars', 'lifecycle_bypass', 'arbitrary_strategy_load'],
      kitchen_checkin: hs.kitchen_checkin,
    };
    if (hs.kitchen_checkin_warning) {
      payload.kitchen_checkin_warning = hs.kitchen_checkin_warning;
    }
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(payload));
  } catch (e) {
    res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
  } finally {
    try {
      dbw.close();
    } catch {
      /* */
    }
  }
}

async function handleOperatorPost(req, res, pathname) {
  const expected = (process.env.JUPITER_OPERATOR_TOKEN || '').trim();
  if (!expected) {
    res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'JUPITER_OPERATOR_TOKEN not set on server' }));
    return;
  }
  const auth = req.headers.authorization || '';
  const tok = auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
  if (tok !== expected) {
    res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'unauthorized' }));
    return;
  }
  if (jupiterWebReadOnly()) {
    res.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        error: 'read_only',
        message:
          'Wallet/funding/stake POST disabled (JUPITER_WEB_READ_ONLY). Sole write: POST /api/v1/jupiter/active-policy with Bearer.',
      })
    );
    return;
  }
  let body;
  try {
    const raw = await readRequestBody(req);
    body = JSON.parse(raw || '{}');
  } catch (e) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
    return;
  }
  const seanPath = dbPath();
  const dbw = new DatabaseSync(seanPath);
  try {
    if (pathname === '/api/operator/paper-wallet') {
      const pk = parseSolanaPubkeyBase58(body.pubkey_base58);
      if (!pk) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify({ error: 'invalid pubkey_base58 (Solana base58 public key)' }));
        return;
      }
      upsertPaperWallet(dbw, { pubkeyBase58: pk, keypairPath: 'jupiter_operator_ui' });
      setMeta(dbw, 'wallet_status', 'connected');
      console.error(`[jupiter] paper wallet set via operator UI: ${pk}`);
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({ ok: true, pubkey_base58: pk, wallet_status: 'connected' }));
      return;
    }
    if (pathname === '/api/operator/funding-mode') {
      const m = String(body.mode || '').trim().toLowerCase();
      if (m !== 'paper' && m !== 'chain' && m !== 'live') {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify({ error: 'mode must be paper|chain|live' }));
        return;
      }
      const store = m === 'live' ? 'chain' : m;
      setMeta(dbw, 'sean_funding_mode', store);
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({ ok: true, sean_funding_mode: store }));
      return;
    }
    if (pathname === '/api/operator/paper-stake') {
      const allow = ['1', 'true', 'yes'].includes((process.env.SEAN_ALLOW_PAPER_STAKE_EDIT || '').trim().toLowerCase());
      if (!allow) {
        res.writeHead(403, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify({ error: 'SEAN_ALLOW_PAPER_STAKE_EDIT not enabled' }));
        return;
      }
      const usd = Number(body.usd);
      if (!Number.isFinite(usd) || usd <= 0) {
        res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify({ error: 'usd must be a positive number' }));
        return;
      }
      setMeta(dbw, 'paper_starting_balance_usd', String(usd));
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({ ok: true, paper_starting_balance_usd: usd }));
      return;
    }
    res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'unknown path' }));
  } finally {
    try {
      dbw.close();
    } catch {
      /* */
    }
  }
}

const portRaw = process.env.JUPITER_WEB_PORT || process.env.SEANV3_WEB_PORT || '707';
const port = Math.max(1, Math.min(65535, parseInt(portRaw, 10) || 707));
const bind = (process.env.JUPITER_WEB_BIND || process.env.SEANV3_WEB_BIND || '0.0.0.0').trim() || '0.0.0.0';

function sha256utf8(s) {
  return createHash('sha256').update(String(s), 'utf8').digest();
}

/**
 * Optional HTTP Basic Auth when JUPITER_WEB_LOGIN_USER and JUPITER_WEB_LOGIN_PASSWORD are both non-empty.
 * Exempt: GET /health (probes). Compare via SHA-256 to reduce timing leaks on length.
 */
function jupiterWebBasicAuthOk(req, res, url) {
  const u = (process.env.JUPITER_WEB_LOGIN_USER || '').trim();
  const p = (process.env.JUPITER_WEB_LOGIN_PASSWORD || '').trim();
  if (!u || !p) return true;
  if (url.pathname === '/health' && req.method === 'GET') return true;
  const hdr = req.headers.authorization || '';
  if (!hdr.startsWith('Basic ')) {
    res.writeHead(401, {
      'Content-Type': 'text/plain; charset=utf-8',
      'WWW-Authenticate': 'Basic realm="Jupiter lab"',
      'Cache-Control': 'no-store',
    });
    res.end('Unauthorized');
    return false;
  }
  let decoded = '';
  try {
    decoded = Buffer.from(hdr.slice(6).trim(), 'base64').toString('utf8');
  } catch {
    decoded = '';
  }
  const colon = decoded.indexOf(':');
  const gotUser = colon >= 0 ? decoded.slice(0, colon) : decoded;
  const gotPass = colon >= 0 ? decoded.slice(colon + 1) : '';
  const hu = sha256utf8(gotUser);
  const hp = sha256utf8(gotPass);
  const eu = sha256utf8(u);
  const ep = sha256utf8(p);
  if (hu.length !== eu.length || hp.length !== ep.length) {
    res.writeHead(401, {
      'Content-Type': 'text/plain; charset=utf-8',
      'WWW-Authenticate': 'Basic realm="Jupiter lab"',
      'Cache-Control': 'no-store',
    });
    res.end('Unauthorized');
    return false;
  }
  if (!timingSafeEqual(hu, eu) || !timingSafeEqual(hp, ep)) {
    res.writeHead(401, {
      'Content-Type': 'text/plain; charset=utf-8',
      'WWW-Authenticate': 'Basic realm="Jupiter lab"',
      'Cache-Control': 'no-store',
    });
    res.end('Unauthorized');
    return false;
  }
  return true;
}

function jupiterAuthMode() {
  const m = (process.env.JUPITER_AUTH_MODE || '').trim().toLowerCase();
  if (m === 'session' || m === 'basic' || m === 'none') return m;
  if ((process.env.JUPITER_WEB_LOGIN_USER || '').trim() && (process.env.JUPITER_WEB_LOGIN_PASSWORD || '').trim())
    return 'basic';
  return 'none';
}

function jupiterPublicPath(pathname, method) {
  if (pathname === '/health' && method === 'GET') return true;
  if (pathname === '/static/jupiter_front_door.png' && method === 'GET') return true;
  return false;
}

/**
 * When ``JUPITER_AUTH_MODE=session``, browser users have a cookie session; automation uses the
 * same ``Authorization: Bearer`` secret as ``POST /api/v1/jupiter/active-policy`` (DV-ARCH-JUPITER-MC2-039).
 */
function jupiterOperatorBearerMatches(req) {
  const expected = (process.env.JUPITER_OPERATOR_TOKEN || '').trim();
  if (!expected) return false;
  const auth = String(req.headers.authorization || '');
  if (!auth.startsWith('Bearer ')) return false;
  const tok = auth.slice(7).trim();
  return tok.length > 0 && tok === expected;
}

const server = http.createServer((req, res) => {
  void (async () => {
    const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
    const mode = jupiterAuthMode();

    if (mode === 'session') {
      const authHandled = await handleJupiterAuthHttp(req, res, url, { dbPath, readRequestBody });
      if (authHandled) return;
      if (!jupiterPublicPath(url.pathname, req.method)) {
        const accept = req.headers.accept || '';
        const wantsJson =
          url.pathname.startsWith('/api') ||
          (accept.includes('application/json') && !accept.includes('text/html'));
        if (!jupiterOperatorBearerMatches(req) && !requireJupiterSession(req, res, url, { wantsJson })) return;
      }
    } else if (mode === 'basic') {
      if (!jupiterWebBasicAuthOk(req, res, url)) return;
    }

    if (url.pathname === '/api/v1/jupiter/policy' && req.method === 'GET') {
      handleJupiterPolicyGet(res);
      return;
    }
    if (
      (url.pathname === '/api/v1/jupiter/active-policy' || url.pathname === '/api/v1/jupiter/set-policy') &&
      req.method === 'POST'
    ) {
      await handleJupiterActivePolicyPost(req, res);
      return;
    }

    if (
      req.method === 'POST' &&
      (url.pathname === '/api/operator/funding-mode' ||
        url.pathname === '/api/operator/paper-stake' ||
        url.pathname === '/api/operator/paper-wallet')
    ) {
      await handleOperatorPost(req, res, url.pathname);
      return;
    }

    if (url.pathname === '/api/operator/state.json' && req.method === 'GET') {
      try {
        const seanPath = dbPath();
        const base = {
          schema: 'jupiter_web_tui_view_v1',
          error: null,
        };
        let db;
        try {
          db = new DatabaseSync(seanPath, { readOnly: true });
          Object.assign(base, buildSummary(db));
        } catch (e) {
          base.error = e instanceof Error ? e.message : String(e);
        } finally {
          try {
            db?.close();
          } catch {
            /* */
          }
        }
        const preflight = await runPreflight();
        const mark = preflight.oracle?.price != null ? Number(preflight.oracle.price) : null;
        const operator = buildOperatorPayload(seanPath, mark, base);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify(operator, null, 2));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      }
      return;
    }

    if (url.pathname === '/api/live-market.json' && req.method === 'GET') {
      try {
        const view = await buildFullView();
        const pf = view.preflight || {};
        const checks = pf.checks || [];
        const live = {
          schema: 'jupiter_live_market_v1',
          last_kline: view.last_kline || null,
          oracle: pf.oracle || null,
          preflight_degraded: Boolean(pf.degraded),
          checks_binance: checks.filter((c) => /binance/i.test(String(c.name || ''))),
          checks_hermes: checks.filter((c) => /hermes|pyth/i.test(String(c.name || ''))),
        };
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify(live, null, 2));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      }
      return;
    }

    if (url.pathname === '/api/v1/sean/trades.csv' && req.method === 'GET') {
      let db;
      try {
        db = new DatabaseSync(dbPath(), { readOnly: true });
        const body = buildSeanTradesCsv(db);
        res.writeHead(200, {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': 'attachment; filename="sean_paper_trades.csv"',
          'Cache-Control': 'no-store',
        });
        res.end(body);
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      } finally {
        try {
          db?.close();
        } catch {
          /* */
        }
      }
      return;
    }

    if (url.pathname === '/api/v1/sean/no-trade-decisions.csv' && req.method === 'GET') {
      let db;
      try {
        db = new DatabaseSync(dbPath(), { readOnly: true });
        const body = buildNoTradeDecisionsCsv(db);
        res.writeHead(200, {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': 'attachment; filename="sean_bar_decisions_no_trade.csv"',
          'Cache-Control': 'no-store',
        });
        res.end(body);
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      } finally {
        try {
          db?.close();
        } catch {
          /* */
        }
      }
      return;
    }

    if (url.pathname === '/api/v1/sean/trade-open-decisions.csv' && req.method === 'GET') {
      let db;
      try {
        db = new DatabaseSync(dbPath(), { readOnly: true });
        const body = buildTradeOpenDecisionsCsv(db);
        res.writeHead(200, {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': 'attachment; filename="sean_bar_decisions_trade_open.csv"',
          'Cache-Control': 'no-store',
        });
        res.end(body);
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      } finally {
        try {
          db?.close();
        } catch {
          /* */
        }
      }
      return;
    }

    const barDecisionMatch = url.pathname.match(/^\/api\/v1\/sean\/decision\/(\d+)\.json$/);
    if (barDecisionMatch && req.method === 'GET') {
      const did = parseInt(barDecisionMatch[1], 10);
      let db;
      try {
        db = new DatabaseSync(dbPath(), { readOnly: true });
        const row = db.prepare(`SELECT * FROM sean_bar_decisions WHERE id = ?`).get(did);
        if (!row) {
          res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ error: 'decision not found' }));
          return;
        }
        const o = String(row.outcome || '');
        if (o !== 'NO_TRADE' && o !== 'TRADE_OPEN') {
          res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ error: 'unsupported outcome for bar decision detail' }));
          return;
        }
        let payload = barDecisionDetailPayload(row);
        payload = augmentBarDecisionDetail(db, payload);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify(payload, null, 2));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      } finally {
        try {
          db?.close();
        } catch {
          /* */
        }
      }
      return;
    }

    const tradeDetailMatch = url.pathname.match(/^\/api\/v1\/sean\/trade\/(\d+)\.json$/);
    if (tradeDetailMatch && req.method === 'GET') {
      const tid = parseInt(tradeDetailMatch[1], 10);
      let db;
      try {
        db = new DatabaseSync(dbPath(), { readOnly: true });
        const row = db
          .prepare(
            `SELECT id, engine_id, side, entry_market_event_id, exit_market_event_id,
                    entry_time_utc, exit_time_utc, entry_price, exit_price, size_notional_sol,
                    gross_pnl_usd, net_pnl_usd, result_class, metadata_json
             FROM sean_paper_trades WHERE id = ?`
          )
          .get(tid);
        if (!row) {
          res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ error: 'trade not found' }));
          return;
        }
        const sym =
          (process.env.SEANV3_CANONICAL_SYMBOL || process.env.CANONICAL_SYMBOL || 'SOL-PERP').trim() || 'SOL-PERP';
        let metaParsed = null;
        try {
          metaParsed = row.metadata_json ? JSON.parse(String(row.metadata_json)) : null;
        } catch {
          metaParsed = { parse_error: true, raw: String(row.metadata_json) };
        }
        const ep = Number(row.entry_price);
        const sz = Number(row.size_notional_sol);
        const payload = {
          schema: 'jupiter_sean_trade_detail_v1',
          id: row.id,
          trade_id: `sean_${row.id}`,
          symbol: sym,
          lane: 'sean_paper',
          engine_id: row.engine_id,
          side: row.side,
          entry_market_event_id: row.entry_market_event_id,
          exit_market_event_id: row.exit_market_event_id,
          entry_time_utc: row.entry_time_utc,
          exit_time_utc: row.exit_time_utc,
          entry_price: row.entry_price,
          exit_price: row.exit_price,
          size_notional_sol: row.size_notional_sol,
          gross_pnl_usd: row.gross_pnl_usd,
          net_pnl_usd: row.net_pnl_usd,
          result_class: row.result_class,
          notional_usd_entry_approx: Number.isFinite(ep) && Number.isFinite(sz) ? ep * sz : null,
          metadata_parsed: metaParsed,
          metadata_json: row.metadata_json != null ? String(row.metadata_json) : null,
        };
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify(payload, null, 2));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      } finally {
        try {
          db?.close();
        } catch {
          /* */
        }
      }
      return;
    }

    if (url.pathname === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(
        JSON.stringify({
          ok: true,
          schema: 'jupiter_web_health_v1',
          application: 'Jupiter',
          port,
          bind,
          tui_parity: true,
        })
      );
      return;
    }

    if (url.pathname === '/api/summary.json') {
      try {
        const view = await buildFullView();
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(JSON.stringify(view, null, 2));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ error: e instanceof Error ? e.message : String(e) }));
      }
      return;
    }

    if (url.pathname === '/static/jupiter_front_door.png' && req.method === 'GET') {
      if (!existsSync(FRONT_DOOR_PNG)) {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('front door image missing (rebuild image with static/)');
        return;
      }
      res.writeHead(200, { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=3600' });
      res.end(readFileSync(FRONT_DOOR_PNG));
      return;
    }

    if (url.pathname === '/' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(frontDoorHtml());
      return;
    }

    if (
      (url.pathname === '/dashboard' || url.pathname === '/dashboard/' || url.pathname === '/index.html') &&
      req.method === 'GET'
    ) {
      try {
        const view = await buildFullView();
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(htmlPage(view));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end(e instanceof Error ? e.message : String(e));
      }
      return;
    }

    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('not found');
  })().catch((e) => {
    res.writeHead(500, { 'Content-Type': 'text/plain' });
    res.end(e instanceof Error ? e.message : String(e));
  });
});

if (jupiterAuthMode() === 'session' && !getSessionSecret()) {
  console.error('[jupiter] FATAL: JUPITER_AUTH_MODE=session requires JUPITER_SESSION_SECRET (long random string)');
  process.exit(1);
}

{
  let db;
  try {
    if (jupiterAuthMode() === 'session') {
      db = new DatabaseSync(dbPath());
      ensureJupiterWebAuthSchema(db);
      bootstrapJupiterAuthUserIfNeeded(db);
    }
  } catch (e) {
    console.error('[jupiter] auth bootstrap:', e instanceof Error ? e.message : e);
  } finally {
    try {
      db?.close();
    } catch {
      /* */
    }
  }
}

server.listen(port, bind, () => {
  console.error(`[jupiter] http://${bind}:${port}/ front door · http://${bind}:${port}/dashboard operator UI · auth=${jupiterAuthMode()}`);
});
