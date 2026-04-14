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

function readStartingUsd(db) {
  try {
    const row = db.prepare(`SELECT v FROM analog_meta WHERE k = ?`).get('paper_starting_balance_usd');
    if (row?.v) {
      const n = parseFloat(String(row.v));
      if (Number.isFinite(n) && n > 0) return n;
    }
  } catch {
    /* no analog_meta yet */
  }
  const raw = (process.env.SEAN_PAPER_STARTING_BALANCE_USD || '1000').trim();
  const n = parseFloat(raw);
  return Number.isFinite(n) && n > 0 ? n : 1000;
}

function unrealizedUsd(entry, mark, size, side) {
  const sd = String(side).toLowerCase();
  if (sd === 'long') return (mark - entry) * size;
  if (sd === 'short') return (entry - mark) * size;
  return 0;
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

const startingUsd = readStartingUsd(db);

let posRow = null;
try {
  posRow = db.prepare(`SELECT side, entry_price, size_notional_sol FROM sean_paper_position WHERE id=1`).get();
} catch {
  /* schema */
}

let markPx = NaN;
try {
  const kr = db
    .prepare(`SELECT close_px FROM sean_binance_kline_poll ORDER BY id DESC LIMIT 1`)
    .get();
  if (kr?.close_px != null) markPx = parseFloat(String(kr.close_px));
} catch {
  /* */
}

let unrealized = 0;
let openSide = 'flat';
if (posRow && String(posRow.side) !== 'flat') {
  openSide = String(posRow.side);
  const entry = Number(posRow.entry_price);
  const size = Number(posRow.size_notional_sol) || 1;
  if (Number.isFinite(markPx) && Number.isFinite(entry)) {
    unrealized = unrealizedUsd(entry, markPx, size, openSide);
  }
}

const equityUsd = startingUsd + sumPnl + (String(openSide) !== 'flat' ? unrealized : 0);

console.log(JSON.stringify({
  sqlite: dbPath,
  paper_starting_balance_usd: Math.round(startingUsd * 1e6) / 1e6,
  trade_count: n,
  wins,
  losses,
  breakevens,
  win_rate: Math.round(winRate * 10000) / 10000,
  cumulative_realized_pnl_usd: Math.round(sumPnl * 1e6) / 1e6,
  /** @deprecated use cumulative_realized_pnl_usd */
  cumulative_pnl_usd: Math.round(sumPnl * 1e6) / 1e6,
  average_trade_pnl_usd: Math.round(avgPnl * 1e6) / 1e6,
  open_side: openSide,
  mark_px_usd_approx: Number.isFinite(markPx) ? Math.round(markPx * 1e6) / 1e6 : null,
  unrealized_pnl_usd_approx: String(openSide) !== 'flat' && Number.isFinite(markPx)
    ? Math.round(unrealized * 1e6) / 1e6
    : 0,
  paper_equity_usd: Math.round(equityUsd * 1e6) / 1e6,
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
