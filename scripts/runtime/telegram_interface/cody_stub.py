"""Read-only engineering persona stub for Telegram (no repo writes, no deploy)."""
from __future__ import annotations


def cody_reply(user_text: str, *, display_name: str | None = None) -> str:
    """
    Deterministic Cody (engineering) voice — not an LLM; safe for locked directive.
    """
    t = (user_text or "").strip()
    short = t[:400] + ("…" if len(t) > 400 else "")

    who = "I am Cody (engineering)"
    if display_name:
        who = f"{display_name}, I am Cody (engineering)"

    return (
        "Plan\n"
        f"{who}. Topic: {short!r}\n\n"
        "Constraints\n"
        "Read-only from chat: guidance on structure, safety, and how runtime scripts fit. "
        "No patches, commits, or secrets from Telegram.\n\n"
        "Proposed next\n"
        "Code: branch → PR → tests. Runtime: DATA for `status` / `report`. Analysis: @anna.\n\n"
        "Concrete ask\n"
        "Paste a file path, error snippet, or ask DATA for `status` / `report`."
    )
