"""
Phase 4.5 — Read-only visibility over `execution_feedback_v1` rows (no ML, no registry, no schema change).
"""
from __future__ import annotations

from .insight_query import fetch_insights
from .insight_summary import summarize_insights
from .report_generator import generate_report

__all__ = ["fetch_insights", "generate_report", "summarize_insights"]
