-- Parallel execution ledger — full trade identity (baseline vs Anna, same market_event_id).
-- Multiple rows per market_event_id allowed (different strategy_id / trade_id).

CREATE TABLE IF NOT EXISTS strategy_registry (
  strategy_id TEXT PRIMARY KEY,
  title TEXT,
  description TEXT,
  registered_at_utc TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'catalog'
);

CREATE TABLE IF NOT EXISTS execution_trades (
  trade_id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  lane TEXT NOT NULL CHECK (lane IN ('baseline', 'anna')),
  mode TEXT NOT NULL CHECK (mode IN ('live', 'paper')),
  market_event_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  side TEXT,
  entry_time TEXT,
  entry_price REAL,
  size REAL,
  exit_time TEXT,
  exit_price REAL,
  exit_reason TEXT,
  pnl_usd REAL,
  context_snapshot_json TEXT,
  notes TEXT,
  schema_version TEXT NOT NULL DEFAULT 'execution_trade_v1',
  created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_trades_market_event
  ON execution_trades (market_event_id);

CREATE INDEX IF NOT EXISTS idx_execution_trades_strategy
  ON execution_trades (strategy_id, created_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_execution_trades_lane_mode
  ON execution_trades (lane, mode, created_at_utc DESC);
