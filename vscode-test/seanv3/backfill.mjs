/**
 * One-shot backfill of sean_parity.db with historical Binance 5m klines (closed bars).
 *
 * Binance allows up to 1000 klines per request (~3.47 days of 5m bars).
 * Default limit 864 = 3 full days (3 * 24 * 12).
 *
 * Usage (host or container with /capture mounted):
 *   SQLITE_PATH=./capture/sean_parity.db node --experimental-sqlite backfill.mjs
 *   SQLITE_PATH=/capture/sean_parity.db LIMIT=864 node --experimental-sqlite backfill.mjs
 */
import { mkdirSync } from 'fs';
import { dirname } from 'path';
import { DatabaseSync } from 'node:sqlite';

const sqlitePath = (process.env.SQLITE_PATH || './capture/sean_parity.db').trim();
const symbol = (process.env.BINANCE_SYMBOL || 'SOLUSDT').trim();
const limit = Math.min(
  1000,
  Math.max(1, parseInt(process.env.LIMIT || '864', 10))
);
const canonicalSymbol = (process.env.CANONICAL_SYMBOL || 'SOL-PERP').trim();

function marketEventIdFromOpenTimeMs(openTimeMs) {
  const d = new Date(Number(openTimeMs));
  const pad = (n) => String(n).padStart(2, '0');
  const iso = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`;
  return `${canonicalSymbol}_5m_${iso}`;
}

function initDb(path) {
  mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
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
  return db;
}

async function main() {
  const binanceOrigin = (
    process.env.BINANCE_API_BASE_URL ||
    process.env.BINANCE_REST_BASE_URL ||
    'https://api.binance.com'
  )
    .trim()
    .replace(/\/$/, '');
  const url = `${binanceOrigin}/api/v3/klines?symbol=${encodeURIComponent(
    symbol
  )}&interval=5m&limit=${limit}`;
  const t0 = Date.now();
  const res = await fetch(url);
  const latencyMs = Date.now() - t0;
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  const data = JSON.parse(text);
  if (!Array.isArray(data)) {
    throw new Error('Expected array of klines');
  }

  const polledAt = new Date().toISOString();
  const db = initDb(sqlitePath);
  const stmt = db.prepare(`
    INSERT INTO sean_binance_kline_poll (
      market_event_id, candle_open_ms, open_px, high_px, low_px, close_px, volume_base,
      polled_at_utc, url, latency_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  let n = 0;
  for (const row of data) {
    const openMs = Number(row[0]);
    const kline = {
      open: row[1],
      high: row[2],
      low: row[3],
      close: row[4],
      volume: row[5],
    };
    const marketEventId = marketEventIdFromOpenTimeMs(openMs);
    stmt.run(
      marketEventId,
      openMs,
      kline.open ?? null,
      kline.high ?? null,
      kline.low ?? null,
      kline.close ?? null,
      kline.volume ?? null,
      polledAt,
      `backfill:${url}`,
      latencyMs
    );
    n += 1;
  }

  console.error(
    `[backfill] sqlite=${sqlitePath} inserted=${n} klines (limit=${limit}) symbol=${symbol}`
  );
  if (data.length > 0) {
    const first = data[0];
    const last = data[data.length - 1];
    console.error(
      `[backfill] range openTime ${first[0]} .. ${last[0]} (${n} bars)`
    );
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
