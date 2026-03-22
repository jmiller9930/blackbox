#!/usr/bin/env python3
"""
Phase 2.10 — Insight trend tracker: aggregate recent [System Insight] tasks into trends.

Deterministic, explainable; no ML, no mutations except optional --store.
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


OUTCOME_KEYS = ("MONITORING", "SUCCESS", "FAILURE", "UNKNOWN", "NOT_APPLICABLE")
ALIGN_KEYS = ("aligned", "cautious", "misaligned", "unknown")
READINESS_KEYS = ("healthy", "degraded", "unstable")


def load_recent_system_insights(conn, limit: int) -> list[tuple[str, dict]]:
    lim = max(1, min(100, int(limit)))
    rows = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[System Insight]%'
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
        if data.get("kind") != "system_insight_v1":
            continue
        out.append((tid, data))
    return out


def _split_windows(
    insights: list[tuple[str, dict]],
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """First half = newer (list is newest-first); second half = older."""
    n = len(insights)
    if n == 0:
        return [], []
    split = n // 2
    if split == 0:
        return list(insights), []
    return list(insights[:split]), list(insights[split:])


def _outcome_counts_from_insight(doc: dict) -> Counter[str]:
    c: Counter[str] = Counter()
    eps = (doc.get("outcome_summary") or {}).get("episodes") or []
    if eps:
        for e in eps:
            o = e.get("outcome_status")
            if o in OUTCOME_KEYS:
                c[o] += 1
            else:
                c["UNKNOWN"] += 1
        return c
    dom = (doc.get("outcome_summary") or {}).get("dominant_outcome_statuses") or {}
    for k, v in dom.items():
        if k in OUTCOME_KEYS and isinstance(v, int):
            c[k] += v
    return c


def _alignment_counts_from_insight(doc: dict) -> Counter[str]:
    c: Counter[str] = Counter()
    eps = (doc.get("decision_alignment") or {}).get("episodes") or []
    if eps:
        for e in eps:
            a = e.get("alignment")
            if a in ALIGN_KEYS:
                c[a] += 1
            else:
                c["unknown"] += 1
        return c
    ac = (doc.get("decision_alignment") or {}).get("alignment_counts") or {}
    for k, v in ac.items():
        if k in ALIGN_KEYS and isinstance(v, int):
            c[k] += v
    return c


def _readiness_counts_from_insight(doc: dict) -> Counter[str]:
    c: Counter[str] = Counter()
    eps = (doc.get("decision_alignment") or {}).get("episodes") or []
    for e in eps:
        r = e.get("system_readiness")
        if r in READINESS_KEYS:
            c[r] += 1
        elif r:
            c["unknown"] += 1
    return c


def _aggregate_counter(
    insights: list[tuple[str, dict]],
    fn: Any,
) -> Counter[str]:
    total: Counter[str] = Counter()
    for _tid, doc in insights:
        total.update(fn(doc))
    return total


def _sum_structural(doc: dict) -> dict[str, int]:
    sg = doc.get("structural_gaps") or {}
    return {
        "null_alert_link_episodes": int(sg.get("episodes_with_null_alert_link") or 0),
        "null_coordination_link_episodes": int(
            sg.get("episodes_with_null_coordination_task_link") or 0
        ),
        "placeholder_episodes": int(sg.get("episodes_containing_placeholder_marker") or 0),
    }


def _aggregate_structural(insights: list[tuple[str, dict]]) -> dict[str, int]:
    acc = {"null_alert_link_episodes": 0, "null_coordination_link_episodes": 0, "placeholder_episodes": 0}
    for _tid, doc in insights:
        s = _sum_structural(doc)
        for k in acc:
            acc[k] += s[k]
    return acc


def _risk_flag_presence_counts(insights: list[tuple[str, dict]]) -> Counter[str]:
    """Per insight run, count 1 if flag appears in risk_signals."""
    presence: Counter[str] = Counter()
    for _tid, doc in insights:
        rs = doc.get("risk_signals") or {}
        mcf = rs.get("most_common_caution_flags") or {}
        seen: set[str] = set()
        if isinstance(mcf, dict):
            for flag_text, cnt in mcf.items():
                if cnt:
                    seen.add(str(flag_text))
        for flag_text in seen:
            presence[flag_text] += 1
    return presence


def _delta_counter(
    recent: Counter[str], prior: Counter[str], keys: tuple[str, ...]
) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in keys:
        out[k] = int(recent.get(k, 0)) - int(prior.get(k, 0))
    return out


def build_system_trend(insights: list[tuple[str, dict]]) -> dict[str, Any]:
    if not insights:
        raise ValueError("no system insights to analyze")

    n = len(insights)
    recent, prior = _split_windows(insights)

    oc_r = _aggregate_counter(recent, _outcome_counts_from_insight)
    oc_p = _aggregate_counter(prior, _outcome_counts_from_insight)
    al_r = _aggregate_counter(recent, _alignment_counts_from_insight)
    al_p = _aggregate_counter(prior, _alignment_counts_from_insight)
    rd_r = _aggregate_counter(recent, _readiness_counts_from_insight)
    rd_p = _aggregate_counter(prior, _readiness_counts_from_insight)

    str_r = _aggregate_structural(recent)
    str_p = _aggregate_structural(prior)

    presence_all = _risk_flag_presence_counts(insights)
    threshold = max(1, int((n * 50 + 99) // 100))  # ceil(n * 0.5)
    persistent_flags = sorted(
        [f for f, c in presence_all.items() if c >= threshold],
        key=str,
    )
    outcome_trend = {
        "recent_window_count": len(recent),
        "prior_window_count": len(prior),
        "recent_outcome_counts": {k: int(oc_r.get(k, 0)) for k in OUTCOME_KEYS},
        "prior_outcome_counts": {k: int(oc_p.get(k, 0)) for k in OUTCOME_KEYS},
        "outcome_delta_recent_minus_prior": _delta_counter(oc_r, oc_p, OUTCOME_KEYS),
    }

    alignment_trend = {
        "recent_alignment_counts": {k: int(al_r.get(k, 0)) for k in ALIGN_KEYS},
        "prior_alignment_counts": {k: int(al_p.get(k, 0)) for k in ALIGN_KEYS},
        "alignment_delta_recent_minus_prior": _delta_counter(al_r, al_p, ALIGN_KEYS),
        "misaligned_recent": int(al_r.get("misaligned", 0)),
        "misaligned_prior": int(al_p.get("misaligned", 0)),
    }

    risk_trend = {
        "insight_runs_analyzed": n,
        "persistence_threshold_count": threshold,
        "persistence_threshold_percent": 50,
        "flag_presence_across_insight_runs": dict(
            sorted(presence_all.items(), key=lambda x: (-x[1], x[0]))
        ),
        "persistent_flags": persistent_flags,
    }

    structural_trend = {
        "recent_structural_totals": str_r,
        "prior_structural_totals": str_p,
        "recent_avg_null_alert_per_insight": (
            str_r["null_alert_link_episodes"] / len(recent) if recent else 0.0
        ),
        "prior_avg_null_alert_per_insight": (
            str_p["null_alert_link_episodes"] / len(prior) if prior else 0.0
        ),
    }

    readiness_trend = {
        "recent_readiness_counts": {k: int(rd_r.get(k, 0)) for k in READINESS_KEYS},
        "prior_readiness_counts": {k: int(rd_p.get(k, 0)) for k in READINESS_KEYS},
        "readiness_delta_recent_minus_prior": _delta_counter(rd_r, rd_p, READINESS_KEYS),
    }

    flags: list[str] = []
    if int(al_r.get("misaligned", 0)) > int(al_p.get("misaligned", 0)):
        flags.append("misalignment rising")
    for pf in persistent_flags:
        if "alert" in pf.lower():
            flags.append("persistent alerts")
            break
    if len(recent) and (
        str_r["null_alert_link_episodes"] + str_r["null_coordination_link_episodes"]
        >= len(recent)
    ):
        flags.append("structural gaps high")

    # Dedupe preserve order
    seen_f: set[str] = set()
    flags_out = []
    for f in flags:
        if f not in seen_f:
            seen_f.add(f)
            flags_out.append(f)

    notes = [
        f"Compared newest {len(recent)} insight run(s) vs older {len(prior)} run(s) "
        f"(total window_size={n}).",
        "Trends aggregate episode-level rows inside each stored system_insight_v1.",
        "Misalignment trend uses misaligned counts in each half-window.",
        "Risk persistence: caution flag text present in ≥50% of insight runs in this window.",
    ]
    if not prior:
        notes.append("No prior window — only one insight run or odd split; deltas are partial.")

    return {
        "kind": "system_trend_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "window_size": n,
        "outcome_trend": outcome_trend,
        "alignment_trend": alignment_trend,
        "risk_trend": risk_trend,
        "structural_trend": structural_trend,
        "readiness_trend": readiness_trend,
        "flags": flags_out,
        "notes": notes,
    }


def run(db_path: Path, *, window: int, store: bool) -> int:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)
    try:
        rows = load_recent_system_insights(conn, window)
    finally:
        conn.close()

    if not rows:
        print(
            json.dumps({"error": "no stored [System Insight] tasks with system_insight_v1"}, indent=2),
            file=sys.stderr,
        )
        return 3

    trend = build_system_trend(rows)
    out: dict[str, Any] = {"system_trend": trend, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = trend["generated_at"]
        title = f"[System Trend] {now[:19]}Z"
        desc = json.dumps(trend, ensure_ascii=False, indent=2)
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
        description="Phase 2.10 — trend analysis from recent [System Insight] tasks",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--recent",
        type=int,
        default=10,
        metavar="N",
        help="Number of most recent [System Insight] tasks (default 10, max 100)",
    )
    p.add_argument(
        "--store",
        action="store_true",
        help="Persist system_trend_v1 as [System Trend] completed task",
    )
    args = p.parse_args(argv)
    db = args.db or default_sqlite_path()
    return run(db, window=args.recent, store=args.store)


if __name__ == "__main__":
    raise SystemExit(main())
