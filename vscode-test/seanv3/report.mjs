#!/usr/bin/env node
/**
 * SeanV3 trade reporting — reads sean_parity.db (or SQLITE_PATH).
 * Usage: node report.mjs [--db /path/to/sean_parity.db]
 */
import { DatabaseSync } from 'node:sqlite';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function argvDb() {
  const i = process.argv.indexOf('--db');
  if (i >= 0 && process.argv[i + 1]) return resolve(process.argv[i + 1]);
  const env = (process.env.SQLITE_PATH || process.env.SEAN_SQLITE_PATH || '').trim();
  if (env) return resolve(env);
  return resolve(__dirname, 'capture', 'sean_parity.db');
}

const dbPath = argvDb();
const db = new DatabaseSync(dbPath);

const trades = db
  .prepare(
    `SELECT id, engine_id, side, entry_time_utc, exit_time_utc, gross_pnl_usd, result_class
     FROM sean_paper_trades ORDER BY id ASC`
  )
  .all();

const n = trades.length;
let wins = 0;
let losses = 0;
let breakevens = 0;
let sumPnl = 0;
for (const t of trades) {
  const g = Number(t.gross_pnl_usd);
  sumPnl += g;
  const rc = String(t.result_class || '');
  if (rc === 'win') wins += 1;
  else if (rc === 'loss') losses += 1;
  else breakevens += 1;
}

const winRate = n > 0 ? wins / n : 0;
const avgPnl = n > 0 ? sumPnl / n : 0;

console.log(JSON.stringify({
  sqlite: dbPath,
  trade_count: n,
  wins,
  losses,
  breakevens,
  win_rate: Math.round(winRate * 10000) / 10000,
  cumulative_pnl_usd: Math.round(sumPnl * 1e6) / 1e6,
  average_trade_pnl_usd: Math.round(avgPnl * 1e6) / 1e6,
}));

if (trades.length) {
  console.log('\nLast 10 trades:');
  for (const t of trades.slice(-10)) {
    console.log(
      `  #${t.id} ${t.side} ${t.result_class} pnl=${t.gross_pnl_usd} ${t.entry_time_utc?.slice(0, 19)} → ${t.exit_time_utc?.slice(0, 19)}`
    );
  }
}

db.close();
