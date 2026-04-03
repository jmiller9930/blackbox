"""Format dispatcher payloads: [Anna]/[DATA]/[Cody] labels, no JSON. Phase 4.6.2 multi-persona."""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from . import agent_identity

logger = logging.getLogger(__name__)

_TELEGRAM_SOFT_LIMIT = 3900

_CLOSINGS = (
    "Does that help?",
    "Want me to go deeper on any part?",
    "Do you want me to check current conditions next?",
)

# Directive 4.6.3.1 — Anna product header (first line must match persona enforcement regex)
ANNA_TELEGRAM_HEADER = "[Anna — Trading Analyst]"

_ROLE = {
    "Anna": "Role: Anna — trading analyst (markets, risk, concepts; advisory only).",
    "DATA": "Role: DATA — system operator; read-only SQLite + execution context on this host.",
    "Mia": "Role: Mia — reserved; silo not connected in this build yet.",
    "Cody": "Role: Cody — engineering guidance (no repo writes from chat).",
}


def _truncate(s: str) -> str:
    if len(s) <= _TELEGRAM_SOFT_LIMIT:
        return s
    return s[: _TELEGRAM_SOFT_LIMIT - 40] + "\n\n… (truncated)"


def _closing(seed: str) -> str:
    if not seed:
        seed = "default"
    return _CLOSINGS[hash(seed) % len(_CLOSINGS)]


def _prefix_anna(body: str) -> str:
    """Directive 4.6.3.1 — single professional header; no Role:/BotFather essay on Anna path."""
    return f"{ANNA_TELEGRAM_HEADER}\n\n{_truncate((body or '').strip())}"


def _prefix(agent: str, body: str) -> str:
    """
    Directive format: [Anna] / [DATA] / [Cody] plus Role line.
    Telegram always shows the bot’s BotFather display name (e.g. BB Trader) as the *sender* on the bubble;
    that is not the persona. The line below makes that explicit for humans reading the chat.
    """
    role = _ROLE.get(agent, "")
    block = f"[{agent}]"
    if role:
        block += f"\n{role}"
    block += (
        f"\nTelegram: the name at the top of this bubble is the bot account (e.g. BB Trader), "
        f"not the speaker. Who is speaking here: [{agent}]."
    )
    return f"{block}\n\n{_truncate(body)}"


def _fallback_anna_body(*, user_display_name: str | None) -> str:
    """Phase 4.6.3 — unlabeled or invalid output blocked; Anna fallback (directive text)."""
    name = (user_display_name or "").strip()
    if name:
        return f"{name}, I need to re-evaluate that — let me take a closer look."
    return "I need to re-evaluate that — let me take a closer look."


# Anna may use "[Anna — Trading Analyst]"; other personas stay "[DATA]" etc.
_PERSONA_FIRST_LINE = re.compile(r"^\[(Anna|DATA|Cody|Mia)(\s+—[^\]]*)?\]")


def _enforce_persona_tag(text: str | None, *, user_display_name: str | None) -> str:
    """
    Every Telegram user-visible string must start with [Anna], [DATA], [Cody], or [Mia] (Mia reserved).
    Primary silos: Anna / DATA / Cody. Otherwise replace with tagged Anna fallback — no unlabeled output.
    """
    s = (text or "").strip()
    if not s:
        logger.warning("persona enforcement: empty body; using Anna fallback")
        return _prefix_anna(_fallback_anna_body(user_display_name=user_display_name))
    first = s.split("\n", 1)[0].strip()
    if _PERSONA_FIRST_LINE.match(first):
        return s
    logger.warning("persona enforcement: missing or invalid tag on first line; using Anna fallback")
    return _prefix_anna(_fallback_anna_body(user_display_name=user_display_name))


def format_response(
    payload: dict[str, Any],
    *,
    user_display_name: str | None = None,
) -> str:
    kind = payload.get("kind")
    if kind == "error":
        msg = str(payload.get("message", "unknown"))
        body = f"I hit a snag on my side: {msg}"
        if user_display_name:
            body = f"{user_display_name}, {body}"
        out = _prefix_anna(body)
        return _enforce_persona_tag(out, user_display_name=user_display_name)
    if kind == "anna":
        out = _prefix_anna(_format_anna_body(payload.get("data") or {}, display_name=user_display_name))
        return _enforce_persona_tag(out, user_display_name=user_display_name)
    if kind == "cody":
        out = _prefix("Cody", _format_cody_body(payload))
        return _enforce_persona_tag(out, user_display_name=user_display_name)
    if kind == "identity":
        out = _prefix_anna(_format_identity_body(str(payload.get("intent") or "help"), display_name=user_display_name))
        return _enforce_persona_tag(out, user_display_name=user_display_name)
    if kind == "data":
        out = _prefix(
            "DATA",
            _format_data_body(payload, display_name=user_display_name),
        )
        return _enforce_persona_tag(out, user_display_name=user_display_name)
    if kind == "mia":
        out = _prefix(
            "Mia",
            _format_mia_body(str(payload.get("user_text") or ""), display_name=user_display_name),
        )
        return _enforce_persona_tag(out, user_display_name=user_display_name)
    logger.warning("persona enforcement: unknown or missing kind %r", kind)
    out = _prefix_anna(_fallback_anna_body(user_display_name=user_display_name))
    return _enforce_persona_tag(out, user_display_name=user_display_name)


