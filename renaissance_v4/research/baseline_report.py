"""
baseline_report.py

Purpose:
Write renaissance_v4/reports/baseline_v1.md from ledger summary and scorecards.

Version:
v1.1

Change History:
- v1.0 Baseline v1 acceptance (architect).
- v1.1 Trade-evidence samples, optional full outcome export, sanity snapshot for full-dataset proof.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from renaissance_v4.core.outcome_record import OutcomeRecord

_RENAISSANCE_V4_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_PATH = _RENAISSANCE_V4_ROOT / "reports" / "baseline_v1.md"
TRADE_EVIDENCE_MAX = 15


def _outcome_table_rows(outcomes: list[OutcomeRecord]) -> list[str]:
    """Markdown lines for a compact trade-evidence table."""
    lines = [
        "| trade_id (prefix) | symbol | dir | entry | exit | stop | target | exit_reason | PnL | MAE | MFE | contributing_signals |",
        "|---|---|:---:|---:|---:|---:|---:|---|---:|---:|---:|---|",
    ]
    for o in outcomes[:TRADE_EVIDENCE_MAX]:
        tid = o.trade_id[:20] + ("…" if len(o.trade_id) > 20 else "")
        sl = o.metadata.get("stop_loss")
        tp = o.metadata.get("take_profit")
        sl_s = f"{float(sl):.6f}" if sl is not None else "—"
        tp_s = f"{float(tp):.6f}" if tp is not None else "—"
        sigs = ",".join(o.contributing_signals) if o.contributing_signals else "—"
        lines.append(
            f"| `{tid}` | {o.symbol} | {o.direction} | {o.entry_price:.6f} | {o.exit_price:.6f} | "
            f"{sl_s} | {tp_s} | {o.exit_reason} | {o.pnl:.8f} | {o.mae:.8f} | {o.mfe:.8f} | {sigs} |"
        )
    return lines


def _sanity_snapshot_lines(
    dataset_bars: int,
    summary: dict,
    sanity: dict[str, int | float | str],
) -> list[str]:
    """Aggregate answers for architect §6-style review (not a substitute for judgment)."""
    total = int(summary.get("total_trades", 0) or 0)
    entries = int(sanity.get("entries_attempted", 0) or 0)
    fn = int(sanity.get("fusion_no_trade_bars", 0) or 0)
    fd = int(sanity.get("fusion_directional_bars", 0) or 0)
    rb = int(sanity.get("risk_blocked_bars", 0) or 0)
    db = float(dataset_bars) if dataset_bars else 1.0

    opens_per_1k = (entries / db) * 1000.0
    fusion_nt_pct = 100.0 * fn / db
    risk_blk_pct = 100.0 * rb / db

    if total > 0:
        trades_ans = f"Yes — **{total}** closed trades."
    else:
        trades_ans = "No — **RenaissanceV4_baseline_v1** requires non-zero closed trades on full data."

    if opens_per_1k < 0.5:
        ot = "Under-trading heuristic: very few entries per 1k bars."
    elif opens_per_1k > 50.0:
        ot = "High entry density — review for overtrading vs policy intent."
    else:
        ot = f"Moderate: ~{opens_per_1k:.2f} entry attempts per 1k bars."

    if fd == 0:
        fus = "No fused long/short bars this run — fusion stayed `no_trade` or neutral; see directional vs no_trade counters."
    elif fusion_nt_pct > 95.0:
        fus = "Fusion is mostly `no_trade` on this run — check thresholds and regime mix."
    elif fusion_nt_pct < 20.0:
        fus = "Fusion is often directional (low `no_trade` share) — confirm against policy intent."
    else:
        fus = f"Mixed: ~{fusion_nt_pct:.1f}% of bars are fusion `no_trade`."

    if fd > 0 and rb > fd * 0.5:
        rg = "Risk governor blocks a large share relative to directional bars — review sizing/gates."
    elif rb == 0:
        rg = "No risk blocks recorded — governor did not veto entries this run."
    else:
        rg = f"~{risk_blk_pct:.1f}% of bars saw a risk block."

    return [
        "### Automated sanity snapshot (full-data review)",
        "",
        f"- **Are trades occurring?** {trades_ans}",
        f"- **Over- vs under-trading (heuristic):** {ot}",
        f"- **Fusion mostly no_trade?** {fus}",
        f"- **Risk governor blocking aggressively?** {rg}",
        "- **Signals vs regimes:** Use per-signal scorecards and regime on each outcome; no single aggregate substitutes for charts.",
        "",
    ]


def maybe_export_outcomes_full(outcomes: list[OutcomeRecord]) -> Path | None:
    """
    If RENAISSANCE_V4_EXPORT_OUTCOMES=1, write one JSON object per line for audit / tooling.
    """
    if os.environ.get("RENAISSANCE_V4_EXPORT_OUTCOMES") != "1":
        return None
    path = _RENAISSANCE_V4_ROOT / "reports" / "outcomes_full.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for o in outcomes:
            f.write(json.dumps(asdict(o), default=str) + "\n")
    print(f"[baseline_report] Wrote {path.resolve()} ({len(outcomes)} outcomes)")
    return path


def write_baseline_report(
    path: Path | None,
    *,
    dataset_bars: int,
    summary: dict,
    scorecards: dict[str, dict],
    cumulative_pnl: float,
    validation_checksum: str,
    sanity: dict[str, int | float | str],
    outcomes: list[OutcomeRecord] | None = None,
) -> Path:
    """
    Overwrite baseline markdown with portfolio metrics and per-signal scorecards.
    """
    out = path or DEFAULT_REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    oc = outcomes or []

    lines = [
        "# RenaissanceV4 — Baseline Report v1",
        "",
        "Generated by replay validation. **Phases 8–11 are not integrated** (promotion/decay/portfolio gates disabled).",
        "",
        "## Dataset",
        "",
        f"- **Bars in replay:** {dataset_bars}",
        "- **Target for `RenaissanceV4_baseline_v1` promotion:** ≥1 year of Binance **5m** bars; `binance_ingest.py` defaults to ~**2 years** SOLUSDT (adjust in code if policy changes).",
        "",
        "## Portfolio metrics",
        "",
        f"- **Total closed trades:** {summary.get('total_trades', 0)}",
        f"- **Wins / losses:** {summary.get('wins', 0)} / {summary.get('losses', 0)}",
        f"- **Win rate:** {summary.get('win_rate', 0.0):.6f}",
        f"- **Gross / net PnL:** {summary.get('gross_pnl', 0.0):.8f} / {summary.get('net_pnl', 0.0):.8f}",
        f"- **Average PnL / expectancy:** {summary.get('average_pnl', 0.0):.8f}",
        f"- **Max drawdown (equity curve):** {summary.get('max_drawdown', 0.0):.8f}",
        f"- **Avg MAE / MFE:** {summary.get('avg_mae', 0.0):.8f} / {summary.get('avg_mfe', 0.0):.8f}",
        f"- **Cumulative simulated PnL (execution manager):** {cumulative_pnl:.8f}",
        f"- **Validation checksum (this run):** `{validation_checksum}`",
        "- **Determinism proof:** Run `./renaissance_v4/run_replay_twice_check.sh` on the **same** DB; the two `[VALIDATION_CHECKSUM]` lines must match **exactly**.",
        "",
    ]

    if oc:
        lines.extend(
            [
                "## Trade evidence (sample)",
                "",
                f"Up to **{TRADE_EVIDENCE_MAX}** closed trades. For a full audit trail: `RENAISSANCE_V4_EXPORT_OUTCOMES=1 python3 -m renaissance_v4.research.replay_runner` → `reports/outcomes_full.jsonl`.",
                "",
            ]
        )
        lines.extend(_outcome_table_rows(oc))
        lines.append("")
    else:
        lines.extend(
            [
                "## Trade evidence (sample)",
                "",
                "*No closed trades in this run (e.g. smoke seed or empty window). **Not sufficient** for `RenaissanceV4_baseline_v1` promotion.*",
                "",
            ]
        )

    lines.extend(
        [
            "## Per-signal scorecards",
            "",
        ]
    )

    if not scorecards:
        lines.append("*No outcomes attributed to contributing signals (empty scorecards).*")
        lines.append("")
    else:
        for name, card in sorted(scorecards.items()):
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- lifecycle (advisory): **{card.get('lifecycle_state', 'n/a')}**")
            lines.append(f"- trades: {card.get('total_trades', 0)}, win_rate: {card.get('win_rate', 0.0):.6f}")
            lines.append(f"- expectancy: {card.get('expectancy', 0.0):.8f}, max_drawdown: {card.get('max_drawdown', 0.0):.8f}")
            lines.append("")

    lines.extend(
        [
            "## Sanity check (required)",
            "",
            f"- **Bars with fusion `no_trade`:** {sanity.get('fusion_no_trade_bars', 0)}",
            f"- **Bars with fused long/short:** {sanity.get('fusion_directional_bars', 0)}",
            f"- **Bars risk blocked (not allowed):** {sanity.get('risk_blocked_bars', 0)}",
            f"- **Simulated opens (entries):** {sanity.get('entries_attempted', 0)}",
            f"- **Closed trades (outcomes recorded):** {sanity.get('closes_recorded', 0)}",
            "",
        ]
    )
    lines.extend(_sanity_snapshot_lines(dataset_bars, summary, sanity))
    lines.extend(
        [
            "### Interpretation (manual)",
            "",
            "- **Overtrading?** Compare entry attempts to bars and to policy intent.",
            "- **Stuck in no_trade?** Compare fusion no_trade bars to directional bars.",
            "- **Signals vs regimes:** Scorecards attribute contributing signals; each outcome carries exit `regime`.",
            "- **Risk overly restrictive?** Compare risk_blocked_bars to directional fusion bars.",
            "",
        ]
    )

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[baseline_report] Wrote {out.resolve()}")
    return out
