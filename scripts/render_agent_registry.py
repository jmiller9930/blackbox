#!/usr/bin/env python3
"""Render agents/<id>/IDENTITY.md, TOOLS.md, SOUL.md from agents/agent_registry.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "agents" / "agent_registry.json"
AGENTS_DIR = REPO_ROOT / "agents"

GENERATED = (
    "<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->"
)


def render_identity(agent_id: str, block: dict) -> str:
    ident = block.get("identity") or {}
    lines = [
        f"# IDENTITY — {block.get('displayName', agent_id)}",
        "",
        GENERATED,
        "",
        f"- **Who:** {ident.get('who', '')}",
        f"- **Mission:** {ident.get('mission', '')}",
    ]
    ins = ident.get("inScope")
    outs = ident.get("outOfScope")
    if isinstance(ins, str):
        lines.append(f"- **In scope:** {ins}")
    else:
        lines.append("- **In scope:**")
        for item in ins or []:
            lines.append(f"  - {item}")
    if isinstance(outs, str):
        lines.append(f"- **Out of scope:** {outs}")
    else:
        lines.append("- **Out of scope:**")
        for item in outs or []:
            lines.append(f"  - {item}")
    lines.append(f"- **Ownership:** {ident.get('ownership', '')}")
    see = ident.get("seeAlso")
    if see:
        ticked = ", ".join(f"`{x}`" for x in see)
        lines.append("")
        lines.append(f"See also: {ticked}.")
    return "\n".join(lines) + "\n"


def render_tools(agent_id: str, block: dict) -> str:
    tools = block.get("tools") or {}
    name = block.get("displayName", agent_id)
    cond_title = "## Conditional" if agent_id == "data" else "## Restricted / conditional"
    sections = [
        ("## Allowed", tools.get("allowed") or []),
        (cond_title, tools.get("conditional") or []),
        ("## Denied", tools.get("denied") or []),
    ]
    out = [f"# TOOLS — {name}", "", GENERATED, ""]
    for title, items in sections:
        out.append(title)
        out.append("")
        if items:
            for line in items:
                out.append(f"- {line}")
        else:
            out.append("- _(none)_")
        out.append("")
    align = tools.get("alignWith")
    if align:
        out.append("Align with:")
        for ref in align:
            out.append(f"- {ref}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_soul(agent_id: str, block: dict) -> str:
    soul = block.get("soul") or {}
    name = block.get("displayName", agent_id)
    title = f"# SOUL.md — {name}" if agent_id == "data" else f"# SOUL — {name}"
    lines = [title, "", GENERATED, ""]

    if soul.get("bullets"):
        for b in soul["bullets"]:
            lines.append(f"- {b}")
        lines.append("")
        return "\n".join(lines)

    if agent_id == "data":
        lines.append(soul.get("openingLine", ""))
        lines.append("")
        for t in soul.get("tabooLines") or []:
            lines.append(t)
        lines.append("")
        cares_intro = soul.get("caresIntro", "DATA cares about:")
        lines.append(cares_intro)
        lines.append("")
        for x in soul.get("caresAbout") or []:
            lines.append(f"- {x}")
        lines.append("")
        pri_intro = soul.get("prioritiesIntro", "DATA prioritizes:")
        lines.append(pri_intro)
        lines.append("")
        for i, p in enumerate(soul.get("prioritiesOrdered") or [], 1):
            lines.append(f"{i}. {p}")
        lines.append("")
        lines.append(soul.get("operatorLine", ""))
        lines.append("")
        lines.append(soul.get("whenUncertainIntro", "When uncertain, DATA says:"))
        lines.append("")
        for x in soul.get("whenUncertain") or []:
            lines.append(f"- {x}")
        lines.append("")
        for bl in soul.get("behavioralLines") or []:
            lines.append(bl)
        lines.append("")
        lines.append("DATA is helpful with:")
        lines.append("")
        for x in soul.get("helpfulWith") or []:
            lines.append(f"- {x}")
        lines.append("")
        lines.append("DATA does not:")
        lines.append("")
        for x in soul.get("doesNot") or []:
            lines.append(f"- {x}")
        lines.append("")
        for cl in soul.get("closingLines") or []:
            lines.append(cl)
        lines.append("")
        return "\n".join(lines)

    # Stub agents
    if soul.get("headline"):
        lines.append(f"- **Headline:** {soul['headline']}")
    if soul.get("principles") is not None:
        lines.append("- **Principles:**")
        pr = soul.get("principles") or []
        if pr:
            for p in pr:
                lines.append(f"  - {p}")
        else:
            lines.append("  - _(TBD)_")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    agents = raw.get("agents") or {}
    for agent_id, block in agents.items():
        dest = AGENTS_DIR / agent_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "IDENTITY.md").write_text(render_identity(agent_id, block), encoding="utf-8")
        (dest / "TOOLS.md").write_text(render_tools(agent_id, block), encoding="utf-8")
        (dest / "SOUL.md").write_text(render_soul(agent_id, block), encoding="utf-8")
    print(
        f"Rendered IDENTITY.md, TOOLS.md, SOUL.md for {len(agents)} agent(s) under {AGENTS_DIR}/",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
