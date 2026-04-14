/**
 * SeanV3-owned paper trade schema + ledger writer (no BlackBox dependency).
 * Closed trades land in sean_paper_trades; open state in sean_paper_position.
 */

/** @param {import('node:sqlite').DatabaseSync} db */
export function ensureSeanLedgerSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS sean_paper_position (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      side TEXT NOT NULL DEFAULT 'flat',
      opened_at_utc TEXT,
      entry_market_event_id TEXT,
      entry_candle_open_ms INTEGER,
      entry_price REAL NOT NULL DEFAULT 0,
      size_notional_sol REAL NOT NULL DEFAULT 1.0,
      bars_held INTEGER NOT NULL DEFAULT 0,
      metadata_json TEXT
    );
    CREATE TABLE IF NOT EXISTS sean_paper_trades (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      engine_id TEXT NOT NULL DEFAULT 'sean_engine_slice_v1',
      side TEXT NOT NULL,
      entry_market_event_id TEXT NOT NULL,
      exit_market_event_id TEXT NOT NULL,
      entry_time_utc TEXT NOT NULL,
      exit_time_utc TEXT NOT NULL,
      entry_price REAL NOT NULL,
      exit_price REAL NOT NULL,
      size_notional_sol REAL NOT NULL,
      gross_pnl_usd REAL NOT NULL,
      net_pnl_usd REAL,
      result_class TEXT NOT NULL,
      metadata_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_sean_trades_entry_mid ON sean_paper_trades (entry_market_event_id);
    CREATE INDEX IF NOT EXISTS idx_sean_trades_exit_utc ON sean_paper_trades (exit_time_utc);
  `);
  const row = db.prepare(`SELECT id FROM sean_paper_position WHERE id = 1`).get();
  if (!row) {
    db.prepare(
      `INSERT INTO sean_paper_position (id, side, entry_price, size_notional_sol, bars_held)
       VALUES (1, 'flat', 0, 1.0, 0)`
    ).run();
  }
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @returns {{ side: string, entry_price: number, size_notional_sol: number, bars_held: number, entry_market_event_id: string | null, entry_candle_open_ms: number | null, opened_at_utc: string | null, metadata_json: string | null }}
 */
export function getPaperPosition(db) {
  const row = db.prepare(`SELECT * FROM sean_paper_position WHERE id = 1`).get();
  if (!row) {
    return {
      side: 'flat',
      entry_price: 0,
      size_notional_sol: 1,
      bars_held: 0,
      entry_market_event_id: null,
      entry_candle_open_ms: null,
      opened_at_utc: null,
      metadata_json: null,
    };
  }
  return {
    side: String(row.side),
    entry_price: Number(row.entry_price),
    size_notional_sol: Number(row.size_notional_sol),
    bars_held: Number(row.bars_held),
    entry_market_event_id: row.entry_market_event_id != null ? String(row.entry_market_event_id) : null,
    entry_candle_open_ms:
      row.entry_candle_open_ms != null ? Number(row.entry_candle_open_ms) : null,
    opened_at_utc: row.opened_at_utc != null ? String(row.opened_at_utc) : null,
    metadata_json: row.metadata_json != null ? String(row.metadata_json) : null,
  };
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {object} p
 */
export function setPaperPositionFlat(db) {
  db.prepare(
    `UPDATE sean_paper_position SET
      side = 'flat',
      opened_at_utc = NULL,
      entry_market_event_id = NULL,
      entry_candle_open_ms = NULL,
      entry_price = 0,
      bars_held = 0,
      metadata_json = NULL
     WHERE id = 1`
  ).run();
}

/**
 * Open a long paper position (slice engine — single position slot).
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {{ marketEventId: string, candleOpenMs: number, entryPrice: number, sizeNotionalSol?: number, metadata?: object }} o
 */
export function openPaperLong(db, o) {
  const size = o.sizeNotionalSol ?? 1.0;
  const meta = JSON.stringify(o.metadata ?? { note: 'sean_ledger' });
  const at = new Date().toISOString();
  db.prepare(
    `UPDATE sean_paper_position SET
      side = 'long',
      opened_at_utc = ?,
      entry_market_event_id = ?,
      entry_candle_open_ms = ?,
      entry_price = ?,
      size_notional_sol = ?,
      bars_held = 0,
      metadata_json = ?
     WHERE id = 1`
  ).run(at, o.marketEventId, o.candleOpenMs, o.entryPrice, size, meta);
}

/**
 * Increment bars_held while carrying a position (new bar while still open).
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function incrementBarsHeld(db) {
  db.prepare(`UPDATE sean_paper_position SET bars_held = bars_held + 1 WHERE id = 1 AND side != 'flat'`).run();
}

/**
 * Write a completed trade and reset position to flat.
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {object} t
 */
export function writeClosedTradeAndFlat(db, t) {
  const gross = Number(t.grossPnlUsd);
  let resultClass = 'breakeven';
  if (gross > 1e-9) resultClass = 'win';
  else if (gross < -1e-9) resultClass = 'loss';

  const stmt = db.prepare(`
    INSERT INTO sean_paper_trades (
      engine_id, side, entry_market_event_id, exit_market_event_id,
      entry_time_utc, exit_time_utc, entry_price, exit_price, size_notional_sol,
      gross_pnl_usd, net_pnl_usd, result_class, metadata_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  stmt.run(
    t.engineId ?? 'sean_engine_slice_v1',
    t.side,
    t.entryMarketEventId,
    t.exitMarketEventId,
    t.entryTimeUtc,
    t.exitTimeUtc,
    t.entryPrice,
    t.exitPrice,
    t.sizeNotionalSol,
    gross,
    t.netPnlUsd != null ? Number(t.netPnlUsd) : null,
    resultClass,
    t.metadataJson ?? null
  );
  setPaperPositionFlat(db);
}
