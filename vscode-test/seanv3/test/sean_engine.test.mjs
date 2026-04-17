import assert from 'node:assert';
import { mkdirSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { join } from 'node:path';
import os from 'node:os';

import { ensurePaperAnalogSchema, setMeta } from '../paper_analog.mjs';
import { ensureSeanLedgerSchema } from '../sean_ledger.mjs';
import { processSeanEngine } from '../sean_engine.mjs';

const H64 = 'a'.repeat(64);

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

function setupRepoWithArtifact() {
  const root = mkdtempSync(join(os.tmpdir(), 'sean-engine-artifact-'));
  const manifest = {
    schema: 'kitchen_policy_deployment_manifest_v1',
    entries: [
      {
        execution_target: 'jupiter',
        deployed_runtime_policy_id: 'dep_test_1',
        submission_id: 'sub_test',
        content_sha256: H64,
      },
    ],
  };
  mkdirSync(join(root, 'renaissance_v4', 'config'), { recursive: true });
  writeFileSync(
    join(root, 'renaissance_v4', 'config', 'kitchen_policy_deployment_manifest_v1.json'),
    JSON.stringify(manifest, null, 2),
    'utf8'
  );
  const artDir = join(root, 'renaissance_v4', 'state', 'policy_intake_submissions', 'sub_test', 'artifacts');
  mkdirSync(artDir, { recursive: true });
  const ev = `export const MIN_BARS = 71;
export const POLICY_ENGINE_TAG = 'test_eval';
export function generateSignalFromOhlc(closes, highs, lows, vols) {
  const n = closes.length;
  const c = closes[n - 1];
  return { longSignal: false, shortSignal: false, signalPrice: c, diag: { atr: 1.0 } };
}`;
  writeFileSync(join(artDir, 'evaluator.mjs'), ev, 'utf8');
  return root;
}

function seedWalletConnected(db, repoRoot) {
  const prev = process.env.BLACKBOX_REPO_ROOT;
  process.env.BLACKBOX_REPO_ROOT = repoRoot;
  setMeta(db, 'jupiter_active_policy', 'dep_test_1');
  setMeta(db, 'wallet_status', 'connected');
  setMeta(db, 'paper_starting_balance_usd', '100000');
  db.prepare(
    `INSERT OR REPLACE INTO paper_wallet (id, pubkey_base58, connected_at_utc, paper_only)
     VALUES (1, 'So11111111111111111111111111111111111111112', ?, 1)`
  ).run(new Date().toISOString());
  return () => {
    if (prev === undefined) delete process.env.BLACKBOX_REPO_ROOT;
    else process.env.BLACKBOX_REPO_ROOT = prev;
  };
}

/** Flat OHLCV — evaluator returns no long/short (full eval, NO_TRADE). */
function seriesFlat(n) {
  const closes = Array(n).fill(100);
  const highs = closes.map((c) => c + 0.1);
  const lows = closes.map((c) => c - 0.1);
  const vols = Array(n).fill(1000);
  return { closes, highs, lows, vols };
}

/**
 * @param {{ closes: number[], highs: number[], lows: number[], vols: number[] }} s
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

const MIN_BARS = 71;

test('warmup / insufficient bars: no sean_bar_decisions row', async () => {
  const repo = setupRepoWithArtifact();
  const db = createEngineTestDb();
  const restore = seedWalletConnected(db, repo);
  try {
    insertBar(db, 'm1', 1e12, 100, 101, 99, 100, 1000);
    await processSeanEngine(db, { marketEventId: 'm1', kline: kline(1e12, 100, 101, 99, 100) });
    assert.strictEqual(countBarDecisions(db), 0);
  } finally {
    restore();
    db.close();
    rmSync(repo, { recursive: true, force: true });
  }
});

test('NO_TRADE: one decision row after full flat evaluation without open', async () => {
  const repo = setupRepoWithArtifact();
  const db = createEngineTestDb();
  const restore = seedWalletConnected(db, repo);
  try {
    const ctx = insertOhlcvSeries(db, seriesFlat(MIN_BARS));
    await processSeanEngine(db, ctx);
    assert.strictEqual(countBarDecisions(db), 1);
    const row = db.prepare(`SELECT outcome, reason_code, candidate_side FROM sean_bar_decisions`).get();
    assert.strictEqual(row.outcome, 'NO_TRADE');
    assert.strictEqual(row.reason_code, 'no_candidate_side');
    assert.strictEqual(row.candidate_side, 'none');
  } finally {
    restore();
    db.close();
    rmSync(repo, { recursive: true, force: true });
  }
});

test('duplicate market_event_id: second call does not add a decision row', async () => {
  const repo = setupRepoWithArtifact();
  const db = createEngineTestDb();
  const restore = seedWalletConnected(db, repo);
  try {
    const ctx = insertOhlcvSeries(db, seriesFlat(MIN_BARS));
    await processSeanEngine(db, ctx);
    assert.strictEqual(countBarDecisions(db), 1);
    await processSeanEngine(db, ctx);
    assert.strictEqual(countBarDecisions(db), 1);
  } finally {
    restore();
    db.close();
    rmSync(repo, { recursive: true, force: true });
  }
});
