-- T2 decision_trace — stored, replayable step trace per (market_event_id, strategy_id).
-- Same DB file as execution_ledger.db; execution_trades.trace_id links to decision_traces.trace_id.

CREATE TABLE IF NOT EXISTS decision_traces (
  trace_id TEXT PRIMARY KEY,
  market_event_id TEXT NOT NULL,
  strategy_id TEXT NOT NULL,
  lane TEXT NOT NULL CHECK (lane IN ('baseline', 'anna')),
  mode TEXT NOT NULL CHECK (mode IN ('live', 'paper', 'paper_stub')),
  paper_stub INTEGER NOT NULL DEFAULT 0 CHECK (paper_stub IN (0, 1)),
  timestamp_start_utc TEXT NOT NULL,
  timestamp_end_utc TEXT NOT NULL,
  steps_json TEXT NOT NULL,
  trade_id TEXT,
  schema_version TEXT NOT NULL DEFAULT 'decision_trace_v1',
  created_at_utc TEXT NOT NULL,
  retrieved_memory_ids_json TEXT NOT NULL DEFAULT '[]',
  memory_used INTEGER NOT NULL DEFAULT 0,
  decision_summary TEXT,
  baseline_action_json TEXT,
  anna_action_json TEXT,
  memory_ablation_off INTEGER NOT NULL DEFAULT 0,
  learning_proof_schema TEXT DEFAULT 'learning_proof_v1'
);

CREATE INDEX IF NOT EXISTS idx_decision_traces_market_event
  ON decision_traces (market_event_id, timestamp_start_utc DESC);

CREATE INDEX IF NOT EXISTS idx_decision_traces_strategy
  ON decision_traces (strategy_id, timestamp_start_utc DESC);

CREATE INDEX IF NOT EXISTS idx_decision_traces_trade
  ON decision_traces (trade_id);
