"""scripts/openclaw/slack_anna_ingress.py — routing exit codes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "openclaw" / "slack_anna_ingress.py"


def test_not_anna_exits_2() -> None:
    r = subprocess.run([sys.executable, str(_SCRIPT), "hello"], capture_output=True, text=True)
    assert r.returncode == 2


def test_anna_route_runs() -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "Anna, ping"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0
    assert "[Anna — Trading Analyst]" in r.stdout or "[BlackBox" in r.stdout
