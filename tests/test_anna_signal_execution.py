"""Anna strategy signal → execution_request_v1 wiring (Jack downstream after approve)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))


def test_validate_anna_proposal_v1_accepts_full() -> None:
    from execution_plane.anna_signal_execution import validate_anna_proposal_v1

    p = {
        "kind": "anna_proposal_v1",
        "schema_version": 1,
        "source_analysis_reference": {"task_id": None, "kind": "anna_analysis_v1"},
        "proposal_type": "OBSERVATION_ONLY",
    }
    ok, err = validate_anna_proposal_v1(p)
    assert ok, err


def test_validate_anna_proposal_v1_rejects_wrong_kind() -> None:
    from execution_plane.anna_signal_execution import validate_anna_proposal_v1

    ok, err = validate_anna_proposal_v1({"kind": "other", "schema_version": 1})
    assert not ok


def test_create_request_rejects_invalid_proposal(tmp_path, monkeypatch) -> None:
    import execution_plane.approval_manager as am

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "req.json")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    from execution_plane.approval_manager import create_request

    with pytest.raises(ValueError, match="BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION"):
        create_request({"kind": "not_anna"})


def test_try_create_execution_request_for_risk_signal(tmp_path, monkeypatch) -> None:
    import execution_plane.approval_manager as am

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "req.json")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")

    from execution_plane.anna_signal_execution import try_create_execution_request_from_anna_analysis

    analysis = {
        "input_text": "reduce exposure now",
        "policy_alignment": {"guardrail_mode": "FROZEN", "alignment": "caution"},
        "risk_assessment": {"level": "high", "factors": []},
        "suggested_action": {"intent": "HOLD", "rationale": ""},
        "concepts_used": ["risk"],
        "interpretation": {"summary": "elevated risk", "headline": "Risk", "signals": []},
        "caution_flags": [],
        "notes": [],
    }
    handoff = try_create_execution_request_from_anna_analysis(analysis, source_task_id=None)
    assert handoff is not None
    assert handoff.get("request_id")
    assert handoff.get("status") == "pending_approval"
    assert (tmp_path / "req.json").is_file()


def test_try_create_blocked_when_strict_signal_missing(tmp_path, monkeypatch) -> None:
    import execution_plane.approval_manager as am

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "req.json")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")
    monkeypatch.setenv("ANNA_REQUIRE_SIGNAL_SNAPSHOT_FOR_EXECUTION", "1")

    from execution_plane.anna_signal_execution import try_create_execution_request_from_anna_analysis

    analysis = {
        "input_text": "reduce exposure now",
        "policy_alignment": {"guardrail_mode": "FROZEN", "alignment": "caution"},
        "risk_assessment": {"level": "high", "factors": []},
        "suggested_action": {"intent": "HOLD", "rationale": ""},
        "concepts_used": ["risk"],
        "interpretation": {"summary": "elevated risk", "headline": "Risk", "signals": []},
        "caution_flags": [],
        "notes": [],
    }
    assert try_create_execution_request_from_anna_analysis(analysis, source_task_id=None) is None


def test_try_create_skips_preflight_blocked(monkeypatch) -> None:
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")
    from execution_plane.anna_signal_execution import try_create_execution_request_from_anna_analysis

    analysis = {"pipeline": {"answer_source": "preflight_blocked"}}
    assert try_create_execution_request_from_anna_analysis(analysis, source_task_id=None) is None


def test_try_create_wires_observation_when_lab_wire_enabled(tmp_path, monkeypatch) -> None:
    """Thin analysis classifies OBSERVATION_ONLY; lab opt-in maps to CONDITION_TIGHTENING → request."""
    import execution_plane.approval_manager as am

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "req.json")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")
    monkeypatch.setenv("ANNA_KARPATHY_LAB_WIRE_JACK", "1")
    monkeypatch.delenv("ANNA_KARPATHY_DISABLE_LAB_WIRE_JACK", raising=False)

    from execution_plane.anna_signal_execution import try_create_execution_request_from_anna_analysis

    analysis = {
        "input_text": "market notes",
        "policy_alignment": {"guardrail_mode": "unknown", "alignment": "unknown"},
        "risk_assessment": {"level": "low", "factors": []},
        "suggested_action": {"intent": "WATCH", "rationale": ""},
        "concepts_used": [],
        "interpretation": {"summary": "thin", "headline": "H", "signals": []},
        "caution_flags": [],
        "notes": [],
    }
    handoff = try_create_execution_request_from_anna_analysis(analysis, source_task_id=None)
    assert handoff is not None
    assert handoff.get("request_id")
    assert (tmp_path / "req.json").is_file()


def test_try_create_skips_observation_when_disable_lab_wire(tmp_path, monkeypatch) -> None:
    """Thin analysis stays OBSERVATION_ONLY — no execution_request (strict)."""
    import execution_plane.approval_manager as am

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "req.json")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")
    monkeypatch.setenv("ANNA_KARPATHY_DISABLE_LAB_WIRE_JACK", "1")

    from execution_plane.anna_signal_execution import try_create_execution_request_from_anna_analysis

    analysis = {
        "input_text": "market notes",
        "policy_alignment": {"guardrail_mode": "unknown", "alignment": "unknown"},
        "risk_assessment": {"level": "low", "factors": []},
        "suggested_action": {"intent": "WATCH", "rationale": ""},
        "concepts_used": [],
        "interpretation": {"summary": "thin", "headline": "H", "signals": []},
        "caution_flags": [],
        "notes": [],
    }
    assert try_create_execution_request_from_anna_analysis(analysis, source_task_id=None) is None


def test_try_create_skips_thin_observation_by_default_without_lab_wire(tmp_path, monkeypatch) -> None:
    """Default: OBSERVATION_ONLY does not wire (no ANNA_KARPATHY_LAB_WIRE_JACK)."""
    import execution_plane.approval_manager as am

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "req.json")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")
    monkeypatch.delenv("ANNA_KARPATHY_DISABLE_LAB_WIRE_JACK", raising=False)
    monkeypatch.delenv("ANNA_KARPATHY_LAB_WIRE_JACK", raising=False)

    from execution_plane.anna_signal_execution import try_create_execution_request_from_anna_analysis

    analysis = {
        "input_text": "market notes",
        "policy_alignment": {"guardrail_mode": "unknown", "alignment": "unknown"},
        "risk_assessment": {"level": "low", "factors": []},
        "suggested_action": {"intent": "WATCH", "rationale": ""},
        "concepts_used": [],
        "interpretation": {"summary": "thin", "headline": "H", "signals": []},
        "caution_flags": [],
        "notes": [],
    }
    assert try_create_execution_request_from_anna_analysis(analysis, source_task_id=None) is None
