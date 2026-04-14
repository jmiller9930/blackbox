#!/usr/bin/env node
/**
 * Jupiter — read-only web UI aligned with scripts/operator/preflight_pyth_tui.py panels:
 * trading mode, active policy, wallet, Sean paper ledger, parity vs BlackBox baseline,
 * closed trades, preflight strip, Pyth oracle window. Same SQLite + same external checks.
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
import { setMeta } from './paper_analog.mjs';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

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
      const r = o.exit_reason || o.exitReason;
      if (r) return String(r).slice(0, 24);
    }
  } catch {
    /* */
  }
  return '—';
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

function parityMatchText(sean, bb) {
  if (sean && bb) {
    if (sideNorm(sean.side) !== sideNorm(bb.side)) return { text: 'SIDE mismatch', cls: 'bad' };
    if (!priceDriftOk(sean.entry_price, bb.entry_price)) return { text: 'MATCH (entry px drift)', cls: 'warn' };
    return { text: 'MATCH', cls: 'ok' };
  }
  if (sean && !bb) return { text: 'Sean only — no BB row', cls: 'bad' };
  if (bb && !sean) return { text: 'BlackBox only — no Sean row', cls: 'bad' };
  return { text: '—', cls: 'dim' };
}

function buildParityRows(seanDbPath, ledgerPath, maxRows) {
  const out = { rows: [], error: null, sean_db: seanDbPath, ledger_db: ledgerPath };
  if (!existsSync(seanDbPath)) {
    out.error = 'Sean DB missing';
    return out;
  }
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
    const pm = parityMatchText(s, b);
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
  try {
    const rows = db
      .prepare(
        `SELECT id, engine_id, side, entry_time_utc, exit_time_utc, entry_price, exit_price,
                size_notional_sol, gross_pnl_usd, result_class, entry_market_event_id, metadata_json
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
      exit_reason: exitReasonFromMeta(r.metadata_json),
      symbol: sym,
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

  const tradingMode = {
    actual_banner: ['1', 'true', 'yes'].includes((process.env.SEANV3_TUI_ACTUAL || '').trim().toLowerCase()),
    paper_trading: (process.env.PAPER_TRADING || '1').trim() !== '0',
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
    policy,
    preflight,
    parity,
    operator,
    refresh_sec: Math.max(0, parseFloat(process.env.JUPITER_WEB_REFRESH_SEC || '3') || 3),
  };
}

function htmlPage(v) {
  const refresh = v.refresh_sec > 0 ? `<meta http-equiv="refresh" content="${esc(String(v.refresh_sec))}"/>` : '';
  const tm = v.trading_mode || {};
  const actual = tm.actual_banner;
  const tradingBlock = actual
    ? `<p class="warn"><strong>ACTUAL</strong> — Live-capital intent. Deploy with PAPER_TRADING=0 when leaving paper; this banner does not change Docker.</p>`
    : `<p><strong>PAPER</strong> — Simulated ledger (default). SEANV3_TUI_ACTUAL=1 for live-intent banner.</p>`;

  let policyBlock = '';
  if (v.policy?.error) {
    policyBlock = `<p class="warn">${esc(v.policy.error)}</p>`;
  } else if (v.policy?.id) {
    const ed = v.policy.effective_db;
    const edLine = ed
      ? existsSync(ed)
        ? `<span class="ok">file</span> ${esc(ed)}`
        : `<span class="warn">missing</span> ${esc(ed)}`
      : '(none — tick optional)';
    const ent = v.policy.entry_path;
    const entLine = ent
      ? existsSync(ent)
        ? `${esc(ent)}`
        : `${esc(ent)} <span class="warn">(missing)</span>`
      : '—';
    policyBlock = `<p><strong>${esc(v.policy.label)}</strong> <span class="muted">(${esc(v.policy.id)})</span> kind=${esc(v.policy.kind)} dataset_mode=${esc(v.policy.dataset_mode)}</p>
      <p class="muted">Effective SQLite (tick): ${edLine}</p>
      <p class="muted">Strategy entry: ${entLine}</p>`;
  }

  const w = v.wallet;
  const keypairEnv = v.paper_ledger?.keypair_env || v.keypair_env || '';
  let walletBlock = '';
  if (w?.pubkey_base58) {
    walletBlock = `<p><span class="ok">Connected</span> (pubkey in DB)</p>
      <p><code>${esc(w.pubkey_base58)}</code></p>
      <p class="muted">wallet_status: ${esc(v.wallet_status || '—')}</p>`;
  } else {
    walletBlock = `<p class="warn">Not connected in DB yet — SeanV3 writes pubkey when KEYPAIR_PATH is set and readable.</p>`;
    if (keypairEnv) {
      walletBlock += `<p class="muted">Env: <code>${esc(keypairEnv)}</code></p>`;
    } else {
      walletBlock += `<p class="muted">Set KEYPAIR_PATH (or SEANV3_KEYPAIR_PATH / BLACKBOX_SOLANA_KEYPAIR_PATH).</p>`;
    }
  }

  const pl = v.paper_ledger;
  let ledgerBlock = '<p class="muted">—</p>';
  if (pl) {
    ledgerBlock = `<p><strong>Paper account (simulated)</strong></p>
      <p>Starting: ${esc(String(pl.starting_balance_usd))} USD · Realized: ${esc(String(pl.realized_pnl_usd))} · Closed: ${esc(String(pl.closed_trade_count))}</p>
      <p><strong>Equity (est.):</strong> ${esc(String(pl.equity_est_usd?.toFixed ? pl.equity_est_usd.toFixed(4) : pl.equity_est_usd))} USD</p>
      <p class="muted">${esc(pl.open_line || '')}</p>`;
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
  const tradeRows = trades.length
    ? trades
        .map(
          (t) =>
            `<tr><td>${esc(t.trade_id)}</td><td>${esc(formatIsoUtcShort(t.exit_time_utc))}</td><td>${esc(formatIsoUtcShort(t.entry_time_utc))}</td><td>${esc(t.symbol)}</td><td>${esc(t.side)}</td><td>${esc(t.entry_price)}</td><td>${esc(t.exit_price)}</td><td>${esc(t.size_notional_sol)}</td><td>${esc(t.gross_pnl_usd)}</td><td>${esc(t.result_class)}</td><td>${esc(t.exit_reason)}</td><td>${esc(truncateMid(t.entry_market_event_id, 40))}</td></tr>`
        )
        .join('')
    : '<tr><td colspan="12" class="muted">No closed trades yet</td></tr>';

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

  const op = v.operator || {};
  const gate = op.next_open_gate || {};
  const gOk = gate.ok === true;
  const pq = op.paper_equity_usd || {};
  const eqStr =
    pq.equity_usd != null && typeof pq.equity_usd === 'number' && Number.isFinite(pq.equity_usd)
      ? pq.equity_usd.toFixed(4)
      : '—';
  let operatorBlock = '<p class="muted">Operator state unavailable.</p>';
  if (!op.error) {
    const postOk = op.operator_controls?.post_token_configured;
    const stakeOk = op.operator_controls?.paper_stake_edit_allowed;
    operatorBlock = `${liveStrip}
      <p><strong>Funding mode (SQLite)</strong> <code>${esc(op.sean_funding_mode || 'paper')}</code>
        · PAPER_TRADING env: ${op.paper_trading_env ? '<span class="ok">on (simulated)</span>' : '<span class="warn">off</span> (compose uses live path for chain gate)</p>
      <p><strong>Paper equity</strong> ~${esc(eqStr)} USD
        <span class="muted">(start ${esc(String(pq.starting_usd ?? '—'))} + realized ${esc(String(pq.realized_pnl_usd ?? '—'))} + unreal ${esc(String(pq.unrealized_usd ?? '—'))})</span></p>
      <p><strong>On-chain SOL</strong> (cached) ${esc(op.chain_sol_balance_lamports || '—')} lamports
        <span class="muted">${esc(op.chain_balance_updated_utc || '')}</span></p>
      ${op.chain_balance_error ? `<p class="bad">${esc(op.chain_balance_error)}</p>` : ''}
      <p><strong>Next engine open</strong> ${gOk ? '<span class="ok">allowed</span>' : '<span class="bad">blocked</span>'} — ${esc(gate.reason || '—')}
        <span class="muted">${esc(gate.detail || '')}</span></p>
      <p class="muted">${postOk ? 'POST /api/operator/* is enabled (token set on server).' : 'POST controls disabled — set JUPITER_OPERATOR_TOKEN in jupiter-web compose.'}</p>
      ${
        postOk
          ? `<details><summary>Change mode / paper stake</summary>
      <p class="muted">Bearer token matches <code>JUPITER_OPERATOR_TOKEN</code> on the server.</p>
      <p><label>Token <input type="password" id="jw-op-token" size="28" autocomplete="off"/></label></p>
      <p><label>Mode <select id="jw-mode"><option value="paper">paper</option><option value="chain">chain</option></select></label>
        <button type="button" id="jw-save-mode">Save mode</button></p>
      ${
        stakeOk
          ? `<p><label>Paper stake (USD) <input type="text" id="jw-stake" size="10" placeholder="1000"/></label>
        <button type="button" id="jw-save-stake">Save stake</button></p>`
          : '<p class="muted">Paper stake edit: set SEAN_ALLOW_PAPER_STAKE_EDIT=1 on jupiter-web.</p>'
      }
      </details>
      <script>
      (function(){
        function tok(){ return (document.getElementById('jw-op-token')||{}).value||''; }
        document.getElementById('jw-save-mode')?.addEventListener('click', async function(){
          const mode = (document.getElementById('jw-mode')||{}).value||'paper';
          const r = await fetch('/api/operator/funding-mode', { method:'POST', headers:{'Authorization':'Bearer '+tok(),'Content-Type':'application/json'}, body: JSON.stringify({mode}) });
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
          : ''
      }`;
  } else {
    operatorBlock = `<p class="warn">${esc(op.error)}</p>`;
  }

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
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel">
      <h1>Jupiter — TUI parity (read-only)</h1>
      <p class="muted">Same checks + SQLite + ledger paths as preflight_pyth_tui.py · Auto-refresh ${esc(String(v.refresh_sec || 0))}s (JUPITER_WEB_REFRESH_SEC, 0=off)</p>
      <p class="muted">${esc(v.sqlite_path)} · repo: ${esc(v.repo_root)}</p>
      <p><a href="https://jup.ag/perps/long/SOL-SOL" target="_blank" rel="noopener noreferrer">jup.ag SOL perps</a> · <a href="/api/summary.json">summary.json</a> · <a href="/api/operator/state.json">operator/state.json</a> · <a href="/api/live-market.json">live-market.json</a> · <a href="/health">health</a></p>
    </section>
    ${v.error ? `<section class="panel"><p class="warn">${esc(v.error)}</p></section>` : ''}
    <section class="panel"><h2>Trading mode</h2>${tradingBlock}</section>
    <section class="panel"><h2>Live market &amp; funding gates</h2>${operatorBlock}</section>
    <section class="panel"><h2>Active policy</h2>${policyBlock}</section>
    <section class="panel"><h2>Wallet (SeanV3 parity DB)</h2>${walletBlock}</section>
    <section class="panel"><h2>SeanV3 paper ledger (testing)</h2>${ledgerBlock}</section>
    <section class="panel"><h2>Parity (Sean V3 vs BlackBox baseline)</h2>
      <p class="muted">Sean: ${esc(v.parity?.sean_db || '')} · Ledger: ${esc(v.parity?.ledger_db || '')}</p>
      <div class="scroll"><table><thead><tr><th>market_event_id</th><th>Sean V3</th><th>BlackBox</th><th>Parity</th></tr></thead><tbody>${parityRows}</tbody></table></div>
    </section>
    <section class="panel"><h2>Position &amp; last kline (Sean DB)</h2>${posBlock}${klBlock}</section>
    <section class="panel"><h2>Trade window (ledger rows)</h2>
      <div class="scroll"><table><thead><tr><th>trade_id</th><th>exit UTC</th><th>entry UTC</th><th>sym</th><th>side</th><th>entry px</th><th>exit px</th><th>size</th><th>PnL</th><th>result</th><th>exit</th><th>market_event_id</th></tr></thead><tbody>${tradeRows}</tbody></table></div>
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

    if (
      req.method === 'POST' &&
      (url.pathname === '/api/operator/funding-mode' || url.pathname === '/api/operator/paper-stake')
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

    if (url.pathname === '/' || url.pathname === '/index.html') {
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
  console.error(`[jupiter] http://${bind}:${port}/  (TUI parity view)`);
});
