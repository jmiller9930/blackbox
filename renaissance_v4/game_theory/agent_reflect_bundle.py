"""
**Agent reflect bundle** — one structured snapshot for “what just happened + what to try next”.

Combines recent **batch scorecard** lines (facts) with **hunter planner** output (diversified scenarios).
Optional HTTP submit is **not** in this module; see ``scripts/pattern_game_agent_reflect.py``.

This supports **self-reflection workflows**: review outcomes, then run again (manually or via gated script),
without embedding an autonomous optimization loop in the LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.batch_scorecard import format_batch_scorecard_for_prompt
from renaissance_v4.game_theory.hunter_planner import build_hunter_suggestion, resolve_repo_root

SCHEMA_V1 = "pattern_game_agent_reflect_bundle_v1"


def build_agent_reflect_bundle(
    *,
    repo_root: Path | None = None,
    scorecard_limit: int = 15,
    scorecard_max_chars: int = 8000,
) -> dict[str, Any]:
    """
    Return JSON-serializable dict: scorecard markdown, hunter suggestion, combined prompt block.

    Hunter suggestion may be ``ok: False`` if manifest missing — still returned for visibility.
    """
    root = resolve_repo_root(repo_root)
    scorecard_md = format_batch_scorecard_for_prompt(
        limit=scorecard_limit,
        max_chars=scorecard_max_chars,
        path=None,
    )
    hunter = build_hunter_suggestion(repo_root=root)

    lines: list[str] = [
        "### Pattern game — reflect bundle (read Referee JSON for per-scenario trade metrics)\n",
        "",
        "#### Recent batch scorecard (parallel runs — timing and counts)\n",
        scorecard_md.strip() or "_No scorecard lines yet — run a parallel batch first._",
        "",
        "#### Suggested next scenarios (deterministic ladder — validate before run)\n",
    ]
    if hunter.get("ok") and hunter.get("scenarios"):
        lines.append("```json")
        lines.append(json.dumps(hunter["scenarios"], indent=2, ensure_ascii=False))
        lines.append("```")
    else:
        lines.append(f"_Hunter suggestion unavailable: {hunter.get('error', 'unknown')}_")

    if hunter.get("rationale_markdown"):
        lines.append("")
        lines.append("#### Rationale (planner)\n")
        lines.append(hunter["rationale_markdown"])

    if hunter.get("warnings"):
        lines.append("")
        lines.append("#### Warnings\n")
        for w in hunter["warnings"]:
            lines.append(f"- {w}")

    prompt_block = "\n".join(lines)

    return {
        "schema": SCHEMA_V1,
        "repo_root": str(root),
        "scorecard_markdown": scorecard_md,
        "hunter_suggestion": hunter,
        "prompt_block": prompt_block,
    }
