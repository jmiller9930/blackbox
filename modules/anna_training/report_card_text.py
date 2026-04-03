"""Plain-text report card — shared by TUI (`anna watch`) and Slack `#report_card` (same signal)."""

from __future__ import annotations

from typing import Any, Mapping


def grade12_progress_percentages(
    g12: Mapping[str, Any],
    mastery_raw: Any,
) -> dict[str, float]:
    """
    Honest progress numbers for the report card (not the same as gate PASS).

    - tool_checklist_pct: 0–100 from how many of four tools are attested (`anna tool-pass`).
    - numeric_track_pct: blend of decisive-count vs min-N and win rate vs floor — **0 while any tool
      is incomplete** (numeric phase is sequential after the four skills).
    - combined_avg_pct: while tools incomplete, equals tool_checklist_pct only (no dilution with locked numeric).
    - bottleneck_pct: while tools incomplete, follows tool checklist; after all tools, min(tool, numeric).

    The Karpathy loop does not increment these; trades + attestation do.
    """
    from modules.anna_training.curriculum_tools import TOOL_IDS, normalize_tool_mastery

    m = normalize_tool_mastery(mastery_raw)
    n_tools = len(TOOL_IDS)
    tool_pct = (100.0 * sum(1 for tid in TOOL_IDS if m.get(tid)) / n_tools) if n_tools else 0.0

    min_dec = max(0, int(g12.get("min_decisive_trades") or 0))
    min_wr = float(g12.get("min_win_rate") or 0.6)
    dec = int(g12.get("decisive_trades") or 0)
    wr = g12.get("win_rate")

    if min_dec <= 0:
        trade_pct = 100.0 if dec > 0 else 0.0
    else:
        trade_pct = min(100.0, 100.0 * float(dec) / float(min_dec))

    if dec == 0 or wr is None:
        win_pct = 0.0
    elif float(wr) >= min_wr:
        win_pct = 100.0
    else:
        win_pct = min(100.0, 100.0 * float(wr) / min_wr)

    tools_all = all(m.get(tid) for tid in TOOL_IDS)
    if not tools_all:
        numeric_pct = 0.0
        trade_pct = 0.0
        win_pct = 0.0
        combined = tool_pct
        bottleneck = tool_pct
    else:
        numeric_pct = (trade_pct + win_pct) / 2.0
        combined = (tool_pct + numeric_pct) / 2.0
        bottleneck = min(tool_pct, numeric_pct)

    def _r(x: float) -> float:
        return round(x, 1)

    return {
        "tool_checklist_pct": _r(tool_pct),
        "numeric_track_pct": _r(numeric_pct),
        "numeric_decisive_count_pct": _r(trade_pct),
        "numeric_win_rate_pct": _r(win_pct),
        "combined_avg_pct": _r(combined),
        "bottleneck_pct": _r(bottleneck),
        "tools_passed_count": int(sum(1 for tid in TOOL_IDS if m.get(tid))),
        "tools_total": n_tools,
    }


def learning_signal_verdict(g12: Mapping[str, Any], _st: Mapping[str, Any]) -> dict[str, str]:
    """
    Binary only (contract: no partial credit for the headline bar).

    - pass: overall Grade-12 gate PASS (all binary predicates true).
    - not_pass: otherwise — diagnostics may list which binary legs are false; still NOT PASS until all true.
    """
    if bool(g12.get("pass")):
        return {
            "verdict": "pass",
            "headline": "LEARNING: PASS — Grade-12 gate (all binary requirements satisfied).",
            "detail": "Curriculum tools (cohesive): PASS. Numeric paper slice: PASS.",
            "border": "green",
        }

    ct = bool(g12.get("curriculum_tools_pass"))
    ng = bool(g12.get("numeric_gate_pass"))
    if not ct:
        parts = [
            "Curriculum tools (binary): NOT PASS",
            "Numeric paper slice: deferred until all four tools are passed (sequential curriculum).",
        ]
    else:
        parts = [
            "Curriculum tools (binary): PASS",
            f"Numeric paper slice (binary): {'PASS' if ng else 'NOT PASS'}",
        ]
    miss = g12.get("missing_curriculum_tools") or []
    cf = g12.get("grade_12_current_focus")
    if not ct and cf:
        parts.append(f"Sequential focus — work ONLY `{cf}` next (do not skip ahead).")
        rest = [x for x in miss if x != cf]
        if rest:
            parts.append("Then in order: " + " → ".join(str(x) for x in rest))
    elif miss:
        parts.append("Missing tool ids: " + ", ".join(str(x) for x in miss))
    return {
        "verdict": "not_pass",
        "headline": "LEARNING: NOT PASS — at least one binary requirement is false.",
        "detail": " | ".join(parts),
        "border": "red",
    }


