#!/usr/bin/env python3
"""
Phase 2.9 — System insight layer: deterministic interpretation of trade episode(s).

Read-only; no ML, no trading, no row updates except optional --store.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_recent_trade_episodes(conn, limit: int) -> list[tuple[str, dict]]:
    """Rows newest first: (task_id, trade_episode_v1 dict)."""
    lim = max(1, min(50, int(limit)))
    rows = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Trade Episode]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT ?
        """,
        (lim,),
    ).fetchall()
    out: list[tuple[str, dict]] = []
    for tid, desc in rows:
        if not desc:
            continue
        try:
            data = json.loads(desc)
        except json.JSONDecodeError:
            continue
        if data.get("kind") != "trade_episode_v1":
            continue
        out.append((tid, data))
    return out


def _readiness(ep: dict) -> str | None:
    ss = ep.get("system_state_summary")
    if isinstance(ss, dict):
        r = ss.get("system_readiness")
        if r in ("healthy", "degraded", "unstable"):
            return r
    return None


def _decision(ep: dict) -> str | None:
    dr = ep.get("decision_reference") or {}
    d = dr.get("decision")
    if d in ("NO_TRADE", "REDUCED_RISK", "ALLOW"):
        return d
    return None


def _action(ep: dict) -> str | None:
    ar = ep.get("action_reference") or {}
    a = ar.get("action")
    if isinstance(a, str) and a.strip():
        return a.strip()
    return None


def _outcome_status(ep: dict) -> str | None:
    oref = ep.get("outcome_reference") or {}
    o = oref.get("outcome_status")
    if isinstance(o, str) and o.strip():
        return o.strip()
    return None


def decision_alignment_label(readiness: str | None, decision: str | None) -> tuple[str, str]:
    """
    Return (alignment, rationale) deterministic strings.
    alignment: aligned | cautious | misaligned | unknown
    """
    if decision is None or readiness is None:
        return "unknown", "Missing decision or system_readiness; cannot score alignment."

    # Rule table (readiness x decision)
    key = (readiness, decision)
    table: dict[tuple[str, str], tuple[str, str]] = {
        ("unstable", "NO_TRADE"): (
            "aligned",
            "Unstable readiness with NO_TRADE matches conservative policy.",
        ),
        ("unstable", "REDUCED_RISK"): (
            "cautious",
            "Unstable readiness with REDUCED_RISK is only partially conservative.",
        ),
        ("unstable", "ALLOW"): (
            "misaligned",
            "Unstable readiness with ALLOW is inconsistent with safe posture.",
        ),
        ("degraded", "NO_TRADE"): (
            "aligned",
            "Degraded state with NO_TRADE is conservative.",
        ),
        ("degraded", "REDUCED_RISK"): (
            "aligned",
            "Degraded readiness with REDUCED_RISK matches the architect alignment example.",
        ),
        ("degraded", "ALLOW"): (
            "misaligned",
            "Degraded readiness with ALLOW is risky relative to system state.",
        ),
        ("healthy", "NO_TRADE"): (
            "cautious",
            "Healthy readiness with NO_TRADE may be overly conservative (context-dependent).",
        ),
        ("healthy", "REDUCED_RISK"): (
            "cautious",
            "Healthy readiness with REDUCED_RISK is conservative despite green signals.",
        ),
        ("healthy", "ALLOW"): (
            "aligned",
            "Healthy readiness with ALLOW is consistent with allowance to proceed (paper-only).",
        ),
    }
    if key in table:
        return table[key]
    return "unknown", f"No rule for readiness={readiness!r} and decision={decision!r}."


def _outcome_one_line(status: str | None) -> str:
    if not status:
        return "Outcome status missing."
    mapping = {
        "MONITORING": "Pipeline ended in watch/monitor posture — no paper trade outcome asserted.",
        "NOT_APPLICABLE": "No paper execution path applied; outcome not applicable.",
        "SUCCESS": "Paper execution record passed structural viability checks.",
        "FAILURE": "Structural or chain checks failed for the paper execution record.",
        "UNKNOWN": "Outcome could not be classified as success/failure with confidence.",
    }
    return mapping.get(status, f"Outcome status is {status!r}.")


def _structural_gaps_for_episode(ep: dict) -> dict[str, Any]:
    gaps: list[str] = []
    ar = ep.get("alert_reference") or {}
    tr = ep.get("task_reference") or {}
    if not ar.get("alert_id"):
        gaps.append("alert_reference.alert_id is null")
    if tr.get("coordination_task_id") is None:
        gaps.append("task_reference.coordination_task_id is null")

    raw = json.dumps(ep, ensure_ascii=False)
    if "PLACEHOLDER" in raw.upper():
        gaps.append("Episode JSON contains PLACEHOLDER marker(s).")

    return {"gaps": gaps, "gap_count": len(gaps)}


