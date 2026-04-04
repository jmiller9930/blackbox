-- Structured lesson memory (W9) — separate from anna_context_memory (Q&A exact-match).
-- Applied via ensure_schema after schema_phase4_anna_context.sql

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS anna_lesson_memory (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  lesson_text TEXT NOT NULL,
  situation_summary TEXT,
  symbol TEXT,
  regime_tag TEXT,
  timeframe TEXT,
  outcome_class TEXT,
  context_tags TEXT,
  source TEXT NOT NULL DEFAULT 'operator',
  validation_status TEXT NOT NULL DEFAULT 'candidate',
  paper_trade_id TEXT,
  request_id TEXT,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_alm_validation ON anna_lesson_memory(validation_status);
CREATE INDEX IF NOT EXISTS idx_alm_symbol ON anna_lesson_memory(symbol);
CREATE INDEX IF NOT EXISTS idx_alm_regime ON anna_lesson_memory(regime_tag);
CREATE INDEX IF NOT EXISTS idx_alm_created ON anna_lesson_memory(created_at);
