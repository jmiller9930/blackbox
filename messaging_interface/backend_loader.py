"""
Resolve and validate `messaging.backend` (Directive 4.6.3.4). One active backend only.
"""

from __future__ import annotations

from typing import Any, Literal

BackendName = Literal["cli", "slack", "telegram"]

_VALID: frozenset[str] = frozenset({"cli", "slack", "telegram"})


def get_backend(cfg: dict[str, Any]) -> BackendName:
    m = cfg.get("messaging") or {}
    b = (m.get("backend") or "").strip().lower()
    if b not in _VALID:
        raise ValueError(
            f"messaging.backend must be one of {sorted(_VALID)}, got {b!r}",
        )
    return b  # type: ignore[return-value]


def validate_backend_config(cfg: dict[str, Any], backend: BackendName) -> None:
    """Raise ValueError if required fields for the selected backend are missing."""
    m = cfg.get("messaging") or {}
    if backend == "slack":
        sl = m.get("slack") or {}
        if not (sl.get("bot_token") or "").strip():
            raise ValueError("Slack backend requires slack.bot_token (or SLACK_BOT_TOKEN env)")
        mode = (sl.get("mode") or "socket").strip().lower()
        if mode == "socket" and not (sl.get("app_token") or "").strip():
            raise ValueError("Slack socket mode requires slack.app_token (or SLACK_APP_TOKEN env)")
    if backend == "telegram":
        tg = m.get("telegram") or {}
        if not (tg.get("token") or "").strip():
            raise ValueError("Telegram backend requires telegram.token (or TELEGRAM_BOT_TOKEN env)")
    # cli: no required secrets
