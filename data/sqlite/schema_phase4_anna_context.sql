-- Anna contextual answer memory (Directive 4.6.3.X)
-- Applied after schema_phase1_6.sql via ensure_schema.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS anna_context_memory (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  question_text TEXT NOT NULL,
  intent TEXT,
  topic TEXT,
  question_mode TEXT,
  symbol TEXT,
  timeframe TEXT,
  context_tags TEXT,
  answer_text TEXT NOT NULL,
  answer_source TEXT NOT NULL,
  validation_status TEXT NOT NULL DEFAULT 'candidate',
  human_intent_json TEXT,
  pipeline_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_acm_intent_topic ON anna_context_memory(intent, topic);
CREATE INDEX IF NOT EXISTS idx_acm_created ON anna_context_memory(created_at);
