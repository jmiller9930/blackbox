"""
Anna modular runtime (Phase 3.4): input → interpretation → risk → policy → proposal.

| Module | Responsibility |
|--------|----------------|
| `input_adapter` | Normalize trader text; load optional `tasks` artifacts (snapshot, context, trend, policy, stored Anna analysis). |
| `interpretation` | Keywords → concepts; interpretation summary/signals/assumptions. |
| `risk` | Risk level, factors, market_context price/spread notes. |
| `policy` | Guardrail mode, alignment vs intent, paper-only `suggested_action`. |
| `analysis` | Assemble full `anna_analysis_v1`. |
| `proposal` | Map analysis → `anna_proposal_v1` (types, validation_plan). |
| `util` | Schema versions, time, float helpers. |

Registry loading, Telegram, ML, and execution live outside this package until later phases.
"""

from __future__ import annotations

from anna_modules.analysis import assemble_anna_analysis_v1, build_analysis
from anna_modules.context_requirements import assess_context_completeness
from anna_modules.input_adapter import (
    load_latest_guardrail_policy,
    load_latest_market_snapshot,
    load_latest_stored_anna_analysis,
    normalize_trader_text,
    try_load_decision_context,
    try_load_trend,
)
from anna_modules.market_data_reader import load_latest_market_tick
from anna_modules.proposal import assemble_anna_proposal_v1, build_anna_proposal

__all__ = [
    "build_analysis",
    "assemble_anna_analysis_v1",
    "build_anna_proposal",
    "assemble_anna_proposal_v1",
    "load_latest_market_snapshot",
    "load_latest_market_tick",
    "load_latest_guardrail_policy",
    "try_load_decision_context",
    "try_load_trend",
    "load_latest_stored_anna_analysis",
    "normalize_trader_text",
    "assess_context_completeness",
]
