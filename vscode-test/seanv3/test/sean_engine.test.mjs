import assert from 'node:assert';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { ensurePaperAnalogSchema } from '../paper_analog.mjs';
import { ensureSeanLedgerSchema } from '../sean_ledger.mjs';
import { processSeanEngine } from '../sean_engine.mjs';

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

test('engine runs without throw on insufficient bars', () => {
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
  insertBar(db, 'm1', 1e12, 100, 101, 99, 100, 1000);
  processSeanEngine(db, { marketEventId: 'm1', kline: kline(1e12, 100, 101, 99, 100) });
  db.close();
});
