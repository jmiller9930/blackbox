"""
Directive 4.6.3.4 — optional diagnostic bundle for Slack closure / architect proof.

Enable with env SLACK_ARCHITECT_DIAGNOSTICS=1 (also: true, yes, on).

Emits one JSON object per line to stderr so stdout stays the channel payload for OpenClaw.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

_ENV = "SLACK_ARCHITECT_DIAGNOSTICS"


def diagnostics_enabled() -> bool:
    v = (os.environ.get(_ENV) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def emit_slack_architect_block(
    *,
    layer: str,
    user_text: str | None = None,
    routing_decision: str | None = None,
    anna_entry_py_ran: bool | None = None,
    anna_entry_note: str | None = None,
    raw_before_enforcement: str | None = None,
    enforcement_rules_fired: list[str] | None = None,
    final_slack_text: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a single JSON line to stderr when diagnostics are enabled."""
    if not diagnostics_enabled():
        return
    row: dict[str, Any] = {
        "slack_architect_diagnostics": True,
        "layer": layer,
        "user_text": user_text,
        "routing_decision": routing_decision,
        "anna_entry_py_ran": anna_entry_py_ran,
        "anna_entry_note": anna_entry_note,
        "raw_before_enforcement": raw_before_enforcement,
        "enforcement_rules_fired": list(enforcement_rules_fired or []),
        "final_slack_text": final_slack_text,
    }
    if extra:
        row["extra"] = extra
    print(json.dumps(row, ensure_ascii=False), file=sys.stderr, flush=True)
