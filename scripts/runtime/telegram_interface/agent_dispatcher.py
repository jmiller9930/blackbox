"""Dispatch routed messages to Anna, DATA, or Cody.

Anna: full analysis may create a **pending** ``execution_request_v1`` (Anna-sourced ``anna_proposal_v1``)
for strategy signals so the Jack path is wired; does not approve, run execution, or call Jack.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from _paths import default_sqlite_path
from anna_analyst_v1 import analyze_to_dict
from modules.anna_training.readiness import (
    build_anna_analysis_preflight_blocked,
    ensure_anna_data_preflight,
)
from learning_visibility.insight_query import fetch_insights
from learning_visibility.insight_summary import summarize_insights
from learning_visibility.report_generator import generate_report

from .cody_stub import cody_reply
from .data_status import (
    build_infra_snapshot,
    build_status_text,
    compose_operator_hashtag_message,
)
from .message_router import RoutedMessage

logger = logging.getLogger(__name__)
LIVE_DATA_FALLBACK = "I don’t have access to live market data for that request right now."


def telegram_anna_use_llm() -> bool:
    """
    Telegram → Anna must use the local LLM (Ollama) pipeline when enabled (Directive 4.6.3.x).

    Resolution order: ANNA_TELEGRAM_USE_LLM (Telegram-only override), then ANNA_USE_LLM, then default **on**.
    Tests set ANNA_USE_LLM=0 in conftest so CI does not call Ollama.
    """
    for key in ("ANNA_TELEGRAM_USE_LLM", "ANNA_USE_LLM"):
        v = os.environ.get(key)
        if v is not None and str(v).strip() != "":
            return str(v).strip().lower() not in ("0", "false", "no")
    return True


def dispatch(routed: RoutedMessage, *, display_name: str | None = None) -> dict[str, Any]:
    """
    Returns a dict with \"kind\" and payload for response_formatter.
    Does not call run_execution or Jack; may create a pending execution request (see execution_plane).
    """
    db = default_sqlite_path()

    if routed.agent == "anna":
        pf0 = ensure_anna_data_preflight()
        if not pf0["ok"]:
            return {
                "kind": "anna",
                "data": {
                    "anna_analysis": build_anna_analysis_preflight_blocked(routed.text or "", pf0),
                    "stored_task_id": None,
                    "preflight": pf0,
                },
            }

        from data_clients.market_data import get_price, get_spread
        from messaging_interface.live_data import extract_symbol, requires_live_data, wants_spread

        if requires_live_data(routed.text):
            symbol = extract_symbol(routed.text)
            is_spread = wants_spread(routed.text)
            data = get_spread(symbol) if is_spread else get_price(symbol)
            logger.info(
                "anna_live_data_v1 detected=%s mode=%s symbol=%s source=%s ok=%s",
                True,
                "spread" if is_spread else "price",
                symbol,
                data.get("source"),
                data.get("ok"),
            )
            if bool(data.get("ok")):
                sym = str(data.get("symbol") or symbol).upper()
                source = str(data.get("source") or "unknown")
                as_of = str(data.get("as_of") or "")
                if is_spread:
                    summary = (
                        f"{sym} spread is {float(data.get('spread') or 0.0):.6f} "
                        f"(bid {float(data.get('bid') or 0.0):.6f}, ask {float(data.get('ask') or 0.0):.6f}). "
                        f"Source: {source}. As of: {as_of}."
                    )
                else:
                    summary = (
                        f"{sym} is trading around {float(data.get('price') or 0.0):.6f} "
                        f"(bid {float(data.get('bid') or 0.0):.6f}, ask {float(data.get('ask') or 0.0):.6f}). "
                        f"Source: {source}. As of: {as_of}."
                    )
                return {
                    "kind": "anna",
                    "data": {
                        "anna_analysis": {
                            "interpretation": {
                                "headline": "Live market data",
                                "summary": summary,
                                "signals": ["intent:live_market_data"],
                            },
                            "human_intent": {"intent": "market_data", "topic": "price_spread"},
                            "pipeline": {
                                "answer_source": "live_market_data",
                                "layer_meta": {
                                    "live_data": True,
                                    "live_data_source": source,
                                    "live_data_symbol": sym,
                                },
                            },
                            "notes": [],
                        },
                        "stored_task_id": None,
                    },
                }
            note = str(data.get("note") or "source unavailable")
            return {
                "kind": "anna",
                "data": {
                    "anna_analysis": {
                        "interpretation": {
                            "headline": "Live data unavailable",
                            "summary": LIVE_DATA_FALLBACK,
                            "signals": ["pipeline:explicit_limitation", "intent:live_market_data"],
                        },
                        "human_intent": {"intent": "market_data", "topic": "price_spread"},
                        "pipeline": {
                            "answer_source": "live_market_data_unavailable",
                            "layer_meta": {
                                "live_data": True,
                                "live_data_fallback_exact": True,
                                "live_data_reason": note,
                                "live_data_source": str(data.get("source") or "unknown"),
                            },
                        },
                        "notes": [f"Live data unavailable: {note}"],
                    },
                    "stored_task_id": None,
                },
            }

        out = analyze_to_dict(
            db,
            routed.text,
            use_snapshot=False,
            use_ctx=False,
            use_trend=False,
            use_policy=False,
            store=False,
            use_llm=telegram_anna_use_llm(),
            skip_preflight=True,
        )
        if not out.get("preflight"):
            from execution_plane.anna_signal_execution import (
                maybe_trader_mode_auto_execute,
                try_create_execution_request_from_anna_analysis,
            )

            analysis = out.get("anna_analysis") or {}
            handoff = try_create_execution_request_from_anna_analysis(
                analysis,
                source_task_id=out.get("stored_task_id"),
            )
            if handoff:
                out = {**out, "execution_handoff": handoff}
                tm = maybe_trader_mode_auto_execute(str(handoff["request_id"]))
                if tm:
                    out = {**out, "trader_mode_execution": tm}
        return {"kind": "anna", "data": out}

    if routed.agent == "cody":
        return {
            "kind": "cody",
            "user_text": routed.text,
            "reply": cody_reply(routed.text, display_name=display_name),
        }

    if routed.agent == "mia":
        return {
            "kind": "mia",
            "user_text": routed.text,
        }

    if routed.agent == "identity":
        intent = (routed.text or "help").strip().lower()
        if intent not in ("help", "who", "capabilities", "how"):
            intent = "help"
        return {"kind": "identity", "intent": intent}

    if routed.agent == "data":
        mode = routed.data_mode
        if mode == "report":
            rows = fetch_insights(limit=None)
            summary = summarize_insights(rows)
            report_text = generate_report(summary)
            return {
                "kind": "data",
                "data_mode": "report",
                "summary": summary,
                "report_text": report_text,
            }
        if mode == "insights":
            rows = fetch_insights(limit=30)
            return {"kind": "data", "data_mode": "insights", "rows": rows}
        if mode == "status":
            return {
                "kind": "data",
                "data_mode": "status",
                "status_text": build_status_text(),
            }
        if mode == "hashtag_composed":
            tok = routed.hashtag_tokens or ()
            return {
                "kind": "data",
                "data_mode": "hashtag_composed",
                "status_text": compose_operator_hashtag_message(tok),
            }
        if mode == "infra":
            return {
                "kind": "data",
                "data_mode": "infra",
                "infra_text": build_infra_snapshot(),
                "status_text": build_status_text(),
            }
        # general @data question
        return {
            "kind": "data",
            "data_mode": "general",
            "user_text": routed.text,
        }

    return {"kind": "error", "message": "unknown route"}
