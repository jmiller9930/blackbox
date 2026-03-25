"""Directive 4.6.3.4 — config loader + backend selection (no Anna changes)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_load_example_config_default_backend_cli() -> None:
    from messaging_interface.config_loader import load_messaging_config
    from messaging_interface.backend_loader import get_backend

    cfg = load_messaging_config(config_path=REPO / "config" / "messaging_config.example.json")
    assert get_backend(cfg) == "cli"


def test_validate_slack_requires_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    from messaging_interface.backend_loader import validate_backend_config

    cfg = {
        "messaging": {
            "backend": "slack",
            "slack": {"bot_token": "", "app_token": "", "mode": "socket"},
        }
    }
    with pytest.raises(ValueError, match="bot_token"):
        validate_backend_config(cfg, "slack")

    cfg2 = {
        "messaging": {
            "backend": "slack",
            "slack": {"bot_token": "xoxb-test", "app_token": "", "mode": "socket"},
        }
    }
    with pytest.raises(ValueError, match="app_token"):
        validate_backend_config(cfg2, "slack")


def test_runner_cli_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Runner with backend=cli delegates to cli_adapter (stdin)."""
    p = tmp_path / "messaging_config.json"
    p.write_text(
        json.dumps(
            {
                "messaging": {
                    "backend": "cli",
                    "telegram": {"token": ""},
                    "cli": {"enabled": True},
                    "slack": {"bot_token": "", "app_token": "", "channel": "", "mode": "socket"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    from messaging_interface import runner
    from messaging_interface import config_loader

    monkeypatch.setattr(config_loader, "_DEFAULT_CONFIG", p)
    monkeypatch.setattr(config_loader, "_EXAMPLE_CONFIG", p)

    import io
    import sys

    old = sys.stdin
    sys.stdin = io.StringIO("What day is it?\n")
    try:
        rc = runner.main()
    finally:
        sys.stdin = old
    assert rc == 0


def test_runner_telegram_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Runner with backend=telegram delegates to telegram_bot.main (mocked — no polling)."""
    p = tmp_path / "messaging_config.json"
    p.write_text(
        json.dumps(
            {
                "messaging": {
                    "backend": "telegram",
                    "telegram": {"token": "dummy-token-for-test"},
                    "cli": {"enabled": True},
                    "slack": {
                        "bot_token": "",
                        "app_token": "",
                        "channel": "",
                        "mode": "socket",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANNA_USE_LLM", "0")
    from messaging_interface import config_loader

    monkeypatch.setattr(config_loader, "_DEFAULT_CONFIG", p)
    monkeypatch.setattr(config_loader, "_EXAMPLE_CONFIG", p)

    import telegram_interface.telegram_bot as telegram_main_mod

    monkeypatch.setattr(telegram_main_mod, "main", lambda: 0)

    from messaging_interface import runner

    assert runner.main() == 0
