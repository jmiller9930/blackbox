"""Directive 4.6.3.3 — messaging_interface normalized output + CLI path."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_normalized_anna_factual_datetime() -> None:
    from messaging_interface.normalized import normalized_from_payload
    from messaging_interface.pipeline import run_dispatch_pipeline

    payload = run_dispatch_pipeline("What day is it?", display_name=None)
    norm = normalized_from_payload(payload)
    assert norm.get("kind") == "anna"
    assert norm.get("interpretation.summary") is not None
    assert norm.get("answer_source") is not None
    assert "limitation_flag" in norm


def test_cli_adapter_smoke() -> None:
    """echo question | python -m messaging_interface.cli_adapter returns JSON."""
    r = subprocess.run(
        [sys.executable, "-m", "messaging_interface.cli_adapter"],
        input="What day is it?\n",
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env={**dict(__import__("os").environ), "ANNA_USE_LLM": "0"},
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data.get("kind") == "anna"
    assert "interpretation.summary" in data
