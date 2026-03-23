#!/usr/bin/env python3
"""
Phase 3.2 — Anna conversational analyst v1: trader text → structured anna_analysis_v1.

Rule-based only; no ML, no Telegram, no registry loader, no execution, no venue calls.
Optional loads from existing tasks: market snapshot, decision context, system trend, guardrail policy.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import connect, ensure_schema, seed_agents
from _paths import default_sqlite_path, repo_root
from analyst_decision_engine import load_latest_stored_decision_context
from guardrail_policy_evaluator import load_latest_stored_system_trend

SCHEMA_VERSION = 1

# Keyword → concept id (strings for concepts_used; registry wiring later)
CONCEPT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("liquidity", re.compile(r"\b(liquidity|thin\s+liquidity|market\s+depth|depth|order\s+book)\b", re.I)),
    ("spread", re.compile(r"\b(spread|spreads|bid[- ]ask|widening|wide\s+spread)\b", re.I)),
    ("slippage", re.compile(r"\b(slippage|slip)\b", re.I)),
    ("volatility", re.compile(r"\b(volatility|volatile|chop|choppy|swing)\b", re.I)),
    ("risk", re.compile(r"\b(risk|risky|danger|careful|caution)\b", re.I)),
    ("trend", re.compile(r"\b(trend|trending|momentum|breakout)\b", re.I)),
    ("volume", re.compile(r"\b(volume|liquidity\s+crunch)\b", re.I)),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _try_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def load_latest_market_snapshot(conn) -> tuple[dict[str, Any] | None, str | None]:
    row = conn.execute(
        """
        SELECT id, description FROM tasks
        WHERE title LIKE '[Market Snapshot]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[1]:
        return None, "No [Market Snapshot] task found in database."
    try:
        data = json.loads(row[1])
    except json.JSONDecodeError:
        return None, "Latest [Market Snapshot] row is not valid JSON."
    if data.get("kind") != "market_snapshot_v1":
        return None, "Latest market task is not market_snapshot_v1."
    return data, None


