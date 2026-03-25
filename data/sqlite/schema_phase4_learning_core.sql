-- Learning core lifecycle baseline (Directive 4.6.3.2 Part A)
-- Enforces reusable knowledge gating through validated-only state.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS learning_records (
  id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN ('candidate', 'under_test', 'validated', 'rejected')),
  source TEXT NOT NULL,
  source_record_id TEXT,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  evidence_links_json TEXT NOT NULL DEFAULT '[]',
  validation_notes TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_source_record
  ON learning_records(source, source_record_id);
CREATE INDEX IF NOT EXISTS idx_learning_state ON learning_records(state);
CREATE INDEX IF NOT EXISTS idx_learning_updated ON learning_records(updated_at);

CREATE TABLE IF NOT EXISTS learning_record_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  changed_at TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (record_id) REFERENCES learning_records(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_learning_transition_record
  ON learning_record_transitions(record_id, changed_at);
