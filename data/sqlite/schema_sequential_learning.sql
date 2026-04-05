-- Sequential learning loop — audit of SPRT evaluations (same DB as execution_ledger.db).

CREATE TABLE IF NOT EXISTS anna_sequential_decision_runs (
  run_id TEXT PRIMARY KEY,
  test_id TEXT NOT NULL,
  strategy_id TEXT NOT NULL,
  evaluated_at_utc TEXT NOT NULL,
  sprt_decision TEXT NOT NULL CHECK (sprt_decision IN ('CONTINUE', 'PROMOTE', 'KILL')),
  eligible_n INTEGER NOT NULL,
  win_n INTEGER NOT NULL,
  wilson_json TEXT,
  sprt_snapshot_json TEXT NOT NULL,
  shadow_tier_json TEXT,
  hypothesis_hash TEXT,
  pattern_spec_hash TEXT,
  engine_version TEXT NOT NULL,
  manifest_content_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_anna_sequential_runs_strategy
  ON anna_sequential_decision_runs (strategy_id, evaluated_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_anna_sequential_runs_test
  ON anna_sequential_decision_runs (test_id, evaluated_at_utc DESC);
