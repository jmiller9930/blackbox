"""Karpathy paper harness: analysis → execution → Jack (optional)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))


def test_harness_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK", "0")
    from modules.anna_training.karpathy_paper_harness import run_karpathy_paper_harness_tick

    out = run_karpathy_paper_harness_tick(iteration=1)
    assert out.get("enabled") is False


def test_harness_full_jack_paper(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    anna_dir = tmp_path / "anna_training"
    anna_dir.mkdir()
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(anna_dir))
    monkeypatch.setenv("ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK", "1")
    monkeypatch.setenv("ANNA_KARPATHY_AUTO_RUN_PAPER", "1")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("BLACKBOX_JACK_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")

    jack_py = tmp_path / "mock_jack.py"
    jack_py.write_text(
        "import json, sys\n"
        "json.load(sys.stdin)\n"
        'print(json.dumps({"ok": True, "paper_trade": {'
        '"symbol": "SOL-PERP", "side": "long", "result": "won", "pnl_usd": 1.0, '
        '"timeframe": "5m", "notes": "harness mock", "venue": "jupiter_perp"}}))\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BLACKBOX_JACK_EXECUTOR_CMD", f"{sys.executable} {jack_py}")

    import execution_plane.approval_manager as am
    import execution_plane.execution_engine as ee

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "execution_requests.json")
    monkeypatch.setattr(ee, "is_active", lambda: False)

    def _fake_analyze(*_a, **_k):
        return {
            "anna_analysis": {
                "input_text": "harness",
                "policy_alignment": {"guardrail_mode": "FROZEN", "alignment": "caution"},
                "risk_assessment": {"level": "high", "factors": []},
                "suggested_action": {"intent": "HOLD", "rationale": ""},
                "concepts_used": ["risk"],
                "interpretation": {"summary": "elevated risk", "headline": "Risk", "signals": []},
                "caution_flags": [],
                "notes": [],
                "pipeline": {"answer_source": "test"},
            }
        }

    monkeypatch.setenv("ANNA_KARPATHY_HARNESS_USE_LLM", "0")

    import anna_analyst_v1 as anna_analyst_v1_mod

    monkeypatch.setattr(anna_analyst_v1_mod, "analyze_to_dict", _fake_analyze)

    from modules.anna_training.karpathy_paper_harness import run_karpathy_paper_harness_tick

    out = run_karpathy_paper_harness_tick(iteration=42)
    assert out.get("enabled") is True
    assert out.get("paper_logged") is True
    assert out.get("execution_status") == "executed"
    snap = out.get("analysis_snapshot")
    assert isinstance(snap, dict)
    assert snap.get("interpretation_headline") == "Risk"
    assert snap.get("answer_source") == "test"

    from modules.anna_training.paper_trades import load_paper_trades

    trades = load_paper_trades()
    assert len(trades) >= 1
    assert trades[-1].get("symbol") == "SOL-PERP"


def test_harness_uses_builtin_jack_stub_when_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ANNA_KARPATHY_JACK_STUB=1 wires jack_paper_bump_stub without BLACKBOX_JACK_EXECUTOR_CMD."""
    anna_dir = tmp_path / "anna_training"
    anna_dir.mkdir()
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(anna_dir))
    monkeypatch.setenv("ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK", "1")
    monkeypatch.setenv("ANNA_KARPATHY_AUTO_RUN_PAPER", "1")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("BLACKBOX_JACK_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")
    monkeypatch.setenv("ANNA_KARPATHY_JACK_STUB", "1")
    monkeypatch.delenv("BLACKBOX_JACK_EXECUTOR_CMD", raising=False)

    import execution_plane.approval_manager as am
    import execution_plane.execution_engine as ee

    monkeypatch.setattr(am, "REQUESTS_PATH", tmp_path / "execution_requests.json")
    monkeypatch.setattr(ee, "is_active", lambda: False)

    def _fake_analyze(*_a, **_k):
        return {
            "anna_analysis": {
                "input_text": "harness",
                "policy_alignment": {"guardrail_mode": "FROZEN", "alignment": "caution"},
                "risk_assessment": {"level": "high", "factors": []},
                "suggested_action": {"intent": "HOLD", "rationale": ""},
                "concepts_used": ["risk"],
                "interpretation": {"summary": "elevated risk", "headline": "Risk", "signals": []},
                "caution_flags": [],
                "notes": [],
                "pipeline": {"answer_source": "test"},
            }
        }

    monkeypatch.setenv("ANNA_KARPATHY_HARNESS_USE_LLM", "0")
    import anna_analyst_v1 as anna_analyst_v1_mod

    monkeypatch.setattr(anna_analyst_v1_mod, "analyze_to_dict", _fake_analyze)

    from modules.anna_training.karpathy_paper_harness import run_karpathy_paper_harness_tick

    out = run_karpathy_paper_harness_tick(iteration=7)
    assert out.get("paper_logged") is True
    assert out.get("skipped") is None


def test_jack_paper_bump_stub_stdout_contract() -> None:
    import subprocess

    stub = ROOT / "scripts" / "runtime" / "jack_paper_bump_stub.py"
    proc = subprocess.run(
        [sys.executable, str(stub)],
        input=json.dumps({"execution_request": {"request_id": "abc"}}),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout.strip())
    assert out["ok"] is True
    assert out["paper_trade"]["symbol"] == "SOL-PERP"
