/**
 * Parity analog: Binance REST (host VPN routing) + SQLite (poll + paper analog).
 *
 * - NDJSON: CAPTURE_PATH
 * - SQLite: SQLITE_PATH — sean_binance_kline_poll + paper_wallet + paper_trade_log
 * - Wallet: KEYPAIR_PATH (optional) — pubkey only in DB; never stores secrets in logs
 * - Paper: no chain txs; stub signals for comparison to Blackbox Sean V3 (Python authoritative)
 *
 * Requires: node --experimental-sqlite (Node 22+)
 */
import { appendFile, mkdir } from 'fs/promises';
import { dirname } from 'path';
import { access } from 'fs/promises';
import { DatabaseSync } from 'node:sqlite';

import {
  ensurePaperAnalogSchema,
  getMeta,
  logPaperEvent,
  logStubPaperSignal,
  setMeta,
  upsertPaperWallet,
} from './paper_analog.mjs';
import { loadPubkeyFromKeypairFile } from './wallet_connect.mjs';

const url =
  process.env.BINANCE_KLINES_URL ||
  'https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=1';
const intervalMs = Math.max(
  5_000,
  parseInt(process.env.POLL_INTERVAL_MS || '300000', 10)
);
const capturePath = (process.env.CAPTURE_PATH || '').trim();
const sqlitePath = (process.env.SQLITE_PATH || '').trim();
const canonicalSymbol = (process.env.CANONICAL_SYMBOL || 'SOL-PERP').trim();
const keypairPath = (process.env.KEYPAIR_PATH || '').trim();
const paperTrading =
  (process.env.PAPER_TRADING || '1').trim().toLowerCase() !== '0' &&
  (process.env.PAPER_TRADING || '1').trim().toLowerCase() !== 'false';

