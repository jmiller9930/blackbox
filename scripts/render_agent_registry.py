#!/usr/bin/env python3
"""Render agents/<id>/IDENTITY.md, TOOLS.md, SOUL.md and docs/architect/agent_registry.md from agents/agent_registry.json."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "agents" / "agent_registry.json"
AGENTS_DIR = REPO_ROOT / "agents"
OVERVIEW = REPO_ROOT / "docs" / "architect" / "agent_registry.md"

GENERATED = (
    "<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->"
)

STATUS_LABEL = {
    "active": "Active",
    "in_progress": "In Progress",
    "in_development": "In Development",
    "stub": "Stub",
}


def render_identity(agent_id: str, block: dict) -> str:
    ident = block.get("identity") or {}
    name = block.get("displayName", agent_id)
    role = block.get("role", "")
    ls = block.get("lifecycleStatus", "")
    status_h = STATUS_LABEL.get(ls, ls or "—")

    lines = [
        f"# IDENTITY — {name}",
        "",
        GENERATED,
        "",
        f"- **Role:** {role}",
        f"- **Status:** {status_h}",
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

    resp = block.get("responsibilities") or []
    if resp:
        lines.append("- **Responsibilities:**")
        for r in resp:
            lines.append(f"  - {r}")
    nresp = block.get("nonResponsibilities") or []
    if nresp:
        lines.append("- **Non-responsibilities:**")
        for r in nresp:
            lines.append(f"  - {r}")
    ho = block.get("handoff") or []
    if ho:
        lines.append("- **Handoff:**")
        for h in ho:
            lines.append(f"  - {h}")

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
        lines.append("DATA cares about:")
        lines.append("")
        for x in soul.get("caresAbout") or []:
            lines.append(f"- {x}")
        lines.append("")
        lines.append("DATA prioritizes:")
        lines.append("")
        for i, p in enumerate(soul.get("prioritiesOrdered") or [], 1):
            lines.append(f"{i}. {p}")
        lines.append("")
        lines.append(soul.get("operatorLine", ""))
        lines.append("")
        lines.append("When uncertain, DATA says:")
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

    if soul.get("traits") is not None or soul.get("headline"):
        if soul.get("traits"):
            lines.append("- **Soul:**")
            for t in soul.get("traits") or []:
                lines.append(f"  - {t}")
        if soul.get("headline"):
            lines.append(f"- **Headline:** {soul['headline']}")
        lines.append("")
        return "\n".join(lines)

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


def render_overview(raw: dict) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "<!-- Generated by scripts/render_agent_registry.py — edit agents/agent_registry.json, not this file. -->",
        "",
        "# Agent Registry — BlackBox System",
        "",
        f"Generated: {ts}",
        "",
        "---",
        "",
        "## Purpose",
        "",
        "Single source of truth for all agents: identity, tools, soul, responsibilities, handoffs.",
        "Canonical data lives in **`agents/agent_registry.json`**; this file is **generated** for reading — edit the JSON, then run `python3 scripts/render_agent_registry.py`.",
        "",
        "## Architecture (three layers)",
        "",
        "| Layer | Answers | Rendered file |",
        "|--------|---------|----------------|",
        "| Identity | Who, mission, scope, ownership, responsibilities | `IDENTITY.md` |",
        "| Tools | Allowed / conditional / denied surfaces | `TOOLS.md` |",
        "| Soul | Voice, traits, behavior under uncertainty | `SOUL.md` |",
        "",
        "Keep **JSON compact** (lists and short strings). **Prose-heavy** behavior lives in generated per-agent Markdown, not duplicated as long strings in the registry.",
        "",
        "## Performance",
        "",
        "- **One file to parse** at build or sync time; no scattered prose sources to drift.",
        "- **Compact fields** in JSON; long-form `SOUL.md` / `IDENTITY.md` per agent are **rendered** for OpenClaw workspaces, not duplicated by hand.",
        "- **Token discipline:** inject the three workspace files for **one** agent at a time; the overview is for humans and cross-agent review, not a second prompt dump.",
        "",
        "## Governance",
        "",
    ]
    for g in raw.get("governance") or []:
        lines.append(f"- {g}")
    lines.extend(["", "# Agents", ""])
    agents = raw.get("agents") or {}
    for aid, block in agents.items():
        name = block.get("displayName", aid)
        lines.extend(["", f"## {name}", ""])
        lines.append(f"- **Role:** {block.get('role', '')}")
        lines.append(f"- **Status:** {STATUS_LABEL.get(block.get('lifecycleStatus', ''), block.get('lifecycleStatus', ''))}")
        ident = block.get("identity") or {}
        lines.append(f"- **Mission:** {ident.get('mission', '')}")
        lines.append(f"- **Identity (summary):** {ident.get('who', '')}")
        soul = block.get("soul") or {}
        if soul.get("traits"):
            lines.append(f"- **Soul:** {', '.join(soul.get('traits') or [])}")
        elif soul.get("bullets"):
            lines.append("- **Soul:** structured (see per-agent SOUL.md)")
        elif aid == "data":
            lines.append(f"- **Soul:** {soul.get('openingLine', '')}")
        else:
            lines.append(f"- **Soul:** {soul.get('headline', '')}")
        tools = block.get("tools") or {}
        al = tools.get("allowed") or []
        den = tools.get("denied") or []
        lines.append("- **Allowed tools:**")
        for x in al:
            lines.append(f"  - {x}")
        lines.append("- **Denied tools:**")
        for x in den:
            lines.append(f"  - {x}")
        resp = block.get("responsibilities") or []
        if resp:
            lines.append("- **Responsibilities:**")
            for r in resp:
                lines.append(f"  - {r}")
        nresp = block.get("nonResponsibilities") or []
        if nresp:
            lines.append("- **Non-responsibilities:**")
            for r in nresp:
                lines.append(f"  - {r}")
        ho = block.get("handoff") or []
        if ho:
            lines.append("- **Handoff:**")
            for h in ho:
                lines.append(f"  - {h}")
        lines.append("")
    lines.extend(
        [
            "---",
            "",
            "## Notes",
            "",
            "- Updates must be version-controlled in **`agents/agent_registry.json`**.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    agents = raw.get("agents") or {}
    for agent_id, block in agents.items():
        dest = AGENTS_DIR / agent_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "IDENTITY.md").write_text(render_identity(agent_id, block), encoding="utf-8")
        (dest / "TOOLS.md").write_text(render_tools(agent_id, block), encoding="utf-8")
        (dest / "SOUL.md").write_text(render_soul(agent_id, block), encoding="utf-8")

    OVERVIEW.parent.mkdir(parents=True, exist_ok=True)
    OVERVIEW.write_text(render_overview(raw), encoding="utf-8")

    print(
        f"Rendered IDENTITY/TOOLS/SOUL for {len(agents)} agent(s); wrote {OVERVIEW}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
