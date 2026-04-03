#!/usr/bin/env python3
"""
Anna training — curriculum, method, paper trade log, dashboard, grade-12 report card (markdown).

State: data/runtime/anna_training/state.json; trades: paper_trades.jsonl (override dir with BLACKBOX_ANNA_TRAINING_DIR).

Examples (repo root):
  python3 scripts/runtime/anna_go_to_school.py   # ONE entry: readiness + gates + start (same as `school` subcommand)
  python3 scripts/runtime/anna_training_cli.py school   # same (check-readiness, gates, then start)
  python3 scripts/runtime/anna_training_cli.py start   # preflight + Grade 12 + Karpathy + interactive TUI only
  python3 scripts/runtime/anna_training_cli.py start --once   # assign + single dashboard, then exit (scripting)
  python3 scripts/runtime/anna_training_cli.py gates   # PASS/FAIL vs 60% + min decisive trades (see env vars)
  python3 scripts/runtime/anna_training_cli.py check-readiness   # Solana RPC + Pyth artifact + DB — run first
  python3 scripts/runtime/anna_training_cli.py loop-daemon       # Karpathy loop until SIGTERM (heartbeat JSONL)
  python3 scripts/runtime/anna_training_cli.py status
  python3 scripts/runtime/anna_training_cli.py log-trade --symbol SOL-PERP --side long --result won --pnl-usd 10.5 --timeframe 5m
  ANNA_KARPATHY_AUTO_PAPER_HARNESS=1 python3 scripts/runtime/anna_karpathy_loop_daemon.py --once   # optional synthetic cohort rows when gate open
  python3 scripts/runtime/anna_training_cli.py harness-tick --force   # one synthetic row if tools PASS & gate not (lab)
  python3 scripts/runtime/anna_training_cli.py dashboard
  python3 scripts/runtime/anna_training_cli.py report-card --out docs/working/anna_grade12_report_card.md --recipient Sean
  python3 scripts/runtime/anna_training_cli.py assign-curriculum grade_12_paper_only
  python3 scripts/runtime/anna_training_cli.py invoke-method karpathy_loop_v1
  python3 scripts/runtime/anna_training_cli.py note "Reviewed simulation run — ok"
  python3 scripts/runtime/anna_training_cli.py llm-cross-check --file draft.txt   # internal Ollama cross-check (no external chat)
  echo "My draft thesis..." | python3 scripts/runtime/anna_training_cli.py llm-cross-check
  python3 scripts/runtime/anna_training_cli.py math-check   # Wilson NIST-style cases (float vs Decimal); run before school
  python3 scripts/runtime/anna_training_cli.py quant-metrics  # paper P&L: Sharpe/Sortino proxies, DD, VaR/CVaR (math engine)
  python3 scripts/runtime/anna_training_cli.py math-engine-full  # ARIMA/GARCH, annualized Sharpe, WFO, MC, ML, Kalman
  python3 scripts/runtime/anna_training_cli.py training-progress  # ACL-lite: next focus + bachelor eligibility + cumulative tail
  python3 scripts/runtime/anna_training_cli.py advance-curriculum bachelor_paper_track_v1  # Grade 12 → bachelor (gates + prereq)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.anna_training.catalog import (  # noqa: E402
    COMPLEMENTARY_PEDAGOGY,
    CURRICULA,
    TRAINING_METHODS,
    describe_catalog,
)
from modules.anna_training.cumulative import append_cumulative_log, promote_to_bachelor_track  # noqa: E402
from modules.anna_training.curriculum_tools import (  # noqa: E402
    GRADE_12_TOOLS,
    TOOL_IDS,
    normalize_tool_mastery,
)
from modules.anna_training.progression import bachelor_eligibility_report, suggest_next_focus  # noqa: E402
from modules.anna_training.report_card_text import (  # noqa: E402
    grade12_progress_percentages,
    improvement_lines_from_gate_result,
    learning_signal_verdict,
)
from modules.anna_training.internalized_knowledge import (  # noqa: E402
    internalized_grade12_snapshot,
    internalized_trading_snapshot,
)
from modules.anna_training.gates import evaluate_grade12_gates  # noqa: E402
from modules.anna_training.readiness import ensure_anna_data_preflight, full_readiness  # noqa: E402
from modules.anna_training.school_mandate import (  # noqa: E402
    build_school_mandate_fact_lines,
    compute_school_mandate_payload,
)
from modules.anna_training.paper_trades import (  # noqa: E402
    append_paper_trade,
    build_report_card_markdown,
    load_paper_trades,
    summarize_trades,
    trades_path,
)
from modules.anna_training.trade_attempts import (  # noqa: E402
    attempts_path,
    format_trade_activity_evidence_lines,
    summarize_trade_activity,
)
from modules.anna_training.llm_cross_check import (  # noqa: E402
    append_cross_check_log,
    run_llm_cross_check,
)
from modules.anna_training.quant_metrics import compute_paper_quant_metrics  # noqa: E402
from modules.anna_training.wilson_nist_reference import run_wilson_reference_check  # noqa: E402
from modules.anna_training.store import (  # noqa: E402
    anna_training_dir,
    load_state,
    save_state,
    state_path,
    utc_now_iso,
)


def _cmd_status() -> int:
    st = load_state()
    cat = describe_catalog()
    cur_id = st.get("curriculum_id")
    meth_id = st.get("training_method_id")
    cur = cat["curricula"].get(cur_id) if cur_id else None
    meth = cat["methods"].get(meth_id) if meth_id else None
    out = {
        "state_file": str(state_path()),
        "assigned_curriculum_id": cur_id,
        "curriculum_title": (cur or {}).get("title") if cur else None,
        "live_venue_execution": (cur or {}).get("live_venue_execution") if cur else None,
        "active_method_id": meth_id,
        "method_title": (meth or {}).get("title") if meth else None,
        "curriculum_assigned_at_utc": st.get("curriculum_assigned_at_utc"),
        "method_invoked_at_utc": st.get("method_invoked_at_utc"),
        "operator_notes_count": len(st.get("operator_notes") or []),
        "last_notes": (st.get("operator_notes") or [])[-5:],
        "completed_curriculum_milestones": st.get("completed_curriculum_milestones") or [],
        "carryforward_bullet_count": len(st.get("carryforward_bullets") or []),
        "cumulative_learning_log_entries": len(st.get("cumulative_learning_log") or []),
        "bachelor_track_started_at_utc": st.get("bachelor_track_started_at_utc"),
        "grade_12_tool_mastery": normalize_tool_mastery(st.get("grade_12_tool_mastery")),
        "grade_12_tools_all_passed": all(normalize_tool_mastery(st.get("grade_12_tool_mastery")).get(tid) for tid in TOOL_IDS),
        "grade_12_skills_deck": st.get("grade_12_skills_deck") or {},
        "karpathy_last_skill_practice": st.get("karpathy_last_skill_practice"),
        "grade_12_knowledge_internalized": internalized_grade12_snapshot(st),
        "grade_12_trading_knowledge_internalized": internalized_trading_snapshot(st),
        "school_mandate_v1": compute_school_mandate_payload(st),
    }
    g12 = evaluate_grade12_gates()
    out["grade_12_progress"] = grade12_progress_percentages(g12, st.get("grade_12_tool_mastery"))
    out["learning_signal"] = learning_signal_verdict(g12, st)
    _tr = load_paper_trades()
    _sm = summarize_trades(_tr)
    _act = summarize_trade_activity()
    out["paper_ledger"] = {
        "path": str(trades_path()),
        "row_count": _sm.trade_count,
        "decisive": _sm.wins + _sm.losses,
        "wins": _sm.wins,
        "losses": _sm.losses,
    }
    out["trade_attempt_log"] = {
        "path": str(attempts_path()),
        "total_events": _act.total_events,
        "jack_delegate_started": _act.jack_delegate_started,
        "jack_delegate_failed": _act.jack_delegate_failed,
        "jack_ok_with_paper": _act.jack_delegate_ok_with_paper,
        "jack_ok_no_paper": _act.jack_delegate_ok_no_paper,
        "execution_blocked": _act.execution_blocked,
        "manual_cli_log_trade_recorded": _act.paper_manual_recorded,
        "karpathy_harness_auto_recorded": _act.harness_auto_recorded,
    }
    out["grade_12_gate_snapshot"] = {
        "pass": g12.get("pass"),
        "curriculum_tools_pass": g12.get("curriculum_tools_pass"),
        "numeric_gate_pass": g12.get("numeric_gate_pass"),
        "decisive_trades": g12.get("decisive_trades"),
        "min_decisive_trades": g12.get("min_decisive_trades"),
        "total_pnl_usd": g12.get("total_pnl_usd"),
        "paper_bankroll_start_usd": g12.get("paper_bankroll_start_usd"),
        "paper_equity_usd": g12.get("paper_equity_usd"),
        "min_net_pnl_usd": g12.get("min_net_pnl_usd"),
        "min_equity_usd": g12.get("min_equity_usd"),
        "min_bankroll_return_frac": g12.get("min_bankroll_return_frac"),
    }
    print(json.dumps(out, indent=2))
    return 0


def _cmd_curricula() -> int:
    print(json.dumps(describe_catalog(), indent=2))
    return 0


def _cmd_assign(args: argparse.Namespace) -> int:
    cid = args.curriculum_id.strip()
    if cid not in CURRICULA:
        print(json.dumps({"error": "unknown_curriculum", "id": cid, "valid": list(CURRICULA.keys())}), file=sys.stderr)
        return 1
    st = load_state()
    st["curriculum_id"] = cid
    st["curriculum_assigned_at_utc"] = utc_now_iso()
    save_state(st)
    print(json.dumps({"ok": True, "curriculum_id": cid, "assigned_at": st["curriculum_assigned_at_utc"]}, indent=2))
    return 0


def _cmd_invoke(args: argparse.Namespace) -> int:
    mid = args.method_id.strip()
    if mid not in TRAINING_METHODS:
        print(json.dumps({"error": "unknown_method", "id": mid, "valid": list(TRAINING_METHODS.keys())}), file=sys.stderr)
        return 1
    st = load_state()
    st["training_method_id"] = mid
    st["method_invoked_at_utc"] = utc_now_iso()
    save_state(st)
    print(
        json.dumps(
            {
                "ok": True,
                "method_id": mid,
                "invoked_at": st["method_invoked_at_utc"],
                "steps": TRAINING_METHODS[mid].get("steps"),
            },
            indent=2,
        )
    )
    return 0


def _cmd_log_trade(args: argparse.Namespace) -> int:
    try:
        row = append_paper_trade(
            symbol=args.symbol,
            side=args.side,
            result=args.result,
            pnl_usd=float(args.pnl_usd),
            timeframe=args.timeframe,
            venue=(args.venue or "jupiter_perp"),
            notes=(args.notes or ""),
            source="manual_cli",
            proposal_ref=((getattr(args, "proposal_ref", None) or "").strip() or None),
            strategy_label=((getattr(args, "strategy_label", None) or "").strip() or None),
        )
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "trade": row}, indent=2))
    return 0


def _cmd_harness_tick(args: argparse.Namespace) -> int:
    """Opt-in synthetic cohort row — same logic as Karpathy daemon auto harness."""
    from modules.anna_training.gates import evaluate_grade12_gates
    from modules.anna_training.harness_auto_tick import run_automated_paper_harness_tick

    st = load_state()
    n = int(st.get("karpathy_loop_iteration") or 0)
    g12 = evaluate_grade12_gates(training_state=st)
    r = run_automated_paper_harness_tick(
        karpathy_iteration=n + 1,
        g12=g12,
        force=bool(getattr(args, "force", False)),
    )
    print(json.dumps({"ok": r is not None, "result": r}, indent=2))
    return 0 if r else 2


def _cmd_math_check() -> int:
    """Wilson 95% intervals: float engine vs Decimal oracle (NIST-style regression cases)."""
    out = run_wilson_reference_check()
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 3


def _cmd_quant_metrics() -> int:
    """Paper-trade quant metrics (same module as Anna math_engine paper_quant)."""
    out = compute_paper_quant_metrics(load_paper_trades())
    print(json.dumps({"ok": True, "metrics": out}, indent=2))
    return 0


def _cmd_math_engine_full() -> int:
    """Full stack: ARIMA, GARCH, annualized Sharpe, walk-forward, Monte Carlo, ML baseline, Kalman; coint if aux added later."""
    try:
        from modules.anna_training.math_engine_full.stack import run_full_math_stack
    except ImportError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "math_engine_full_import_failed",
                    "detail": str(e),
                    "hint": "Install deps: python3 -m pip install -r requirements.txt (see README, lab host without venv)",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    result = run_full_math_stack(load_paper_trades(), aux=None)
    print(json.dumps({"ok": True, "result": result}, indent=2))
    return 0


def _cmd_training_progress() -> int:
    """ACL-lite: next focus + bachelor eligibility + cumulative log tail."""
    st = load_state()
    out = {
        "suggest_next_focus": suggest_next_focus(
            curriculum_id=st.get("curriculum_id"),
            training_method_id=st.get("training_method_id"),
        ),
        "bachelor_eligibility": bachelor_eligibility_report(
            curriculum_id=st.get("curriculum_id"),
            completed_milestones=st.get("completed_curriculum_milestones") or [],
        ),
        "cumulative_learning_log_last_8": (st.get("cumulative_learning_log") or [])[-8:],
        "carryforward_bullets": (st.get("carryforward_bullets") or [])[:12],
    }
    print(json.dumps(out, indent=2))
    return 0


def _cmd_advance_curriculum(args: argparse.Namespace) -> int:
    """Promote to bachelor_paper_track_v1 when gates + prereq satisfied (or ANNA_ALLOW_BACHELOR_WITHOUT_GATE)."""
    cid = (args.curriculum_id or "").strip()
    if cid not in CURRICULA:
        print(
            json.dumps({"error": "unknown_curriculum", "id": cid, "valid": list(CURRICULA.keys())}),
            file=sys.stderr,
        )
        return 1
    if cid != "bachelor_paper_track_v1":
        print(
            json.dumps(
                {
                    "error": "advance_only_bachelor_implemented",
                    "hint": "Use assign-curriculum for other ids; advance-curriculum promotes Grade 12 → bachelor track.",
                }
            ),
            file=sys.stderr,
        )
        return 1
    st = load_state()
    if st.get("curriculum_id") == "bachelor_paper_track_v1":
        print(json.dumps({"ok": True, "already": "bachelor_paper_track_v1"}, indent=2))
        return 0
    rep = bachelor_eligibility_report(
        curriculum_id=st.get("curriculum_id"),
        completed_milestones=st.get("completed_curriculum_milestones") or [],
    )
    if not rep.get("eligible_for_bachelor_paper_track_v1"):
        print(json.dumps({"ok": False, "bachelor_eligibility": rep}, indent=2), file=sys.stderr)
        return 1
    promote_to_bachelor_track(st)
    save_state(st)
    print(json.dumps({"ok": True, "curriculum_id": "bachelor_paper_track_v1", "state_file": str(state_path())}, indent=2))
    return 0


def _cmd_check_readiness() -> int:
    print(json.dumps(full_readiness(), indent=2))
    return 0


def _cmd_gates() -> int:
    """Grade-12 gate: curriculum tools (cohesive) then numeric paper cohort; exit 0 when pass."""
    out = evaluate_grade12_gates()
    print(json.dumps(out, indent=2))
    return 0 if out.get("pass") else 1


def _cmd_tool_list() -> int:
    """JSON checklist of Grade 12 tools (must pass before 60% / min-N counts for overall PASS)."""
    st = load_state()
    m = normalize_tool_mastery(st.get("grade_12_tool_mastery"))
    out = {
        "schema": "anna_grade_12_tool_list_v1",
        "tools": [{**t, "passed": bool(m.get(t["id"]))} for t in GRADE_12_TOOLS],
        "all_passed": all(m.get(tid) for tid in TOOL_IDS),
        "hint": (
            "Default: Karpathy loop auto-attests when education_benchmark passes (ANNA_KARPATHY_AUTO_ATTEST_TOOLS, default on). "
            "Manual override: anna tool-pass <tool_id>. Each tool includes education_benchmark in this JSON."
        ),
        "auto_attest_default": True,
        "auto_attest_env": "ANNA_KARPATHY_AUTO_ATTEST_TOOLS (set 0/false to disable)",
    }
    print(json.dumps(out, indent=2))
    return 0


def _cmd_tool_pass(args: argparse.Namespace) -> int:
    """Operator attestation: tool mastered (see anna tool-list for ids)."""
    tid = (args.tool_id or "").strip()
    if tid not in TOOL_IDS:
        print(json.dumps({"error": "unknown_tool_id", "id": tid, "valid": list(TOOL_IDS)}), file=sys.stderr)
        return 1
    st = load_state()
    mp = normalize_tool_mastery(st.get("grade_12_tool_mastery"))
    mp[tid] = True
    st["grade_12_tool_mastery"] = mp
    append_cumulative_log(
        st,
        kind="grade_12_tool_passed",
        summary=f"Operator passed curriculum tool {tid}",
        curriculum_id=st.get("curriculum_id"),
    )
    save_state(st)
    print(
        json.dumps(
            {
                "ok": True,
                "tool_id": tid,
                "all_tools_passed": all(mp.get(x) for x in TOOL_IDS),
            },
            indent=2,
        )
    )
    return 0


def _require_preflight_or_exit() -> int | None:
    """Run before every subcommand except `check-readiness`. Fail closed with JSON on stderr."""
    pf = ensure_anna_data_preflight()
    if pf["ok"] or pf.get("skipped"):
        return None
    print(json.dumps({"error": "preflight_failed", "preflight": pf}, indent=2), file=sys.stderr)
    return 5


def _cmd_dashboard(args: argparse.Namespace | None = None) -> int:
    live = bool(getattr(args, "live", False) if args is not None else False)
    refresh_sec = max(3.0, float(getattr(args, "interval", 10.0) if args is not None else 10.0))

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
    except ImportError:
        trades = load_paper_trades()
        s = summarize_trades(trades)
        g12 = evaluate_grade12_gates()
        st0 = load_state()
        prog = grade12_progress_percentages(g12, st0.get("grade_12_tool_mastery"))
        lv0 = learning_signal_verdict(g12, st0)
        tact = summarize_trade_activity()
        print(
            json.dumps(
                {
                    "report_card": {
                        "learning_slice_pass": bool(g12.get("pass")),
                        "learning_signal": lv0,
                        "blockers": g12.get("blockers"),
                        "improvement_hints": improvement_lines_from_gate_result(g12),
                        "grade_12_progress": prog,
                    },
                    "summary": s.__dict__,
                    "trades": len(trades),
                    "trade_attempt_log": {
                        "path": str(attempts_path()),
                        "total_events": tact.total_events,
                        "manual_cli_log_trade_recorded": tact.paper_manual_recorded,
                        "karpathy_harness_auto_recorded": tact.harness_auto_recorded,
                    },
                },
                indent=2,
            )
        )
        return 0

    def _print_once() -> None:
        st = load_state()
        cid = (st.get("curriculum_id") or "") or ""
        cur = CURRICULA.get(cid) if cid else None
        g12 = evaluate_grade12_gates()
        sf = suggest_next_focus(
            curriculum_id=st.get("curriculum_id"),
            training_method_id=st.get("training_method_id"),
        )
        be = bachelor_eligibility_report(
            curriculum_id=st.get("curriculum_id"),
            completed_milestones=st.get("completed_curriculum_milestones") or [],
        )
        prog = grade12_progress_percentages(g12, st.get("grade_12_tool_mastery"))
        lv = learning_signal_verdict(g12, st)
        gate_pass = bool(g12.get("pass"))
        gate_style = "[bold green]PASS[/bold green]" if gate_pass else "[bold red]NOT PASS[/bold red]"
        v = lv.get("verdict") or "not_pass"
        if v == "pass":
            learn_block = f"[bold green]{lv['headline']}[/bold green]\n[dim]{lv['detail']}[/dim]"
        else:
            learn_block = f"[bold red]{lv['headline']}[/bold red]\n[dim]{lv['detail']}[/dim]"
        ct_ok = bool(g12.get("curriculum_tools_pass"))
        ng_ok = bool(g12.get("numeric_gate_pass"))
        ct_s = "[bold green]PASS[/bold green]" if ct_ok else "[bold yellow]NOT PASS[/bold yellow]"
        ng_s = "[bold green]PASS[/bold green]" if ng_ok else "[bold yellow]NOT PASS[/bold yellow]"
        min_dt = g12.get("min_decisive_trades")
        dec_raw = g12.get("decisive_trades")
        wr = g12.get("win_rate")
        wr_s = f"{wr:.0%}" if wr is not None else "—"
        elig = "[bold green]yes[/bold green]" if be.get("eligible_for_bachelor_paper_track_v1") else "[dim]no[/dim]"
        cur_title = (cur or {}).get("title", cid or "(not assigned)")
        stage = (cur or {}).get("stage", "—")
        hints_lines = (sf.get("hints") or [])[:5]
        hints_txt = "\n".join(f"  • {h}" for h in hints_lines) if hints_lines else "  —"
        bullets = list(st.get("carryforward_bullets") or [])[:6]
        carry_txt = "\n".join(f"  • {b}" for b in bullets) if bullets else "  — (none yet; promotes with bachelor track)"

        blockers = list(g12.get("blockers") or [])
        why_txt = ""
        if blockers:
            why_txt = "\n[bold]Why not (from gates)[/bold]\n" + "\n".join(
                f"  [red]•[/red] {b}" for b in blockers
            )
        imp = improvement_lines_from_gate_result(g12)
        imp_txt = ""
        if imp and not gate_pass:
            imp_txt = "\n[bold]Where to improve her code / stack[/bold]\n" + "\n".join(f"  • {x}" for x in imp)

        border_learning = "green" if lv.get("verdict") == "pass" else "red"
        deck = st.get("grade_12_skills_deck") or {}
        deck_line = ""
        if isinstance(deck, dict) and deck.get("version"):
            cf = deck.get("current_focus_requirement") or "—"
            dc = "yes" if deck.get("deck_complete") else "no"
            deck_line = (
                f"\n[bold]Skills deck[/bold] — [yellow]ONE skill at a time[/yellow] in fixed order "
                f"(do not skip ahead). Current focus [yellow]{cf}[/yellow]  |  deck complete [cyan]{dc}[/cyan]\n"
            )
        sp_line = ""
        sp = st.get("karpathy_last_skill_practice")
        if isinstance(sp, dict) and sp.get("tick_index") is not None:
            if sp.get("ran"):
                p_ok = bool(sp.get("passed"))
                sp_style = "[bold green]PASS[/bold green]" if p_ok else "[bold yellow]NOT PASS[/bold yellow]"
                sp_line = (
                    f"\n[bold]Last Karpathy skill check (daemon)[/bold] — {sp_style}  |  "
                    f"[cyan]{sp.get('skill_id', '—')}[/cyan]  |  [dim]{sp.get('summary', '')}[/dim]\n"
                )
            else:
                sp_line = (
                    f"\n[bold]Last Karpathy skill check (daemon)[/bold] — [dim]no tool practice this tick[/dim]  "
                    f"(focus [yellow]{sp.get('current_focus', '—')}[/yellow])\n"
                )
        report_body = (
            f"[dim]Report card — answers: is learning shown on the scored path (tools, paper, logs)?[/dim]\n\n"
            f"{learn_block}{deck_line}{sp_line}\n"
            f"[bold]Measurable progress[/bold]: tool checklist [cyan]{prog['tool_checklist_pct']}%[/cyan] "
            f"([cyan]{prog['tools_passed_count']}/{prog['tools_total']}[/cyan] attested)  |  "
            f"paper numeric track [cyan]{prog['numeric_track_pct']}%[/cyan]"
            + (
                " [dim](locked until all four tools passed)[/dim]"
                if not g12.get("curriculum_tools_pass")
                else ""
            )
            + "  |  "
            f"combined avg [cyan]{prog['combined_avg_pct']}%[/cyan]  |  bottleneck [yellow]{prog['bottleneck_pct']}%[/yellow]\n"
            f"[dim]Per-row % below = attestation after evidence. Sequential skills first; then paper cohort.[/dim]\n\n"
            f"[bold]Curriculum[/bold]: {cid or '—'} — {cur_title}\n"
            f"[dim]Stage[/dim]: {stage}\n\n"
            f"[bold]Overall[/bold]: {gate_style}  [dim](tools, then numeric min-N + win rate; optional P&L/bankroll env)[/dim]\n"
            f"[bold]Curriculum tools[/bold]: {ct_s}  |  [bold]Numeric paper[/bold]: {ng_s}\n"
            f"[dim]Cohort: decisive {dec_raw}/{min_dt}, win rate {wr_s}  |  net P&L USD [cyan]{float(g12.get('total_pnl_usd') or 0):.2f}[/cyan][/dim]"
            f"{why_txt}"
            f"{imp_txt}\n\n"
            f"[bold]Bachelor paper track eligible[/bold]: {elig}\n\n"
            f"[bold]Next focus[/bold]: {sf.get('focus', '—')}\n"
            f"{hints_txt}\n\n"
            f"[bold]Carry-forward[/bold]:\n{carry_txt}"
        )

        trades = load_paper_trades()
        s = summarize_trades(trades)
        bs = g12.get("paper_bankroll_start_usd")
        eq = g12.get("paper_equity_usd")
        bankroll_line = ""
        if bs is not None and eq is not None:
            bankroll_line = (
                f"\nNotional bankroll: start [bold]${float(bs):,.2f}[/bold] → "
                f"equity [bold]${float(eq):,.2f}[/bold] (start + sum of pnl_usd in log)"
            )
        elif bs is None and ct_ok and s.trade_count > 0:
            bankroll_line = (
                "\n[dim]Set ANNA_GRADE12_PAPER_BANKROLL_START_USD to show start → equity (growth vs notional).[/dim]"
            )
        req_bits: list[str] = []
        if g12.get("min_net_pnl_usd") is not None:
            req_bits.append(f"net P&L ≥ ${float(g12['min_net_pnl_usd']):,.2f}")
        if g12.get("min_equity_usd") is not None:
            req_bits.append(f"equity ≥ ${float(g12['min_equity_usd']):,.2f}")
        if g12.get("min_bankroll_return_frac") is not None:
            req_bits.append(f"return ≥ {float(g12['min_bankroll_return_frac']):.2%} on start")
        req_line = ""
        if req_bits:
            req_line = "\n[dim]Optional numeric gates also require:[/dim] " + " | ".join(req_bits)
        pnl_note = (
            "\n[dim]Outcome (won/lost) is separate from P&L $: each row’s pnl_usd is what you logged "
            "(e.g. anna log-trade). Won + $0 means pnl_usd was 0 — use modeled $ when logging.[/dim]"
            "\n[dim]School / Karpathy does not auto-append trades from Jupiter; add rows via log-trade or Jack bridge.[/dim]"
        )
        console = Console()
        mandate_lines = build_school_mandate_fact_lines(g12=g12, st=st)
        console.print(
            Panel.fit(
                "\n".join(f"  • {ln}" for ln in mandate_lines),
                title="School mandate (analyst FACTs — repeat work until gates pass)",
                border_style="magenta",
            )
        )
        _bs = border_learning if border_learning in ("green", "yellow", "red") else ("green" if gate_pass else "red")
        console.print(
            Panel.fit(
                report_body,
                title="Anna — report card (live)",
                border_style=_bs,
            )
        )

        tm = normalize_tool_mastery(st.get("grade_12_tool_mastery"))
        cur_focus = g12.get("grade_12_current_focus")
        tools_tbl = Table(
            title="Tool checklist — sequential (finish current focus before the next; then numeric gate)",
            caption="Checklist % = passed when education_benchmark succeeds (auto, default) or anna tool-pass — not idle-loop vibes.",
        )
        tools_tbl.add_column("Tool", no_wrap=True)
        tools_tbl.add_column("ID", style="dim")
        tools_tbl.add_column("Now?", justify="center")
        tools_tbl.add_column("Status")
        tools_tbl.add_column("Checklist %", justify="right")
        for t in GRADE_12_TOOLS:
            tid = t["id"]
            ok = bool(tm.get(tid))
            pct = "100%" if ok else "0%"
            now_cell = (
                "[bold yellow]YES[/bold yellow]"
                if (cur_focus and tid == cur_focus and not ok)
                else ("—" if ok else "[dim]later[/dim]")
            )
            tools_tbl.add_row(
                t["title"][:48] + ("…" if len(t["title"]) > 48 else ""),
                tid,
                now_cell,
                "[green]PASS[/green]" if ok else "[yellow]not yet[/yellow]",
                f"[green]{pct}[/green]" if ok else f"[dim]{pct}[/dim]",
            )
        console.print(tools_tbl)

        meth_id = st.get("training_method_id") or "karpathy_loop_v1"
        meth = TRAINING_METHODS.get(meth_id) or {}
        steps_tbl = Table(
            title=f"[dim]Reference — Karpathy steps ({meth_id})[/dim]",
        )
        steps_tbl.add_column("#", justify="right", width=3)
        steps_tbl.add_column("Step")
        for i, step in enumerate(meth.get("steps") or [], start=1):
            steps_tbl.add_row(str(i), step)
        console.print(steps_tbl)

        act = summarize_trade_activity()
        ev_plain = format_trade_activity_evidence_lines(
            act,
            ledger_trade_count=s.trade_count,
            ledger_decisive=s.wins + s.losses,
            ledger_wins=s.wins,
            ledger_losses=s.losses,
            attempts_path=str(attempts_path()),
            ledger_path=str(trades_path()),
        )
        trade_vis = "\n".join(ev_plain) + "\n\n[dim]Breakeven {s.breakeven} | abstain {s.abstain} | failed+blocked {fb}[/dim]".format(
            s=s,
            fb=act.failed_or_blocked,
        )
        console.print(Panel.fit(trade_vis, title="Trades — ledger vs attempts", border_style="yellow"))

        console.print(
            Panel.fit(
                "[dim]Paper harness evidence for this report card (not live fills).[/dim]\n"
                f"Trades: {s.trade_count} | W {s.wins} / L {s.losses} | "
                f"P&L USD [bold]{s.total_pnl_usd:.2f}[/bold]"
                + (f" | Win rate {s.win_rate:.0%}" if s.win_rate is not None else "")
                + bankroll_line
                + req_line
                + pnl_note,
                title="Paper cohort — summary",
                border_style="cyan",
            )
        )
        table = Table(title="Paper trades (most recent last) — raw rows behind the numeric gate")
        for col in ("UTC", "Symbol", "Venue", "Side", "TF", "Result", "P&L $", "Src", "Strategy", "Ref"):
            table.add_column(col)
        for row in sorted(trades, key=lambda x: x.get("ts_utc") or "")[-40:]:
            src = str(row.get("source") or "—")
            if src == "":
                src = "—"
            strat = (str(row.get("strategy_label") or "") or "—")[:20]
            pref = (str(row.get("proposal_ref") or "") or "—")[:16]
            table.add_row(
                str(row.get("ts_utc", ""))[:19],
                str(row.get("symbol", "")),
                str(row.get("venue", "")),
                str(row.get("side", "")),
                str(row.get("timeframe", "")),
                str(row.get("result", "")),
                f"{float(row.get('pnl_usd') or 0):.2f}",
                src[:12],
                strat,
                pref,
            )
        console.print(table)
        console.print(f"[dim]Ledger: {trades_path()} | Attempts: {attempts_path()}[/dim]")
        if live:
            console.print(
                f"[dim]Report card refresh every {refresh_sec:.0f}s — Ctrl+C to quit. "
                f"(Karpathy training loop is separate, e.g. anna loop in tmux.)[/dim]"
            )

    if live:
        print(
            f"Anna report card — live refresh every {refresh_sec:.0f}s (Ctrl+C to quit).",
            file=sys.stderr,
        )
        try:
            while True:
                if sys.stdout.isatty():
                    sys.stdout.write("\033[2J\033[H")
                    sys.stdout.flush()
                _print_once()
                time.sleep(refresh_sec)
        except KeyboardInterrupt:
            print(file=sys.stderr)
            return 0

    _print_once()
    return 0


def _cmd_report_card(args: argparse.Namespace) -> int:
    md = build_report_card_markdown(
        recipient_name=(args.recipient or "Sean"),
        operator_name=(args.operator or ""),
    )
    out = args.out
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(md, encoding="utf-8")
        print(json.dumps({"ok": True, "path": str(Path(out).resolve())}, indent=2))
    else:
        print(md, end="")
    return 0


def _read_utf8_file(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def _cmd_llm_cross_check(args: argparse.Namespace) -> int:
    """In-process LLM reviewer pass (Ollama); does not use Telegram/Slack."""
    draft_parts: list[str] = []
    if getattr(args, "text", None):
        draft_parts.append(args.text)
    if getattr(args, "file", None):
        draft_parts.append(_read_utf8_file(args.file))
    if not draft_parts and not sys.stdin.isatty():
        draft_parts.append(sys.stdin.read())
    draft = "\n\n".join(draft_parts).strip()
    if not draft:
        print(
            json.dumps(
                {
                    "error": "empty_draft",
                    "hint": "Use --text, --file, or pipe stdin. Example: llm-cross-check --file notes.txt",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    ctx: str | None = None
    if getattr(args, "context_text", None):
        ctx = args.context_text
    if getattr(args, "context_file", None):
        block = _read_utf8_file(args.context_file)
        ctx = f"{ctx}\n\n{block}".strip() if ctx else block

    out = run_llm_cross_check(draft, supporting_context=ctx)
    if not getattr(args, "no_log", False) and (out.get("ok") or out.get("skipped")):
        log_row = {
            "verdict": out.get("verdict"),
            "ok": out.get("ok"),
            "skipped": out.get("skipped"),
            "model": out.get("model"),
            "error": out.get("error"),
            "raw_text": (out.get("raw_text") or "")[:8000],
        }
        p = append_cross_check_log(log_row)
        if p:
            out["log_path"] = str(p)

    if getattr(args, "append_note", False) and out.get("ok"):
        summary = out.get("verdict") or "?"
        snippet = (out.get("raw_text") or "")[:400].replace("\n", " ")
        note_txt = f"[llm-cross-check] verdict={summary} — {snippet}"
        st = load_state()
        notes = list(st.get("operator_notes") or [])
        notes.append({"ts_utc": utc_now_iso(), "text": note_txt})
        st["operator_notes"] = notes[-200:]
        save_state(st)
        out["note_appended"] = True

    print(json.dumps(out, indent=2))
    if out.get("error") and not out.get("skipped"):
        return 1
    return 0


def _cmd_note(args: argparse.Namespace) -> int:
    text = (args.text or "").strip()
    if not text:
        print(json.dumps({"error": "empty_note"}), file=sys.stderr)
        return 1
    st = load_state()
    notes = list(st.get("operator_notes") or [])
    notes.append({"ts_utc": utc_now_iso(), "text": text})
    st["operator_notes"] = notes[-200:]
    save_state(st)
    print(json.dumps({"ok": True, "note_count": len(st["operator_notes"])}, indent=2))
    return 0


def _print_start_banner(curriculum_id: str, method_id: str) -> None:
    cur = CURRICULA[curriculum_id]
    meth = TRAINING_METHODS[method_id]
    print()
    print("=== BLACK BOX — Anna training session ===")
    print(f"Curriculum: {curriculum_id} — {cur.get('title', '')}")
    print(f"Method: {method_id} — {meth.get('title', '')}")
    print()
    print("Karpathy loop (canonical steps):")
    for i, step in enumerate(meth.get("steps") or [], start=1):
        print(f"  {i}. {step}")
    print()
    print("Complementary layers (same harness; see `curricula` JSON):")
    for row in COMPLEMENTARY_PEDAGOGY:
        print(f"  • [{row['id']}] {row['title']}")
    print()


def _cmd_start(args: argparse.Namespace) -> int:
    """Preflight (via main), assign curriculum + method, then TUI menu or --once dashboard."""
    cid = (args.curriculum_id or "grade_12_paper_only").strip()
    mid = (args.method_id or "karpathy_loop_v1").strip()
    if cid not in CURRICULA:
        print(json.dumps({"error": "unknown_curriculum", "id": cid, "valid": list(CURRICULA.keys())}), file=sys.stderr)
        return 1
    if mid not in TRAINING_METHODS:
        print(json.dumps({"error": "unknown_method", "id": mid, "valid": list(TRAINING_METHODS.keys())}), file=sys.stderr)
        return 1

    now = utc_now_iso()
    st = load_state()
    st["curriculum_id"] = cid
    st["curriculum_assigned_at_utc"] = now
    st["training_method_id"] = mid
    st["method_invoked_at_utc"] = now
    save_state(st)

    out = {
        "ok": True,
        "curriculum_id": cid,
        "method_id": mid,
        "assigned_at": now,
        "steps": TRAINING_METHODS[mid].get("steps"),
    }
    print(json.dumps(out, indent=2))
    _print_start_banner(cid, mid)

    if args.once:
        return _cmd_dashboard()

    if not sys.stdin.isatty():
        print("Non-interactive stdin: showing dashboard once.", file=sys.stderr)
        return _cmd_dashboard()

    return _interactive_training_menu()


def _cmd_school(args: argparse.Namespace) -> int:
    """Single operator flow: readiness, gates, then start (curriculum + TUI). Step (0) math runs in main() before preflight."""
    print("=== (1) Data readiness ===", flush=True)
    _cmd_check_readiness()
    print("\n=== (2) Grade-12 numeric gates ===", flush=True)
    gates_rc = _cmd_gates()
    if gates_rc != 0:
        print("\n[Note] Numeric gates did not PASS yet — expected until cohort is large enough.", file=sys.stderr)
    print("\n=== (3) Training session ===", flush=True)
    start_rc = _cmd_start(args)
    return start_rc


def _interactive_training_menu() -> int:
    """Simple REPL: dashboard, status, note, readiness snapshot, quit."""
    help_lines = (
        "Commands: [d] dashboard  [s] status  [n] note  [x] llm cross-check (file)  "
        "[p] readiness  [g] gates (60% check)  [q] quit"
    )
    print(help_lines)
    while True:
        try:
            raw = input("anna-training> ").strip().lower()
        except EOFError:
            print()
            return 0
        if raw in ("q", "quit", "exit"):
            return 0
        if raw in ("d", "dashboard", ""):
            _cmd_dashboard()
            continue
        if raw == "s" or raw == "status":
            _cmd_status()
            continue
        if raw == "p" or raw == "readiness":
            _cmd_check_readiness()
            continue
        if raw == "g" or raw == "gates":
            _cmd_gates()
            continue
        if raw == "n" or raw == "note":
            try:
                line = input("note text> ").strip()
            except EOFError:
                print()
                return 0
            if line:
                ns = argparse.Namespace(text=line)
                _cmd_note(ns)
            continue
        if raw == "x" or raw == "cross-check":
            try:
                p = input("Draft file path (UTF-8 text, ANNA_USE_LLM=1 for Ollama): ").strip()
            except EOFError:
                print()
                return 0
            if not p:
                print("Cancelled.")
                continue
            fp = Path(p).expanduser()
            if not fp.is_file():
                print(json.dumps({"error": "not_a_file", "path": str(fp)}))
                continue
            ns = argparse.Namespace(
                text=None,
                file=str(fp),
                context_text=None,
                context_file=None,
                no_log=False,
                append_note=False,
            )
            _cmd_llm_cross_check(ns)
            continue
        if raw in ("h", "help", "?"):
            print(help_lines)
            continue
        print("Unknown command. " + help_lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Anna training control (curriculum + method + notes).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="JSON snapshot of assigned curriculum, method, timestamps, notes tail.")
    sub.add_parser("curricula", help="List built-in curricula and training methods.")

    ap_a = sub.add_parser("assign-curriculum", help=f"Set active curriculum. IDs: {', '.join(CURRICULA.keys())}")
    ap_a.add_argument("curriculum_id")

    ap_i = sub.add_parser("invoke-method", help=f"Mark training method active. IDs: {', '.join(TRAINING_METHODS.keys())}")
    ap_i.add_argument("method_id")

    ap_n = sub.add_parser("note", help="Append operator note (timestamped).")
    ap_n.add_argument("text", nargs="?", default="")

    ap_l = sub.add_parser("log-trade", help="Append one paper trade row (won|lost|breakeven|abstain).")
    ap_l.add_argument("--symbol", required=True)
    ap_l.add_argument("--side", required=True, help="e.g. long, short")
    ap_l.add_argument("--result", required=True, choices=["won", "lost", "breakeven", "abstain"])
    ap_l.add_argument("--pnl-usd", type=float, required=True)
    ap_l.add_argument("--timeframe", required=True, help="e.g. 5m, 1h, session")
    ap_l.add_argument("--venue", default="jupiter_perp")
    ap_l.add_argument("--notes", default="")
    ap_l.add_argument(
        "--proposal-ref",
        default="",
        help="Optional link to execution_request_id / anna proposal trace (stored on paper row + attempt detail).",
    )
    ap_l.add_argument(
        "--strategy-label",
        default="",
        help="Optional human-readable strategy / thesis name for this paper row (stored on row + attempt detail).",
    )

    ap_ht = sub.add_parser(
        "harness-tick",
        help="Append one synthetic lab paper row when curriculum tools PASS and overall gate not PASS "
        "(ANNA_KARPATHY_AUTO_PAPER_HARNESS=1 or --force).",
    )
    ap_ht.add_argument(
        "--force",
        action="store_true",
        help="Bypass env off switch; still requires eligible gates.",
    )

    sub.add_parser(
        "check-readiness",
        help="First: Solana RPC (Jupiter prerequisite), Pyth stream artifact, market_data.db; see JSON.",
    )

    sub.add_parser(
        "gates",
        help="Grade-12 gate: curriculum tools (cohesive) then win rate vs ANNA_GRADE12_MIN_WIN_RATE (0.6) "
        "and min decisive trades (30). Exit 0 if pass. Dev: ANNA_SKIP_CURRICULUM_TOOLS_GATE=1.",
    )
    sub.add_parser(
        "tool-list",
        help="Grade 12 curriculum tools checklist (JSON). Pass tools before 60%% / revenue headline.",
    )
    ap_tp = sub.add_parser(
        "tool-pass",
        help="Mark a Grade 12 tool passed (operator attestation). IDs: see tool-list.",
    )
    ap_tp.add_argument("tool_id", help="e.g. math_engine_literacy, analysis_algorithms, rcs_rca_discipline, karpathy_harness_loop")

    ap_dash = sub.add_parser("dashboard", help="Terminal view: summary + trade table (requires rich).")
    ap_dash.add_argument(
        "--live",
        action="store_true",
        help="Keep refreshing until Ctrl+C (TTY recommended). Default interval 10s.",
    )
    ap_dash.add_argument(
        "--interval",
        type=float,
        default=10.0,
        metavar="SEC",
        help="Seconds between refreshes when --live (minimum 3).",
    )

    ap_r = sub.add_parser("report-card", help="Markdown grade-12 report for Sean (or stdout).")
    ap_r.add_argument("--out", help="Write markdown file path")
    ap_r.add_argument("--recipient", default="Sean", help="Recipient name in header (e.g. Sean)")
    ap_r.add_argument("--operator", default="", help="Optional operator name on report")

    ap_x = sub.add_parser(
        "start",
        help="Preflight + assign Grade 12 + Karpathy + interactive TUI (or --once for one dashboard).",
    )
    ap_x.add_argument(
        "--curriculum-id",
        default="grade_12_paper_only",
        help="Curriculum id (default: grade_12_paper_only).",
    )
    ap_x.add_argument(
        "--method-id",
        default="karpathy_loop_v1",
        help="Training method id (default: karpathy_loop_v1).",
    )
    ap_x.add_argument(
        "--once",
        action="store_true",
        help="After assign, print dashboard once and exit (no interactive menu).",
    )

    ap_z = sub.add_parser(
        "school",
        help="One command: check-readiness JSON + gates JSON + start (preflight runs first). Same flags as start.",
    )
    ap_z.add_argument("--curriculum-id", default="grade_12_paper_only")
    ap_z.add_argument("--method-id", default="karpathy_loop_v1")
    ap_z.add_argument("--once", action="store_true")
    ap_z.add_argument(
        "--skip-math-check",
        action="store_true",
        help="Skip step (0) Wilson float-vs-Decimal regression (not recommended).",
    )

    sub.add_parser(
        "math-check",
        help="NIST-style Wilson 95%% interval cases: float implementation vs Decimal oracle. Exit 3 if any fail.",
    )

    sub.add_parser(
        "quant-metrics",
        help="Paper P&L quant metrics (Sharpe/Sortino proxies, max DD, Calmar, VaR/CVaR) — math engine training layer.",
    )

    sub.add_parser(
        "math-engine-full",
        help="Full math stack on paper trades (ARIMA/GARCH, annualized Sharpe, WFO, bootstrap, ML, Kalman). Needs pip -r requirements.txt.",
    )

    sub.add_parser(
        "training-progress",
        help="ACL-lite JSON: suggest_next_focus, bachelor_eligibility, cumulative log tail, carryforward bullets.",
    )

    ap_adv = sub.add_parser(
        "advance-curriculum",
        help="Promote to bachelor_paper_track_v1 when grade-12 gate + prerequisite satisfied (or ANNA_ALLOW_BACHELOR_WITHOUT_GATE).",
    )
    ap_adv.add_argument(
        "curriculum_id",
        help="Target curriculum id (only bachelor_paper_track_v1 implemented for promotion).",
    )

    ap_loop = sub.add_parser(
        "loop-daemon",
        help="Karpathy learning loop until SIGTERM: heartbeat JSONL + state iteration (no preflight gate on entry).",
    )
    ap_loop.add_argument(
        "--interval-sec",
        type=float,
        default=None,
        help="Seconds between ticks (default ANNA_LOOP_INTERVAL_SEC or 5).",
    )
    ap_loop.add_argument(
        "--once",
        action="store_true",
        help="Single tick then exit.",
    )

    ap_xc = sub.add_parser(
        "llm-cross-check",
        help="Internal Ollama cross-check of draft text (no Telegram/Slack); respects ANNA_USE_LLM.",
    )
    ap_xc.add_argument("--text", help="Draft text (optional if --file or stdin).")
    ap_xc.add_argument("--file", help="Path to UTF-8 file with draft text.")
    ap_xc.add_argument("--context-text", dest="context_text", default=None, help="Optional supporting context string.")
    ap_xc.add_argument(
        "--context-file",
        dest="context_file",
        default=None,
        help="Optional path to extra context (e.g. numbers to verify against).",
    )
    ap_xc.add_argument(
        "--no-log",
        action="store_true",
        help="Do not append llm_cross_checks.jsonl under the training dir.",
    )
    ap_xc.add_argument(
        "--append-note",
        action="store_true",
        help="If cross-check runs successfully, append a short line to operator_notes in state.json.",
    )

    args = p.parse_args(argv)

    # Wilson NIST cases before data preflight so math regressions surface even without DB/Solana.
    if args.cmd == "school" and not getattr(args, "skip_math_check", False):
        print("=== (0) Math engine — Wilson NIST reference cases ===", flush=True)
        mc = run_wilson_reference_check()
        print(json.dumps(mc, indent=2), flush=True)
        if not mc.get("ok"):
            print("math-check FAILED — fix analysis_math / wilson before training.", file=sys.stderr)
            return 3
        print(flush=True)

    if args.cmd not in (
        "check-readiness",
        "gates",
        "loop-daemon",
        "llm-cross-check",
        "math-check",
        "quant-metrics",
        "math-engine-full",
        "training-progress",
        "advance-curriculum",
        "dashboard",
        "status",
        "curricula",
        "tool-list",
        "tool-pass",
    ):
        rc = _require_preflight_or_exit()
        if rc is not None:
            return rc
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "curricula":
        return _cmd_curricula()
    if args.cmd == "assign-curriculum":
        return _cmd_assign(args)
    if args.cmd == "invoke-method":
        return _cmd_invoke(args)
    if args.cmd == "note":
        return _cmd_note(args)
    if args.cmd == "log-trade":
        return _cmd_log_trade(args)
    if args.cmd == "harness-tick":
        return _cmd_harness_tick(args)
    if args.cmd == "math-check":
        return _cmd_math_check()
    if args.cmd == "quant-metrics":
        return _cmd_quant_metrics()
    if args.cmd == "math-engine-full":
        return _cmd_math_engine_full()
    if args.cmd == "training-progress":
        return _cmd_training_progress()
    if args.cmd == "advance-curriculum":
        return _cmd_advance_curriculum(args)
    if args.cmd == "check-readiness":
        return _cmd_check_readiness()
    if args.cmd == "gates":
        return _cmd_gates()
    if args.cmd == "tool-list":
        return _cmd_tool_list()
    if args.cmd == "tool-pass":
        return _cmd_tool_pass(args)
    if args.cmd == "dashboard":
        return _cmd_dashboard(args)
    if args.cmd == "report-card":
        return _cmd_report_card(args)
    if args.cmd == "start":
        return _cmd_start(args)
    if args.cmd == "school":
        return _cmd_school(args)
    if args.cmd == "llm-cross-check":
        return _cmd_llm_cross_check(args)
    if args.cmd == "loop-daemon":
        lp = ROOT / "scripts" / "runtime" / "anna_karpathy_loop_daemon.py"
        spec = importlib.util.spec_from_file_location("anna_karpathy_loop_daemon", lp)
        if spec is None or spec.loader is None:
            print(json.dumps({"error": "cannot_load_loop_daemon", "path": str(lp)}), file=sys.stderr)
            return 2
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        argv_ld: list[str] = []
        if getattr(args, "interval_sec", None) is not None:
            argv_ld.extend(["--interval-sec", str(args.interval_sec)])
        if args.once:
            argv_ld.append("--once")
        return int(mod.main(argv_ld))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
