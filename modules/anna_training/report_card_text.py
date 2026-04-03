"""Plain-text report card — shared by TUI (`anna watch`) and Slack `#report_card` (same signal)."""

from __future__ import annotations

from typing import Any, Mapping


def improvement_lines_from_gate_result(g12: Mapping[str, Any]) -> list[str]:
    """Actionable hooks when the report card is NOT PASS — where to change Anna’s stack."""
    out: list[str] = []
    tb = g12.get("tool_blockers") or []
    nb = g12.get("numeric_blockers") or []
    if tb:
        out.append(
            "Tools gap: tighten LLM/pipeline use of math engine + FACT discipline, RCS/RCA, harness loop "
            "(see `modules/anna_training/`, `scripts/runtime/anna_modules/`, `llm/prompt_builder.py`); "
            "after evidence, `anna tool-pass <id>`."
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

    cid = (st.get("curriculum_id") or "") or "—"
    gate_pass = bool(g12.get("pass"))
    learn = (
        "Learning on track for this paper slice (tools + numeric gate)."
        if gate_pass
        else "Not yet learning to spec — use WHY NOT / IMPROVE STACK below to fix prompts, harness, or logging."
    )

    ct_ok = bool(g12.get("curriculum_tools_pass"))
    ng_ok = bool(g12.get("numeric_gate_pass"))
    min_dt = g12.get("min_decisive_trades")
    dec_raw = g12.get("decisive_trades")
    wr = g12.get("win_rate")
    wr_s = f"{wr:.0%}" if wr is not None else "n/a"

    meth = (training_method_id or "").strip() or "—"
    lines: list[str] = [
        "Anna — report card (same signal as `anna watch` / dashboard TUI)",
        "",
        f"LEARNING: {learn}",
        "",
        f"Curriculum: {cid} — {curriculum_title}",
        f"Stage: {stage}",
        f"Training method: {meth}",
        "",
        f"OVERALL GATE: {'PASS' if gate_pass else 'NOT PASS'}  (cohesive tools, then numeric min-N @ 60%)",
        f"  • Curriculum tools (cohesive): {'PASS' if ct_ok else 'NOT PASS'}",
        f"  • Numeric paper slice: {'PASS' if ng_ok else 'NOT PASS'}",
        f"  • Cohort: decisive {dec_raw}/{min_dt}  |  win rate {wr_s}",
    ]

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
    lines.extend(["", "TOOL CHECKLIST (pass all as a set; then numeric / fund bar applies):"])
    for t in GRADE_12_TOOLS:
        tid = t["id"]
        mark = "PASS" if tm.get(tid) else "not yet"
        lines.append(f"  • {t['title']}  (`{tid}`) — {mark}")

    pf_line = "OK" if preflight_ok else "NOT OK"
    lines.extend(["", f"Data preflight: {pf_line}"])
    if preflight_blockers:
        lines.append(f"  Preflight blockers: {', '.join(str(x) for x in preflight_blockers)}")

    it = st.get("karpathy_loop_iteration")
    last = st.get("karpathy_loop_last_tick_utc")
    if it is not None or last:
        lines.append(f"Loop supervisor: iteration={it if it is not None else '—'}  |  last_tick={last or '—'}")

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
