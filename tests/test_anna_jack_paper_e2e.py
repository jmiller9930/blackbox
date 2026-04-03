"""
E2E: Anna strategy proposal → approve → run_execution → Jack (mock) → paper_trades.jsonl.

Anna supplies analysis/strategy only; Jack (fake executable) returns the paper row — she does not
implement venue placement mechanics.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))


def _risk_analysis() -> dict:
    return {
        "input_text": "reduce exposure now",
        "policy_alignment": {"guardrail_mode": "FROZEN", "alignment": "caution"},
        "risk_assessment": {"level": "high", "factors": []},
        "suggested_action": {"intent": "HOLD", "rationale": ""},
        "concepts_used": ["risk"],
        "interpretation": {"summary": "elevated risk", "headline": "Risk", "signals": []},
        "caution_flags": [],
        "notes": [],
    }


def _fake_jack_script(path: Path) -> None:
    path.write_text(
        "import json, sys\n"
        "json.load(sys.stdin)\n"
        'print(json.dumps({"ok": True, "paper_trade": {'
        '"symbol": "SOL-PERP", "side": "long", "result": "won", "pnl_usd": 3.25, '
        '"timeframe": "5m", "notes": "mock Jack Jupiter paper", "venue": "jupiter_perp", '
        '"bid": 100.0, "ask": 100.05}}))\n',
        encoding="utf-8",
    )


def test_anna_signal_approve_run_jack_logs_paper_trade(tmp_path, monkeypatch) -> None:
    anna_dir = tmp_path / "anna_training"
    anna_dir.mkdir()
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(anna_dir))
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("BLACKBOX_JACK_DELEGATE_ENABLED", "1")

    jack_py = tmp_path / "mock_jack.py"
    _fake_jack_script(jack_py)
    monkeypatch.setenv("BLACKBOX_JACK_EXECUTOR_CMD", f"{sys.executable} {jack_py}")

    import execution_plane.approval_manager as am
    import execution_plane.execution_engine as ee

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "execution_requests.json")
    monkeypatch.setattr(ee, "is_active", lambda: False)

    from anna_modules.proposal import assemble_anna_proposal_v1
    from execution_plane.approval_manager import approve_request, create_request
    from execution_plane.execution_engine import run_execution
    from modules.anna_training.paper_trades import load_paper_trades

    proposal = assemble_anna_proposal_v1(_risk_analysis(), source_task_id=None, extra_notes=[])
    req = create_request(proposal)
    rid = req["request_id"]
    assert approve_request(rid, "e2e-human")

    result = run_execution(rid)
    assert result.get("status") == "executed"
    jd = result.get("jack_delegate") or {}
    assert jd.get("paper_logged") is True, jd

    trades = load_paper_trades()
    assert len(trades) == 1
    assert trades[0].get("symbol") == "SOL-PERP"
    assert "mock jack" in (trades[0].get("notes") or "").lower()
    assert trades[0].get("bid") == 100.0
    assert trades[0].get("ask") == 100.05
    assert abs(float(trades[0].get("spread") or 0) - 0.05) < 1e-9


def test_trader_mode_auto_execute_runs_jack_without_separate_approve(tmp_path, monkeypatch) -> None:
    anna_dir = tmp_path / "anna_training"
    anna_dir.mkdir()
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(anna_dir))
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("BLACKBOX_JACK_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ANNA_TRADER_MODE_AUTO_EXECUTE", "1")

    jack_py = tmp_path / "mock_jack.py"
    _fake_jack_script(jack_py)
    monkeypatch.setenv("BLACKBOX_JACK_EXECUTOR_CMD", f"{sys.executable} {jack_py}")

    import execution_plane.approval_manager as am
    import execution_plane.execution_engine as ee

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "execution_requests.json")
    monkeypatch.setattr(ee, "is_active", lambda: False)

    from anna_modules.proposal import assemble_anna_proposal_v1
    from execution_plane.anna_signal_execution import maybe_trader_mode_auto_execute
    from execution_plane.approval_manager import create_request
    from modules.anna_training.paper_trades import load_paper_trades

    proposal = assemble_anna_proposal_v1(_risk_analysis(), source_task_id=None, extra_notes=[])
    req = create_request(proposal)
    assert req.get("approval_status") == "pending"

    result = maybe_trader_mode_auto_execute(req["request_id"])
    assert result is not None
    assert result.get("status") == "executed"
    assert (result.get("jack_delegate") or {}).get("paper_logged") is True
    assert len(load_paper_trades()) == 1
