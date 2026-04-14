-- Forward-only baseline policy activation (DV-ARCH-POLICY-ACTIVATION-023-A).
-- previous_baseline_policy_slot: snapshot of execution-effective slot at assignment time (while pending).

CREATE TABLE IF NOT EXISTS policy_activation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  policy_id TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  slot TEXT NOT NULL,
  activation_state TEXT NOT NULL CHECK (activation_state IN ('pending', 'active', 'superseded')),
  activation_effective_at_utc TEXT,
  activation_market_event_id TEXT,
  assigned_by TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  previous_baseline_policy_slot TEXT
);

CREATE INDEX IF NOT EXISTS idx_policy_activation_log_slot_state
  ON policy_activation_log (slot, activation_state);

CREATE INDEX IF NOT EXISTS idx_policy_activation_log_effective_at
  ON policy_activation_log (activation_effective_at_utc);