function marketEventIdFromOpenTimeMs(openTimeMs) {
  const d = new Date(Number(openTimeMs));
  const pad = (n) => String(n).padStart(2, '0');
  const iso = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`;
  return `${canonicalSymbol}_5m_${iso}`;
}

function summarizeKline(row) {
  if (!Array.isArray(row) || row.length < 7) return row;
  return {
    openTime: row[0],
    open: row[1],
    high: row[2],
    low: row[3],
    close: row[4],
    volume: row[5],
    closeTime: row[6],
  };
}

/** @type {import('node:sqlite').DatabaseSync | null} */
let parityDb = null;
/** @type {string | null} */
let walletPubkey = null;

function initSqlite() {
  if (!sqlitePath) return null;
  try {
    const db = new DatabaseSync(sqlitePath);
    db.exec(`
      CREATE TABLE IF NOT EXISTS sean_binance_kline_poll (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_event_id TEXT NOT NULL,
        candle_open_ms INTEGER NOT NULL,
        open_px TEXT,
        high_px TEXT,
        low_px TEXT,
        close_px TEXT,
        volume_base TEXT,
        polled_at_utc TEXT NOT NULL,
        url TEXT,
        latency_ms INTEGER
      );
      CREATE INDEX IF NOT EXISTS idx_sean_poll_mid ON sean_binance_kline_poll (market_event_id);
    `);
    ensurePaperAnalogSchema(db);
    return db;
  } catch (e) {
    console.error(`[binance-klines-mini] SQLite init failed: ${e.message}`);
    return null;
  }
}

function insertKlinePoll(db, { marketEventId, openMs, kline, polledAt, latencyMs, reqUrl }) {
  const stmt = db.prepare(`
    INSERT INTO sean_binance_kline_poll (
      market_event_id, candle_open_ms, open_px, high_px, low_px, close_px, volume_base,
      polled_at_utc, url, latency_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  stmt.run(
    marketEventId,
    openMs,
    kline.open ?? null,
    kline.high ?? null,
    kline.low ?? null,
    kline.close ?? null,
    kline.volume ?? null,
    polledAt,
    reqUrl,
    latencyMs
  );
}

async function appendNdjsonLine(obj) {
  if (!capturePath) return;
  await mkdir(dirname(capturePath), { recursive: true });
  await appendFile(
    capturePath,
    JSON.stringify({ source: 'binance_klines_mini', ...obj }) + '\n',
    'utf8'
  );
}

async function connectWalletOnce(db) {
  if (!keypairPath) {
    console.error('[binance-klines-mini] KEYPAIR_PATH unset — paper wallet not connected (pubkey-only mode skipped)');
    setMeta(db, 'wallet_status', 'no_keypair_path');
    logPaperEvent(db, {
      atUtc: new Date().toISOString(),
      marketEventId: null,
      eventKind: 'wallet_skipped',
      ohlcvJson: null,
      walletPubkey: null,
      detailsJson: JSON.stringify({ reason: 'KEYPAIR_PATH empty' }),
    });
    return;
  }
  try {
    await access(keypairPath);
  } catch {
    console.error(`[binance-klines-mini] KEYPAIR_PATH not readable: ${keypairPath}`);
    setMeta(db, 'wallet_status', 'keypair_missing');
    logPaperEvent(db, {
      atUtc: new Date().toISOString(),
      marketEventId: null,
      eventKind: 'wallet_error',
      ohlcvJson: null,
      walletPubkey: null,
      detailsJson: JSON.stringify({ reason: 'file_not_found', path: keypairPath }),
    });
    return;
  }
  try {
    const w = await loadPubkeyFromKeypairFile(keypairPath);
    if (!w) return;
    walletPubkey = w.pubkeyBase58;
    upsertPaperWallet(db, { pubkeyBase58: w.pubkeyBase58, keypairPath });
    setMeta(db, 'wallet_status', 'connected');
    setMeta(
      db,
      'financial_api_routing',
      'host_table_wireguard_binance — see VPN/README.md; container uses network_mode:host'
    );
    logPaperEvent(db, {
      atUtc: new Date().toISOString(),
      marketEventId: null,
      eventKind: 'wallet_connected',
      ohlcvJson: null,
      walletPubkey: walletPubkey,
      detailsJson: JSON.stringify({
        paper_only: true,
        pubkey: walletPubkey,
        keypair_path: keypairPath,
      }),
    });
    console.error(`[binance-klines-mini] paper wallet pubkey: ${walletPubkey}`);
  } catch (e) {
    console.error(`[binance-klines-mini] wallet load failed: ${e.message}`);
    logPaperEvent(db, {
      atUtc: new Date().toISOString(),
      marketEventId: null,
      eventKind: 'wallet_error',
      ohlcvJson: null,
      walletPubkey: null,
      detailsJson: JSON.stringify({ error: String(e.message) }),
    });
  }
}

function processPaperAnalog(db, { marketEventId, kline }) {
  if (!paperTrading) return;
  const ohlcvJson = JSON.stringify(kline);
  logPaperEvent(db, {
    atUtc: new Date().toISOString(),
    marketEventId,
    eventKind: 'binance_kline_ingest',
    ohlcvJson,
    walletPubkey,
    detailsJson: JSON.stringify({
      source: 'rest_klines',
      parity_note: 'Blackbox truth: binance_strategy_bars_5m + jupiter_3_sean_policy',
    }),
  });

  const lastStub = getMeta(db, 'last_stub_signal_open_ms');
  const openMs = String(kline.openTime ?? '');
  if (lastStub === openMs) return;
  setMeta(db, 'last_stub_signal_open_ms', openMs);
  logStubPaperSignal(db, {
    marketEventId,
    closePx: String(kline.close ?? ''),
    walletPubkey,
  });
}

async function fetchOnce() {
  const t0 = Date.now();
  const res = await fetch(url, {
    headers: { Accept: 'application/json' },
  });
  const latencyMs = Date.now() - t0;
  const bodyText = await res.text();
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${bodyText.slice(0, 200)}`);
  }
  let data;
  try {
    data = JSON.parse(bodyText);
  } catch {
    throw new Error(`Invalid JSON: ${bodyText.slice(0, 120)}`);
  }
  const kline = Array.isArray(data) && data.length ? summarizeKline(data[0]) : data;
  const polledAt = new Date().toISOString();
  const openMs = kline && kline.openTime != null ? Number(kline.openTime) : 0;
  const marketEventId = openMs > 0 ? marketEventIdFromOpenTimeMs(openMs) : '';

  const record = {
    ok: true,
    at: polledAt,
    latencyMs,
    url,
    kline,
    market_event_id: marketEventId || undefined,
    paper_wallet: walletPubkey || undefined,
  };
  console.log(JSON.stringify(record));
  await appendNdjsonLine(record);

  if (parityDb && marketEventId && kline) {
    try {
      insertKlinePoll(parityDb, {
        marketEventId,
        openMs,
        kline,
        polledAt,
        latencyMs,
        reqUrl: url,
      });
      processPaperAnalog(parityDb, { marketEventId, kline });
    } catch (e) {
      console.error(`[binance-klines-mini] sqlite insert failed: ${e.message}`);
    }
  }
}

async function main() {
  console.error(
    `[binance-klines-mini] poll every ${intervalMs}ms — ${url}` +
      (capturePath ? ` — ndjson: ${capturePath}` : '') +
      (sqlitePath ? ` — sqlite: ${sqlitePath}` : '') +
      ` — paper: ${paperTrading}` +
      (keypairPath ? ` — keypair: ${keypairPath}` : '')
  );
  parityDb = initSqlite();
  if (parityDb) {
    await connectWalletOnce(parityDb);
  }

  for (;;) {
    try {
      await fetchOnce();
    } catch (err) {
      const record = {
        ok: false,
        at: new Date().toISOString(),
        error: err instanceof Error ? err.message : String(err),
      };
      console.error(JSON.stringify(record));
      await appendNdjsonLine(record);
      if (parityDb) {
        logPaperEvent(parityDb, {
          atUtc: new Date().toISOString(),
          marketEventId: null,
          eventKind: 'binance_fetch_error',
          ohlcvJson: null,
          walletPubkey,
          detailsJson: JSON.stringify(record),
        });
      }
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
