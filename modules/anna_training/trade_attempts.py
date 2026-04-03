"""Append-only trade *activity* log — attempts, blocks, and manual paper rows (school visibility).

``paper_trades.jsonl`` remains the cohort ledger for gates. This file records **events** so the
TUI can show tried / failed / blocked vs **outcomes** in the paper ledger (won / lost).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.anna_training.store import anna_training_dir, utc_now_iso

ATTEMPTS_FILE = "paper_trade_attempts.jsonl"
SCHEMA = "anna_trade_attempt_v1"


def attempts_path() -> Path:
    return anna_training_dir() / ATTEMPTS_FILE


def append_trade_attempt(
    *,
    phase: str,
    status: str,
    detail: dict[str, Any] | None = None,
    request_id: str | None = None,
    trade_id: str | None = None,
) -> dict[str, Any]:
    """
    phase: jack_handoff | execution | paper_manual
    status: started | ok | fail | blocked | recorded
    """
    row = {
        "schema": SCHEMA,
        "event_id": str(uuid.uuid4()),
        "ts_utc": utc_now_iso(),
        "phase": (phase or "").strip(),
        "status": (status or "").strip(),
        "request_id": request_id,
        "trade_id": trade_id,
        "detail": detail if isinstance(detail, dict) else {},
    }
    p = attempts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_trade_attempts() -> list[dict[str, Any]]:
    p = attempts_path()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            if isinstance(o, dict) and o.get("schema") == SCHEMA:
                out.append(o)
        except json.JSONDecodeError:
            continue
    return out


@dataclass
class TradeActivitySummary:
    """Roll-up of ``paper_trade_attempts.jsonl`` — not the same as ``paper_trades.jsonl`` row count."""

    total_events: int
    jack_delegate_started: int
    jack_delegate_failed: int
    jack_delegate_ok_with_paper: int
    jack_delegate_ok_no_paper: int
    execution_blocked: int
    paper_manual_recorded: int

    @property
    def failed_or_blocked(self) -> int:
        return self.jack_delegate_failed + self.execution_blocked


def summarize_trade_activity(rows: list[dict[str, Any]] | None = None) -> TradeActivitySummary:
    r = rows if rows is not None else load_trade_attempts()
    js = jf = jokp = jokn = eb = pm = 0
    for e in r:
        phase = str(e.get("phase") or "")
        status = str(e.get("status") or "")
        det = e.get("detail") if isinstance(e.get("detail"), dict) else {}
        if phase == "jack_handoff":
            if status == "started":
                js += 1
            elif status == "fail":
                jf += 1
            elif status == "ok":
                if det.get("paper_logged"):
                    jokp += 1
                else:
                    jokn += 1
        elif phase == "execution" and status == "blocked":
            eb += 1
        elif phase == "paper_manual" and status == "recorded":
            pm += 1
    return TradeActivitySummary(
        total_events=len(r),
        jack_delegate_started=js,
        jack_delegate_failed=jf,
        jack_delegate_ok_with_paper=jokp,
        jack_delegate_ok_no_paper=jokn,
        execution_blocked=eb,
        paper_manual_recorded=pm,
    )


def format_trade_activity_evidence_lines(
    act: TradeActivitySummary,
    *,
    ledger_trade_count: int,
    ledger_decisive: int,
    ledger_wins: int,
    ledger_losses: int,
    attempts_path: str,
    ledger_path: str,
) -> list[str]:
    """
    Plain lines for TUI / Slack / report card: reconciles cohort ledger vs attempt JSONL.
    """
    lines = [
        "EVIDENCE — ledger (gates) vs attempt log (visibility):",
        f"  • Paper ledger rows: {ledger_trade_count} total; decisive {ledger_decisive} "
        f"(W {ledger_wins} / L {ledger_losses}) — file: {ledger_path}",
        f"  • Attempt log events: {act.total_events} lines — file: {attempts_path}",
        "  • Attempt breakdown: "
        f"Jack started {act.jack_delegate_started} | Jack failed {act.jack_delegate_failed} | "
        f"Jack OK + paper row {act.jack_delegate_ok_with_paper} | Jack OK no paper {act.jack_delegate_ok_no_paper} | "
        f"execution blocked {act.execution_blocked} | manual CLI `log-trade` recorded {act.paper_manual_recorded}",
        "  • If ledger >> manual-recorded: older rows predate attempt logging, imports, or rows from Jack "
        "(Jack OK logs trade_id on success; not every historical row has a backfilled attempt).",
    ]
    if act.paper_manual_recorded <= 1 and ledger_trade_count > act.paper_manual_recorded:
        lines.append(
            "  • Operator CLI attempts since wiring: "
            f"{act.paper_manual_recorded} — that is not the same as {ledger_trade_count} ledger rows."
        )
    return lines
