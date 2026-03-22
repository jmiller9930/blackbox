"""Console-oriented logging setup using Rich (optional, for local diagnostics)."""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.logging import RichHandler


def configure_rich_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a Rich-backed handler."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def log_banner(console: Console | None = None, **kwargs: Any) -> None:
    """Emit a one-line startup banner to the given or default console."""
    c = console or Console()
    c.print("[bold]BLACK BOX[/bold] — logging ready.", **kwargs)
