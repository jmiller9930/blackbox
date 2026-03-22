"""Smoke tests for Cody CLI and shared planning/reporting models."""

from __future__ import annotations

from agents.cody.runtime import __version__
from agents.cody.runtime.main import main
from modules.planning.base import PlanArtifact
from modules.reporting.base import ReportArtifact, utc_now


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_main_exits_zero() -> None:
    assert main([]) == 0


def test_main_version_flag() -> None:
    assert main(["--version"]) == 0


def test_plan_artifact() -> None:
    p = PlanArtifact(title="t", summary="s", steps=["a", "b"])
    assert p.title == "t"
    assert len(p.steps) == 2


def test_report_artifact() -> None:
    r = ReportArtifact(title="r", body="x")
    assert r.title == "r"
    assert utc_now().tzinfo is not None
