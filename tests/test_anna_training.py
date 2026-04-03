"""Anna training state + catalog."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

def test_ensure_preflight_respects_skip(monkeypatch) -> None:
    monkeypatch.delenv("ANNA_SKIP_PREFLIGHT", raising=False)
    monkeypatch.setenv("ANNA_SKIP_PREFLIGHT", "1")
    from modules.anna_training.readiness import ensure_anna_data_preflight

    r = ensure_anna_data_preflight()
    assert r["ok"] is True
    assert r.get("skipped") is True


def test_readiness_shape(tmp_path: Path) -> None:
    class _Resp:
        def read(self) -> bytes:
            return b'{"jsonrpc":"2.0","result":"ok","id":1}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    with patch("modules.anna_training.readiness.urllib.request.urlopen", return_value=_Resp()):
        from modules.anna_training.readiness import full_readiness

        r = full_readiness(repo_root=tmp_path)
    assert "solana_rpc" in r and "pyth_stream" in r
    assert r["solana_rpc"].get("ok") is True


def test_default_state_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.catalog import CURRICULA, TRAINING_METHODS, default_state
    from modules.anna_training.store import load_state, save_state

    assert "grade_12_paper_only" in CURRICULA
    assert CURRICULA["grade_12_paper_only"]["live_venue_execution"] is False
    assert "karpathy_loop_v1" in TRAINING_METHODS

    s = default_state()
    save_state(s)
    s2 = load_state()
    assert s2["schema_version"] == "anna_training_state_v2"
    assert "carryforward_bullets" in s2


def test_paper_trades_and_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.paper_trades import (
        append_paper_trade,
        build_report_card_markdown,
        load_paper_trades,
        summarize_trades,
    )

    append_paper_trade(
        symbol="SOL-PERP",
        side="long",
        result="won",
        pnl_usd=10.0,
        timeframe="5m",
    )
    append_paper_trade(
        symbol="SOL-PERP",
        side="short",
        result="lost",
        pnl_usd=-4.0,
        timeframe="5m",
    )
    assert len(load_paper_trades()) == 2
    s = summarize_trades(load_paper_trades())
    assert s.wins == 1 and s.losses == 1
    assert abs(s.total_pnl_usd - 6.0) < 1e-6
    md = build_report_card_markdown(recipient_name="Sean")
    assert "Grade 12" in md and "Sean" in md and "SOL-PERP" in md


def test_assign_and_invoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.store import load_state, save_state, utc_now_iso

    st = load_state()
    st["curriculum_id"] = "grade_12_paper_only"
    st["curriculum_assigned_at_utc"] = utc_now_iso()
    st["training_method_id"] = "karpathy_loop_v1"
    st["method_invoked_at_utc"] = utc_now_iso()
    save_state(st)
    raw = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw["curriculum_id"] == "grade_12_paper_only"
    assert raw["training_method_id"] == "karpathy_loop_v1"


def test_describe_catalog_includes_complementary() -> None:
    from modules.anna_training.catalog import describe_catalog

    d = describe_catalog()
    assert d["primary_method_id"] == "karpathy_loop_v1"
    assert isinstance(d.get("complementary_pedagogy"), list)
    assert any(x.get("id") == "core_learning_loop_lock" for x in d["complementary_pedagogy"])
    assert "university_methodology_canon" in d
    assert any(x.get("id") == "bayesian_optimization_safe_strategy_tuning" for x in d["complementary_pedagogy"])


def test_gates_empty_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "1")
    from modules.anna_training.gates import evaluate_grade12_gates

    r = evaluate_grade12_gates()
    assert r["pass"] is False
    assert r["blockers"]


def test_gates_passes_when_threshold_met(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.6")
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "5")
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.gates import evaluate_grade12_gates

    for _ in range(4):
        append_paper_trade(
            symbol="S", side="long", result="won", pnl_usd=1.0, timeframe="5m"
        )
    append_paper_trade(symbol="S", side="long", result="lost", pnl_usd=-1.0, timeframe="5m")
    r = evaluate_grade12_gates()
    assert r["decisive_trades"] == 5
    assert r["win_rate"] == 0.8
    assert r["pass"] is True


def test_school_once_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_SKIP_PREFLIGHT", "1")
    repo = Path(__file__).resolve().parents[1]
    cli = repo / "scripts/runtime/anna_go_to_school.py"
    r = subprocess.run(
        [sys.executable, str(cli), "--once"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env={**os.environ, "BLACKBOX_ANNA_TRAINING_DIR": str(tmp_path), "ANNA_SKIP_PREFLIGHT": "1"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "(1) Data readiness" in r.stdout or "solana_rpc" in r.stdout
    raw = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw.get("curriculum_id") == "grade_12_paper_only"


def test_start_once_sets_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_SKIP_PREFLIGHT", "1")
    repo = Path(__file__).resolve().parents[1]
    cli = repo / "scripts/runtime/anna_training_cli.py"
    r = subprocess.run(
        [sys.executable, str(cli), "start", "--once"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env={**os.environ, "BLACKBOX_ANNA_TRAINING_DIR": str(tmp_path), "ANNA_SKIP_PREFLIGHT": "1"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    raw = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw["curriculum_id"] == "grade_12_paper_only"
    assert raw["training_method_id"] == "karpathy_loop_v1"


def test_bachelor_eligibility_requires_grade12_engagement(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_ALLOW_BACHELOR_WITHOUT_GATE", "1")
    from modules.anna_training.progression import bachelor_eligibility_report

    r = bachelor_eligibility_report(curriculum_id=None, completed_milestones=[])
    assert r["eligible_for_bachelor_paper_track_v1"] is False
    r2 = bachelor_eligibility_report(curriculum_id="grade_12_paper_only", completed_milestones=[])
    assert r2["eligible_for_bachelor_paper_track_v1"] is True


def test_promote_to_bachelor_track_sets_carryforward(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.cumulative import promote_to_bachelor_track
    from modules.anna_training.store import load_state, save_state

    st = load_state()
    st["curriculum_id"] = "grade_12_paper_only"
    save_state(st)
    st2 = load_state()
    promote_to_bachelor_track(st2)
    save_state(st2)
    st3 = load_state()
    assert st3["curriculum_id"] == "bachelor_paper_track_v1"
    assert "grade_12_paper_only" in (st3.get("completed_curriculum_milestones") or [])
    assert len(st3.get("carryforward_bullets") or []) >= 1
    assert st3.get("bachelor_track_started_at_utc")


def test_cli_training_progress_and_advance_curriculum(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_SKIP_PREFLIGHT", "1")
    monkeypatch.setenv("ANNA_ALLOW_BACHELOR_WITHOUT_GATE", "1")
    repo = Path(__file__).resolve().parents[1]
    cli = repo / "scripts/runtime/anna_training_cli.py"
    env = {
        **os.environ,
        "BLACKBOX_ANNA_TRAINING_DIR": str(tmp_path),
        "ANNA_SKIP_PREFLIGHT": "1",
        "ANNA_ALLOW_BACHELOR_WITHOUT_GATE": "1",
    }

    r0 = subprocess.run(
        [sys.executable, str(cli), "assign-curriculum", "grade_12_paper_only"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
    )
    assert r0.returncode == 0, r0.stderr
    r1 = subprocess.run(
        [sys.executable, str(cli), "training-progress"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
    )
    assert r1.returncode == 0, r1.stderr
    j1 = json.loads(r1.stdout)
    assert "suggest_next_focus" in j1 and "bachelor_eligibility" in j1

    r2 = subprocess.run(
        [sys.executable, str(cli), "advance-curriculum", "bachelor_paper_track_v1"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
    )
    assert r2.returncode == 0, r2.stderr
    raw = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw["curriculum_id"] == "bachelor_paper_track_v1"
