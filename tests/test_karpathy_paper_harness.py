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


def test_harness_default_stub_when_no_jack_cmd_no_stub_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bundled stub is default when JACK cmd unset (tier-1); no ANNA_KARPATHY_JACK_STUB needed."""
    anna_dir = tmp_path / "anna_training"
    anna_dir.mkdir()
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(anna_dir))
    monkeypatch.setenv("ANNA_KARPATHY_PAPER_HARNESS_EACH_TICK", "1")
    monkeypatch.setenv("ANNA_KARPATHY_AUTO_RUN_PAPER", "1")
    monkeypatch.setenv("BLACKBOX_REQUIRE_ANNA_PROPOSAL_FOR_EXECUTION", "1")
    monkeypatch.setenv("BLACKBOX_JACK_DELEGATE_ENABLED", "1")
    monkeypatch.setenv("ANNA_AUTO_EXECUTION_REQUEST", "1")
    monkeypatch.delenv("BLACKBOX_JACK_EXECUTOR_CMD", raising=False)
    monkeypatch.delenv("ANNA_KARPATHY_JACK_STUB", raising=False)

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

    out = run_karpathy_paper_harness_tick(iteration=9)
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
    assert out["paper_trade"]["result"] in ("won", "lost", "breakeven", "abstain")


def test_jack_stub_paper_outcomes_deterministic() -> None:
    """Same request_id → same ledger result; overrides still work."""
    import os
    import subprocess

    stub = ROOT / "scripts" / "runtime" / "jack_paper_bump_stub.py"
    payload = json.dumps({"execution_request": {"request_id": "deterministic-test-rid-001"}})

    def run_stub(extra: dict | None = None) -> dict:
        env = {**os.environ, **(extra or {})}
        proc = subprocess.run(
            [sys.executable, str(stub)],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
            env=env,
        )
        assert proc.returncode == 0
        return json.loads(proc.stdout.strip())

    a = run_stub()
    b = run_stub()
    assert a["paper_trade"]["result"] == b["paper_trade"]["result"]
    assert a["paper_trade"]["pnl_usd"] == b["paper_trade"]["pnl_usd"]

    forced = run_stub({"JACK_STUB_RESULT": "lost", "JACK_STUB_PNL_USD": "-2.5"})
    assert forced["paper_trade"]["result"] == "lost"
    assert forced["paper_trade"]["pnl_usd"] == -2.5

    always_won = run_stub({"JACK_STUB_ALWAYS_WIN": "1"})
    assert always_won["paper_trade"]["result"] == "won"
    assert always_won["paper_trade"]["pnl_usd"] == 0.0

    legacy_sim_off = run_stub({"JACK_STUB_SIMULATE": "0"})
    assert legacy_sim_off["paper_trade"]["result"] == "won"
    assert legacy_sim_off["paper_trade"]["pnl_usd"] == 0.0


def test_jack_stub_mix_key_includes_created_at() -> None:
    """Same request_id but different created_at → different mix key (distinct outcomes per new request)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "jack_paper_bump_stub",
        ROOT / "scripts" / "runtime" / "jack_paper_bump_stub.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = mod._handoff_mix_key(
        {
            "execution_request": {
                "request_id": "same",
                "created_at": "2026-01-01T00:00:00Z",
                "proposal_id": "p1",
            }
        }
    )
    b = mod._handoff_mix_key(
        {
            "execution_request": {
                "request_id": "same",
                "created_at": "2026-01-02T00:00:00Z",
                "proposal_id": "p1",
            }
        }
    )
    assert a != b
