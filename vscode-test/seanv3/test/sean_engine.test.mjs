import assert from 'node:assert';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { ensurePaperAnalogSchema, setMeta } from '../paper_analog.mjs';
import { ensureSeanLedgerSchema } from '../sean_ledger.mjs';
import { processSeanEngine } from '../sean_engine.mjs';
import { MIN_BARS } from '../jupiter_4_sean_policy.mjs';

function kline(ms, o, h, l, c, v = 1) {
  return {
    openTime: ms,
    open: String(o),
    high: String(h),
    low: String(l),
    close: String(c),
    volume: String(v),
  };
}

function insertBar(db, mid, ms, o, h, l, c, v) {
  db.prepare(
    `INSERT INTO sean_binance_kline_poll (
      market_event_id, candle_open_ms, open_px, high_px, low_px, close_px, volume_base,
      polled_at_utc, url, latency_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(mid, ms, String(o), String(h), String(l), String(c), String(v), 't', 'u', 1);
}

function createEngineTestDb() {
  const db = new DatabaseSync(':memory:');
  db.exec(`
    CREATE TABLE sean_binance_kline_poll (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      market_event_id TEXT NOT NULL,
      candle_open_ms INTEGER NOT NULL,
      open_px TEXT, high_px TEXT, low_px TEXT, close_px TEXT, volume_base TEXT,
      polled_at_utc TEXT NOT NULL, url TEXT, latency_ms INTEGER
    );
  `);
  ensurePaperAnalogSchema(db);
  ensureSeanLedgerSchema(db);
  return db;
}

function countBarDecisions(db) {
  return Number(db.prepare(`SELECT COUNT(*) AS c FROM sean_bar_decisions`).get().c || 0);
}

function seedWalletConnected(db) {
  setMeta(db, 'jupiter_active_policy', 'jup_v4');
  setMeta(db, 'wallet_status', 'connected');
  setMeta(db, 'paper_starting_balance_usd', '100000');
  db.prepare(
    `INSERT OR REPLACE INTO paper_wallet (id, pubkey_base58, connected_at_utc, paper_only)
     VALUES (1, 'So11111111111111111111111111111111111111112', ?, 1)`
  ).run(new Date().toISOString());
}

/** Flat OHLCV — JUPv4 yields no long/short signal (full eval, NO_TRADE). */
function seriesFlat(n) {
  const closes = Array(n).fill(100);
  const highs = closes.map((c) => c + 0.1);
  const lows = closes.map((c) => c - 0.1);
  const vols = Array(n).fill(1000);
  return { closes, highs, lows, vols };
}

/** Trend + last-bar rip — JUPv4 long signal (full eval, TRADE_OPEN when gates pass). */
function seriesLongOpen(n) {
  const closes = [];
  const highs = [];
  const lows = [];
  const vols = [];
  for (let i = 0; i < n - 3; i++) {
    const c = 100 - i * 0.02;
    closes.push(c);
    highs.push(c + 0.3);
    lows.push(c - 0.3);
    vols.push(1000);
  }
  closes.push(99, 98.5, 105);
  highs.push(99.5, 99, 106);
  lows.push(98.5, 98, 104);
  vols.push(1000, 1000, 200000);
  return { closes, highs, lows, vols };
}

/**
 * @param {{ closes: number[], highs: number[], lows: number[], vols: number[] }} s
 * @returns {{ marketEventId: string, kline: ReturnType<typeof kline> }}
 */
function insertOhlcvSeries(db, s) {
  const { closes, highs, lows, vols } = s;
  const base = 1e12;
  const step = 300000;
  for (let i = 0; i < closes.length; i++) {
    const ms = base + i * step;
    insertBar(db, `t${i}`, ms, closes[i], highs[i], lows[i], closes[i], vols[i]);
  }
  const last = closes.length - 1;
  return {
    marketEventId: `t${last}`,
    kline: kline(base + last * step, closes[last], highs[last], lows[last], closes[last], vols[last]),
  };
}

test('warmup / insufficient bars: no sean_bar_decisions row', () => {
  const db = createEngineTestDb();
  seedWalletConnected(db);
  insertBar(db, 'm1', 1e12, 100, 101, 99, 100, 1000);
  processSeanEngine(db, { marketEventId: 'm1', kline: kline(1e12, 100, 101, 99, 100) });
  assert.strictEqual(countBarDecisions(db), 0);
  db.close();
});

test('NO_TRADE: one decision row after full flat evaluation without open', () => {
  const db = createEngineTestDb();
  seedWalletConnected(db);
  const ctx = insertOhlcvSeries(db, seriesFlat(MIN_BARS));
  processSeanEngine(db, ctx);
  assert.strictEqual(countBarDecisions(db), 1);
  const row = db.prepare(`SELECT outcome, reason_code, candidate_side FROM sean_bar_decisions`).get();
  assert.strictEqual(row.outcome, 'NO_TRADE');
  assert.strictEqual(row.reason_code, 'no_candidate_side');
  assert.strictEqual(row.candidate_side, 'none');
  db.close();
});

test('TRADE_OPEN: one decision row after full flat evaluation opens position', () => {
  const db = createEngineTestDb();
  seedWalletConnected(db);
  const ctx = insertOhlcvSeries(db, seriesLongOpen(MIN_BARS));
  processSeanEngine(db, ctx);
  assert.strictEqual(countBarDecisions(db), 1);
  const row = db.prepare(`SELECT outcome, reason_code, market_event_id FROM sean_bar_decisions`).get();
  assert.strictEqual(row.outcome, 'TRADE_OPEN');
  assert.strictEqual(row.reason_code, 'trade_open_ok');
  assert.strictEqual(row.market_event_id, ctx.marketEventId);
  const pos = db.prepare(`SELECT side FROM sean_paper_position WHERE id=1`).get();
  assert.strictEqual(pos.side, 'long');
  db.close();
});

test('duplicate market_event_id: second call does not add a decision row', () => {
  const db = createEngineTestDb();
  seedWalletConnected(db);
  const ctx = insertOhlcvSeries(db, seriesFlat(MIN_BARS));
  processSeanEngine(db, ctx);
  assert.strictEqual(countBarDecisions(db), 1);
  processSeanEngine(db, ctx);
  assert.strictEqual(countBarDecisions(db), 1);
  db.close();
});