def improvement_lines_from_gate_result(g12: Mapping[str, Any]) -> list[str]:
    """Actionable hooks when the report card is NOT PASS — where to change Anna’s stack."""
    out: list[str] = []
    tb = g12.get("tool_blockers") or []
    nb = g12.get("numeric_blockers") or []
    if tb:
        focus = g12.get("grade_12_current_focus")
        seq = (
            f" Work only `{focus}` next (sequential); do not skip ahead. "
            if focus
            else " Work one skill at a time in deck order; do not skip ahead. "
        )
        out.append(
            "Tools gap: tighten LLM/pipeline use of math engine + FACT discipline, RCS/RCA, harness loop "
            "(see `modules/anna_training/`, `scripts/runtime/anna_modules/`, `llm/prompt_builder.py`); "
            f"after evidence, `anna tool-pass <id>`.{seq}"
        )
    if nb:
        out.append(
            "Numeric gap: paper cohort under gate — review harness outcomes, trade logging, and strategy "
            "logic on the paper path (`paper_trades.jsonl`, analysis/execution modules feeding the harness)."
        )
    if not out and not g12.get("pass"):
        out.append("See blockers above; split between tool checklist vs paper metrics.")
    return out[:4]


def format_slack_report_card_text(
    *,
    st: Mapping[str, Any],
    g12: Mapping[str, Any],
    sf: Mapping[str, Any],
    be: Mapping[str, Any],
    summ: Any,
    preflight_ok: bool,
    preflight_blockers: list[str],
    curriculum_title: str,
    stage: str,
    training_method_id: str | None = None,
) -> str:
    """
    Easy-to-read plaintext aligned with the Rich TUI report card (sections and wording).
    Safe for Slack / Telegram DATA replies (no Rich markup).
    """
    from modules.anna_training.curriculum_tools import GRADE_12_TOOLS, normalize_tool_mastery
    from modules.anna_training.school_mandate import build_school_mandate_fact_lines

    cid = (st.get("curriculum_id") or "") or "—"
    gate_pass = bool(g12.get("pass"))
    prog = grade12_progress_percentages(g12, st.get("grade_12_tool_mastery"))
    lv = learning_signal_verdict(g12, st)

    ct_ok = bool(g12.get("curriculum_tools_pass"))
    ng_ok = bool(g12.get("numeric_gate_pass"))
    min_dt = g12.get("min_decisive_trades")
    dec_raw = g12.get("decisive_trades")
    wr = g12.get("win_rate")
    wr_s = f"{wr:.0%}" if wr is not None else "n/a"

    meth = (training_method_id or "").strip() or "—"
    deck = st.get("grade_12_skills_deck") or {}
    deck_lines: list[str] = []
    if isinstance(deck, dict) and deck.get("version"):
        deck_lines = [
            "",
            "SKILLS DECK — one skill at a time in fixed order (Karpathy loop updates deck):",
            f"  • Current focus: {deck.get('current_focus_requirement') or '—'}",
            f"  • Deck complete (full gate PASS): {'yes' if deck.get('deck_complete') else 'no'}",
        ]
    lines: list[str] = [
        "Anna — report card (same signal as `anna watch` / dashboard TUI)",
        "",
        lv["headline"],
        lv["detail"],
    ]
    lines.extend(deck_lines)
    sm = build_school_mandate_fact_lines(g12=g12, st=st)
    lines.extend(
        ["", "SCHOOL MANDATE (injected as FACT on every analyst run — repeat harness work until gates pass):"]
        + [f"  • {x}" for x in sm]
    )
    lines.extend(
        [
            "",
            "MEASURABLE PROGRESS (evidence on the scored path — `anna tool-pass`, `log-trade`, learning log):",
            f"  • Tool checklist: {prog['tool_checklist_pct']}% ({prog['tools_passed_count']}/{prog['tools_total']} attested)",
            f"  • Paper numeric track: {prog['numeric_track_pct']}%"
            + (
                " (locked at 0% until all four tools passed — sequential curriculum)"
                if not ct_ok
                else " (decisive count + win-rate vs gate)"
            ),
            f"  • Combined average: {prog['combined_avg_pct']}%  |  Bottleneck: {prog['bottleneck_pct']}%",
            "",
            f"Curriculum: {cid} — {curriculum_title}",
            f"Stage: {stage}",
            f"Training method: {meth}",
            "",
            f"OVERALL GATE: {'PASS' if gate_pass else 'NOT PASS'}  (tools, then numeric min-N + win rate; optional P&L/bankroll env)",
            f"  • Curriculum tools (cohesive): {'PASS' if ct_ok else 'NOT PASS'}",
            f"  • Numeric paper slice: {'PASS' if ng_ok else 'NOT PASS'}",
            f"  • Cohort: decisive {dec_raw}/{min_dt}  |  win rate {wr_s}  |  net P&L USD {float(g12.get('total_pnl_usd') or 0):.2f}",
        ]
    )
    bs = g12.get("paper_bankroll_start_usd")
    eq = g12.get("paper_equity_usd")
    if bs is not None and eq is not None:
        lines.append(f"  • Paper bankroll: start ${float(bs):,.2f} → equity ${float(eq):,.2f}")

    blockers = list(g12.get("blockers") or [])
    if blockers:
        lines.extend(["", "WHY NOT (from gates):"])
        lines.extend(f"  • {b}" for b in blockers)

    if not gate_pass:
        imp = improvement_lines_from_gate_result(g12)
        if imp:
            lines.extend(["", "IMPROVE STACK (where to change code / process):"])
            lines.extend(f"  • {x}" for x in imp)

    elig = "yes" if be.get("eligible_for_bachelor_paper_track_v1") else "no"
    lines.extend(
        [
            "",
            f"Bachelor paper track eligible: {elig}",
            f"Next focus: {sf.get('focus', '—')}",
        ]
    )
    for h in (sf.get("hints") or [])[:5]:
        lines.append(f"  • {h}")

    cf = list(st.get("carryforward_bullets") or [])[:6]
    if cf:
        lines.append("")
        lines.append("Carry-forward:")
        for b in cf:
            lines.append(f"  • {b}")

    tm = normalize_tool_mastery(st.get("grade_12_tool_mastery"))
    lines.extend(
        [
            "",
            "TOOL CHECKLIST (per-row % = attestation only: 0% until tool-pass, 100% after — not auto 'learning' from idle loop):",
        ]
    )
    for t in GRADE_12_TOOLS:
        tid = t["id"]
        mark = "PASS" if tm.get(tid) else "not yet"
        row_pct = "100%" if tm.get(tid) else "0%"
        lines.append(f"  • {t['title']}  (`{tid}`) — {mark}  |  checklist {row_pct}")

    pf_line = "OK" if preflight_ok else "NOT OK"
    lines.extend(["", f"Data preflight: {pf_line}"])
    if preflight_blockers:
        lines.append(f"  Preflight blockers: {', '.join(str(x) for x in preflight_blockers)}")

    it = st.get("karpathy_loop_iteration")
    last = st.get("karpathy_loop_last_tick_utc")
    if it is not None or last:
        lines.append(f"Loop supervisor: iteration={it if it is not None else '—'}  |  last_tick={last or '—'}")

    from modules.anna_training.paper_trades import trades_path
    from modules.anna_training.trade_attempts import (
        attempts_path,
        format_trade_activity_evidence_lines,
        summarize_trade_activity,
    )

    _act = summarize_trade_activity()
    lines.append("")
    lines.extend(
        format_trade_activity_evidence_lines(
            _act,
            ledger_trade_count=summ.trade_count,
            ledger_decisive=summ.wins + summ.losses,
            ledger_wins=summ.wins,
            ledger_losses=summ.losses,
            attempts_path=str(attempts_path()),
            ledger_path=str(trades_path()),
        )
    )

    lines.extend(
        [
            "",
            "Paper harness (evidence behind numeric gate):",
            f"  Trades logged: {summ.trade_count}  |  decisive (W+L): {summ.wins + summ.losses}",
            f"  W {summ.wins} / L {summ.losses}  |  P&L sum ${summ.total_pnl_usd:.2f}  |  win rate (decisive): "
            f"{summ.win_rate if summ.win_rate is not None else 'n/a'}",
            "",
            "Full markdown report: `python3 scripts/runtime/anna_training_cli.py report-card --recipient Sean`",
        ]
    )
    return "\n".join(lines)
