"""Pattern game prototype (game theory) — validate → replay → binary scorecard."""

from renaissance_v4.game_theory.pattern_game import (
    OUTCOME_RULE_V1,
    PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC,
    PATTERN_GAME_STARTING_EQUITY_USD_SPEC,
    json_summary,
    run_pattern_game,
    score_binary_outcomes,
)

__all__ = [
    "OUTCOME_RULE_V1",
    "PATTERN_GAME_RISK_FRACTION_PER_TRADE_SPEC",
    "PATTERN_GAME_STARTING_EQUITY_USD_SPEC",
    "json_summary",
    "run_pattern_game",
    "score_binary_outcomes",
]
