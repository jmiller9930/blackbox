-- Per closed-bar policy outcome (baseline / future Anna) for backtest replay and joins to market_bars_5m.
-- Same DB file as execution_ledger.db; optional FK to market tape is logical (market_event_id).

CREATE TABLE IF NOT EXISTS policy_evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_event_id TEXT NOT NULL,
  lane TEXT NOT NULL CHECK (lane IN ('baseline', 'anna')),
  strategy_id TEXT NOT NULL,
  signal_mode TEXT NOT NULL,
  tick_mode TEXT NOT NULL CHECK (tick_mode IN ('live', 'paper')),
  trade INTEGER NOT NULL CHECK (trade IN (0, 1)),
  side TEXT,
  reason_code TEXT NOT NULL,
  features_json TEXT NOT NULL,
  pnl_usd REAL,
  evaluated_at_utc TEXT NOT NULL,
  schema_version TEXT NOT NULL DEFAULT 'policy_evaluation_v1',
  UNIQUE (market_event_id, lane, strategy_id, signal_mode)
);

CREATE INDEX IF NOT EXISTS idx_policy_evaluations_market_event
  ON policy_evaluations (market_event_id, evaluated_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_policy_evaluations_reason
  ON policy_evaluations (reason_code, evaluated_at_utc DESC);
