"""Pattern game prototype (game theory) — validate → replay → binary scorecard."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "PatternGameAgent",
    "OUTCOME_RULE_V1",
    "PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC",
    "PATTERN_GAME_STARTING_EQUITY_USD_SPEC",
    "json_summary",
    "run_pattern_game",
    "score_binary_outcomes",
]

_LAZY = {
    "PatternGameAgent": ("renaissance_v4.game_theory.pattern_game_agent", "PatternGameAgent"),
    "OUTCOME_RULE_V1": ("renaissance_v4.game_theory.pattern_game", "OUTCOME_RULE_V1"),
    "PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC": (
        "renaissance_v4.game_theory.pattern_game",
        "PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC",
    ),
    "PATTERN_GAME_STARTING_EQUITY_USD_SPEC": (
        "renaissance_v4.game_theory.pattern_game",
        "PATTERN_GAME_STARTING_EQUITY_USD_SPEC",
    ),
    "json_summary": ("renaissance_v4.game_theory.pattern_game", "json_summary"),
    "run_pattern_game": ("renaissance_v4.game_theory.pattern_game", "run_pattern_game"),
    "score_binary_outcomes": ("renaissance_v4.game_theory.pattern_game", "score_binary_outcomes"),
}


def __getattr__(name: str) -> Any:
    """
    Lazy exports so importing submodules (e.g. ``evaluation_window_runtime``) for replay
    does not eagerly import ``pattern_game`` / ``parallel_runner`` / ``replay_runner``.
    """
    if name in _LAZY:
        mod_name, attr = _LAZY[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Parallel batch: ``from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel``
# (not re-exported here — avoids import-order warnings for ``python -m ...parallel_runner``).