def load_latest_guardrail_policy(conn) -> tuple[dict[str, Any] | None, str | None]:
    row = conn.execute(
        """
        SELECT description FROM tasks
        WHERE title LIKE '[Guardrail Policy]%'
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row or not row[0]:
        return None, "No [Guardrail Policy] task found."
    try:
        data = json.loads(row[0])
    except json.JSONDecodeError:
        return None, "Latest [Guardrail Policy] row is not valid JSON."
    if data.get("kind") != "guardrail_policy_v1":
        return None, "Latest policy task is not guardrail_policy_v1."
    return data, None


def try_load_decision_context(conn) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_latest_stored_decision_context(conn), None
    except (LookupError, ValueError, json.JSONDecodeError):
        return None, "No valid [Decision Context] with decision_context_v1."


def try_load_trend(conn) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_latest_stored_system_trend(conn), None
    except (LookupError, ValueError, json.JSONDecodeError):
        return None, "No valid [System Trend] with system_trend_v1."


def extract_concepts(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid, pat in CONCEPT_PATTERNS:
        if pat.search(text) and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def _readiness_from_context(ctx: dict | None) -> str | None:
    if not ctx:
        return None
    r = ctx.get("system_readiness")
    if r in ("healthy", "degraded", "unstable"):
        return r
    return None


def build_analysis(
    input_text: str,
    *,
    market: dict[str, Any] | None,
    market_err: str | None,
    ctx: dict[str, Any] | None,
    ctx_err: str | None,
    trend: dict[str, Any] | None,
    trend_err: str | None,
    policy: dict[str, Any] | None,
    policy_err: str | None,
    use_snapshot: bool,
    use_ctx: bool,
    use_trend: bool,
    use_policy: bool,
) -> dict[str, Any]:
    notes: list[str] = []
    if use_snapshot and market_err:
        notes.append(market_err)
    if use_ctx and ctx_err:
        notes.append(ctx_err)
    if use_trend and trend_err:
        notes.append(trend_err)
    if use_policy and policy_err:
        notes.append(policy_err)

    concepts = extract_concepts(input_text)

    price = _read_float(market, "price") if market else None
    spread = _read_float(market, "spread") if market else None
    m_notes: list[str] = []
    if market and market.get("source") == "unavailable":
        m_notes.append("Market snapshot source was unavailable when recorded; no fabricated prices.")
    if not use_snapshot:
        m_notes.append("Market snapshot not requested; price/spread may be null.")
    elif market_err or not market:
        m_notes.append("No market snapshot data applied.")
    if price is not None and spread is not None and price > 0:
        bps = (spread / price) * 10000.0
        m_notes.append(f"Snapshot mid context: spread ≈ {bps:.2f} bps of price (informational).")

    guard_mode_raw = policy.get("mode") if policy else None
    if guard_mode_raw in ("FROZEN", "CAUTION", "NORMAL"):
        guardrail_mode = guard_mode_raw
    else:
        guardrail_mode = "unknown"

    readiness = _readiness_from_context(ctx)

    # Risk
    factors: list[str] = []
    neg = re.search(r"\b(thin|crash|panic|liquidat|unsafe|avoid|stop\s*hunt)\b", input_text, re.I)
    if neg:
        factors.append("Language suggests stress or adverse conditions.")
    if guardrail_mode == "FROZEN":
        factors.append("Guardrail policy mode is FROZEN.")
    elif guardrail_mode == "CAUTION":
        factors.append("Guardrail policy mode is CAUTION.")
    if readiness == "unstable":
        factors.append("Decision context reports unstable system readiness.")
    elif readiness == "degraded":
        factors.append("Decision context reports degraded readiness.")
    if trend and isinstance(trend.get("flags"), list) and trend["flags"]:
        factors.append(f"System trend flags present: {len(trend['flags'])} flag(s).")
    if price is not None and spread is not None and price > 0 and (spread / price) > 0.005:
        factors.append("Observed spread is large relative to price (rough check).")

    if not factors:
        factors.append("No strong risk amplifiers detected from text and available context.")

    risk_level = "low"
    if guardrail_mode == "FROZEN" or readiness == "unstable":
        risk_level = "high"
    elif guardrail_mode == "CAUTION" or readiness == "degraded" or neg or (
        trend and trend.get("flags")
    ):
        risk_level = "medium"
    if risk_level != "high" and concepts and "risk" in concepts:
        risk_level = "medium"

    # Suggested action (paper-only intent)
    intent = "WATCH"
    conf = "medium"
    rationale = "Default cautious stance without full policy/market context."

    if guardrail_mode == "FROZEN":
        intent, conf = "HOLD", "low"
        rationale = "Policy mode FROZEN: stand down from new risk; paper rehearsal only if explicitly gated elsewhere."
    elif guardrail_mode == "CAUTION":
        intent, conf = "WATCH", "medium"
        rationale = "Policy mode CAUTION: monitor and size conservatively; no execution implied."
    elif guardrail_mode == "NORMAL":
        if neg or risk_level == "high":
            intent, conf = "WATCH", "medium"
            rationale = "NORMAL policy but language or signals warrant monitoring before any paper rehearsal."
        else:
            intent, conf = "PAPER_TRADE_READY", "low"
            rationale = (
                "Policy mode NORMAL and no strong caution signals in text/context; "
                "paper path only — still no live execution."
            )
    else:
        intent, conf = "WATCH", "low"
        rationale = "Guardrail mode unknown or missing; avoid aggressive posture."

    # Policy alignment vs intent
    alignment = "unknown"
    if guardrail_mode == "unknown":
        alignment = "unknown"
    elif guardrail_mode == "FROZEN":
        alignment = "aligned" if intent == "HOLD" else "misaligned"
    elif guardrail_mode == "CAUTION":
        alignment = "aligned" if intent in ("HOLD", "WATCH") else "cautious"
    elif guardrail_mode == "NORMAL":
        if intent == "PAPER_TRADE_READY" and neg:
            alignment = "cautious"
        elif intent == "PAPER_TRADE_READY":
            alignment = "aligned"
        else:
            alignment = "aligned"

    pol_notes: list[str] = []
    if policy:
        pol_notes.append(f"Policy reasoning (excerpt): {(policy.get('reasoning') or '')[:280]}")
    else:
        pol_notes.append("No guardrail policy document loaded.")

    signals = [f"concept:{c}" for c in concepts]
    if not signals:
        signals.append("no strong keyword match; interpret manually")

    assumptions = [
        "Rule-based v1 analyst — not predictive; does not call markets or execute.",
        "Concept tags are keyword-derived; not registry-backed in v1.",
    ]
    if readiness:
        assumptions.append(f"Decision context readiness (if loaded): {readiness}.")

    summary = (
        f"Interpreted trader concern as focusing on: {', '.join(concepts) or 'general market commentary'}. "
        f"Structured under current guardrail posture ({guardrail_mode})."
    )

    return {
        "kind": "anna_analysis_v1",
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "input_text": input_text,
        "interpretation": {
            "summary": summary,
            "signals": signals,
            "assumptions": assumptions,
        },
        "market_context": {
            "price": price,
            "spread": spread,
            "notes": m_notes,
        },
        "risk_assessment": {
            "level": risk_level,
            "factors": factors[:12],
        },
        "policy_alignment": {
            "guardrail_mode": guardrail_mode,
            "alignment": alignment,
            "notes": pol_notes,
        },
        "suggested_action": {
            "intent": intent,
            "confidence": conf,
            "rationale": rationale,
        },
        "concepts_used": concepts,
        "caution_flags": [
            "anna_analysis_v1 is advisory only; no execution.",
            "Do not treat keyword concepts as validated registry entries.",
        ],
        "notes": notes,
    }


def _read_float(blob: dict[str, Any], key: str) -> float | None:
    return _try_float(blob.get(key))


def run(
    db_path: Path,
    input_text: str,
    *,
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

    # Trend informs notes only if loaded (risk already uses flags)
    if trend and not trend_err:
        analysis["notes"].append(
            f"System trend window_size={trend.get('window_size')} (loaded)."
        )

    out: dict[str, Any] = {"anna_analysis": analysis, "stored_task_id": None}

    if store:
        conn = connect(db_path)
        ensure_schema(conn, root)
        seed_agents(conn)
        tid = str(uuid.uuid4())
        now = analysis["generated_at"]
        title = f"[Anna Analysis] {now[:19]}Z"
        desc = json.dumps({"anna_analysis": analysis}, ensure_ascii=False, indent=2)
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
        description="Phase 3.2 — Anna analyst v1 (structured, rule-based, no execution)",
    )
    p.add_argument(
        "input_text",
        nargs="+",
        help="Trader-language input (quote multiple words as one shell argument or separate words)",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--use-latest-market-snapshot",
        action="store_true",
        help="Load latest [Market Snapshot] task (market_snapshot_v1)",
    )
    p.add_argument(
        "--use-latest-decision-context",
        action="store_true",
        help="Load latest [Decision Context] task (decision_context_v1)",
    )
    p.add_argument(
        "--use-latest-trend",
        action="store_true",
        help="Load latest [System Trend] task (system_trend_v1)",
    )
    p.add_argument(
        "--use-latest-policy",
        action="store_true",
        help="Load latest [Guardrail Policy] task (guardrail_policy_v1)",
    )
    p.add_argument("--store", action="store_true", help="Persist anna_analysis as [Anna Analysis] task")
    args = p.parse_args(argv)
    text = " ".join(args.input_text).strip()
    if not text:
        print(json.dumps({"error": "empty input_text"}, indent=2), file=sys.stderr)
        return 2
    db = args.db or default_sqlite_path()
    return run(
        db,
        text,
        use_snapshot=args.use_latest_market_snapshot,
        use_ctx=args.use_latest_decision_context,
        use_trend=args.use_latest_trend,
        use_policy=args.use_latest_policy,
        store=args.store,
    )


if __name__ == "__main__":
    raise SystemExit(main())
