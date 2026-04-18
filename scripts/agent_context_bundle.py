"""
Optional **repository context** prepended to Anna (Ollama) prompts — not model training.

Experience lives in **git**: policy specs, game specs, Renaissance V4 fusion math (checked-in source),
and optional extra files. This module loads whitelisted paths so the LLM sees the same rules operators use,
without inventing retention in weights.

Env:
  ANNA_CONTEXT_PROFILE   — comma-separated tokens (default when **this module** is called alone: none).
                           **Pattern-game Anna** (``renaissance_v4/game_theory/player_agent.py``) sets the profile
                           to **all** before calling ``build_context_prefix`` when the env profile is unset, so
                           narration and ``--ask`` get the full designed prefix unless you override.
                           **both** = checked-in docs only: pattern_game + policy files.
                           **all** = same docs **plus** retrospective + scorecard blocks (full available prefix;
                           larger prompts). For manual mixes use: pattern_game | policy | retrospective | scorecard.
                           **pattern_game** loads game spec, QUANT research design, ``context_memory.py`` (tide metaphor),
                           and **Renaissance V4 fusion** (``fusion_engine.py``, ``signal_weights.py``, ``fusion_result.py``).
                           **policy** loads ``policy_package_standard.md``.
                           **retrospective** appends recent ``retrospective_log.jsonl`` (what you observed / try next).
                           **scorecard** appends recent ``batch_scorecard.jsonl`` (parallel batch timing, ok/fail counts, workers —
                           read-only facts; does not run replays or change strategy).
  ANNA_CONTEXT_RETROSPECTIVE — ``1`` to include retrospective even if token omitted (optional).
  ANNA_CONTEXT_SCORECARD — ``1`` to include scorecard even if token omitted (optional).
  ANNA_CONTEXT_RETROSPECTIVE_LIMIT — max retrospective lines (default 15).
  ANNA_CONTEXT_SCORECARD_LIMIT — max scorecard lines (default 15).
  ANNA_CONTEXT_SCORECARD_MAX_CHARS — max chars for scorecard block (default 8000).
  ANNA_CONTEXT_FILES     — extra repo-relative paths, colon-separated (optional)
  ANNA_CONTEXT_MAX_CHARS — cap total injected text (default 120000)
"""

from __future__ import annotations

import os
from pathlib import Path

from renaissance_v4.game_theory.batch_scorecard import format_batch_scorecard_for_prompt
from renaissance_v4.game_theory.retrospective_log import format_retrospective_for_prompt

_PROFILE_PATHS: dict[str, tuple[str, ...]] = {
    "pattern_game": (
        "renaissance_v4/game_theory/GAME_SPEC_INDICATOR_PATTERN_V1.md",
        "renaissance_v4/game_theory/QUANT_RESEARCH_AGENT_DESIGN.md",
        "renaissance_v4/game_theory/context_memory.py",
        "renaissance_v4/core/fusion_result.py",
        "renaissance_v4/core/signal_weights.py",
        "renaissance_v4/core/fusion_engine.py",
    ),
    "policy": ("docs/architect/policy_package_standard.md",),
}


def _read_capped(root: Path, rel: str, remaining: int) -> tuple[str, int]:
    p = (root / rel).resolve()
    try:
        if not str(p).startswith(str(root.resolve())):
            return "", remaining
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return f"[unreadable: {rel}]\n", remaining
    if len(raw) > remaining:
        raw = raw[:remaining] + "\n… [truncated]\n"
    block = f"### File: `{rel}`\n\n{raw}\n\n"
    return block, remaining - len(block)


def build_context_prefix(repo_root: Path | str | None = None) -> str:
    """
    Return markdown to prepend before the main Anna task, or empty string if disabled / nothing loaded.
    """
    root = Path(repo_root or os.environ.get("REPO_ROOT", ".")).resolve()
    profile_raw = os.environ.get("ANNA_CONTEXT_PROFILE", "none").strip().lower()
    if profile_raw in ("", "none", "0", "false", "no"):
        return ""

    max_chars = int(os.environ.get("ANNA_CONTEXT_MAX_CHARS", "120000"))
    want_retrospective = os.environ.get("ANNA_CONTEXT_RETROSPECTIVE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    want_scorecard = os.environ.get("ANNA_CONTEXT_SCORECARD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    parts: list[str] = []
    seen: set[str] = set()

    for token in profile_raw.replace(";", ",").split(","):
        token = token.strip()
        if not token or token == "none":
            continue
        if token == "both":
            keys = list(_PROFILE_PATHS.keys())
        elif token == "all":
            keys = list(_PROFILE_PATHS.keys())
            want_retrospective = True
            want_scorecard = True
        elif token == "pattern_game":
            keys = ["pattern_game"]
        elif token == "policy":
            keys = ["policy"]
        elif token == "retrospective":
            want_retrospective = True
            continue
        elif token == "scorecard":
            want_scorecard = True
            continue
        else:
            continue
        for k in keys:
            for rel in _PROFILE_PATHS.get(k, ()):
                if rel not in seen:
                    seen.add(rel)

    extra = os.environ.get("ANNA_CONTEXT_FILES", "").strip()
    if extra:
        for rel in extra.split(":"):
            rel = rel.strip()
            if rel and rel not in seen:
                seen.add(rel)

    remaining = max_chars
    for rel in sorted(seen):
        block, remaining = _read_capped(root, rel, remaining)
        parts.append(block)
        if remaining <= 0:
            break

    body = "".join(parts)
    retro_limit = int(os.environ.get("ANNA_CONTEXT_RETROSPECTIVE_LIMIT", "15"))
    scorecard_limit = int(os.environ.get("ANNA_CONTEXT_SCORECARD_LIMIT", "15"))
    scorecard_max = int(os.environ.get("ANNA_CONTEXT_SCORECARD_MAX_CHARS", "8000"))

    retro_block = ""
    if want_retrospective and remaining > 200:
        retro_block = format_retrospective_for_prompt(
            limit=retro_limit,
            max_chars=max(0, remaining - 400),
            path=None,
        )
        remaining -= len(retro_block)

    scorecard_block = ""
    if want_scorecard and remaining > 200:
        scorecard_block = format_batch_scorecard_for_prompt(
            limit=scorecard_limit,
            max_chars=min(scorecard_max, max(0, remaining - 400)),
            path=None,
        )

    if not body.strip() and not retro_block and not scorecard_block:
        return ""

    out = "--- REPOSITORY CONTEXT (authoritative docs; do not invent requirements not shown here) ---\n\n"
    if body.strip():
        out += body
    if retro_block:
        out += "\n--- RETROSPECTIVE LOG (prior runs — operator notes; not Referee trade scores) ---\n\n"
        out += retro_block
        out += "\n"
    if scorecard_block:
        out += "\n--- BATCH SCORECARD (recent parallel batches — timing and counts from JSONL; read-only) ---\n\n"
        out += scorecard_block
        out += "\n"
    out += "--- END REPOSITORY CONTEXT ---\n\n"
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Print Anna context bundle to stdout (for piping into prompts).")
    ap.add_argument(
        "--profile",
        default=os.environ.get("ANNA_CONTEXT_PROFILE", "none"),
        help="Same as ANNA_CONTEXT_PROFILE, e.g. policy,pattern_game,scorecard",
    )
    ap.add_argument("--repo", type=Path, default=None, help="Repo root (default: cwd)")
    args = ap.parse_args()
    os.environ["ANNA_CONTEXT_PROFILE"] = args.profile
    text = build_context_prefix(args.repo or Path.cwd())
    print(text, end="")


if __name__ == "__main__":
    main()
