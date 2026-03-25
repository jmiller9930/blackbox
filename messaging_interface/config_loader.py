"""
Load `config/messaging_config.json` with safe fallbacks and env overrides (Directive 4.6.3.4).

Secrets: prefer env (SLACK_BOT_TOKEN, SLACK_APP_TOKEN, TELEGRAM_BOT_TOKEN) over file values.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "messaging_config.json"
_EXAMPLE_CONFIG = _REPO_ROOT / "config" / "messaging_config.example.json"


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_messaging_config(
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """
    Load messaging block. Uses `config/messaging_config.json` if present, else example file.

    Env overrides (non-empty wins over file for secrets):
    - TELEGRAM_BOT_TOKEN → messaging.telegram.token
    - SLACK_BOT_TOKEN → messaging.slack.bot_token
    - SLACK_APP_TOKEN → messaging.slack.app_token
    """
    path = config_path or _DEFAULT_CONFIG
    if path.is_file():
        raw = _read_json(path)
    elif _EXAMPLE_CONFIG.is_file():
        raw = _read_json(_EXAMPLE_CONFIG)
    else:
        raise FileNotFoundError(
            f"No messaging config at {path} and no example at {_EXAMPLE_CONFIG}",
        )

    msg = raw.get("messaging")
    if not isinstance(msg, dict):
        raise ValueError("messaging_config: missing top-level 'messaging' object")

    # Deep copy via json round-trip for safety
    out = json.loads(json.dumps(msg))

    tg = out.get("telegram") or {}
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        tg["token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    out["telegram"] = tg

    sl = out.get("slack") or {}
    if os.environ.get("SLACK_BOT_TOKEN"):
        sl["bot_token"] = os.environ["SLACK_BOT_TOKEN"]
    if os.environ.get("SLACK_APP_TOKEN"):
        sl["app_token"] = os.environ["SLACK_APP_TOKEN"]
    out["slack"] = sl

    return {"messaging": out}
