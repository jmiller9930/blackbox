-- Quantitative Evaluation Layer (QEL) — same DB file as execution_ledger.db
-- Survival tests, evaluation runs (binary survive/drop), lifecycle audit.

CREATE TABLE IF NOT EXISTS anna_survival_tests (
  test_id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  hypothesis_json TEXT NOT NULL,
  hypothesis_hash TEXT NOT NULL,
  allowed_inputs_json TEXT NOT NULL DEFAULT '{}',
  lane_allowed_json TEXT NOT NULL,
  mode_allowed_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active', 'completed_survived', 'completed_dropped', 'superseded')),
  supersedes_test_id TEXT,
  created_at_utc TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_anna_survival_tests_strategy
  ON anna_survival_tests (strategy_id, status);
CREATE INDEX IF NOT EXISTS idx_anna_survival_tests_hash
  ON anna_survival_tests (hypothesis_hash, status);

CREATE TABLE IF NOT EXISTS anna_survival_evaluation_runs (
  run_id TEXT PRIMARY KEY,
  test_id TEXT NOT NULL,
  checkpoint_name TEXT NOT NULL,
  evaluated_at_utc TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('survive', 'drop')),
  checkpoint_summary_json TEXT NOT NULL,
  metrics_snapshot_json TEXT,
  regime_coverage_json TEXT,
  engine_version TEXT NOT NULL,
  determinism_inputs_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_anna_survival_runs_test
  ON anna_survival_evaluation_runs (test_id, evaluated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_anna_survival_runs_checkpoint
  ON anna_survival_evaluation_runs (checkpoint_name, evaluated_at_utc DESC);

CREATE TABLE IF NOT EXISTS strategy_lifecycle_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  actor TEXT NOT NULL,
  payload_json TEXT,
  created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_lifecycle_strategy
  ON strategy_lifecycle_transitions (strategy_id, created_at_utc DESC);
