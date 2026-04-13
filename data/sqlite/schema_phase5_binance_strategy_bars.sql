-- Jupiter_3 only — Binance-authoritative 5m OHLC + exchange volume (not Pyth-derived OHLC).
-- V2 / Jupiter_2 continues to use market_bars_5m unchanged.

CREATE TABLE IF NOT EXISTS binance_strategy_bars_5m (
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
  volume_base_asset REAL,
  quote_volume_usdt REAL,
  price_source TEXT NOT NULL DEFAULT 'binance_klines_strategy_v1',
  bar_schema_version TEXT NOT NULL DEFAULT 'binance_strategy_bar_v1',
  computed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_binance_strategy_bars_5m_symbol_open
  ON binance_strategy_bars_5m (canonical_symbol, candle_open_utc DESC);

CREATE INDEX IF NOT EXISTS idx_binance_strategy_bars_5m_event
  ON binance_strategy_bars_5m (market_event_id);
