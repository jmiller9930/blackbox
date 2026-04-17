/**
 * Parity analog: Binance REST + SQLite (poll + paper analog).
 *
 * Binance MUST use the host routing table (WireGuard/Proton split-tunnel on clawbot). Deploy with
 * docker-compose network_mode:host only — see VPN/README.md. No VPN inside the container.
 *
 * - NDJSON: CAPTURE_PATH
 * - SQLite: SQLITE_PATH — sean_binance_kline_poll + Sean ledger (sean_paper_position, sean_paper_trades) + paper_wallet + paper_trade_log
 * - Wallet: KEYPAIR_PATH (optional) — pubkey only in DB; never stores secrets in logs
 * - Paper: no chain txs; stub + analog events; Sean trade engine: sean_ledger + sean_engine (Jupiter_3)
 *
 * Requires: node --experimental-sqlite (Node 22+)
 */
import { appendFile, mkdir } from 'fs/promises';
import { dirname } from 'path';
import { access } from 'fs/promises';
import { DatabaseSync } from 'node:sqlite';

import {
  ensurePaperAnalogSchema,
  ensurePaperStartingBalanceUsd,
  getMeta,
  logPaperEvent,
  logStubPaperSignal,
  setMeta,
  upsertPaperWallet,
} from './paper_analog.mjs';
import { processSeanEngine } from './sean_engine.mjs';
import { ensureSeanLedgerSchema } from './sean_ledger.mjs';
import { loadPubkeyFromKeypairFile } from './wallet_connect.mjs';

async function refreshChainBalanceCache(db) {
  if (!walletPubkey) return;
  const rpc = (process.env.SOLANA_RPC_URL || 'https://api.mainnet-beta.solana.com').trim();
  try {
    const { Connection, PublicKey } = await import('@solana/web3.js');
    const conn = new Connection(rpc, 'confirmed');
    const lamports = await conn.getBalance(new PublicKey(walletPubkey));
    setMeta(db, 'chain_sol_balance_lamports', String(lamports));
    setMeta(db, 'chain_sol_balance_updated_utc', new Date().toISOString());
    setMeta(db, 'chain_balance_error', '');
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    setMeta(db, 'chain_balance_error', msg);
  }
}

const _binanceOrigin = (
  process.env.BINANCE_API_BASE_URL ||
  process.env.BINANCE_REST_BASE_URL ||
  'https://api.binance.com'
)
  .trim()
  .replace(/\/$/, '');
const url =
  process.env.BINANCE_KLINES_URL ||
  `${_binanceOrigin}/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=1`;
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

const seanEngineSliceOn = () => {
  const v = (process.env.SEAN_ENGINE_SLICE ?? '1').trim().toLowerCase();
  return v !== '0' && v !== 'false' && v !== 'no';
};

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
    ensurePaperStartingBalanceUsd(db);
    ensureSeanLedgerSchema(db);
    if (!getMeta(db, 'sean_funding_mode')) {
      setMeta(db, 'sean_funding_mode', 'paper');
    }
    return db;
  } catch (e) {
    console.error(`[seanv3] SQLite init failed: ${e.message}`);
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
    JSON.stringify({ source: 'seanv3', ...obj }) + '\n',
    'utf8'
  );
}

async function connectWalletOnce(db) {
  const existingPw = db.prepare(`SELECT pubkey_base58, keypair_path FROM paper_wallet WHERE id=1`).get();
  const kpTag = existingPw?.keypair_path != null ? String(existingPw.keypair_path) : '';
  if (!keypairPath) {
    if (existingPw?.pubkey_base58 && kpTag === 'jupiter_operator_ui') {
      walletPubkey = String(existingPw.pubkey_base58);
      setMeta(db, 'wallet_status', 'connected');
      console.error('[seanv3] paper wallet: operator UI pubkey (no KEYPAIR_PATH on host)');
      return;
    }
    console.error('[seanv3] KEYPAIR_PATH unset — paper wallet not connected (pubkey-only mode skipped)');
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
    console.error(`[seanv3] KEYPAIR_PATH not readable: ${keypairPath}`);
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
    console.error(`[seanv3] paper wallet pubkey: ${walletPubkey}`);
  } catch (e) {
    console.error(`[seanv3] wallet load failed: ${e.message}`);
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
      ingest_note: 'SeanV3 sean_binance_kline_poll',
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
      await refreshChainBalanceCache(parityDb);
      processPaperAnalog(parityDb, { marketEventId, kline });
      if (seanEngineSliceOn()) {
        try {
          await processSeanEngine(parityDb, { marketEventId, kline });
        } catch (engErr) {
          console.error(`[seanv3] sean_engine failed: ${engErr.message}`);
        }
      }
    } catch (e) {
      console.error(`[seanv3] sqlite insert failed: ${e.message}`);
    }
  }
}

async function main() {
  console.error(
    `[seanv3] poll every ${intervalMs}ms — ${url}` +
      (capturePath ? ` — ndjson: ${capturePath}` : '') +
      (sqlitePath ? ` — sqlite: ${sqlitePath}` : '') +
      ` — paper: ${paperTrading}` +
      ` — sean_engine: ${seanEngineSliceOn()}` +
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