def format_anna_system_message(body: str, *, user_display_name: str | None = None) -> str:
    """
    Hard path for Telegram copy that does not go through dispatch (e.g. /start, unauthorized).
    Still wrapped as [Anna] + enforcement — never send raw strings to Telegram.
    """
    out = _prefix_anna((body or "").strip() or _fallback_anna_body(user_display_name=user_display_name))
    return _enforce_persona_tag(out, user_display_name=user_display_name)


def _format_mia_body(user_text: str, *, display_name: str | None = None) -> str:
    """Placeholder until the Mia silo is wired; still shows [Mia] and addresses the user by name."""
    greet = f"Hi {display_name}, " if display_name else ""
    ut = (user_text or "").strip()
    if not ut:
        q = "(no text after @mia — when Mia is online, put your question here.)"
    else:
        q = ut[:600] + ("…" if len(ut) > 600 else "")
    parts = [
        "Summary",
        f"{greet}I'm not live in this build yet. Your note is recorded for when we connect my silo.",
        "",
        "Your message",
        q,
        "",
        "Guidance",
        "For now: @anna (trading / concepts / registry planning), @data (telemetry / infra), @cody (engineering).",
        "",
        _closing("mia" + ut[:40]),
    ]
    return _truncate("\n".join(parts))


def _format_identity_body(intent: str, *, display_name: str | None = None) -> str:
    if intent == "who":
        body = "\n".join(agent_identity.who_lines())
    elif intent == "capabilities":
        body = "\n".join(agent_identity.capabilities_lines())
    elif intent == "how":
        body = "\n".join(agent_identity.how_lines())
    else:
        body = "\n".join(agent_identity.identity_lines())

    if display_name:
        body = f"Hi {display_name},\n\n{body}"

    guide = (
        "Explicit mentions: @anna (trading / concepts), @data (system / DB / infra), "
        "@mia (reserved), @cody (engineering). Personas do not consult each other in chat yet — that comes with later hardening."
    )
    return _truncate(
        f"{body}\n\n{guide}\n\n{_closing('identity:' + intent)}"
    )


def _format_cody_body(payload: dict[str, Any]) -> str:
    return _truncate(str(payload.get("reply") or ""))


def _anna_telegram_verbose() -> bool:
    """Set ANNA_TELEGRAM_VERBOSE=1 to include Risk read / How I'd play it blocks (debug-style)."""
    return os.environ.get("ANNA_TELEGRAM_VERBOSE", "") == "1"


def _sanitize_anna_lead(gist: str, headline: str) -> str:
    """Strip legacy / internal template phrasing; user-facing text is the analyst answer only."""
    g = (gist or "").strip()
    low = g.lower()
    bad = (
        "interpreted trader concern",
        "guardrail posture",
        "structured under",
        "anna_analysis",
        "without tight keyword",
    )
    if any(b in low for b in bad):
        return (headline or "").strip()
    return g


def _telegram_safe_suggested_rationale(text: str) -> str:
    """Do not surface policy/debug lines as the main 'answer' in Telegram."""
    s = (text or "").strip()
    if not s:
        return ""
    low = s.lower()
    if any(
        x in low
        for x in (
            "guardrail mode unknown",
            "guardrail mode",
            "anna_analysis",
            "registry snapshot",
            "paper-only — still no live",
        )
    ):
        return ""
    return s


def _telegram_safe_anna_notes(notes: list[Any]) -> list[str]:
    """Directive 4.6.3 — do not leak guardrail/registry/debug strings to Telegram."""
    out: list[str] = []
    for n in notes:
        s = str(n).strip()
        if not s:
            continue
        low = s.lower()
        if any(
            m in low
            for m in (
                "guardrail",
                "registry",
                "debug",
                "anna_analysis",
                "concept_support",
                "telemetry",
                "execution plane",
                "anna_analysis",
            )
        ):
            continue
        out.append(s)
    return out


