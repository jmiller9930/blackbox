"""Learning proof loop — memory attribution, ablation, join to vs-baseline (MIT directive).

Canonical claim (phase): Anna learned if retrieved knowledge changed the decision and improved
outcomes vs baseline. This module builds operator-facing aggregates; traces are persisted on
``decision_traces`` (see ``decision_trace.insert_decision_trace`` learning-proof columns).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_lesson_sqlite_path() -> Path:
    env = (os.environ.get("BLACKBOX_SQLITE_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    return _repo_root() / "data" / "sqlite" / "blackbox.db"


def _memory_ablation_off() -> bool:
    return (os.environ.get("ANNA_LEARNING_PROOF_MEMORY_OFF") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _lesson_runtime_imports() -> tuple[Any, Any]:
    import sys

    repo = _repo_root()
    rt = repo / "scripts" / "runtime"
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    if str(rt) not in sys.path:
        sys.path.insert(0, str(rt))
    from anna_modules.lesson_memory import (  # noqa: PLC0415
        build_situation,
        retrieve_lessons_for_situation,
    )

    return build_situation, retrieve_lessons_for_situation


def open_lesson_connection() -> sqlite3.Connection | None:
    """Open lesson DB if file exists and ``anna_lesson_memory`` table is present."""
    p = default_lesson_sqlite_path()
    if not p.is_file():
        return None
    conn = sqlite3.connect(str(p))
    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='anna_lesson_memory' LIMIT 1"
        )
        if not cur.fetchone():
            conn.close()
            return None
    except sqlite3.Error:
        conn.close()
        return None
    return conn


def compute_learning_proof_attachment(
    *,
    strategy_id: str,
    market_event_id: str,
    bar: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """
    Build learning-proof fields for a parallel Anna trace (before insert).

    If ``ANNA_LEARNING_PROOF_MEMORY_OFF`` is set, no retrieval — explicit ablation.
    Otherwise retrieve validated/promoted lessons via ``lesson_memory`` scoring.
    """
    o = bar.get("open")
    c = bar.get("close")
    sym = str(bar.get("canonical_symbol") or "SOL-PERP")
    tf = str(bar.get("timeframe") or "5m")
    baseline_action = {
        "lane": "baseline_reference",
        "side": "long",
        "size": 1.0,
        "entry_price": o,
        "exit_price": c,
        "summary": "Baseline reference: open→close long size 1 (same spine as pairing).",
    }
    anna_action = {
        "lane": "anna",
        "strategy_id": strategy_id,
        "mode": mode,
        "side": "long",
        "size": 1.0,
        "entry_price": o,
        "exit_price": c,
        "summary": f"Anna parallel harness open→close long size 1 ({mode}).",
    }

    ablation = _memory_ablation_off()
    retrieved_ids: list[str] = []
    memory_used = False
    summary = (
        f"Parallel {mode} strategy={strategy_id} market_event_id={market_event_id}; "
        f"open→close long size 1."
    )

    if ablation:
        summary += " Memory ablation: ANNA_LEARNING_PROOF_MEMORY_OFF (no retrieval)."
    else:
        conn = open_lesson_connection()
        if conn is not None:
            try:
                build_situation, retrieve_lessons = _lesson_runtime_imports()
                situation = build_situation(
                    input_text=f"{sym} {tf} candle market_event_id={market_event_id}",
                    timeframe_override=tf,
                )
                scored = retrieve_lessons(conn, situation, top_k=5, min_score=None)
                for row, _sc in scored:
                    lid = str(row.get("id") or "").strip()
                    if lid:
                        retrieved_ids.append(lid)
                memory_used = len(retrieved_ids) > 0
                if memory_used:
                    summary += f" Retrieved {len(retrieved_ids)} validated/promoted lesson(s)."
                else:
                    summary += " No eligible lessons matched (or lesson DB empty)."
            except Exception as exc:  # noqa: BLE001
                summary += f" Lesson retrieval skipped: {str(exc)[:120]}."
            finally:
                conn.close()
        else:
            summary += " Lesson DB unavailable — memory_used=false."

    return {
        "retrieved_memory_ids": retrieved_ids,
        "memory_used": memory_used,
        "decision_summary": summary[:512],
        "baseline_action_json": baseline_action,
        "anna_action_json": anna_action,
        "memory_ablation_off": ablation,
    }


def _vs_bucket(vs: Any) -> str:
    s = str(vs or "").strip().upper()
    if s == "WIN":
        return "WIN"
    if s == "NOT_WIN":
        return "NOT_WIN"
    if s == "EXCLUDED":
        return "EXCLUDED"
    return "NONE"


def build_learning_proof_bundle(
    *,
    trade_chain: dict[str, Any],
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Join trade_chain cells to ``decision_traces`` for Anna rows; aggregate memory vs non-memory.

    Requires migrated ``decision_traces`` columns (``retrieved_memory_ids_json``, etc.).
    """
    from modules.anna_training.decision_trace import query_trace_by_trade_id
    from modules.anna_training.execution_ledger import default_execution_ledger_path

    db_path = db_path or default_execution_ledger_path()
    schema = "learning_proof_bundle_v1"
    rows_tc = trade_chain.get("rows") or []
    event_axis = trade_chain.get("event_axis") or []
    if not isinstance(event_axis, list):
        event_axis = []

    per_event: list[dict[str, Any]] = []
    mem_wins = mem_not = mem_exc = mem_n = 0
    nom_wins = nom_not = nom_exc = nom_n = 0

    for r in rows_tc:
        ck = str(r.get("chain_kind") or "")
        if ck not in ("anna_test", "anna_strategy"):
            continue
        sid = str(r.get("strategy_id") or "").strip()
        cells = r.get("cells") or {}
        if not isinstance(cells, dict):
            continue
        for mid in event_axis:
            mid = str(mid).strip()
            if not mid:
                continue
            cell = cells.get(mid)
            if not isinstance(cell, dict) or cell.get("empty"):
                continue
            tid = str(cell.get("trade_id") or "").strip()
            vs = _vs_bucket(cell.get("vs_baseline"))
            tr = query_trace_by_trade_id(tid, db_path=db_path) if tid else None
            mem_used = bool(tr and tr.get("memory_used"))
            ids = tr.get("retrieved_memory_ids") if tr else []
            if not isinstance(ids, list):
                ids = []
            proof = {
                "market_event_id": mid,
                "strategy_id": sid,
                "trade_id": tid or None,
                "trace_id": (tr or {}).get("trace_id"),
                "memory_used": mem_used,
                "retrieved_memory_ids": ids,
                "memory_ablation_off": bool((tr or {}).get("memory_ablation_off")),
                "vs_baseline": vs if vs != "NONE" else None,
                "pnl_usd": cell.get("pnl_usd"),
                "decision_summary": (tr or {}).get("decision_summary"),
            }
            per_event.append(proof)

            if vs == "NONE":
                continue
            if mem_used:
                mem_n += 1
                if vs == "WIN":
                    mem_wins += 1
                elif vs == "NOT_WIN":
                    mem_not += 1
                else:
                    mem_exc += 1
            else:
                nom_n += 1
                if vs == "WIN":
                    nom_wins += 1
                elif vs == "NOT_WIN":
                    nom_not += 1
                else:
                    nom_exc += 1

    def _rate(w: int, n: int) -> float | None:
        if n <= 0:
            return None
        return round(w / n, 6)

    mem_rate = _rate(mem_wins, mem_n)
    nom_rate = _rate(nom_wins, nom_n)
    delta = None
    if mem_rate is not None and nom_rate is not None:
        delta = round(mem_rate - nom_rate, 6)

    status = "insufficient_data"
    if mem_n >= 2 and nom_n >= 2:
        if delta is not None:
            if delta > 0.02:
                status = "improving"
            elif delta < -0.02:
                status = "degrading"
            else:
                status = "neutral"

    return {
        "schema": schema,
        "claim": (
            "Anna learned if retrieved knowledge changed the decision and improved outcomes vs baseline."
        ),
        "per_event": per_event[-96:],  # cap
        "aggregate": {
            "memory_used_events": mem_n,
            "memory_unused_events": nom_n,
            "memory_used_wins": mem_wins,
            "memory_used_not_wins": mem_not,
            "memory_used_excluded": mem_exc,
            "memory_unused_wins": nom_wins,
            "memory_unused_not_wins": nom_not,
            "memory_unused_excluded": nom_exc,
            "win_rate_memory_used": mem_rate,
            "win_rate_memory_unused": nom_rate,
            "win_rate_delta_memory_minus_nomemory": delta,
            "learning_proof_status": status,
            "note": (
                "WIN rate = WIN / (WIN+NOT+EXCLUDED) per bucket. "
                "Compare only when both buckets have enough paired events; "
                "otherwise status=insufficient_data."
            ),
        },
        "ablation_env": "ANNA_LEARNING_PROOF_MEMORY_OFF",
        "lesson_db_path": str(default_lesson_sqlite_path()),
    }
