-- Phase 5.1 — shared market_ticks (Pyth primary + Coinbase comparator + optional Jupiter implied)
-- Applied by scripts/runtime/market_data/store.ensure_market_schema

CREATE TABLE IF NOT EXISTS market_ticks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  inserted_at TEXT NOT NULL,
  primary_source TEXT NOT NULL,
  primary_price REAL,
  primary_observed_at TEXT,
  primary_publish_time INTEGER,
  primary_raw_json TEXT,
  comparator_source TEXT NOT NULL,
  comparator_price REAL,
  comparator_observed_at TEXT,
  comparator_raw_json TEXT,
  tertiary_source TEXT,
  tertiary_price REAL,
  tertiary_observed_at TEXT,
  tertiary_raw_json TEXT,
  gate_state TEXT NOT NULL,
  gate_reason TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_ticks_symbol_inserted
  ON market_ticks (symbol, inserted_at DESC, id DESC);