def _risk_signals_aggregate(episodes: list[tuple[str, dict]]) -> dict[str, Any]:
    all_flags: list[str] = []
    readiness_c = Counter()
    open_alerts: list[int] = []

    for _tid, ep in episodes:
        for f in ep.get("caution_flags") or []:
            if isinstance(f, str) and f.strip():
                all_flags.append(f.strip())
        r = _readiness(ep)
        if r:
            readiness_c[r] += 1
        ss = ep.get("system_state_summary")
        if isinstance(ss, dict):
            n = ss.get("alert_open_unacknowledged")
            if isinstance(n, int):
                open_alerts.append(n)

    flag_counts = dict(Counter(all_flags).most_common(20))
    repeated = [f for f, c in Counter(all_flags).items() if c > 1]

    return {
        "caution_flag_total_occurrences": len(all_flags),
        "caution_flag_distinct_count": len(set(all_flags)),
        "most_common_caution_flags": flag_counts,
        "repeated_across_episodes": sorted(set(repeated)),
        "readiness_counts": dict(readiness_c),
        "alert_open_unacknowledged_values_seen": sorted(set(open_alerts)),
    }


def build_system_insight(episodes: list[tuple[str, dict]]) -> dict[str, Any]:
    if not episodes:
        raise ValueError("no episodes to analyze")

    # Deterministic order by episode_id string
    episodes_sorted = sorted(episodes, key=lambda x: (x[1].get("episode_id") or "", x[0]))

    eids = [e[1].get("episode_id") or f"task:{e[0]}" for e in episodes_sorted]

    per_outcome: list[dict[str, Any]] = []
    per_align: list[dict[str, Any]] = []
    gap_notes: list[str] = []
    placeholder_hits = 0

    for task_id, ep in episodes_sorted:
        oid = ep.get("episode_id") or f"task:{task_id}"
        ost = _outcome_status(ep)
        per_outcome.append(
            {
                "episode_id": oid,
                "source_trade_episode_task_id": task_id,
                "outcome_status": ost,
                "summary_line": _outcome_one_line(ost),
            }
        )

        readiness = _readiness(ep)
        dec = _decision(ep)
        act = _action(ep)
        align, rat = decision_alignment_label(readiness, dec)
        per_align.append(
            {
                "episode_id": oid,
                "system_readiness": readiness,
                "analyst_decision": dec,
                "simulated_action": act,
                "alignment": align,
                "rationale": rat,
            }
        )

        sg = _structural_gaps_for_episode(ep)
        if sg["gap_count"]:
            gap_notes.append(f"{oid}: {sg['gap_count']} gap(s): " + "; ".join(sg["gaps"]))
        raw = json.dumps(ep, ensure_ascii=False)
        if "PLACEHOLDER" in raw.upper():
            placeholder_hits += 1

    risk = _risk_signals_aggregate(episodes)

    structural_gaps: dict[str, Any] = {
        "episodes_analyzed": len(episodes_sorted),
        "episodes_with_null_alert_link": sum(
            1
            for _t, ep in episodes_sorted
            if not ((ep.get("alert_reference") or {}).get("alert_id"))
        ),
        "episodes_with_null_coordination_task_link": sum(
            1
            for _t, ep in episodes_sorted
            if (ep.get("task_reference") or {}).get("coordination_task_id") is None
        ),
        "episodes_containing_placeholder_marker": placeholder_hits,
        "per_episode_gap_notes": gap_notes,
    }

    notes = [
        "Deterministic rule-based insight only — no ML, no market data, no PnL.",
        "Decision alignment uses fixed readiness × decision table.",
    ]

    return {
        "kind": "system_insight_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "episode_ids": eids,
        "outcome_summary": {
            "episodes": per_outcome,
            "dominant_outcome_statuses": dict(
                Counter(_outcome_status(ep) or "UNKNOWN" for _tid, ep in episodes_sorted).most_common()
            ),
        },
        "decision_alignment": {
            "episodes": per_align,
            "alignment_counts": dict(Counter(p["alignment"] for p in per_align).most_common()),
        },
        "risk_signals": risk,
        "structural_gaps": structural_gaps,
        "notes": notes,
    }


def run(db_path: Path, *, recent: int, store: bool) -> int:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)
    try:
        eps = load_recent_trade_episodes(conn, recent)
    finally:
        conn.close()

    if not eps:
        print(
            json.dumps({"error": "no stored [Trade Episode] tasks with trade_episode_v1"}, indent=2),
            file=sys.stderr,
        )
        return 3

    insight = build_system_insight(eps)
    out: dict[str, Any] = {"system_insight": insight, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = insight["generated_at"]
        title = f"[System Insight] {now[:19]}Z"
        desc = json.dumps(insight, ensure_ascii=False, indent=2)
        conn.execute(
            """
            INSERT INTO tasks (id, agent_id, title, description, state, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, "main", title, desc, "completed", "normal", now, now),
        )
        conn.commit()
        conn.close()
        out["stored_task_id"] = tid

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Phase 2.9 — system insight from recent [Trade Episode] rows",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--recent",
        type=int,
        default=8,
        metavar="N",
        help="Number of most recent [Trade Episode] tasks to analyze (default 8, max 50)",
    )
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist system_insight_v1 as [System Insight] completed task",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(db, recent=args.recent, store=args.store)


if __name__ == "__main__":
    raise SystemExit(main())
