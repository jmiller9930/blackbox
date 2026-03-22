#!/usr/bin/env python3
"""
Phase 2.12 — Policy-gated action filter: guardrail mode × simulated action → allowed paper intent.

Read-only except optional --store. No execution, no exchanges.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from guardrail_policy_evaluator import build_guardrail_document
from simulated_action_router import compute_simulated_action, load_latest_stored_simulated_action


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_latest_stored_guardrail_policy(conn) -> tuple[str, dict]:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Guardrail Policy]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        raise LookupError("no stored [Guardrail Policy] task found")
    data = json.loads(row[1])
    if data.get("kind") != "guardrail_policy_v1":
        raise ValueError("latest guardrail task is not guardrail_policy_v1")
    return row[0], data


def _merge_caution(a: list[Any], b: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for src in (a, b):
        for x in src or []:
            s = str(x).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def apply_policy_gate(policy: dict, sim: dict) -> dict[str, Any]:
    mode = policy.get("mode")
    incoming = sim.get("action")

    if incoming not in ("HOLD", "WATCH", "PAPER_TRADE_READY"):
        return {
            "final_action": "BLOCKED",
            "policy_result": "FROZEN_BLOCK",
            "rationale": f"Unrecognized simulated action {incoming!r}; treating as blocked.",
        }

    if mode == "FROZEN":
        return {
            "final_action": "BLOCKED",
            "policy_result": "FROZEN_BLOCK",
            "rationale": "Guardrail mode is FROZEN; policy forbids downstream action proposals.",
        }

    if mode == "CAUTION":
        if incoming == "HOLD":
            return {
                "final_action": "HOLD",
                "policy_result": "CAUTION_PASS",
                "rationale": "CAUTION mode: HOLD passes through unchanged.",
            }
        if incoming == "WATCH":
            return {
                "final_action": "WATCH",
                "policy_result": "CAUTION_PASS",
                "rationale": "CAUTION mode: WATCH passes through unchanged.",
            }
        if incoming == "PAPER_TRADE_READY":
            return {
                "final_action": "WATCH",
                "policy_result": "CAUTION_DOWNGRADE",
                "rationale": "CAUTION mode: PAPER_TRADE_READY downgraded to WATCH under policy.",
            }

    if mode == "NORMAL":
        return {
            "final_action": incoming,
            "policy_result": "NORMAL_PASS",
            "rationale": "NORMAL mode: simulated action passes through without downgrade.",
        }

    return {
        "final_action": "BLOCKED",
        "policy_result": "FROZEN_BLOCK",
        "rationale": f"Unrecognized guardrail mode {mode!r}; blocking.",
    }


def build_policy_gated_document(
    db_path: Path,
    *,
    use_stored_policy: bool,
    use_stored_simulated_action: bool,
    include_optional_refs: bool,
    guardrail_use_stored_context: bool,
    guardrail_use_stored_trend: bool,
    guardrail_include_insight: bool,
    guardrail_trend_recent: int,
    sim_analyst_from_stored: bool,
    sim_use_stored_context: bool,
    sim_include_context_ref: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
) -> dict[str, Any]:
    root = repo_root()

    if use_stored_policy:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        try:
            _pid, policy = load_latest_stored_guardrail_policy(conn)
        finally:
            conn.close()
    else:
        policy = build_guardrail_document(
            db_path,
            use_stored_context=guardrail_use_stored_context,
            use_stored_trend=guardrail_use_stored_trend,
            include_insight_ref=guardrail_include_insight,
            health_limit=health_limit,
            task_limit=task_limit,
            alert_window=alert_window,
            trend_recent=guardrail_trend_recent,
        )

    if use_stored_simulated_action:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        try:
            _sid, sim = load_latest_stored_simulated_action(conn)
        finally:
            conn.close()
    else:
        sim, _src = compute_simulated_action(
            db_path,
            analyst_from_stored=sim_analyst_from_stored,
            use_stored_context_for_live=sim_use_stored_context,
            include_context_ref=sim_include_context_ref,
            health_limit=health_limit,
            task_limit=task_limit,
            alert_window=alert_window,
        )

    gate = apply_policy_gate(policy, sim)
    cflags = _merge_caution(policy.get("caution_flags"), sim.get("caution_flags"))

    doc: dict[str, Any] = {
        "kind": "policy_gated_action_v1",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "source_policy": policy,
        "source_action": sim,
        "guardrail_mode": policy.get("mode"),
        "incoming_action": sim.get("action"),
        "final_action": gate["final_action"],
        "policy_result": gate["policy_result"],
        "rationale": gate["rationale"],
        "caution_flags": cflags,
        "notes": [
            "Paper-intent gating only — no live execution, no exchange, no executor.",
            "final_action is the post-policy simulated intent (BLOCKED/HOLD/WATCH/PAPER_TRADE_READY).",
        ],
    }

    if include_optional_refs:
        doc["analyst_decision_reference"] = {
            "source_analyst_task_id": sim.get("source_analyst_task_id"),
            "decision": (sim.get("source_decision") or {}).get("decision")
            if isinstance(sim.get("source_decision"), dict)
            else None,
            "kind": (sim.get("source_decision") or {}).get("kind")
            if isinstance(sim.get("source_decision"), dict)
            else None,
        }
        doc["decision_context_reference"] = sim.get("decision_context_reference")

    return doc


def run_local_branch_tests() -> dict[str, Any]:
    """FROZEN_BLOCK, CAUTION_DOWNGRADE, NORMAL_PASS without DB."""
    results: list[dict[str, Any]] = []

    p_frozen = {"mode": "FROZEN", "caution_flags": []}
    sim_ptr = {"action": "PAPER_TRADE_READY", "caution_flags": []}
    g1 = apply_policy_gate(p_frozen, sim_ptr)
    results.append(
        {
            "branch": "LOCAL FROZEN_BLOCK",
            "policy_result": g1["policy_result"],
            "final_action": g1["final_action"],
            "ok": g1["policy_result"] == "FROZEN_BLOCK" and g1["final_action"] == "BLOCKED",
        }
    )

    p_caution = {"mode": "CAUTION", "caution_flags": ["x"]}
    sim_ready = {"action": "PAPER_TRADE_READY", "caution_flags": []}
    g2 = apply_policy_gate(p_caution, sim_ready)
    results.append(
        {
            "branch": "LOCAL CAUTION_DOWNGRADE",
            "policy_result": g2["policy_result"],
            "final_action": g2["final_action"],
            "ok": g2["policy_result"] == "CAUTION_DOWNGRADE" and g2["final_action"] == "WATCH",
        }
    )

    p_normal = {"mode": "NORMAL", "caution_flags": []}
    sim_ok = {"action": "PAPER_TRADE_READY", "caution_flags": []}
    g3 = apply_policy_gate(p_normal, sim_ok)
    results.append(
        {
            "branch": "LOCAL NORMAL_PASS",
            "policy_result": g3["policy_result"],
            "final_action": g3["final_action"],
            "ok": g3["policy_result"] == "NORMAL_PASS" and g3["final_action"] == "PAPER_TRADE_READY",
        }
    )

    return {"branch_tests": results, "all_pass": all(r["ok"] for r in results)}


def run(
    db_path: Path,
    *,
    use_stored_policy: bool,
    use_stored_simulated_action: bool,
    include_optional_refs: bool,
    guardrail_use_stored_context: bool,
    guardrail_use_stored_trend: bool,
    guardrail_include_insight: bool,
    guardrail_trend_recent: int,
    sim_analyst_from_stored: bool,
    sim_use_stored_context: bool,
    sim_include_context_ref: bool,
    health_limit: int,
    task_limit: int,
    alert_window: int,
    store: bool,
) -> int:
    root = repo_root()
    try:
        doc = build_policy_gated_document(
            db_path,
            use_stored_policy=use_stored_policy,
            use_stored_simulated_action=use_stored_simulated_action,
            include_optional_refs=include_optional_refs,
            guardrail_use_stored_context=guardrail_use_stored_context,
            guardrail_use_stored_trend=guardrail_use_stored_trend,
            guardrail_include_insight=guardrail_include_insight,
            guardrail_trend_recent=guardrail_trend_recent,
            sim_analyst_from_stored=sim_analyst_from_stored,
            sim_use_stored_context=sim_use_stored_context,
            sim_include_context_ref=sim_include_context_ref,
            health_limit=health_limit,
            task_limit=task_limit,
            alert_window=alert_window,
        )
    except (LookupError, ValueError) as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        return 3

    out: dict[str, Any] = {"policy_gated_action": doc, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = doc["generated_at"]
        title = f"[Policy Gated Action] {now[:19]}Z"
        desc = json.dumps(doc, ensure_ascii=False, indent=2)
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
        description="Phase 2.12 — policy-gated simulated action (paper intent only)",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-policy",
        action="store_true",
        help="Load latest [Guardrail Policy] task instead of live guardrail build",
    )
    p.add_argument(
        "--use-latest-stored-simulated-action",
        action="store_true",
        help="Load latest [Simulated Action] task instead of live compute",
    )
    p.add_argument(
        "--include-optional-refs",
        action="store_true",
        help="Include analyst/decision-context reference fields when present on simulated action",
    )
    p.add_argument(
        "--guardrail-use-latest-stored-decision-context",
        action="store_true",
        help="When building live policy: use stored [Decision Context]",
    )
    p.add_argument(
        "--guardrail-use-latest-stored-trend",
        action="store_true",
        help="When building live policy: use stored [System Trend]",
    )
    p.add_argument(
        "--guardrail-include-insight-reference",
        action="store_true",
        help="When building live policy: attach insight ref",
    )
    p.add_argument("--guardrail-trend-recent", type=int, default=10)
    p.add_argument(
        "--sim-use-latest-stored-analyst",
        action="store_true",
        help="When building live simulated action: use stored analyst",
    )
    p.add_argument(
        "--sim-use-latest-stored-context",
        action="store_true",
        help="When building live simulated action: use stored decision context for live analyst",
    )
    p.add_argument(
        "--sim-include-decision-context-ref",
        action="store_true",
        help="When building live simulated action: attach decision context ref",
    )
    p.add_argument("--health-limit", type=int, default=120)
    p.add_argument("--task-limit", type=int, default=50)
    p.add_argument("--alert-window-days", type=int, default=7)
    p.add_argument("--store", action="store_true")
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Run FROZEN_BLOCK / CAUTION_DOWNGRADE / NORMAL_PASS fixture tests (no DB)",
    )
    args = p.parse_args(argv)
    if args.self_test:
        print(json.dumps(run_local_branch_tests(), indent=2, ensure_ascii=False))
        return 0

    db = args.db or default_sqlite_path()
    return run(
        db,
        use_stored_policy=args.use_latest_stored_policy,
        use_stored_simulated_action=args.use_latest_stored_simulated_action,
        include_optional_refs=args.include_optional_refs,
        guardrail_use_stored_context=args.guardrail_use_latest_stored_decision_context,
        guardrail_use_stored_trend=args.guardrail_use_latest_stored_trend,
        guardrail_include_insight=args.guardrail_include_insight_reference,
        guardrail_trend_recent=max(1, min(100, args.guardrail_trend_recent)),
        sim_analyst_from_stored=args.sim_use_latest_stored_analyst,
        sim_use_stored_context=args.sim_use_latest_stored_context,
        sim_include_context_ref=args.sim_include_decision_context_ref,
        health_limit=max(10, args.health_limit),
        task_limit=max(5, args.task_limit),
        alert_window=max(1, args.alert_window_days),
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
