#!/usr/bin/env python3
"""
Phase 3.3 — Anna proposal builder: anna_analysis_v1 → anna_proposal_v1 (validation-loop bridge).

Deterministic; paper-only; no Telegram, no registry load, no schema migration, no trades.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from anna_analyst_v1 import (
    build_analysis,
    load_latest_guardrail_policy,
    load_latest_market_snapshot,
    try_load_decision_context,
    try_load_trend,
)

SCHEMA_VERSION = 1

PROPOSAL_TYPES = ("NO_CHANGE", "RISK_REDUCTION", "CONDITION_TIGHTENING", "OBSERVATION_ONLY")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_latest_stored_anna_analysis(conn) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Return (task_id, anna_analysis_v1 dict, error_message)."""
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Anna Analysis]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        return None, None, "No [Anna Analysis] task found in database."
    tid, desc = row[0], row[1]
    try:
        blob = json.loads(desc)
    except json.JSONDecodeError:
        return None, None, "Latest [Anna Analysis] row is not valid JSON."
    if isinstance(blob, dict) and "anna_analysis" in blob:
        anna = blob["anna_analysis"]
    else:
        anna = blob
    if not isinstance(anna, dict) or anna.get("kind") != "anna_analysis_v1":
        return None, None, "Latest Anna task is not anna_analysis_v1."
    return tid, anna, None


def classify_proposal_type(anna: dict[str, Any]) -> str:
    """Map analysis to one of PROPOSAL_TYPES (deterministic)."""
    pol = anna.get("policy_alignment") or {}
    mode = pol.get("guardrail_mode") or "unknown"
    risk = (anna.get("risk_assessment") or {}).get("level") or "low"
    intent = (anna.get("suggested_action") or {}).get("intent") or "WATCH"
    concepts = list(anna.get("concepts_used") or [])
    text = anna.get("input_text") or ""
    confirm_need = re.search(
        r"\b(confirm|confirmation|wait|unsure|ambiguous|more data|need more)\b", text, re.I
    )

    if not concepts and mode == "unknown" and risk == "low":
        return "OBSERVATION_ONLY"

    if mode == "FROZEN" or intent == "HOLD" or risk == "high":
        return "RISK_REDUCTION"

    if mode == "CAUTION" or (intent == "WATCH" and risk in ("medium", "high")) or confirm_need:
        return "CONDITION_TIGHTENING"

    if mode == "NORMAL" and risk == "low" and intent == "PAPER_TRADE_READY" and not confirm_need:
        return "NO_CHANGE"

    if mode == "unknown" or risk == "low":
        return "OBSERVATION_ONLY"

    return "CONDITION_TIGHTENING"


def paper_intent_for_proposal(proposal_type: str, anna_intent: str) -> str:
    if proposal_type == "NO_CHANGE":
        return "unchanged"
    if proposal_type == "OBSERVATION_ONLY":
        return "unknown"
    return anna_intent if anna_intent in ("HOLD", "WATCH", "PAPER_TRADE_READY") else "unknown"


def build_anna_proposal(
    anna: dict[str, Any],
    *,
    source_task_id: str | None,
    extra_notes: list[str],
) -> dict[str, Any]:
    ptype = classify_proposal_type(anna)
    pol = anna.get("policy_alignment") or {}
    mode = pol.get("guardrail_mode") or "unknown"
    risk = (anna.get("risk_assessment") or {}).get("level") or "unknown"
    alignment = pol.get("alignment") or "unknown"
    intent = (anna.get("suggested_action") or {}).get("intent") or "WATCH"
    rationale = (anna.get("suggested_action") or {}).get("rationale") or ""
    interp = (anna.get("interpretation") or {}).get("summary") or ""
    concepts = list(anna.get("concepts_used") or [])

    paper_intent = paper_intent_for_proposal(ptype, intent)

    guardrail_interaction = (
        f"Proposal derived under guardrail posture {mode}. "
        f"Type {ptype}: align Anna interpretation with paper-only evaluation and later outcome checks — not execution."
    )

    reasoning_scope = ["risk", "market_conditions"]
    if concepts:
        reasoning_scope.append("execution_quality")

    summary = (
        f"{ptype}: Anna recommends structuring follow-up as {ptype.lower().replace('_', ' ')} "
        f"based on trader input, risk {risk}, and policy {mode}."
    )

    validation_plan = {
        "what_to_watch": [
            "Paper pipeline outcomes and guardrail mode stability after this interpretation.",
            "Whether market_context fields (if present) evolve consistently with the stated concern.",
        ],
        "success_signals": [
            "Later insights/trends show reduced misalignment or stable readiness when proposal was observational.",
            "Recorded reflections cite this proposal when explaining a cautious or no-change decision.",
        ],
        "failure_signals": [
            "Outcomes contradict the stated risk posture without documented reason.",
            "Repeated failures while policy remained unchanged despite RISK_REDUCTION proposal.",
        ],
    }
    if ptype == "RISK_REDUCTION":
        validation_plan["what_to_watch"].insert(0, "Elevated risk factors and FROZEN/CAUTION persistence in guardrail policy.")
    elif ptype == "CONDITION_TIGHTENING":
        validation_plan["what_to_watch"].insert(0, "Conditions that must improve before increasing paper exposure.")

    caution = list(anna.get("caution_flags") or [])
    caution.append("anna_proposal_v1 is not an order; compare later to paper outcomes and reflections.")

    notes = list(extra_notes)
    notes.append(
        "Prepared for later comparison to paper outcomes, reflections, insights, and trends — automated diff not implemented in this phase."
    )

    return {
        "kind": "anna_proposal_v1",
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "source_analysis_reference": {
            "task_id": source_task_id,
            "kind": "anna_analysis_v1",
        },
        "proposal_type": ptype,
        "proposal_summary": summary,
        "proposed_effect": {
            "paper_mode_intent": paper_intent,
            "guardrail_interaction": guardrail_interaction,
            "reasoning_scope": reasoning_scope,
        },
        "validation_plan": validation_plan,
        "supporting_reasoning": {
            "interpretation_summary": interp,
            "risk_level": risk,
            "policy_alignment": f"guardrail_mode={mode}, alignment={alignment}",
            "concepts_used": concepts,
        },
        "caution_flags": caution[:16],
        "notes": notes,
    }