def _format_data_body(payload: dict[str, Any], *, display_name: str | None = None) -> str:
    mode = payload.get("data_mode")
    if mode == "report":
        return _format_report_body(payload, display_name=display_name)
    if mode == "insights":
        return _format_insights_body(payload.get("rows") or [], display_name=display_name)
    if mode == "status":
        st = str(payload.get("status_text") or "")
        lead = "System / execution context snapshot (telemetry, read-only)."
        if display_name:
            lead = f"{display_name}, {lead}"
        parts = [
            "State",
            lead,
            "",
            "Facts",
            st,
            "",
            "Next check",
            "Compare with clawbot verification when closing phases. Say insights for recent feedback rows.",
            "",
            _closing("status"),
        ]
        return _truncate("\n".join(parts))
    if mode == "hashtag_composed":
        st = str(payload.get("status_text") or "")
        lead = (
            "Composable operator hashtags (pure #tokens only). "
            "Example: #status #system = full stack; #status #context_engine = slice only."
        )
        if display_name:
            lead = f"{display_name}, {lead}"
        parts = [
            "State",
            lead,
            "",
            "Facts",
            st,
            "",
            "Next check",
            "Say #ops_help for the tag index. Chat output is read-only unless a future gated op is enabled.",
            "",
            _closing("hashtag-composed"),
        ]
        return _truncate("\n".join(parts))
    if mode == "infra":
        infra = str(payload.get("infra_text") or "")
        st = str(payload.get("status_text") or "")
        lead = (
            "DATA is answering from live workspace telemetry (Telegram may still show the bot name "
            "e.g. BB Trader — that is display only; the speaking persona here is DATA)."
        )
        if display_name:
            lead = f"{display_name}, {lead}"
        parts = [
            "State",
            lead,
            "",
            "Facts",
            st,
            "",
            "Infrastructure snapshot",
            infra,
            "",
            "Next check",
            "For trading or market questions: @anna or plain text (defaults to Anna).",
            "",
            _closing("infra"),
        ]
        return _truncate("\n".join(parts))
    if mode == "general":
        ut = str(payload.get("user_text") or "")
        sum0 = "DATA routes execution feedback and phase context — not trading advice."
        if display_name:
            sum0 = f"{display_name}, {sum0}"
        parts = [
            "State",
            sum0,
            "",
            "Facts",
            f"Your message: {ut[:600]}{'…' if len(ut) > 600 else ''}",
            "",
            "Next check",
            "Try: status (phase + host), report (aggregates), insights (row list). @anna for analyst questions.",
            "",
            _closing("data-general" + ut[:40]),
        ]
        return _truncate("\n".join(parts))
    return _truncate("State\nNo DATA mode specified.")


def _anna_model_limitation_note(aa: dict[str, Any]) -> str:
    """Directive 4.6.3.1 — explicit limitation when model path failed but rules/memory answered."""
    pipe = aa.get("pipeline") or {}
    meta = pipe.get("layer_meta") or {}
    err = meta.get("llm_error")
    if not err:
        return ""
    return (
        f"\n\n(Note: the analyst model didn’t produce usable output for this turn — {err}. "
        "What you see above is from rules or prior context.)"
    )


def _execution_handoff_footer(data: dict[str, Any]) -> str:
    eh = data.get("execution_handoff") or {}
    rid = eh.get("request_id")
    if not rid:
        return ""
    return (
        "\n\n— Execution handoff: request "
        f"{rid} pending approval → Jack (Jupiter) after approve + run_execution."
    )


