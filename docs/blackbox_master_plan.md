# BLACK BOX — MASTER PROJECT PLAN

## Overview

This document defines the full Phase 1 bootstrap for Cody (Code Bot) using OpenClaw.

---

## Core Philosophy

- Pattern recognition over prediction
- Structured learning
- Risk-controlled decisions
- No autonomous unsafe behavior

---

## Phase 1 Goal

Build Cody as an OpenClaw SKILL-driven engineering agent.

---

## Key Components

### Cody — Code Bot

**Role:**

- Software engineer agent
- System architect
- Planning and scaffolding

**NOT:**

- Trader
- Analyst
- Execution bot

---

## Directory Structure

```text
blackbox/
├── agents/
│   └── cody/
│       ├── agent.md
│       ├── prompts/
│       ├── skills/
│       │   └── cody-planner/
│       │       └── SKILL.md
│       ├── runtime/
│       └── templates/
├── docs/
├── modules/
├── data/
└── tests/
```

---

## SKILL.md Core

- **name:** `cody_planner`
- **Purpose:** Plan system architecture, recommend build steps, guide development (see `agents/cody/skills/cody-planner/SKILL.md` in-repo).

---

## OpenClaw Integration

OpenClaw loads skills from `<workspace>/skills` (highest precedence), then `~/.openclaw/skills`, then bundled skills. The canonical copy in **git** lives at `agents/cody/skills/`.

**Make skills visible to the gateway** by one of:

- Copying `cody-planner` into `<workspace>/skills/` (symlinks that escape the workspace root may be **rejected** by OpenClaw), or  
- Setting `skills.load.extraDirs` in `~/.openclaw/openclaw.json` to an allowed path (see OpenClaw docs: *Skills*, *Creating Skills*).

**Verify:**

```bash
openclaw skills list
```

---

## Test Prompt

Use the Cody planner skill to recommend next steps for building BLACK BOX.

---

## Success Criteria

- Cody loads in OpenClaw
- Cody responds as engineering agent
- No trading behavior
- Structured outputs

---

## Future phases (stub — architect review)

> **Note:** Not in scope for Phase 1 delivery. Below is a **proposal stub** for roadmap alignment. **Confirm with the architect** before design or implementation.

**Proposed addition (Cursor assistant, 2026-03-22) — should be looked at**

1. **Consult / escalation (API “second opinion”)**  
   After the application is in a working state, support **optional** calls to **web/API models** (e.g. Claude, ChatGPT-class providers) using **server-held API keys**, so agents can **escalate** when an answer is **insufficient** or **confidence is low**—without replacing the default local-first Cody loop.

2. **Router / model picker / scoring**  
   Introduce a **routing or scoring layer** that selects among **multiple** candidate models (order-of-magnitude ~10–15 profiles) by **task type, cost, latency, and policy**, rather than a single fixed model for every turn.

3. **Governance**  
   Escalation should be **explicitly triggered** (rules + signals—not only model self-reported confidence), **metered**, **audited**, and **key-safe** (secrets never in repo or public channels).

This section is intentionally high-level; detailed triggers, providers, and OpenClaw wiring belong in a follow-on spec once Phase 1.5 hardening and product direction are set.

---

## Final Rule

If unclear: **STOP → LOOK UP DOCS → THEN IMPLEMENT**
