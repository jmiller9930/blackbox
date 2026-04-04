"""Anna training state + catalog."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

def test_apply_repo_dotenv_sets_ollama_from_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("OLLAMA_BASE_URL=http://from-dotenv.example:11434\n", encoding="utf-8")
    from modules.anna_training.repo_env import apply_repo_dotenv

    try:
        apply_repo_dotenv(repo_root=tmp_path)
        assert os.environ.get("OLLAMA_BASE_URL") == "http://from-dotenv.example:11434"
    finally:
        os.environ.pop("OLLAMA_BASE_URL", None)


def test_apply_repo_dotenv_does_not_override_existing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://already-set:11434")
    (tmp_path / ".env").write_text("OLLAMA_BASE_URL=http://from-dotenv.example:11434\n", encoding="utf-8")
    from modules.anna_training.repo_env import apply_repo_dotenv

    apply_repo_dotenv(repo_root=tmp_path)
    assert os.environ.get("OLLAMA_BASE_URL") == "http://already-set:11434"


def test_apply_repo_dotenv_local_overrides_env_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    (tmp_path / ".env").write_text("OLLAMA_BASE_URL=http://a:11434\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("OLLAMA_BASE_URL=http://b:11434\n", encoding="utf-8")
    from modules.anna_training.repo_env import apply_repo_dotenv

    try:
        apply_repo_dotenv(repo_root=tmp_path)
        assert os.environ.get("OLLAMA_BASE_URL") == "http://b:11434"
    finally:
        os.environ.pop("OLLAMA_BASE_URL", None)


def test_ensure_preflight_respects_skip(monkeypatch) -> None:
    monkeypatch.delenv("ANNA_SKIP_PREFLIGHT", raising=False)
    monkeypatch.setenv("ANNA_SKIP_PREFLIGHT", "1")
    from modules.anna_training.readiness import ensure_anna_data_preflight

    r = ensure_anna_data_preflight()
    assert r["ok"] is True
    assert r.get("skipped") is True


def test_attempt_math_engine_wilson_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.karpathy_skill_engine import attempt_curriculum_skill
    from modules.anna_training.store import load_state

    st = load_state()
    g12 = evaluate_grade12_gates()
    r = attempt_curriculum_skill("math_engine_literacy", state=st, g12=g12)
    assert r.get("practice_kind") == "wilson_nist_reference"
    assert r.get("passed") is True


def test_karpathy_once_writes_skills_deck_and_cycle_log(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_SKIP_PREFLIGHT", "1")
    repo = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, str(repo / "scripts/runtime/anna_karpathy_loop_daemon.py"), "--once"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env={**os.environ, "BLACKBOX_ANNA_TRAINING_DIR": str(tmp_path), "ANNA_SKIP_PREFLIGHT": "1"},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    raw = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw.get("grade_12_skills_deck", {}).get("version") == 1
    assert raw.get("cumulative_learning_log")
    assert any(
        e.get("kind") == "karpathy_learning_cycle_v1" for e in (raw.get("cumulative_learning_log") or [])
    )
    ksp = raw.get("karpathy_last_skill_practice")
    assert isinstance(ksp, dict)
    assert ksp.get("ran") is True
    assert ksp.get("skill_id")
    assert "passed" in ksp
    hb_lines = (tmp_path / "karpathy_loop_heartbeat.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert hb_lines
    last_hb = json.loads(hb_lines[-1])
    assert last_hb.get("kind") == "karpathy_loop_heartbeat_v1"
    assert last_hb.get("skill_practice") == ksp
    assert (last_hb.get("data_preflight") or {}).get("schema") == "anna_data_preflight_v1"
    assert isinstance(last_hb.get("llm_preflight"), dict)
    pol = last_hb.get("preflight_policy") or {}
    assert pol.get("llm_probe_never_blocks_school") is True
    assert (raw.get("karpathy_last_data_preflight") or {}).get("schema") == "anna_data_preflight_v1"


def test_grade12_internalizes_when_all_tools_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.store import load_state, save_state

    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    st2 = load_state()
    snap = st2.get("grade_12_knowledge_internalized")
    assert isinstance(snap, dict)
    assert snap.get("version") == 1
    assert len(snap.get("skills") or []) == len(TOOL_IDS)
    assert any("INTERNALIZED G12" in str(b) for b in (st2.get("carryforward_bullets") or []))
    assert any(
        e.get("kind") == "grade_12_knowledge_internalized_v1"
        for e in (st2.get("cumulative_learning_log") or [])
    )
    save_state(st2)
    st3 = load_state()
    assert len([e for e in (st3.get("cumulative_learning_log") or []) if e.get("kind") == "grade_12_knowledge_internalized_v1"]) == 1


def test_grade12_trading_internalizes_when_overall_gate_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "1")
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.5")
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.store import load_state, save_state

    append_paper_trade(symbol="S", side="long", result="won", pnl_usd=1.0, timeframe="5m")
    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    st2 = load_state()
    assert st2.get("grade_12_knowledge_internalized")
    snap = st2.get("grade_12_trading_knowledge_internalized")
    assert isinstance(snap, dict)
    assert snap.get("version") == 1
    assert any("INTERNALIZED G12 TRADING" in str(b) for b in (st2.get("carryforward_bullets") or []))
    assert any(
        e.get("kind") == "grade_12_trading_knowledge_internalized_v1"
        for e in (st2.get("cumulative_learning_log") or [])
    )


def test_learning_signal_verdict_binary_pass_not_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.report_card_text import learning_signal_verdict
    from modules.anna_training.store import load_state

    g12_fail = evaluate_grade12_gates()
    st = load_state()
    lv_fail = learning_signal_verdict(g12_fail, st)
    assert lv_fail["verdict"] == "not_pass"
    assert lv_fail["border"] == "red"
    assert "deferred" in lv_fail["detail"].lower()
    assert "math_engine_literacy" in lv_fail["detail"]

    g12_ok = {**g12_fail, "pass": True, "curriculum_tools_pass": True, "numeric_gate_pass": True}
    lv_ok = learning_signal_verdict(g12_ok, st)
    assert lv_ok["verdict"] == "pass"
    assert lv_ok["border"] == "green"


def test_jack_executor_bridge_skips_without_cmd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.delenv("BLACKBOX_JACK_EXECUTOR_CMD", raising=False)
    from modules.anna_training.jack_executor_bridge import maybe_delegate_to_jack

    r = maybe_delegate_to_jack(execution_request={"x": 1}, mock_execution_result={"status": "executed"})
    assert r["delegated"] is False


def test_jack_executor_bridge_appends_paper_trade(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    helper = tmp_path / "fake_jack.py"
    helper.write_text(
        "import json, sys\n"
        "json.load(sys.stdin)\n"
        'print(json.dumps({"ok": True, "paper_trade": {'
        '"symbol": "SOL", "side": "long", "result": "won", "pnl_usd": 2.5, '
        '"timeframe": "5m", "notes": "jack stub"}}))\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BLACKBOX_JACK_EXECUTOR_CMD", f"{sys.executable} {helper}")
    from modules.anna_training.jack_executor_bridge import maybe_delegate_to_jack
    from modules.anna_training.paper_trades import load_paper_trades

    r = maybe_delegate_to_jack(execution_request={"kind": "execution_request_v1"}, mock_execution_result={})
    assert r.get("delegated") is True
    assert r.get("ok") is True
    assert r.get("paper_logged") is True
    trades = load_paper_trades()
    assert len(trades) == 1
    assert trades[0].get("symbol") == "SOL"
    assert "jack" in (trades[0].get("notes") or "").lower()


def test_grade12_progress_percentages_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.report_card_text import grade12_progress_percentages
    from modules.anna_training.store import load_state, save_state

    g12 = evaluate_grade12_gates()
    st = load_state()
    p0 = grade12_progress_percentages(g12, st.get("grade_12_tool_mastery"))
    assert p0["tool_checklist_pct"] == 0.0
    assert p0["numeric_track_pct"] == 0.0
    assert p0["combined_avg_pct"] == 0.0
    assert p0["tools_passed_count"] == 0
    assert p0["tools_total"] == len(TOOL_IDS)

    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    g12b = evaluate_grade12_gates()
    p1 = grade12_progress_percentages(g12b, load_state().get("grade_12_tool_mastery"))
    assert p1["tool_checklist_pct"] == 100.0
    assert p1["tools_passed_count"] == len(TOOL_IDS)


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
    assert s2["schema_version"] == "anna_training_state_v3"
    assert "carryforward_bullets" in s2
    assert "grade_12_tool_mastery" in s2
    assert "grade_12_skills_deck" in s2
    assert set((s2.get("grade_12_tool_mastery") or {}).keys()) >= {
        "math_engine_literacy",
        "analysis_algorithms",
        "rcs_rca_discipline",
        "karpathy_harness_loop",
    }


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


def test_paper_trade_stores_placement_bid_ask_spread(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.paper_trades import append_paper_trade, load_paper_trades

    append_paper_trade(
        symbol="SOL-PERP",
        side="long",
        result="won",
        pnl_usd=1.0,
        timeframe="5m",
        bid=100.0,
        ask=100.04,
    )
    r = load_paper_trades()[0]
    assert r.get("bid") == 100.0
    assert r.get("ask") == 100.04
    assert abs(float(r.get("spread") or 0) - 0.04) < 1e-9


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


def test_grade12_tool_list_includes_education_benchmark(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.curriculum_tools import GRADE_12_TOOLS

    assert all("education_benchmark" in t for t in GRADE_12_TOOLS)
    assert GRADE_12_TOOLS[0]["education_benchmark"]["id"] == "wilson_nist_reference_v1"


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
    monkeypatch.setenv("ANNA_SKIP_CURRICULUM_TOOLS_GATE", "1")
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


def test_gates_fail_when_tools_incomplete_even_if_numeric_ok(tmp_path: Path, monkeypatch) -> None:
    """Cohesive tool set must pass before overall PASS; numeric cohort alone is not enough."""
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.delenv("ANNA_SKIP_CURRICULUM_TOOLS_GATE", raising=False)
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
    assert r["numeric_gate_pass"] is True
    assert r["curriculum_tools_pass"] is False
    assert r["pass"] is False
    assert r["grade_12_current_focus"] == "math_engine_literacy"
    assert r["blockers"]
    joined = " ".join(r["blockers"])
    assert "deferred" in joined.lower()
    assert not any("decisive_trades_below" in b or "win_rate_below" in b for b in r["blockers"])


def test_gates_pass_when_all_tools_marked_and_numeric_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.delenv("ANNA_SKIP_CURRICULUM_TOOLS_GATE", raising=False)
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.6")
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "5")
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.store import load_state, save_state

    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)

    for _ in range(4):
        append_paper_trade(
            symbol="S", side="long", result="won", pnl_usd=1.0, timeframe="5m"
        )
    append_paper_trade(symbol="S", side="long", result="lost", pnl_usd=-1.0, timeframe="5m")
    r = evaluate_grade12_gates()
    assert r["curriculum_tools_pass"] is True
    assert r["numeric_gate_pass"] is True
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


def test_grade12_numeric_gate_min_net_pnl_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "1")
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.5")
    monkeypatch.setenv("ANNA_GRADE12_MIN_NET_PNL_USD", "50")
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.store import load_state, save_state

    append_paper_trade(symbol="S", side="long", result="won", pnl_usd=10.0, timeframe="5m")
    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    g12 = evaluate_grade12_gates()
    assert not g12["numeric_gate_pass"]
    assert any("net_pnl" in x for x in g12["numeric_blockers"])


def test_grade12_numeric_gate_min_net_pnl_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "1")
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.5")
    monkeypatch.setenv("ANNA_GRADE12_MIN_NET_PNL_USD", "50")
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.store import load_state, save_state

    append_paper_trade(symbol="S", side="long", result="won", pnl_usd=60.0, timeframe="5m")
    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    g12 = evaluate_grade12_gates()
    assert g12["numeric_gate_pass"]
    assert g12["pass"]


def test_grade12_bankroll_return_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "1")
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.5")
    monkeypatch.setenv("ANNA_GRADE12_PAPER_BANKROLL_START_USD", "1000")
    monkeypatch.setenv("ANNA_GRADE12_MIN_BANKROLL_RETURN_FRAC", "0.05")
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.store import load_state, save_state

    append_paper_trade(symbol="S", side="long", result="won", pnl_usd=40.0, timeframe="5m")
    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    g12 = evaluate_grade12_gates()
    assert not g12["numeric_gate_pass"]
    assert any("return_on_bankroll" in x for x in g12["numeric_blockers"])

    append_paper_trade(symbol="S", side="long", result="won", pnl_usd=10.0, timeframe="5m")
    g12b = evaluate_grade12_gates()
    assert g12b["numeric_gate_pass"]
    assert float(g12b["paper_equity_usd"] or 0) >= 1050.0


def test_school_mandate_facts_repeat_harness_until_numeric_gate(tmp_path: Path, monkeypatch) -> None:
    """Analyst FACT layer must say 'keep doing' when tools pass but cohort gate does not."""
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "50")
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.6")
    from modules.anna_training.cumulative import carryforward_fact_lines
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.store import load_state, save_state

    append_paper_trade(symbol="S", side="long", result="won", pnl_usd=5.0, timeframe="5m")
    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    st2 = load_state()
    lines = carryforward_fact_lines(st2)
    blob = " ".join(lines).lower()
    assert "school mandate" in blob
    assert "one winning trade" in blob
    assert "numeric paper cohort gate not satisfied" in blob or "not satisfied" in blob


def test_paper_manual_row_links_attempt_and_activity_total(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    from modules.anna_training.paper_trades import append_paper_trade, trades_path
    from modules.anna_training.trade_attempts import summarize_trade_activity

    append_paper_trade(
        symbol="X",
        side="long",
        result="won",
        pnl_usd=2.0,
        timeframe="1h",
        source="manual_cli",
        strategy_label="smoke-strat",
        proposal_ref="req-smoke-1",
    )
    act = summarize_trade_activity()
    assert act.total_events >= 1
    assert act.paper_manual_recorded == 1
    line = trades_path().read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(line)
    assert row.get("source") == "manual_cli"
    assert row.get("strategy_label") == "smoke-strat"
    assert row.get("proposal_ref") == "req-smoke-1"
    assert row.get("linked_attempt_event_id")


def test_vacuous_all_wins_zero_pnl_fails_numeric_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke-mode ledger (won + $0 each) must not count as a real cohort for Grade-12 numeric PASS."""
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "5")
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.6")
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.store import load_state, save_state

    for _ in range(5):
        append_paper_trade(symbol="S", side="long", result="won", pnl_usd=0.0, timeframe="5m")
    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    g12 = evaluate_grade12_gates()
    assert g12.get("curriculum_tools_pass") is True
    assert g12.get("cohort_vacuous_all_wins_zero_pnl") is True
    assert g12.get("numeric_gate_pass") is False
    assert any("vacuous" in str(b).lower() for b in (g12.get("numeric_blockers") or []))


