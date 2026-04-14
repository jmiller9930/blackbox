/**
 * SeanV3-owned paper trade schema + ledger writer (no BlackBox dependency).
 */

const DEFAULT_ENGINE = 'jupiter_3_sean_v1';

/** @param {import('node:sqlite').DatabaseSync} db */
function _columnNames(db, table) {
  return new Set(db.prepare(`PRAGMA table_info(${table})`).all().map((r) => r.name));
}

/** @param {import('node:sqlite').DatabaseSync} db */
function migratePositionLifecycle(db) {
  const c = _columnNames(db, 'sean_paper_position');
  const add = (name, sql) => {
    if (!c.has(name)) {
      db.exec(`ALTER TABLE sean_paper_position ADD COLUMN ${name} ${sql}`);
      c.add(name);
    }
  };
  add('stop_loss', 'REAL');
  add('take_profit', 'REAL');
  add('initial_stop_loss', 'REAL');
  add('initial_take_profit', 'REAL');
  add('breakeven_applied', 'INTEGER NOT NULL DEFAULT 0');
  add('atr_entry', 'REAL');
  add('last_processed_market_event_id', 'TEXT');
}

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
      engine_id TEXT NOT NULL DEFAULT 'jupiter_3_sean_v1',
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
  migratePositionLifecycle(db);
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
 */
export function getPaperPosition(db) {
  const row = db.prepare(`SELECT * FROM sean_paper_position WHERE id = 1`).get();
  if (!row) {
    return _flatPosition();
  }
  const g = (k, d) => (row[k] != null && row[k] !== '' ? Number(row[k]) : d);
  const gs = (k) => (row[k] != null ? String(row[k]) : null);
  return {
    side: String(row.side),
    entry_price: g('entry_price', 0),
    size_notional_sol: g('size_notional_sol', 1),
    bars_held: g('bars_held', 0),
    entry_market_event_id: gs('entry_market_event_id'),
    entry_candle_open_ms: row.entry_candle_open_ms != null ? Number(row.entry_candle_open_ms) : null,
    opened_at_utc: gs('opened_at_utc'),
    metadata_json: gs('metadata_json'),
    stop_loss: row.stop_loss != null ? Number(row.stop_loss) : null,
    take_profit: row.take_profit != null ? Number(row.take_profit) : null,
    initial_stop_loss: row.initial_stop_loss != null ? Number(row.initial_stop_loss) : null,
    initial_take_profit: row.initial_take_profit != null ? Number(row.initial_take_profit) : null,
    breakeven_applied: Boolean(row.breakeven_applied),
    atr_entry: row.atr_entry != null ? Number(row.atr_entry) : null,
    last_processed_market_event_id: gs('last_processed_market_event_id'),
  };
}

function _flatPosition() {
  return {
    side: 'flat',
    entry_price: 0,
    size_notional_sol: 1,
    bars_held: 0,
    entry_market_event_id: null,
    entry_candle_open_ms: null,
    opened_at_utc: null,
    metadata_json: null,
    stop_loss: null,
    take_profit: null,
    initial_stop_loss: null,
    initial_take_profit: null,
    breakeven_applied: false,
    atr_entry: null,
    last_processed_market_event_id: null,
  };
}

/** @param {import('node:sqlite').DatabaseSync} db */
export function setPaperPositionFlat(db) {
  db.prepare(
    `UPDATE sean_paper_position SET
      side = 'flat',
      opened_at_utc = NULL,
      entry_market_event_id = NULL,
      entry_candle_open_ms = NULL,
      entry_price = 0,
      bars_held = 0,
      metadata_json = NULL,
      stop_loss = NULL,
      take_profit = NULL,
      initial_stop_loss = NULL,
      initial_take_profit = NULL,
      breakeven_applied = 0,
      atr_entry = NULL,
      last_processed_market_event_id = NULL
     WHERE id = 1`
  ).run();
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {object} o
 */
export function openPaperPosition(db, o) {
  const size = o.sizeNotionalSol ?? 1.0;
  const meta = JSON.stringify(o.metadata ?? {});
  const at = new Date().toISOString();
  db.prepare(
    `UPDATE sean_paper_position SET
      side = ?,
      opened_at_utc = ?,
      entry_market_event_id = ?,
      entry_candle_open_ms = ?,
      entry_price = ?,
      size_notional_sol = ?,
      bars_held = 0,
      metadata_json = ?,
      stop_loss = ?,
      take_profit = ?,
      initial_stop_loss = ?,
      initial_take_profit = ?,
      breakeven_applied = 0,
      atr_entry = ?,
      last_processed_market_event_id = ?
     WHERE id = 1`
  ).run(
    o.side,
    at,
    o.marketEventId,
    o.candleOpenMs,
    o.entryPrice,
    size,
    meta,
    o.stopLoss,
    o.takeProfit,
    o.initialStopLoss,
    o.initialTakeProfit,
    o.atrEntry,
    o.lastProcessedMarketEventId ?? o.marketEventId
  );
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {object} u
 */
export function updatePositionLifecycle(db, u) {
  db.prepare(
    `UPDATE sean_paper_position SET
      stop_loss = ?,
      take_profit = ?,
      breakeven_applied = ?,
      last_processed_market_event_id = ?,
      bars_held = bars_held + 1
     WHERE id = 1 AND side != 'flat'`
  ).run(
    u.stopLoss,
    u.takeProfit,
    u.breakevenApplied ? 1 : 0,
    u.lastProcessedMarketEventId
  );
}

export function incrementBarsHeld(db) {
  db.prepare(`UPDATE sean_paper_position SET bars_held = bars_held + 1 WHERE id = 1 AND side != 'flat'`).run();
}

/**
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
    t.engineId ?? DEFAULT_ENGINE,
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

export { DEFAULT_ENGINE as SEAN_DEFAULT_ENGINE_ID };
