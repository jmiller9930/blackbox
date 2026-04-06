-- Trade lifecycle events (TP/SL/trail/open/close) — bucket 2 vs policy_evaluations (bucket 1).
-- Baseline paper: open + close on same bar until a real execution engine appends trail_update / tp_hit / sl_hit.

CREATE TABLE IF NOT EXISTS position_events (
  event_id TEXT PRIMARY KEY,
  trade_id TEXT NOT NULL,
  market_event_id TEXT NOT NULL,
  lane TEXT NOT NULL CHECK (lane IN ('baseline', 'anna')),
  sequence_num INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  schema_version TEXT NOT NULL DEFAULT 'position_event_v1',
  UNIQUE (trade_id, sequence_num)
);

CREATE INDEX IF NOT EXISTS idx_position_events_trade_seq
  ON position_events (trade_id, sequence_num);

CREATE INDEX IF NOT EXISTS idx_position_events_created
  ON position_events (created_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_position_events_market_event
  ON position_events (market_event_id);
