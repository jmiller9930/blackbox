# BLACK BOX — Phase 1 clarification (for Cursor / team)

## What we are doing right now

We are **not** building the full Slack team yet.

We are doing **Phase 1 only**:

> **Get Cody working inside OpenClaw first.**

Slack comes later.

---

## Simple architecture

### Right now

- **OpenClaw** = the brain router
- **Cody** = the engineering agent
- **BLACK BOX repo** = Cody’s files, prompts, and skill
- **Control UI / OpenClaw chat** = where we test Cody first

### Later

- **Slack** = the conversation layer (humans talk to agents there)
- Slack is **not** the first thing to build

---

## What Cursor must understand

OpenClaw loads agents from a **workspace** and loads skills from **directories containing `SKILL.md`**. The workspace root is often `~/.openclaw/workspace` unless changed in config. OpenClaw also injects context from workspace files (e.g. `AGENTS.md`). Skills are a first-class layer.

Reference: [OpenClaw on GitHub](https://github.com/openclaw/openclaw)

Cody is **not** “just Python.” Cody needs:

1. **Identity** (`agent.md`, workspace context as applicable)
2. **`SKILL.md`** (e.g. `cody_planner`)
3. **Optional Python** helpers under `agents/cody/runtime/`

---

## Phase 1 goal

OpenClaw must be able to:

- **Discover** the Cody skill
- **Load** Cody’s behavior from `SKILL.md`
- Let us **test Cody** in the OpenClaw UI
- Have Cody respond as an **engineering** agent

---

## Cody’s job (one sentence)

> Cody is the **engineering agent** for BLACK BOX: plan structure, propose safe code work, and help build the rest of the system later — **not** trading, market analysis, or execution.

---

## Required vs optional files (repo)

**Required**

- `agents/cody/agent.md`
- `agents/cody/prompts/system_prompt.md`
- `agents/cody/prompts/recommendation_format.md`
- `agents/cody/prompts/patch_policy.md`
- `agents/cody/skills/cody-planner/SKILL.md`

**Optional (support only)**

- `agents/cody/runtime/contracts.py`, `planner.py`, `recommender.py`, `reporter.py`, `patch_guard.py`

**OpenClaw cares most about `SKILL.md` for skill behavior.**

---

## Verify on ClawBot host

### 1. Workspace / skill path

Determine where the running gateway loads **workspace** and **skills** from (`openclaw.json`, `gateway`, `skills.*`).

### 2. Make Cody visible

Ensure `cody_planner` lives where OpenClaw scans, e.g.:

- `<workspace>/skills/cody-planner/SKILL.md`, and/or  
- `skills.load.extraDirs` (see OpenClaw *Skills* docs)

**Important (Claw verified):** A **symlink** from `~/.openclaw/workspace/skills/cody-planner` → `~/blackbox/...` was **skipped** with: *“Skipping skill path that resolves outside its configured root.”* OpenClaw requires the skill’s real path to stay inside the allowed root. **Fix:** **copy** the skill folder into `~/.openclaw/workspace/skills/` (or configure an allowed `extraDirs` path), then re-run `openclaw skills info cody_planner`.

### 3. Skill discovery

```bash
openclaw skills list
```

Success: **`cody_planner`** (or the skill `name` from frontmatter) appears.

If not: wrong path, wrong workspace, config, or gateway needs restart.

### 4. UI smoke test

Prompt (example):

> Use the Cody planner to recommend next steps for building BLACK BOX.

Expected: engineering / planning tone, **not** trader; structured recommendations.

---

## Not in Phase 1

Do **not** build yet: Slack, Billy, Robbie, Bobby trading bridge, market scoring, live trading. That is Phase 2+.

---

## Why not Slack first

Slack is a front door. If Cody is wrong in OpenClaw, Slack only hides debugging. Order: **(1) Cody in OpenClaw → (2) Control UI looks right → (3) Slack later.**

---

## One-line summary for Cursor

Build Cody as an **OpenClaw skill-driven** engineering agent; ensure the **running workspace** can **discover** `cody_planner`; verify with **`openclaw skills list`**; test in the **OpenClaw UI** before Slack or other agents.
