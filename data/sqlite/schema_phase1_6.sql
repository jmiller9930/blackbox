-- BLACK BOX — Phase 1.6 controlled execution (architect)
-- Apply AFTER schema_phase1_5.sql (provides `tasks`, `alerts`, `system_events`, etc.)
-- Usage: ./scripts/init_phase1_6_sqlite.sh

PRAGMA foreign_keys = ON;

-- Health checks DATA logs (gateway, Ollama, SQLite, endpoints, …)
CREATE TABLE IF NOT EXISTS system_health_logs (
  id TEXT PRIMARY KEY,
  checked_at TEXT NOT NULL DEFAULT (datetime('now')),
  target TEXT NOT NULL,
  check_type TEXT NOT NULL,
  status TEXT NOT NULL,
  severity TEXT,
  summary TEXT,
  evidence TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_system_health_logs_checked ON system_health_logs(checked_at);
CREATE INDEX IF NOT EXISTS idx_system_health_logs_status ON system_health_logs(status);

-- Architect name `agent_tasks`: alias to Phase 1.5 `tasks` (same shape, no duplicate writes)
CREATE VIEW IF NOT EXISTS agent_tasks AS
SELECT
  id,
  agent_id,
  title,
  description,
  state,
  priority,
  created_at,
  updated_at,
  completed_at
FROM tasks;

-- `alerts` is defined in schema_phase1_5.sql — required for controlled execution logging.