def _format_anna_body(data: dict[str, Any], *, display_name: str | None = None) -> str:
    aa = data.get("anna_analysis") or {}
    interp = aa.get("interpretation") or {}
    pipe = aa.get("pipeline") or {}
    layer_meta = pipe.get("layer_meta") or {}
    if bool(layer_meta.get("live_data_fallback_exact")):
        # Directive 4.6.3.5.A requires this fallback sentence verbatim.
        return _truncate(str(interp.get("summary") or ""))

    headline = str(interp.get("headline") or "Analysis")
    gist = _sanitize_anna_lead(str(interp.get("summary") or ""), headline)
    signals = interp.get("signals") or []
    hi = aa.get("human_intent") or {}
    factual_dt = hi.get("bypass") == "datetime" or (
        isinstance(signals, list) and "intent:factual_datetime" in signals
    )

    def _lead_line() -> str:
        lead = gist if gist else headline
        if display_name:
            return f"{display_name}, {lead}"
        return lead

    if factual_dt:
        return _truncate(_lead_line())

    if pipe.get("answer_source") == "clarification_requested" or (
        isinstance(signals, list) and "pipeline:clarification_required" in signals
    ):
        # Context stop — body is the clarifying question only (4.6.3.1)
        return _truncate(_lead_line())

    # Default 4.6.3.1: interpretation.summary is the product; no generic tails or rotating closings.
    if not _anna_telegram_verbose():
        text = _lead_line()
        if (
            gist
            and headline
            and headline.strip().lower() not in (gist or "").lower()
            and headline.strip().lower() not in ("analysis", "your question", "need a bit more context")
        ):
            hl = headline.strip()
            text = f"{text}\n\n{hl}"
        text += _anna_model_limitation_note(aa)
        text += _execution_handoff_footer(data)
        return _truncate(text)

    # Debug-style: extra sections only when verbose — still avoid WATCH / "low risk" / empty posture.
    ra = aa.get("risk_assessment") or {}
    risk = str(ra.get("level") or "?").strip().lower()
    factors = ra.get("factors") or []
    factor_txt = ""
    if isinstance(factors, list) and factors:
        factor_txt = "; ".join(str(f) for f in factors[:4])

    suggested = aa.get("suggested_action") or {}
    action = str(suggested.get("intent") or "").strip().upper()
    intent_expl = _telegram_safe_suggested_rationale(str(suggested.get("rationale") or ""))

    lead = _lead_line()
    parts: list[str] = [lead]
    if gist and headline and headline.lower() not in lead.lower():
        hl = headline.strip().lower()
        if hl not in ("analysis", "anna analysis", "your question"):
            parts.append("")
            parts.append(headline)

    if factor_txt and risk != "low":
        parts.extend(["", "Risk factors", factor_txt])
    elif factor_txt and risk == "low":
        parts.extend(["", "Context", factor_txt])

    if action and action != "WATCH":
        parts.append("")
        parts.append("Posture (advisory)")
        parts.append(f"{action}.")
        if intent_expl:
            parts.append(intent_expl)
    elif intent_expl:
        parts.append("")
        parts.append("Context")
        parts.append(intent_expl)

    notes = _telegram_safe_anna_notes(list(aa.get("notes") or []))
    if notes:
        parts.append("")
        parts.append("Worth noting: " + "; ".join(str(n) for n in notes[:2]))

    lim = _anna_model_limitation_note(aa).strip()
    if lim:
        parts.append(lim)
    body = "\n".join(p for p in parts if p)
    body += _execution_handoff_footer(data)
    return _truncate(body)


def _format_report_body(payload: dict[str, Any], *, display_name: str | None = None) -> str:
    summ = payload.get("summary") or {}
    body = str(payload.get("report_text") or "")
    total = int(summ.get("total") or 0)
    ok = int(summ.get("success") or 0)
    bad = int(summ.get("failure") or 0)

    sum0 = f"Execution feedback records: {total} total ({ok} succeeded, {bad} did not)."
    if display_name:
        sum0 = f"{display_name}, {sum0}"
    parts = [
        "State",
        sum0,
        "",
        "Facts",
        body,
        "",
        "Next check",
        "Use insights for row detail; @anna for interpretation of failures.",
        "",
        _closing("report" + str(total)),
    ]
    return _truncate("\n".join(parts))


def _format_insights_body(
    rows: list[dict[str, Any]],
    *,
    display_name: str | None = None,
) -> str:
    if not rows:
        return _truncate(
            "State\nNo execution insights in the database yet.\n\n"
            "Next check\nRun execution plane checks from the backend, then retry.\n\n"
            + _closing("insights-empty")
        )

    sum0 = f"Up to {min(15, len(rows))} recent insight rows (newest first)."
    if display_name:
        sum0 = f"{display_name}, {sum0}"
    lines: list[str] = [
        "State",
        sum0,
        "",
        "Facts",
    ]
    for i, row in enumerate(rows[:15], 1):
        ins = row.get("insight") or {}
        kind = str(ins.get("insight_kind", "?"))
        rid = str(ins.get("linked_request_id", "?"))
        ts = str(row.get("created_at", ""))
        short = rid[:8] if len(rid) > 8 else rid
        lines.append(f"{i}. {kind} — request {short}… @ {ts}")

    if len(rows) > 15:
        lines.append(f"… and {len(rows) - 15} more (say report for summary).")

    lines.extend(
        [
            "",
            "Next check",
            "Compare counts with report; ask @anna to reason about patterns.",
            "",
            _closing("insights" + str(len(rows))),
        ]
    )
    return _truncate("\n".join(lines))