def run_live_build(
    db_path: Path,
    input_text: str,
    *,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
) -> tuple[dict[str, Any], list[str]]:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)
    extra_notes: list[str] = []
    market, market_err = (None, None)
    ctx, ctx_err = (None, None)
    trend, trend_err = (None, None)
    policy, policy_err = (None, None)
    try:
        if use_snapshot:
            market, market_err = load_latest_market_snapshot(conn)
        if use_ctx:
            ctx, ctx_err = try_load_decision_context(conn)
        if use_trend:
            trend, trend_err = try_load_trend(conn)
        if use_policy:
            policy, policy_err = load_latest_guardrail_policy(conn)
    finally:
        conn.close()

    analysis = build_analysis(
        input_text,
        market=market,
        market_err=market_err,
        ctx=ctx,
        ctx_err=ctx_err,
        trend=trend,
        trend_err=trend_err,
        policy=policy,
        policy_err=policy_err,
        use_snapshot=use_snapshot,
        use_ctx=use_ctx,
        use_trend=use_trend,
        use_policy=use_policy,
    )
    if trend and not trend_err:
        analysis["notes"].append(
            f"System trend window_size={trend.get('window_size')} (loaded)."
        )
    extra_notes.extend(analysis.get("notes") or [])
    return analysis, extra_notes


def run(
    db_path: Path,
    *,
    input_text: str | None,
    use_stored: bool,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
    store: bool,
) -> int:
    root = repo_root()
    conn = connect(db_path)
    ensure_schema(conn, root)
    seed_agents(conn)

    source_task_id: str | None = None
    extra_notes: list[str] = []
    analysis: dict[str, Any]

    try:
        if use_stored:
            tid, anna, err = load_latest_stored_anna_analysis(conn)
            conn.close()
            conn = None  # type: ignore
            if err or not anna:
                print(json.dumps({"error": err or "missing analysis"}, indent=2), file=sys.stderr)
                return 3  # conn already closed and set None above
            source_task_id = tid
            analysis = anna
        else:
            if not input_text or not input_text.strip():
                conn.close()
                conn = None  # type: ignore
                print(json.dumps({"error": "input_text required unless --use-latest-stored-anna-analysis"}, indent=2), file=sys.stderr)
                return 2
            conn.close()
            conn = None  # type: ignore
            analysis, extra_notes = run_live_build(
                db_path,
                input_text.strip(),
                use_snapshot=use_snapshot,
                use_ctx=use_ctx,
                use_trend=use_trend,
                use_policy=use_policy,
            )
    finally:
        if conn:
            conn.close()

    proposal = build_anna_proposal(analysis, source_task_id=source_task_id, extra_notes=extra_notes)
    out: dict[str, Any] = {"anna_proposal": proposal, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = proposal["generated_at"]
        title = f"[Anna Proposal] {now[:19]}Z"
        desc = json.dumps({"anna_proposal": proposal}, ensure_ascii=False, indent=2)
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
        description="Phase 3.3 — Anna analysis → anna_proposal_v1 (validation bridge)",
    )
    p.add_argument(
        "input_text",
        nargs="*",
        default=[],
        help="Trader text for live Anna build (omit if --use-latest-stored-anna-analysis)",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-stored-anna-analysis",
        action="store_true",
        help="Use latest [Anna Analysis] task instead of live build",
    )
    p.add_argument("--use-latest-market-snapshot", action="store_true")
    p.add_argument("--use-latest-decision-context", action="store_true")
    p.add_argument("--use-latest-trend", action="store_true")
    p.add_argument("--use-latest-policy", action="store_true")
    p.add_argument("--store", action="store_true", help="Persist as [Anna Proposal] completed task")
    args = p.parse_args(argv)
    text = " ".join(args.input_text).strip() if args.input_text else ""
    db = args.db or default_sqlite_path()
    return run(
        db,
        input_text=text or None,
        use_stored=args.use_latest_stored_anna_analysis,
        use_snapshot=args.use_latest_market_snapshot,
        use_ctx=args.use_latest_decision_context,
        use_trend=args.use_latest_trend,
        use_policy=args.use_latest_policy,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
