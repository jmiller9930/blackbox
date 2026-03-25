"""scripts/openclaw/slack_anna_ingress.py — routing/containment behaviors."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "openclaw" / "slack_anna_ingress.py"


def test_greeting_returns_single_system_reply() -> None:
    r = subprocess.run([sys.executable, str(_SCRIPT), "hello"], capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.startswith("[BlackBox — System Agent]")
    assert "Hello — how can I help?" in r.stdout


def test_wrapped_greeting_returns_single_system_reply() -> None:
    r = subprocess.run([sys.executable, str(_SCRIPT), "1. `hello`"], capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.startswith("[BlackBox — System Agent]")
    assert "Hello — how can I help?" in r.stdout


def test_non_anna_non_greeting_exits_2() -> None:
    r = subprocess.run([sys.executable, str(_SCRIPT), "status"], capture_output=True, text=True)
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
