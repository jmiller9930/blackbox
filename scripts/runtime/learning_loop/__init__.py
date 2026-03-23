"""
Phase 4.4 — Execution feedback: outcome + deterministic insight → system_events only (no schema change).

Amendment 4.4.1: canonical store is `system_events` (`source='execution_plane'`); one feedback row per attempt.
"""
from __future__ import annotations

from .insight_engine import build_insight
from .outcome_tracker import record_execution_feedback

__all__ = ["build_insight", "record_execution_feedback"]
