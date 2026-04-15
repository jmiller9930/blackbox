#!/usr/bin/env node
/**
 * Jupiter dashboard + JSON API. GET surfaces are unauthenticated (restrict via network).
 * JUPITER_WEB_READ_ONLY=1 blocks POST /api/operator/*; sole write: POST /api/v1/jupiter/active-policy (Bearer).
 *
 * Mount repo read-only at BLACKBOX_REPO_ROOT for policy registry + execution_ledger parity.
 * Default port 707. Lab: http://clawbot.a51.corp:707/
 */
import { execSync } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import http from 'http';
import { DatabaseSync } from 'node:sqlite';
import { resolve, join } from 'path';
import { fileURLToPath } from 'url';

import { assertCanOpenPosition, getPaperEquityUsd } from './funding_guards.mjs';
import { setMeta, upsertPaperWallet } from './paper_analog.mjs';
import { PublicKey } from '@solana/web3.js';
import {
  ALLOWED_POLICY_IDS,
  JUPITER_ACTIVE_POLICY_KEY,
  normalizePolicyId,
  resolveJupiterPolicy,
} from './jupiter_policy_runtime.mjs';

/** GET /api/v1/jupiter/policy — observability only. */
const JUPITER_POLICY_OBSERVABILITY_CONTRACT = 'jupiter_policy_observability_v1';
/**
 * Sole write: select one of the shipped policy modules (ALLOWED_POLICY_IDS).
 * Records analog_meta.jupiter_active_policy; engine applies on next cycle. Does not mutate trades/bars.
 */
const JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT = 'jupiter_active_policy_switch_v1';

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
    const alignTarget =
      normalizePolicyId(process.env.JUPITER_PARITY_ALIGNED_POLICY || 'jup_v4') || 'jup_v4';
    const active = resolveJupiterPolicy(dba).policyId;
    policyAligned = active === alignTarget;
    alignNote = policyAligned
      ? `aligned policy ${active} (compare vs BlackBox baseline)`
      : `Jupiter policy ${active} ≠ compare target ${alignTarget} — parity column blank (set JUPITER_PARITY_ALIGNED_POLICY on jupiter-web to match)`;
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
    <p class="note">No login UI — restrict with VPN/firewall. Operator Bearer token required for policy POST only when read-only.</p>
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

  let jupiterRuntime = { active_policy: 'jup_v4', source: 'default' };
  let db;
  try {
    db = new DatabaseSync(seanPath, { readOnly: true });
    Object.assign(base, buildSummary(db));
    const rp = resolveJupiterPolicy(db);
    jupiterRuntime = { active_policy: rp.policyId, source: rp.source };
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

function htmlPage(v) {
  const readOnly = Boolean(v.read_only_except_policy);
  const refresh = v.refresh_sec > 0 ? `<meta http-equiv="refresh" content="${esc(String(v.refresh_sec))}"/>` : '';
  const tm = v.trading_mode || {};
  const actual = tm.actual_banner;
  const jr = tm.jupiter_runtime || {};
  const ap = jr.active_policy || 'jup_v4';
  const src = jr.source || 'default';
  const postOk = Boolean(tm.post_token_configured);
  const policySel = `
    <p><strong>Policy</strong> (runtime — next bar onward; does not close or force-open positions)</p>
    <p class="muted">Active: <code>${esc(ap)}</code> · source: <code>${esc(src)}</code> · meta key <code>${esc(JUPITER_ACTIVE_POLICY_KEY)}</code></p>
    <p><label>JUPv4 / JUPv3 / JUP-MC-Test <select id="jw-jupiter-policy">
      <option value="jup_v4" ${ap === 'jup_v4' ? 'selected' : ''}>JUPv4</option>
      <option value="jup_v3" ${ap === 'jup_v3' ? 'selected' : ''}>JUPv3</option>
      <option value="jup_mc_test" ${ap === 'jup_mc_test' ? 'selected' : ''}>JUP-MC-Test</option>
    </select></label>
    <button type="button" id="jw-apply-policy">Set active Jupiter policy</button></p>
    ${postOk ? `<p class="muted">Uses Bearer token in <strong>Operator token</strong> panel above.</p>
    <script>
    (function(){
      fetch('/api/v1/jupiter/policy').then(r=>r.json()).then(j=>{
        const s=document.getElementById('jw-jupiter-policy');
        if(s && j.active_policy) s.value=j.active_policy;
      }).catch(function(){});
      document.getElementById('jw-apply-policy')?.addEventListener('click', async function(){
        const pol=(document.getElementById('jw-jupiter-policy')||{}).value||'jup_v4';
        const tok=(document.getElementById('jw-op-token')||{}).value||'';
        const r=await fetch('/api/v1/jupiter/active-policy',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+tok},body:JSON.stringify({policy:pol})});
        const t=await r.text();
        alert(r.ok? t : 'HTTP '+r.status+' '+t);
        if(r.ok) location.reload();
      });
    })();
    </script>` : '<p class="muted">Set <code>JUPITER_OPERATOR_TOKEN</code> on jupiter-web to enable policy switching.</p>'}`;
  const tradingBlock = actual
    ? `<p class="warn"><strong>ACTUAL</strong> — Live-capital intent. Deploy with PAPER_TRADING=0 when leaving paper; this banner does not change Docker.</p>
      ${policySel}
      <p class="muted small">This <strong>Policy</strong> selector is the Jupiter/Sean runtime strategy (<code>jupiter_active_policy</code>). It is <em>not</em> the BlackBox <code>policy_registry.json</code> “strategy entry” line (that registry is for other operator tools only).</p>
      ${
        readOnly
          ? '<p class="muted small">Read-only API: wallet/funding POSTs are off. Other apps may <strong>set active Jupiter policy</strong> via <code>POST /api/v1/jupiter/active-policy</code> (Bearer).</p>'
          : ''
      }`
    : `<p><strong>PAPER</strong> — Simulated ledger (default). SEANV3_TUI_ACTUAL=1 for live-intent banner.</p>
      ${policySel}
      <p class="muted small">This <strong>Policy</strong> selector is the Jupiter/Sean runtime strategy (<code>jupiter_active_policy</code>). Ignore BlackBox registry “strategy entry” elsewhere — not used here.</p>
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
      <p><strong>Paper PnL (live)</strong> — equity ~<strong>${esc(eqStr)}</strong> USD
        <span class="muted">= bankroll ${esc(String(pq.starting_usd ?? '—'))} + realized ${esc(String(pq.realized_pnl_usd ?? '—'))} + unreal ${esc(String(pq.unrealized_usd ?? '—'))}</span>
        ${pl ? ` · closed: ${esc(String(pl.closed_trade_count))}` : ''}</p>
      ${pl?.open_line ? `<p class="muted">${esc(pl.open_line)}</p>` : ''}
      <p class="muted">Stored funding mode: <code>${esc(modeCur)}</code> · PAPER_TRADING: ${
        op.paper_trading_env ? `<span class="ok">on</span>` : `<span class="warn">off</span>`
      }</p>
      ${
        w?.pubkey_base58
          ? `<p class="ok">Pubkey in DB — <code>${esc(w.pubkey_base58)}</code> · ${esc(v.wallet_status || '—')}</p>`
          : `<p class="warn">No pubkey in DB — use <code>KEYPAIR_PATH</code> on seanv3 or temporarily set <code>JUPITER_WEB_READ_ONLY=0</code> to register via UI.</p>`
      }
      <p class="muted small"><strong>Set active Jupiter policy (sole write):</strong> <code>POST /api/v1/jupiter/active-policy</code> · <code>Authorization: Bearer &lt;token&gt;</code> · body exactly <code>{"policy":"jup_v4"}</code> (or <code>jup_v3</code>, <code>jup_mc_test</code>). Alias: <code>/api/v1/jupiter/set-policy</code>.</p>`;
    } else {
      walletFundingBlock = `
      <p class="muted"><strong>Paper wallet</strong> — <strong>Equity = bankroll + realized PnL + unrealized</strong> (same numbers the engine uses). Raising “Add paper funds” increases <strong>bankroll</strong> immediately after save + reload. <strong>Chain wallet</strong> switches the gate to cached SOL; live fills still need <code>PAPER_TRADING=0</code> on seanv3 + restart.</p>
      <p><strong>Paper PnL (live)</strong> — equity ~<strong>${esc(eqStr)}</strong> USD
        <span class="muted">= bankroll ${esc(String(pq.starting_usd ?? '—'))} + realized ${esc(String(pq.realized_pnl_usd ?? '—'))} + unreal ${esc(String(pq.unrealized_usd ?? '—'))}</span>
        ${pl ? ` · closed: ${esc(String(pl.closed_trade_count))}` : ''}</p>
      ${pl?.open_line ? `<p class="muted">${esc(pl.open_line)}</p>` : ''}
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
          if(r.ok) location.reload();
        }
        document.getElementById('jw-fund-paper')?.addEventListener('click', function(){ postMode('paper'); });
        document.getElementById('jw-fund-chain')?.addEventListener('click', function(){ postMode('chain'); });
        document.getElementById('jw-save-wallet')?.addEventListener('click', async function(){
          const pubkey_base58 = (document.getElementById('jw-pubkey')||{}).value||'';
          const r = await fetch('/api/operator/paper-wallet', { method:'POST', headers:{'Authorization':'Bearer '+tok(),'Content-Type':'application/json'}, body: JSON.stringify({pubkey_base58}) });
          alert(r.ok ? await r.text() : 'HTTP '+r.status+' '+await r.text());
          if(r.ok) location.reload();
        });
        document.getElementById('jw-save-stake')?.addEventListener('click', async function(){
          const usd = parseFloat((document.getElementById('jw-stake')||{}).value||'');
          const r = await fetch('/api/operator/paper-stake', { method:'POST', headers:{'Authorization':'Bearer '+tok(),'Content-Type':'application/json'}, body: JSON.stringify({usd}) });
          alert(r.ok ? await r.text() : 'HTTP '+r.status+' '+await r.text());
          if(r.ok) location.reload();
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

  let ledgerBlock = '<p class="muted">—</p>';
  if (pl) {
    ledgerBlock = `<p><strong>Paper ledger</strong> — starting ${esc(String(pl.starting_balance_usd))} USD · realized ${esc(String(pl.realized_pnl_usd))} · equity ~${esc(String(pl.equity_est_usd?.toFixed ? pl.equity_est_usd.toFixed(4) : pl.equity_est_usd))} USD</p>
      <p class="muted">Same figures as <strong>Wallet &amp; funding</strong>; trade list below.</p>`;
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
    operatorBlock = `${liveStrip}
      <p><strong>Funding mode (SQLite)</strong> <code>${esc(op.sean_funding_mode || 'paper')}</code>
        · PAPER_TRADING env: ${
          op.paper_trading_env
            ? `<span class="ok">on (simulated)</span>`
            : `<span class="warn">off</span> (compose uses live path for chain gate)`
        }</p>
      <p><strong>Paper equity</strong> ~${esc(eqStr)} USD
        <span class="muted">(start ${esc(String(pq.starting_usd ?? '—'))} + realized ${esc(String(pq.realized_pnl_usd ?? '—'))} + unreal ${esc(String(pq.unrealized_usd ?? '—'))})</span></p>
      <p><strong>On-chain SOL</strong> (cached) ${esc(op.chain_sol_balance_lamports || '—')} lamports
        <span class="muted">${esc(op.chain_balance_updated_utc || '')}</span></p>
      ${op.chain_balance_error ? `<p class="bad">${esc(op.chain_balance_error)}</p>` : ''}
      <p><strong>Next engine open</strong> ${gOk ? '<span class="ok">allowed</span>' : '<span class="bad">blocked</span>'} — ${esc(gate.reason || '—')}
        <span class="muted">${esc(gate.detail || '')}</span></p>
      <p class="muted">Controls: <strong>Wallet &amp; funding</strong> panel (above this section).</p>`;
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
    ? `<section class="panel"><h2>Operator token</h2>
      <p class="muted">Same secret as <code>JUPITER_OPERATOR_TOKEN</code> on jupiter-web (see <code>lab_operator_token.env</code> in this stack). ${
        readOnly
          ? '<strong>Read-only mode:</strong> use Bearer only for <strong>Set active Jupiter policy</strong> below — wallet/funding POSTs are disabled.'
          : 'Used for policy switch, paper wallet, funding mode, and paper stake'
      } — <em>not</em> your Solana wallet.</p>
      <p><label>Bearer <input type="${bearerInputType}" id="jw-op-token" size="44" value="${esc(prefillBearer)}" autocomplete="off" spellcheck="false"/></label></p>
      ${
        prefillBearer
          ? '<p class="muted small">Prefilled while <code>JUPITER_WEB_PREFILL_BEARER=1</code>. Set to <code>0</code> in <code>lab_operator_token.env</code> to hide.</p>'
          : ''
      }
    </section>`
    : `<section class="panel"><h2>Operator token</h2>
      <p class="warn">POST actions are off until you set <code>JUPITER_OPERATOR_TOKEN</code> on jupiter-web and restart the container.</p>
    </section>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  ${refresh}
  <title>Jupiter — TUI parity</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: ui-monospace, Menlo, Consolas, monospace; background: #0c0c0c; color: #e6edf3; margin: 0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 1rem; }
    .wrap { width: 100%; max-width: 120ch; }
    .panel { border: 1px solid #3d3d3d; border-radius: 2px; padding: 0.75rem 1rem; margin-bottom: 0.75rem; background: #121212; }
    .panel h2 { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #8b949e; margin: 0 0 0.5rem 0; border-bottom: 1px solid #30363d; padding-bottom: 0.35rem; }
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
    a.csv-btn { display: inline-block; padding: 0.25rem 0.6rem; border: 1px solid #30363d; border-radius: 2px; color: #58a6ff; text-decoration: none; font-size: 0.85rem; }
    a.csv-btn:hover { background: #1f2428; }
    .trade-snap-h { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #8b949e; margin: 0.75rem 0 0.35rem 0; }
    pre.trade-detail { margin: 0; max-height: 42vh; overflow: auto; font-size: 0.68rem; line-height: 1.35; white-space: pre-wrap; word-break: break-word; background: #0a0a0b; border: 1px solid #30363d; padding: 0.5rem 0.6rem; border-radius: 2px; }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel">
      <h1>Jupiter — operator dashboard</h1>
      ${
        w?.pubkey_base58
          ? `<p class="pubkey-banner"><strong>Paper wallet pubkey (published)</strong><br/><code id="jw-pubkey-published">${esc(w.pubkey_base58)}</code>
        <button type="button" class="fund-btn" id="jw-copy-pk" style="margin-top:0.35rem">Copy pubkey</button></p>`
          : `<p class="pubkey-banner bad"><strong>No pubkey published yet</strong> — scroll to <strong>Wallet &amp; funding</strong>, paste your base58 address, click <strong>Register pubkey</strong> (requires operator token). Same flow as the VS Code SeanV3 path: stored in <code>paper_wallet</code>.</p>`
      }
      <p class="muted">SQLite + parity vs BlackBox baseline · Auto-refresh ${esc(String(v.refresh_sec || 0))}s</p>
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
    </section>
    ${tokenPanel}
    ${v.error ? `<section class="panel"><p class="warn">${esc(v.error)}</p></section>` : ''}
    <section class="panel"><h2>Wallet &amp; funding</h2>${walletFundingBlock}</section>
    <section class="panel"><h2>Trading mode</h2>${tradingBlock}</section>
    <section class="panel"><h2>Live market &amp; gates</h2>${operatorBlock}</section>
    <section class="panel"><h2>Wallet status</h2>${walletBlock}</section>
    <section class="panel"><h2>SeanV3 paper ledger (testing)</h2>${ledgerBlock}</section>
    <section class="panel"><h2>Parity (Jupiter vs BlackBox baseline)</h2>
      <p class="muted">Jupiter DB: ${esc(v.parity?.sean_db || '')} · baseline ledger: ${esc(v.parity?.ledger_db || '')}</p>
      ${v.parity?.parity_align_note ? `<p class="muted small">${esc(v.parity.parity_align_note)}</p>` : ''}
      <div class="scroll"><table><thead><tr><th>market_event_id</th><th>Jupiter</th><th>BlackBox</th><th>Parity</th></tr></thead><tbody>${parityRows}</tbody></table></div>
    </section>
    <section class="panel"><h2>Position &amp; last kline (Sean DB)</h2>${posBlock}${klBlock}</section>
    <section class="panel"><h2>Trade window (Sean paper trades)</h2>
      <p class="op-row">
        <label>Jump to trade <select id="jw-trade-jump">${tradeJumpOpts}</select></label>
        <a class="csv-btn" href="/api/v1/sean/trades.csv">Download all trades (CSV)</a>
      </p>
      <p class="muted small">Winning trades are tinted light green. CSV includes standard columns plus full <code>metadata_json</code> (entry <code>signal</code> + exit snapshot for closes written with the current engine). BlackBox baseline trade synthesis tiles use a different pipeline.</p>
      <div class="scroll"><table><thead><tr><th>trade_id</th><th>exit UTC</th><th>entry UTC</th><th>sym</th><th>side</th><th>entry px</th><th>exit px</th><th>size</th><th>PnL</th><th>result</th><th>exit</th><th>entry MEI</th><th>exit MEI</th></tr></thead><tbody>${tradeRows}</tbody></table></div>
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
    </section>
    <section class="panel"><h2>Preflight strip</h2>${banner}<div class="scroll"><table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>${chkRows}</tbody></table></div></section>
    <section class="panel"><h2>Trade / oracle window (Pyth SOL/USD)</h2>${oracleBlock}</section>
  </div>
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
    const p = resolveJupiterPolicy(db);
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        contract: JUPITER_POLICY_OBSERVABILITY_CONTRACT,
        active_policy: p.policyId,
        source: p.source,
        allowed_policies: [...ALLOWED_POLICY_IDS],
        api: {
          sole_write: 'POST /api/v1/jupiter/active-policy',
          sole_write_alias: 'POST /api/v1/jupiter/set-policy',
          body: { policy: 'jup_v4 | jup_v3 | jup_mc_test' },
          auth: 'Authorization: Bearer JUPITER_OPERATOR_TOKEN',
          effect:
            'Writes analog_meta.jupiter_active_policy only; engine reads it each cycle. Does not mutate trades, bars, or lifecycle state.',
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
        allowed_policies: [...ALLOWED_POLICY_IDS],
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
        allowed_policies: [...ALLOWED_POLICY_IDS],
      })
    );
    return;
  }
  const nid = normalizePolicyId(body.policy);
  if (!nid || !ALLOWED_POLICY_IDS.includes(nid)) {
    res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        error: 'policy_not_in_approved_set',
        contract: JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT,
        message: 'Unknown or unapproved policy identifier — maps only to shipped SeanV3 modules.',
        allowed_policies: [...ALLOWED_POLICY_IDS],
      })
    );
    return;
  }
  const seanPath = dbPath();
  const dbw = new DatabaseSync(seanPath);
  try {
    const before = resolveJupiterPolicy(dbw).policyId;
    setMeta(dbw, JUPITER_ACTIVE_POLICY_KEY, nid);
    const after = resolveJupiterPolicy(dbw).policyId;
    console.error(`[jupiter] set active Jupiter policy: ${before} → ${after}`);
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        ok: true,
        contract: JUPITER_ACTIVE_POLICY_SWITCH_CONTRACT,
        operation: 'set_active_jupiter_policy',
        active_policy: after,
        previous_policy: before,
        source: 'runtime_config',
        applied_on_next_engine_cycle: true,
        does_not_mutate: ['trade_history', 'bars', 'lifecycle_bypass', 'arbitrary_strategy_load'],
      })
    );
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

const server = http.createServer((req, res) => {
  void (async () => {
    const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);

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

server.listen(port, bind, () => {
  console.error(`[jupiter] http://${bind}:${port}/ front door · http://${bind}:${port}/dashboard operator UI`);
});
