from renaissance_v4.game_theory.anna_hard_rules import (
    HARDCODED_ANNA_RULES_MARKDOWN,
    format_hard_rules_for_prompt,
)


def test_hard_rules_nonempty() -> None:
    assert "Visible window" in HARDCODED_ANNA_RULES_MARKDOWN or "short OHLCV" in HARDCODED_ANNA_RULES_MARKDOWN
    assert "Referee" in HARDCODED_ANNA_RULES_MARKDOWN
    assert len(format_hard_rules_for_prompt()) >= 100
