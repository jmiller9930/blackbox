"""
Optional caps on Student Ollama prompt size and generation length to reduce token/compute burn.

**Default:** guards are **off** (no behavior change). Enable with::

    export BLACKBOX_TOKEN_BURN_GUARD=1

Optional overrides (when guard is on):

* ``BLACKBOX_STUDENT_PROMPT_JSON_MAX_CEILING`` — max chars for embedded packet JSON (default 32000).
* ``BLACKBOX_OLLAMA_NUM_PREDICT_MAX`` — hard ceiling on ``num_predict`` (default 1536).

Existing ``PATTERN_GAME_STUDENT_PROMPT_PACKET_JSON_MAX`` still sets the *requested* max;
when the guard is on, the effective limit is ``min(requested, ceiling)``.
"""

from __future__ import annotations

import os
from typing import Any


_GUARD_ENV_V1 = "BLACKBOX_TOKEN_BURN_GUARD"
_PROMPT_CEILING_ENV_V1 = "BLACKBOX_STUDENT_PROMPT_JSON_MAX_CEILING"
_NUM_PREDICT_MAX_ENV_V1 = "BLACKBOX_OLLAMA_NUM_PREDICT_MAX"
_LEGACY_PROMPT_MAX_ENV_V1 = "PATTERN_GAME_STUDENT_PROMPT_PACKET_JSON_MAX"


def token_burn_guard_enabled_v1() -> bool:
    raw = (os.environ.get(_GUARD_ENV_V1) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def resolve_max_packet_json_chars_v1() -> int:
    """Effective max chars for truncating ``student_decision_packet_v1`` JSON in Ollama prompts."""
    raw = (os.environ.get(_LEGACY_PROMPT_MAX_ENV_V1) or "56000").strip()
    try:
        requested = int(raw or "56000")
    except ValueError:
        requested = 56000
    requested = max(4096, requested)
    if not token_burn_guard_enabled_v1():
        return requested
    ceiling = max(4096, _env_int(_PROMPT_CEILING_ENV_V1, 32000))
    return min(requested, ceiling)


def clamp_ollama_options_v1(options: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of Ollama ``options`` with ``num_predict`` capped when guard is enabled."""
    if options is None:
        return {}
    opts = dict(options)
    if not token_burn_guard_enabled_v1():
        return opts
    cap = max(256, _env_int(_NUM_PREDICT_MAX_ENV_V1, 1536))
    if "num_predict" not in opts:
        return opts
    np = opts.get("num_predict")
    try:
        np_i = int(np)
    except (TypeError, ValueError):
        np_i = cap
    opts["num_predict"] = min(np_i, cap)
    return opts


__all__ = [
    "clamp_ollama_options_v1",
    "resolve_max_packet_json_chars_v1",
    "token_burn_guard_enabled_v1",
]
