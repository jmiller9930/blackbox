#!/usr/bin/env python3
"""
Anna training — curriculum, method, paper trade log, dashboard, grade-12 report card (markdown).

State: data/runtime/anna_training/state.json; trades: paper_trades.jsonl (override dir with BLACKBOX_ANNA_TRAINING_DIR).

Examples (repo root):
  python3 scripts/runtime/anna_training_cli.py start   # one-shot: preflight + Grade 12 + Karpathy + interactive TUI menu
  python3 scripts/runtime/anna_training_cli.py start --once   # assign + single dashboard, then exit (scripting)
  python3 scripts/runtime/anna_training_cli.py gates   # PASS/FAIL vs 60% + min decisive trades (see env vars)
  python3 scripts/runtime/anna_training_cli.py check-readiness   # Solana RPC + Pyth artifact + DB — run first
  python3 scripts/runtime/anna_training_cli.py status
  python3 scripts/runtime/anna_training_cli.py log-trade --symbol SOL-PERP --side long --result won --pnl-usd 10.5 --timeframe 5m
  python3 scripts/runtime/anna_training_cli.py dashboard
  python3 scripts/runtime/anna_training_cli.py report-card --out docs/working/anna_grade12_report_card.md --recipient Sean
  python3 scripts/runtime/anna_training_cli.py assign-curriculum grade_12_paper_only
  python3 scripts/runtime/anna_training_cli.py invoke-method karpathy_loop_v1
  python3 scripts/runtime/anna_training_cli.py note "Reviewed simulation run — ok"
"""
from __future__ import annotations

import argparse
import json
import sys
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
from modules.anna_training.gates import evaluate_grade12_gates  # noqa: E402
from modules.anna_training.readiness import ensure_anna_data_preflight, full_readiness  # noqa: E402
from modules.anna_training.paper_trades import (  # noqa: E402
    TRADES_FILE,
    append_paper_trade,
    build_report_card_markdown,
    load_paper_trades,
    summarize_trades,
)
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
        )
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "trade": row}, indent=2))
    return 0


def _cmd_check_readiness() -> int:
    print(json.dumps(full_readiness(), indent=2))
    return 0


def _cmd_gates() -> int:
    """Numeric grade-12 exit gate (paper trades); exit 0 when pass, 1 when fail."""
    out = evaluate_grade12_gates()
    print(json.dumps(out, indent=2))
    return 0 if out.get("pass") else 1


def _require_preflight_or_exit() -> int | None:
    """Run before every subcommand except `check-readiness`. Fail closed with JSON on stderr."""
    pf = ensure_anna_data_preflight()
    if pf["ok"] or pf.get("skipped"):
        return None
    print(json.dumps({"error": "preflight_failed", "preflight": pf}, indent=2), file=sys.stderr)
    return 5


def _cmd_dashboard() -> int:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
    except ImportError:
        trades = load_paper_trades()
        s = summarize_trades(trades)
        print(
            json.dumps(
                {
                    "execution_path": "Anna (analyst) → Jack (executor) → Jupiter Perps (exchange on Solana)",
                    "summary": s.__dict__,
                    "trades": len(trades),
                },
                indent=2,
            )
        )
        return 0

    trades = load_paper_trades()
    s = summarize_trades(trades)
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]Anna[/bold cyan] (analyst)  [dim]── handoff ──▶[/dim]  "
            "[bold green]Jack[/bold green] (executor)  [dim]│[/dim]  "
            "[yellow]Jupiter Perps[/yellow] = exchange / venue\n"
            "[dim]Default live path when venue is Jupiter: Anna’s packets go to Jack; "
            "Drift would be Billy (not shown here). Rows below are paper harness outcomes, not live fills.[/dim]\n\n"
            "[bold]Grade 12 — paper training[/bold]\n"
            f"Trades: {s.trade_count} | W {s.wins} / L {s.losses} | "
            f"P&L USD [bold]{s.total_pnl_usd:.2f}[/bold]"
            + (f" | Win rate {s.win_rate:.0%}" if s.win_rate is not None else ""),
            title="BLACK BOX · Anna training (TUI)",
            border_style="cyan",
        )
    )
    table = Table(title="Paper trades — Jupiter Perps venue (most recent last)")
    for col in ("UTC", "Symbol", "Venue", "Side", "TF", "Result", "P&L $"):
        table.add_column(col)
    for row in sorted(trades, key=lambda x: x.get("ts_utc") or "")[-40:]:
        table.add_row(
            str(row.get("ts_utc", ""))[:19],
            str(row.get("symbol", "")),
            str(row.get("venue", "")),
            str(row.get("side", "")),
            str(row.get("timeframe", "")),
            str(row.get("result", "")),
            f"{float(row.get('pnl_usd') or 0):.2f}",
        )
    console.print(table)
    console.print(f"[dim]Log: {anna_training_dir() / TRADES_FILE}[/dim]")
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


def _interactive_training_menu() -> int:
    """Simple REPL: dashboard, status, note, readiness snapshot, quit."""
    help_lines = (
        "Commands: [d] dashboard  [s] status  [n] note  [p] readiness  [g] gates (60% check)  [q] quit"
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

    sub.add_parser(
        "check-readiness",
        help="First: Solana RPC (Jupiter prerequisite), Pyth stream artifact, market_data.db; see JSON.",
    )

    sub.add_parser(
        "gates",
        help="Grade-12 numeric gate: win rate vs ANNA_GRADE12_MIN_WIN_RATE (default 0.6) and "
        "min decisive trades ANNA_GRADE12_MIN_DECISIVE_TRADES (default 30). Exit 0 if pass.",
    )

    sub.add_parser("dashboard", help="Terminal view: summary + trade table (requires rich).")

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

    args = p.parse_args(argv)
    if args.cmd not in ("check-readiness", "gates"):
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
    if args.cmd == "check-readiness":
        return _cmd_check_readiness()
    if args.cmd == "gates":
        return _cmd_gates()
    if args.cmd == "dashboard":
        return _cmd_dashboard()
    if args.cmd == "report-card":
        return _cmd_report_card(args)
    if args.cmd == "start":
        return _cmd_start(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
