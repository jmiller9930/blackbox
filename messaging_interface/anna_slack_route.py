"""
Directive 4.6.3.4.C — explicit-only Anna routing for Slack (v1).

NO intent detection, keywords, or classifiers.
"""

from __future__ import annotations

import re
from typing import Final

# Word "Anna" (avoid matching substrings like "Johanna" when possible).
_ANNA_WORD: Final[re.Pattern[str]] = re.compile(r"\bAnna\b", re.IGNORECASE)


def explicit_anna_route(user_text: str) -> bool:
    """
    Return True only when the user explicitly invokes Anna per finalized directive:
    - message contains \"Anna\" as a word
    - OR message contains \"@Anna\" (substring, case-insensitive)
    - OR message begins with \"Anna,\"
    """
    t = (user_text or "").strip()
    if not t:
        return False
    if t.startswith("Anna,") or t.startswith("anna,"):
        return True
    if "@anna" in t.lower():
        return True
    return bool(_ANNA_WORD.search(t))
