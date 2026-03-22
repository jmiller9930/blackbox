"""Support-only CLI entry (version / smoke). Does not implement OpenClaw agent behavior."""

from __future__ import annotations

import argparse

from agents.cody.runtime import __version__


def build_parser() -> argparse.ArgumentParser:
    """Construct the Cody CLI argument parser."""
    p = argparse.ArgumentParser(prog="cody", description="Cody — Code Bot (BLACK BOX)")
    p.add_argument("--version", action="store_true", help="print version and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args and run a single non-interactive action."""
    args = build_parser().parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    print("Cody runtime ready. Pass --version to print the package version.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
