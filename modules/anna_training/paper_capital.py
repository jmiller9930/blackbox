"""Paper capital flows — contributed capital vs trading PnL (integrity model).

Equity = net_contributed_capital + trading_pnl (cohort or ledger, see build_summary).

Journal is append-only JSONL: ``data/runtime/anna_training/paper_capital_journal.jsonl``.
Do not change ``paper_wallet.starting_usd`` to simulate deposits — use deposit events.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema
from modules.anna_training.paper_trades import load_paper_trades_for_gates, summarize_trades
from modules.anna_training.paper_wallet import DEFAULT_PAPER_WALLET, merge_paper_wallet_into_state
from modules.anna_training.store import anna_training_dir, utc_now_iso

FLOW_SCHEMA = "paper_capital_flow_v1"
JOURNAL_NAME = "paper_capital_journal.jsonl"


def journal_path() -> Path:
    return anna_training_dir() / JOURNAL_NAME


def _legacy_seed_usd(training_state: dict[str, Any]) -> float:
    raw = (os.environ.get("ANNA_GRADE12_PAPER_BANKROLL_START_USD") or "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    merge_paper_wallet_into_state(training_state)
    pw = training_state.get("paper_wallet") or {}
    try:
        return float(pw.get("starting_usd", DEFAULT_PAPER_WALLET["starting_usd"]))
    except (TypeError, ValueError):
        return float(DEFAULT_PAPER_WALLET["starting_usd"])


def _read_all_flows() -> list[dict[str, Any]]:
    p = journal_path()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def ensure_journal_seeded(training_state: dict[str, Any]) -> bool:
    """If journal is empty, write a single ``initial`` flow from legacy seed. Returns True if wrote."""
    p = journal_path()
    if p.is_file() and p.stat().st_size > 0:
        existing = _read_all_flows()
        if existing:
            return False
    p.parent.mkdir(parents=True, exist_ok=True)
    amt = _legacy_seed_usd(training_state)
    flow = {
        "schema": FLOW_SCHEMA,
        "flow_id": uuid.uuid4().hex,
        "ts_utc": utc_now_iso(),
        "event_type": "initial",
        "amount_usd": float(amt),
        "note": "Seeded from ANNA_GRADE12_PAPER_BANKROLL_START_USD or paper_wallet.starting_usd (legacy).",
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(flow, ensure_ascii=False) + "\n")
    return True


def append_flow(
    *,
    event_type: str,
    amount_usd: float,
    note: str = "",
) -> dict[str, Any]:
    """Append deposit or withdrawal. ``initial`` is only allowed via seeding."""
    et = (event_type or "").strip().lower()
    if et == "initial":
        return {"ok": False, "reason_code": "initial_via_seed_only", "detail": "Use empty journal + ensure_journal_seeded or migration."}
    if et not in ("deposit", "withdrawal"):
        return {"ok": False, "reason_code": "invalid_event_type", "detail": "Expected deposit or withdrawal."}
    try:
        amt = float(amount_usd)
    except (TypeError, ValueError):
        return {"ok": False, "reason_code": "invalid_amount", "detail": "amount_usd must be a number."}
    if amt <= 0:
        return {"ok": False, "reason_code": "amount_must_be_positive", "detail": "Use positive USD amount for deposit/withdrawal."}

    flows = _read_all_flows()
    if not flows:
        return {"ok": False, "reason_code": "journal_empty", "detail": "Seed journal first (restart bundle or call ensure_journal_seeded)."}

    if not any(str(f.get("event_type")).lower() == "initial" for f in flows):
        return {"ok": False, "reason_code": "missing_initial", "detail": "Journal must contain an initial flow."}

    flow = {
        "schema": FLOW_SCHEMA,
        "flow_id": uuid.uuid4().hex,
        "ts_utc": utc_now_iso(),
        "event_type": et,
        "amount_usd": amt,
        "note": (note or "").strip()[:500],
    }
    p = journal_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(flow, ensure_ascii=False) + "\n")
    return {"ok": True, "flow": flow}


@dataclass(frozen=True)
class CapitalRollup:
    starting_capital: float
    capital_added: float
    capital_withdrawn: float
    net_contributed_capital: float


def _rollup_from_flows(flows: list[dict[str, Any]]) -> CapitalRollup:
    start = 0.0
    added = 0.0
    withdrawn = 0.0
    initial_n = 0
    for f in flows:
        et = str(f.get("event_type") or "").lower()
        try:
            a = float(f.get("amount_usd") or 0.0)
        except (TypeError, ValueError):
            a = 0.0
        if et == "initial":
            initial_n += 1
            start += a
        elif et == "deposit":
            added += a
        elif et == "withdrawal":
            withdrawn += a
    if initial_n > 1:
        # Defensive: sum multiple initial lines if legacy mistake — operator should fix journal.
        pass
    net = start + added - withdrawn
    return CapitalRollup(
        starting_capital=start,
        capital_added=added,
        capital_withdrawn=withdrawn,
        net_contributed_capital=net,
    )


def sum_trading_pnl_execution_ledger(*, db_path: Path | None = None) -> float:
    """Sum realized pnl_usd on economic modes (paper + live) in execution ledger."""
    db = db_path or default_execution_ledger_path()
    conn = connect_ledger(db)
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT COALESCE(SUM(pnl_usd), 0)
            FROM execution_trades
            WHERE pnl_usd IS NOT NULL AND mode IN ('paper', 'live')
            """
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return 0.0
        return float(row[0])
    finally:
        conn.close()


