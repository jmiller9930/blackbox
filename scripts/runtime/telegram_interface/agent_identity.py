"""
Anna identity copy for Telegram (Phase 4.6.1). Advisory-only; matches implemented analyst behavior.
"""
from __future__ import annotations

ANNA_NAME = "Anna"
ANNA_ROLE = "Trading Analyst"

# Capabilities align with anna_analysis_v1 (interpretation, risk, concepts, no execution).
ANNA_CAPABILITIES = [
    "market interpretation in trader language",
    "risk assessment and suggested posture (advisory)",
    "structured reasoning with concept context from the registry (read-only)",
    "strategy-awareness hints (keyword-based, advisory only)",
]

EXAMPLE_PROMPTS = [
    "@anna What is liquidity risk?",
    "@data status",
    "@mia (reserved until online)",
    "infra",
    "report",
    "@cody what can you improve?",
]


def identity_lines() -> list[str]:
    lines = [
        f"I'm {ANNA_NAME}, your {ANNA_ROLE} in this workspace.",
        "",
        "What I can do",
    ]
    for c in ANNA_CAPABILITIES:
        lines.append(f"• {c}")
    lines.extend(
        [
            "",
            "Example prompts",
        ]
    )
    for ex in EXAMPLE_PROMPTS:
        lines.append(f"• {ex}")
    return lines


def who_lines() -> list[str]:
    return [
        f"I'm {ANNA_NAME} — a {ANNA_ROLE} for BLACK BOX.",
        "I turn your questions into structured, read-only analysis (risk, interpretation, suggestions).",
        "I do not execute trades or move money; execution stays in the secured backend.",
    ]


def capabilities_lines() -> list[str]:
    lines = ["Here's what I can help with:", ""]
    for c in ANNA_CAPABILITIES:
        lines.append(f"• {c}")
    lines.extend(
        [
            "",
            "Try @anna, @data, @mia (placeholder), @cody — each silo is separate; no agent-to-agent chat yet.",
        ]
    )
    return lines


def how_lines() -> list[str]:
    return [
        "How to use this chat",
        "• @anna <question> — analyst (or plain text defaults to Anna).",
        "• @data status | report | insights | infra — execution feedback and read-only DB snapshot on this host.",
        "• @mia <question> — reserved; placeholder until her silo is online.",
        "• @cody <question> — engineering guidance (read-only stub).",
        "• Same without @: report, insights, status, infra, or a free-form question.",
        "",
        "Telegram shows one bot name (e.g. BB Trader); replies are labeled [Anna], [DATA], [Mia], or [Cody] in the message.",
        "Personas do not hand off or consult each other inside one reply yet — planned for later hardening.",
        "This interface is read-only: no approvals or execution from Telegram.",
    ]
