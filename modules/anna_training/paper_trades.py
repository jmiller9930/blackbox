"""Append-only paper trade log for grade-12 report card (JSONL under anna_training dir)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.anna_training.store import anna_training_dir, utc_now_iso

TRADES_FILE = "paper_trades.jsonl"

VALID_RESULTS = frozenset({"won", "lost", "breakeven", "abstain"})


def trades_path() -> Path:
    return anna_training_dir() / TRADES_FILE


def append_paper_trade(
    *,
    symbol: str,
    side: str,
    result: str,
    pnl_usd: float,
    timeframe: str,
    venue: str = "jupiter_perp",
    notes: str = "",
    trade_id: str | None = None,
    ts_utc: str | None = None,
    log_manual_activity: bool = True,
) -> dict[str, Any]:
    r = (result or "").strip().lower()
    if r not in VALID_RESULTS:
        raise ValueError(f"result must be one of {sorted(VALID_RESULTS)}")
    row: dict[str, Any] = {
        "schema": "anna_paper_trade_v1",
        "trade_id": trade_id or str(uuid.uuid4()),
        "ts_utc": ts_utc or utc_now_iso(),
        "symbol": (symbol or "").strip(),
        "venue": (venue or "").strip() or "jupiter_perp",
        "side": (side or "").strip().lower(),
        "result": r,
        "pnl_usd": float(pnl_usd),
        "timeframe": (timeframe or "").strip(),
        "notes": (notes or "").strip(),
    }
    p = trades_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if log_manual_activity:
        try:
            from modules.anna_training.trade_attempts import append_trade_attempt

            append_trade_attempt(
                phase="paper_manual",
                status="recorded",
                trade_id=str(row.get("trade_id")),
                detail={
                    "symbol": row.get("symbol"),
                    "side": row.get("side"),
                    "result": row.get("result"),
                    "pnl_usd": row.get("pnl_usd"),
                    "venue": row.get("venue"),
                },
            )
        except Exception:
            pass
    return row


def load_paper_trades() -> list[dict[str, Any]]:
    p = trades_path()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            if isinstance(o, dict) and o.get("schema") == "anna_paper_trade_v1":
                out.append(o)
        except json.JSONDecodeError:
            continue
    return out


@dataclass
class TradeSummary:
    trade_count: int
    wins: int
    losses: int
    breakeven: int
    abstain: int
    total_pnl_usd: float
    win_rate: float | None  # None if no decisive trades
    period_start_utc: str | None
    period_end_utc: str | None


def summarize_trades(trades: Iterable[dict[str, Any]]) -> TradeSummary:
    tlist = list(trades)
    if not tlist:
        return TradeSummary(0, 0, 0, 0, 0, 0.0, None, None, None)
    wins = losses = breakeven = abstain = 0
    total = 0.0
    ts_list: list[str] = []
    for t in tlist:
        total += float(t.get("pnl_usd") or 0)
        ts_list.append(str(t.get("ts_utc") or ""))
        res = str(t.get("result") or "")
        if res == "won":
            wins += 1
        elif res == "lost":
            losses += 1
        elif res == "breakeven":
            breakeven += 1
        else:
            abstain += 1
    decisive = wins + losses
    wr = (wins / decisive) if decisive else None
    ts_list = sorted(x for x in ts_list if x)
    return TradeSummary(
        trade_count=len(tlist),
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        abstain=abstain,
        total_pnl_usd=round(total, 6),
        win_rate=round(wr, 4) if wr is not None else None,
        period_start_utc=ts_list[0] if ts_list else None,
        period_end_utc=ts_list[-1] if ts_list else None,
    )


def build_report_card_markdown(
    *,
    trades: list[dict[str, Any]] | None = None,
    recipient_name: str = "Sean",
    operator_name: str = "",
) -> str:
    """Grade 12 paper-trading report card (markdown) for external share."""
    t = trades if trades is not None else load_paper_trades()
    s = summarize_trades(t)
    st_path = anna_training_dir() / "state.json"
    curriculum_title = "—"
    try:
        if st_path.is_file():
            st = json.loads(st_path.read_text(encoding="utf-8"))
            cid = st.get("curriculum_id")
            if cid == "grade_12_paper_only":
                curriculum_title = "Grade 12 equivalent — paper trading only"
    except (json.JSONDecodeError, OSError):
        pass

    wr_cell = "—"
    if s.win_rate is not None:
        wr_cell = f"{100.0 * s.win_rate:.1f}%"
    lines: list[str] = [
        "# Anna — Grade 12 paper trading report card",
        "",
        "## Who does what (routing)",
        "",
        "| Role | Responsibility |",
        "|------|------------------|",
        "| **Anna** | Analyst / signals; does not place live orders. |",
        "| **Jack** | Executor for **Jupiter Perps** — the path Anna’s Jupiter-venue packets use when live execution is enabled. |",
        "| **Jupiter Perps** | The **exchange / program** surface (Solana); not Drift, not a generic “DEX” label. |",
        "",
        "_This report measures **paper** outcomes only — not live Jack fills._",
        "",
    ]
    if operator_name.strip():
        lines.append(f"**Operator:** {operator_name.strip()}")
        lines.append("")
    lines.extend(
        [
            f"**Curriculum:** {curriculum_title}",
            f"**Period (UTC):** {s.period_start_utc or '—'} → {s.period_end_utc or '—'}",
            f"**Prepared for:** {recipient_name}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Paper trades logged | {s.trade_count} |",
            f"| Wins | {s.wins} |",
            f"| Losses | {s.losses} |",
            f"| Breakeven | {s.breakeven} |",
            f"| Abstain | {s.abstain} |",
            f"| Win rate (excl. breakeven/abstain) | {wr_cell} |",
            f"| **Total P&L (USD, paper)** | **{s.total_pnl_usd:.2f}** |",
            "",
            "## Trade log",
            "",
            "| UTC | Symbol | Venue | Side | TF | Result | P&L USD | Notes |",
            "|-----|--------|-------|------|-----|--------|---------|-------|",
        ]
    )
    for row in sorted(t, key=lambda x: x.get("ts_utc") or ""):
        lines.append(
            "| {ts} | {sym} | {ven} | {side} | {tf} | {res} | {pnl:.2f} | {notes} |".format(
                ts=row.get("ts_utc", ""),
                sym=row.get("symbol", ""),
                ven=row.get("venue", ""),
                side=row.get("side", ""),
                tf=row.get("timeframe", ""),
                res=row.get("result", ""),
                pnl=float(row.get("pnl_usd") or 0),
                notes=(row.get("notes") or "").replace("|", "\\|")[:80],
            )
        )
    if not t:
        lines.append("| _(none yet)_ | | | | | | | |")

    lines.extend(
        [
            "",
            "## How we measure (paper)",
            "",
            "Each row is a **paper / simulation** outcome (not live Jack/Billy). P&L is in **USD** as recorded by the operator or harness. ",
            "`won` / `lost` / `breakeven` / `abstain` are explicit outcomes; interrogation (why) lives in RCS/RCA when wired per directive.",
            "",
            "**Useful report-card inputs (for humans and later automation):** symbol, timeframe, side, explicit result, P&L, optional notes (thesis / mistake / Jupiter context). ",
            "Headline win rate alone is not enough — pair it with **why** on wins and losses and whether the mistake repeats (failure archive / differential), per training doctrine.",
            "",
            "---",
            "",
            "*Generated by `python3 scripts/runtime/anna_training_cli.py report-card`*",
        ]
    )
    return "\n".join(lines) + "\n"