def net_contributed_capital_usd(training_state: dict[str, Any] | None = None) -> float:
    """Net operator-contributed capital (initial + deposits − withdrawals)."""
    from modules.anna_training.store import load_state

    st = training_state if training_state is not None else load_state()
    ensure_journal_seeded(st)
    flows = _read_all_flows()
    if not flows:
        ensure_journal_seeded(st)
        flows = _read_all_flows()
    return _rollup_from_flows(flows).net_contributed_capital


def build_paper_capital_summary(
    *,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> dict[str, Any]:
    """Dashboard / API: full separation of flows vs trading PnL."""
    from modules.anna_training.store import load_state

    st = training_state if training_state is not None else load_state()
    merge_paper_wallet_into_state(st)
    ensure_journal_seeded(st)
    flows = _read_all_flows()
    rollup = _rollup_from_flows(flows)

    trades = load_paper_trades_for_gates()
    cohort = summarize_trades(trades)
    trading_pnl_cohort = float(cohort.total_pnl_usd)
    trading_pnl_ledger = sum_trading_pnl_execution_ledger(db_path=ledger_db_path)

    # Grade-12 gates use cohort log; execution ledger is parallel truth for operator.
    equity_cohort = rollup.net_contributed_capital + trading_pnl_cohort
    equity_ledger = rollup.net_contributed_capital + trading_pnl_ledger

    return {
        "schema": "paper_capital_summary_v1",
        "journal_path": str(journal_path()),
        "flow_count": len(flows),
        "starting_capital": round(rollup.starting_capital, 8),
        "capital_added": round(rollup.capital_added, 8),
        "capital_withdrawn": round(rollup.capital_withdrawn, 8),
        "net_contributed_capital": round(rollup.net_contributed_capital, 8),
        "trading_pnl_cohort": round(trading_pnl_cohort, 8),
        "trading_pnl_execution_ledger": round(trading_pnl_ledger, 8),
        "current_equity_cohort": round(equity_cohort, 8),
        "current_equity_ledger": round(equity_ledger, 8),
        "note": (
            "Equity = net_contributed_capital + trading_pnl. "
            "Cohort uses paper_trades.jsonl (grade-12 gates). "
            "Ledger uses execution_trades sum(pnl) for paper+live economic rows."
        ),
    }
