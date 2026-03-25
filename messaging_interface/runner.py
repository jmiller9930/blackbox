"""
Single-backend entrypoint: load config → validate → start one adapter (Directive 4.6.3.4).

  python -m messaging_interface

Does not modify Anna pipeline — only `run_dispatch_pipeline` + transports.
"""

from __future__ import annotations

import sys


def main() -> int:
    from messaging_interface.backend_loader import get_backend, validate_backend_config
    from messaging_interface.config_loader import load_messaging_config

    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(
            "Usage: python -m messaging_interface\n"
            "Loads config/messaging_config.json (or example) and starts messaging.backend "
            "(cli | slack | telegram). One backend only.",
        )
        return 0

    cfg = load_messaging_config()
    backend = get_backend(cfg)
    validate_backend_config(cfg, backend)

    if backend == "cli":
        from messaging_interface.cli_adapter import main as cli_main

        return cli_main()

    if backend == "slack":
        from messaging_interface.slack_adapter import run_slack_from_config

        return run_slack_from_config(cfg)

    if backend == "telegram":
        from messaging_interface.telegram_adapter import run_telegram_bot_from_config

        return run_telegram_bot_from_config(cfg)

    raise RuntimeError(f"unhandled backend: {backend}")


if __name__ == "__main__":
    raise SystemExit(main())
