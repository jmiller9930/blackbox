"""
Optional TUI wrapper for the playground CLI.

Delegates to run_data_pipeline via subprocess — does not import learning_core.
Install: prompt_toolkit (see requirements.txt).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1]


def main() -> None:
    argv = list(sys.argv[1:])
    if argv:
        cmd = [sys.executable, "-m", "playground.run_data_pipeline"] + argv
        raise SystemExit(subprocess.call(cmd, cwd=str(_RUNTIME)))

    try:
        from prompt_toolkit import PromptSession
    except ImportError:
        print(
            "prompt_toolkit not installed. Use: python -m playground.run_data_pipeline --help",
            file=sys.stderr,
        )
        raise SystemExit(1)

    session = PromptSession()
    sb = session.prompt("sandbox-db path (required): ").strip()
    if not sb:
        print("sandbox-db required.", file=sys.stderr)
        raise SystemExit(2)
    step = session.prompt("Enable step mode? [y/N]: ").strip().lower() in ("y", "yes")
    seed = session.prompt("Use --seed-demo? [Y/n]: ").strip().lower() not in ("n", "no")
    extra = ["--sandbox-db", sb]
    if seed:
        extra.append("--seed-demo")
    if step:
        extra.append("--step")
    cmd = [sys.executable, "-m", "playground.run_data_pipeline"] + extra
    raise SystemExit(subprocess.call(cmd, cwd=str(_RUNTIME)))


if __name__ == "__main__":
    main()
