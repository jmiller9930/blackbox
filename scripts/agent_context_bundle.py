"""
Optional **repository context** prepended to Anna (Ollama) prompts — not model training.

Experience lives in **git**: policy specs, game specs, and optional extra files. This module loads
whitelisted paths so the LLM sees the same rules operators use, without inventing retention in weights.

Env:
  ANNA_CONTEXT_PROFILE   — comma-separated: none | pattern_game | policy (default: none)
  ANNA_CONTEXT_FILES     — extra repo-relative paths, colon-separated (optional)
  ANNA_CONTEXT_MAX_CHARS — cap total injected text (default 120000)
"""

from __future__ import annotations

import os
from pathlib import Path

_PROFILE_PATHS: dict[str, tuple[str, ...]] = {
    "pattern_game": ("renaissance_v4/game_theory/GAME_SPEC_INDICATOR_PATTERN_V1.md",),
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
    parts: list[str] = []
    seen: set[str] = set()

    for token in profile_raw.replace(";", ",").split(","):
        token = token.strip()
        if not token or token == "none":
            continue
        if token in ("both", "all"):
            keys = list(_PROFILE_PATHS.keys())
        elif token == "pattern_game":
            keys = ["pattern_game"]
        elif token == "policy":
            keys = ["policy"]
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

    if not parts:
        return ""

    body = "".join(parts)
    return (
        "--- REPOSITORY CONTEXT (authoritative docs; do not invent requirements not shown here) ---\n\n"
        + body
        + "--- END REPOSITORY CONTEXT ---\n\n"
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Print Anna context bundle to stdout (for piping into prompts).")
    ap.add_argument(
        "--profile",
        default=os.environ.get("ANNA_CONTEXT_PROFILE", "none"),
        help="Same as ANNA_CONTEXT_PROFILE, e.g. policy,pattern_game",
    )
    ap.add_argument("--repo", type=Path, default=None, help="Repo root (default: cwd)")
    args = ap.parse_args()
    os.environ["ANNA_CONTEXT_PROFILE"] = args.profile
    text = build_context_prefix(args.repo or Path.cwd())
    print(text, end="")


if __name__ == "__main__":
    main()
