# Agent registry — identity, tools, soul in one place

## The three layers (your model)

| Layer | Question it answers | Typical file (generated) |
|--------|---------------------|---------------------------|
| **Identity** | Who is this agent? Mission, scope, ownership vs other agents. | `IDENTITY.md` |
| **Tools** | What may they touch? Allowed, conditional, denied; align with live gateway policy. | `TOOLS.md` |
| **Soul** | How do they think and respond? Voice, taboos, priorities, behavior under uncertainty. | `SOUL.md` |

That split makes sense: **identity** is factual role; **tools** is permission and surface area; **soul** is behavioral contract. They overlap slightly at the edges (e.g. “guardian” is both identity and tone), but keeping them separate avoids mixing “what I am” with “what I may do” with “how I speak.”

## Single source of truth

- **Canonical:** [`../../agents/agent_registry.json`](../../agents/agent_registry.json) — one JSON object per agent id (`cody`, `data`, `mia`, `anna`, `billy`, …). Adding an agent means adding a **new key** with `identity`, `tools`, and `soul` (stubs use `status: "stub"` until defined).
- **Generated:** `agents/<id>/IDENTITY.md`, `TOOLS.md`, `SOUL.md` are produced by **`scripts/render_agent_registry.py`** so OpenClaw workspaces can keep the same three-file layout **without** hand-editing three places. Edit the JSON, then run:

```bash
python3 scripts/render_agent_registry.py
```

- **Gateway enforcement:** `TOOLS.md` is the human/agent-facing contract; **`~/.openclaw/openclaw.json`** and tool policy still enforce what is actually allowed.

## Rules

1. **Never** copy one agent’s `identity` / `tools` / `soul` as the default for another; stubs must stay explicit TBDs.
2. **Humans** (e.g. Sean, John) are not required in the JSON unless you later add optional entries for persona prompts.

## Supersedes

This document replaces the narrower “soul-only” registry description; the repo now uses **`agent_registry.json`**, not `souls.json`.
