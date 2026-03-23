"""Dispatch routed messages to Anna, DATA, or Cody (no execution plane)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _paths import default_sqlite_path
from anna_analyst_v1 import analyze_to_dict
from learning_visibility.insight_query import fetch_insights
from learning_visibility.insight_summary import summarize_insights
from learning_visibility.report_generator import generate_report

from .cody_stub import cody_reply
from .data_status import build_infra_snapshot, build_status_text
from .message_router import RoutedMessage


def dispatch(routed: RoutedMessage, *, display_name: str | None = None) -> dict[str, Any]:
    """
    Returns a dict with \"kind\" and payload for response_formatter.
    Does not call run_execution, approval, or kill switch.
    """
    db = default_sqlite_path()

    if routed.agent == "anna":
        out = analyze_to_dict(
            db,
            routed.text,
            use_snapshot=False,
            use_ctx=False,
            use_trend=False,
            use_policy=False,
            store=False,
        )
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
