/**
 * SeanV3 paper analog: ingest + wallet + stub events — paper-only, no on-chain txs.
 * Market data uses host routing (WireGuard / Proton for Binance) via Docker network_mode:host.
 * Strategy truth and trade ledger for SeanV3 live in this stack (`sean_ledger`, engine); this table is auxiliary logging.
 */

/** @param {import('node:sqlite').DatabaseSync} db */
export function ensurePaperAnalogSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS analog_meta (
      k TEXT PRIMARY KEY,
      v TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS paper_wallet (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      pubkey_base58 TEXT NOT NULL,
      connected_at_utc TEXT NOT NULL,
      keypair_path TEXT,
      paper_only INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS paper_trade_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      at_utc TEXT NOT NULL,
      market_event_id TEXT,
      event_kind TEXT NOT NULL,
      ohlcv_json TEXT,
      wallet_pubkey TEXT,
      details_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_paper_log_mid ON paper_trade_log (market_event_id);
    CREATE INDEX IF NOT EXISTS idx_paper_log_kind ON paper_trade_log (event_kind);
  `);
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {{ pubkeyBase58: string, keypairPath: string }} w
 */
export function upsertPaperWallet(db, w) {
  const stmt = db.prepare(`
    INSERT INTO paper_wallet (id, pubkey_base58, connected_at_utc, keypair_path, paper_only)
    VALUES (1, ?, ?, ?, 1)
    ON CONFLICT(id) DO UPDATE SET
      pubkey_base58 = excluded.pubkey_base58,
      connected_at_utc = excluded.connected_at_utc,
      keypair_path = excluded.keypair_path,
      paper_only = 1
  `);
  stmt.run(w.pubkeyBase58, new Date().toISOString(), w.keypairPath);
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function setMeta(db, k, v) {
  const stmt = db.prepare(`INSERT INTO analog_meta (k, v) VALUES (?, ?)
    ON CONFLICT(k) DO UPDATE SET v = excluded.v`);
  stmt.run(k, v);
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function getMeta(db, k) {
  const row = db.prepare(`SELECT v FROM analog_meta WHERE k = ?`).get(k);
  return row ? String(row.v) : null;
}

/**
 * One-time: persist paper "account" size for testing (USD notional label — no real funds).
 * Env SEAN_PAPER_STARTING_BALANCE_USD (default 1000). Frozen in analog_meta after first set.
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function ensurePaperStartingBalanceUsd(db) {
  const existing = getMeta(db, 'paper_starting_balance_usd');
  if (existing != null && String(existing).trim() !== '') return;
  const raw = (process.env.SEAN_PAPER_STARTING_BALANCE_USD || '1000').trim();
  const n = parseFloat(raw);
  const v = Number.isFinite(n) && n > 0 ? String(n) : '1000';
  setMeta(db, 'paper_starting_balance_usd', v);
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function logPaperEvent(db, { atUtc, marketEventId, eventKind, ohlcvJson, walletPubkey, detailsJson }) {
  const stmt = db.prepare(`
    INSERT INTO paper_trade_log (at_utc, market_event_id, event_kind, ohlcv_json, wallet_pubkey, details_json)
    VALUES (?, ?, ?, ?, ?, ?)
  `);
  stmt.run(
    atUtc,
    marketEventId ?? null,
    eventKind,
    ohlcvJson ?? null,
    walletPubkey ?? null,
    detailsJson ?? null
  );
}

/**
 * Stub “paper signal” — not Sean V3 parity (use Python for that). Logs intent for pipeline comparison.
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {{ marketEventId: string, closePx: string, walletPubkey: string | null }} ctx
 */
export function logStubPaperSignal(db, ctx) {
  const details = JSON.stringify({
    engine: 'paper_analog_stub_v1',
    note: 'Legacy stub row; SeanV3 trade outcomes use sean_paper_trades + engine',
    side_suggestion: 'flat',
    execution: 'paper_only_no_chain',
  });
  logPaperEvent(db, {
    atUtc: new Date().toISOString(),
    marketEventId: ctx.marketEventId,
    eventKind: 'paper_signal_stub',
    ohlcvJson: null,
    walletPubkey: ctx.walletPubkey,
    detailsJson: details,
  });
}
