"""
FinQuant engineering-grade learning system.

Implements the full architect-required loop:
  Observe → Hypothesize → Execute → Measure → Falsify → Score → Accumulate
  → Compete → Promote → Apply → Explain → Decay

Modules:
  pattern_signature   : deterministic regime+indicator signature
  learning_unit       : unit data model with falsification, evidence, status
  learning_unit_store : write-ahead log + materialized state + fsync
  falsification_engine: hypothesis-vs-outcome verdict logic
  promotion_engine    : candidate→provisional→validated→active→retired
  pattern_competition : multi-unit ranking and conflict resolution
  decision_explainer  : unit-attributed explanation at decision time
"""
