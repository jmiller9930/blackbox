"""Agent reflect bundle — scorecard + hunter snapshot."""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.game_theory.agent_reflect_bundle import SCHEMA_V1, build_agent_reflect_bundle

_REPO = Path(__file__).resolve().parents[1]


def test_build_agent_reflect_bundle_shape() -> None:
    out = build_agent_reflect_bundle(repo_root=_REPO)
    assert out["schema"] == SCHEMA_V1
    assert "prompt_block" in out
    assert "scorecard_markdown" in out
    assert "hunter_suggestion" in out
    assert isinstance(out["prompt_block"], str)
    hs = out["hunter_suggestion"]
    assert hs.get("ok") is True
    assert len(hs.get("scenarios", [])) == 4
