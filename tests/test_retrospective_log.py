"""Retrospective JSONL — append / read / prompt formatting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renaissance_v4.game_theory.retrospective_log import (
    append_retrospective,
    format_retrospective_for_prompt,
    read_retrospective_recent,
)


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    append_retrospective(
        what_observed="Win rate 34%; PnL small positive.",
        what_to_try_next="Run parallel_scenarios with tighter ATR vs wide.",
        run_ref="job-abc",
        path=p,
    )
    rows = read_retrospective_recent(5, path=p)
    assert len(rows) == 1
    assert rows[0]["what_to_try_next"].startswith("Run parallel")
    assert rows[0]["run_ref"] == "job-abc"


def test_format_for_prompt_non_empty(tmp_path: Path) -> None:
    p = tmp_path / "r.jsonl"
    p.write_text(
        json.dumps(
            {
                "schema": "pattern_game_retrospective_v1",
                "utc": "2030-01-01T00:00:00Z",
                "what_observed": "x",
                "what_to_try_next": "y",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    s = format_retrospective_for_prompt(limit=5, path=p)
    assert "Retrospective log" in s
    assert "Observed" in s
    assert "Try next" in s