def test_flush_runtime_clears_files_and_writes_default_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    (tmp_path / "paper_trades.jsonl").write_text('{"schema":"anna_paper_trade_v1"}\n', encoding="utf-8")
    (tmp_path / "state.json").write_text('{"schema_version":"anna_training_state_v3","karpathy_loop_iteration":999}\n', encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "school_extra.json").write_text("{}", encoding="utf-8")

    from modules.anna_training.catalog import default_state
    from modules.anna_training.runtime_reset import flush_anna_training_runtime
    from modules.anna_training.store import load_state

    # Do not clear repo execution_plane/requests.json from unit tests; CLI default does clear it on host.
    r = flush_anna_training_runtime(include_execution_requests=False)
    assert r.get("ok") is True
    assert not (tmp_path / "paper_trades.jsonl").is_file()
    assert not (nested / "school_extra.json").is_file()
    assert (tmp_path / "state.json").is_file()
    st = load_state()
    assert st.get("karpathy_loop_iteration") is None
    assert st.get("schema_version") == default_state().get("schema_version")


def test_vacuous_win_streak_can_be_ignored_for_dev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLACKBOX_ANNA_TRAINING_DIR", str(tmp_path))
    monkeypatch.setenv("ANNA_GRADE12_MIN_DECISIVE_TRADES", "5")
    monkeypatch.setenv("ANNA_GRADE12_MIN_WIN_RATE", "0.6")
    monkeypatch.setenv("ANNA_GRADE12_IGNORE_VACUOUS_WIN_STREAK", "1")
    from modules.anna_training.curriculum_tools import TOOL_IDS
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.paper_trades import append_paper_trade
    from modules.anna_training.store import load_state, save_state

    for _ in range(5):
        append_paper_trade(symbol="S", side="long", result="won", pnl_usd=0.0, timeframe="5m")
    st = load_state()
    st["grade_12_tool_mastery"] = {tid: True for tid in TOOL_IDS}
    save_state(st)
    g12 = evaluate_grade12_gates()
    assert g12.get("numeric_gate_pass") is True
    assert g12.get("cohort_vacuous_all_wins_zero_pnl") is True
