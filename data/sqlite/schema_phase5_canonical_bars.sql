-- Phase 5.2 — canonical 5m bars (identity); ticks remain input in market_ticks
-- Applied after schema_phase5_market_data.sql

CREATE TABLE IF NOT EXISTS market_bars_5m (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_symbol TEXT NOT NULL,
  tick_symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL DEFAULT '5m',
  candle_open_utc TEXT NOT NULL,
  candle_close_utc TEXT NOT NULL,
  market_event_id TEXT NOT NULL UNIQUE,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  tick_count INTEGER NOT NULL DEFAULT 0,
  volume_base REAL,
  price_source TEXT NOT NULL DEFAULT 'pyth_primary',
  bar_schema_version TEXT NOT NULL DEFAULT 'canonical_bar_v1',
  computed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_bars_5m_symbol_open
  ON market_bars_5m (canonical_symbol, candle_open_utc DESC);

CREATE INDEX IF NOT EXISTS idx_market_bars_5m_event
  ON market_bars_5m (market_event_id);
