"""
context_memory.py — **single-silo** memory for pattern-game runs (RAG-style, not “the universe”).

**Scope:** Only ``renaissance_v4`` pattern-game / replay memory — manifests, session logs,
indicator **context**, hypotheses. Not general world knowledge.

**Critical idea (tide metaphor):** Standing in six feet of water does **not** tell you whether the
tide is **coming in or going out**. Raw indicator **values** without **context** (direction,
regime, transitions, velocity / “which way is it moving”) are **noise** — same number, opposite
meaning. What must live in memory is **context around indicators**, not lone prints.
"""

from __future__ import annotations

from typing import Any

# One silo — retrieval and promotion stay here; no claim to “remember everything.”
CONTEXT_SILO_ID = "renaissance_v4_pattern_game_v1"

TIDE_METAPHOR = (
    "**Tide check:** Six feet of water does not tell you if the tide is **coming in or going out**. "
    "An indicator **value** without **context** (regime, direction, transition, velocity) is **noise** — "
    "not memory worth promoting. This silo stores **context around indicators**, not the universe."
)

# Keys that signal “context, not just a number” (any subset helps; more is better).
INDICATOR_CONTEXT_SIGNAL_KEYS: frozenset[str] = frozenset(
    {
        "regime",
        "direction",
        "transition",
        "velocity",
        "tide",
        "structure",
        "phase",
        "session",
        "bias",
    }
)


def assess_indicator_context(ctx: dict[str, Any] | None) -> dict[str, Any]:
    """
    Lightweight quality tag for run_memory / HUMAN_READABLE (not a hard gate unless you add one).

    Returns ``level``: ``missing`` | ``noise_risk`` | ``thin`` | ``rich``.
    """
    if not ctx:
        return {
            "level": "missing",
            "silo": CONTEXT_SILO_ID,
            "matched_signal_keys": [],
            "warn": TIDE_METAPHOR,
        }
    matched = [k for k in ctx.keys() if str(k).lower() in INDICATOR_CONTEXT_SIGNAL_KEYS]
    n = len(matched)
    if n >= 3:
        level = "rich"
    elif n >= 1:
        level = "thin"
    else:
        level = "noise_risk"
    out: dict[str, Any] = {
        "level": level,
        "silo": CONTEXT_SILO_ID,
        "matched_signal_keys": matched,
    }
    if level in ("missing", "noise_risk", "thin"):
        out["warn"] = TIDE_METAPHOR
    return out
