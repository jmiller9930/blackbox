# Local ↔ remote development, testing, and sync (agent + human)

**Purpose:** One place that defines **how we develop**, **where tests count**, and **how the Mac clone stays aligned with `clawbot`**, so assistants do not re-litigate SSH vs workspace vs proof.

**Audience:** Humans, architects, and coding agents (Cody layer). **Read this before** claiming “I can’t touch the server” or “SSH doesn’t matter.”

---

## 1. Vocabulary (non‑negotiable)

| Term | Meaning |
|------|--------|
| **Local workspace** | Cursor opened a folder on **your machine** (e.g. macOS `.../Documents/.../blackbox`). Editor file ops and a normal `git` in that window apply to **that clone**. |
| **Remote SSH workspace** | Cursor **Remote SSH** connected to `clawbot` with **`~/blackbox`** (or server path) open. The “project” **is** the server tree; edits and git apply **there**. |
| **SSH command** | Running `ssh jmiller@clawbot.a51.corp '...'` (or an interactive `ssh` in the integrated terminal). This runs **on the server** but does **not** by itself move the **editor’s** workspace to the server. |

**Core fact:** SSH working and “I’m editing the repo” are **orthogonal** until you know **which folder is open in Cursor**. Confusing them wastes time.

---

## 2. Roles (alignment)

| Role | Responsibility |
|------|----------------|
| **Architect** | Plan, phases, proof standards, what “done” means. |
| **Coding agent (implementation layer)** | Implement the plan in the repo, run tests, surface failures, produce **proof** where the architect/runtime docs require it. |
| **Human** | Chooses **local vs Remote SSH** window, pushes policy, runs interactive steps when needed. |

**Testing the plan:** Local-only green checks are **insufficient** when [`execution_context.md`](../runtime/execution_context.md) or [`global_clawbot_proof_standard.md`](global_clawbot_proof_standard.md) mandate **clawbot** execution. The agent must **not** treat “passes on my laptop” as closure when the directive says verify on **`primary_host`**.

---

## 3. Two supported modes (pick explicitly)

### Mode A — Remote SSH (best for sustained server work)

1. **Cursor → Remote SSH → `jmiller@clawbot.a51.corp` → open `~/blackbox`.**
2. Edit, `git`, run tests and project commands **in that window** — one filesystem, one truth for server-side work.

Use when: heavy editing on the canonical server tree, DB paths, or anything that must not drift from `~/blackbox` on clawbot.

### Mode B — Local clone + explicit remote verification (common for Mac workflow)

1. Open the **local** clone in Cursor for day-to-day edits and **local** tests (fast feedback).
2. **Push / merge** to `origin` per team Git workflow.
3. **Sync server:** On clawbot, `git pull` in `~/blackbox` (human in SSH session, CI, or **agent-run** `ssh ... 'cd ~/blackbox && git pull ...'` **when the user or the plan requires server parity**).
4. **Run verification on clawbot** for phase closure: tests, scripts, persistence checks — as specified in `execution_context.md` and the proof standard.

Use when: you prefer editing on the Mac but **truth** for closure is still **clawbot**.

**Agents:** When the workspace is **local**, **do not** pretend the server repo does not exist. **Do** state clearly: “Edits here are local; to validate on clawbot I will run …” and then run the **remote** commands the plan requires (or ask the user to switch to Remote SSH).

---

## 4. Keeping local and remote in sync (Git)

| Direction | Practice |
|-----------|----------|
| **Local → origin** | Commit and push from the **machine where you made changes** (local clone or server clone). |
| **origin → server (`~/blackbox`)** | `git pull` (or `fetch` + merge) **on clawbot** after the branch you care about is on `origin`. |
| **origin → local** | `git pull` in the Mac clone for parity. |

**Rule:** The **canonical lab path** is **`~/blackbox` on `clawbot.a51.corp`** unless stated otherwise. A Mac clone is valid for development; **server** must be updated before claiming server-side verification.

### 4.1 — `scripts/sync.py` (default close-out after Black Box updates)

When work in this repo should be **on `origin`** and **live on the lab host** with **UIUX.Web** (nginx/api/dashboard path) rebuilt and restarted, run from the **repo root**:

```bash
python3 scripts/sync.py
```

That script **pushes** the current branch to `origin`, **SSHs** to clawbot, **`git pull`** in `~/blackbox`, then **`docker compose build web`**, **`docker compose up -d`**, and **`docker compose restart api`** under **`UIUX.Web`**. Use **`--dry-run`** to print actions only; **`--skip-push`** if you already pushed and only need remote pull + compose.

Treat this as the **standard post-update step** for Black Box changes that matter on clawbot, unless the user or directive explicitly skips deploy or SSH is unavailable (then say so in the proof gap).

**Conditional UI deploy:** **`python3 scripts/gsync.py`** does the same local commit (optional) + push + remote `git pull`, then restarts **only what changed**: **UIUX.Web** `docker compose` when paths under `UIUX.Web/` change, and the **pattern-game Flask** app (port **8765**, via `scripts/pattern_game_remote_restart.sh`) when paths under `renaissance_v4/game_theory/` (or `scripts/agent_context_bundle.py`, configurable) change. **`--force-restart`** runs both even when `git pull` is a no-op. See `scripts/gsync.py` docstring and env `GSYNC_UIUX_PREFIXES` / `GSYNC_PATTERN_GAME_PREFIXES`. Use **`sync.py`** when you always need the operator stack rebuilt regardless of paths.

**Pattern-game only (always pull + restart + verify):** **`./scripts/deploy_pattern_game.sh`** (same as **`python3 scripts/gsync.py --pattern-game`**) stages game_theory paths, pushes, pulls on the lab, restarts Flask, then **fails with exit code 1** if the remote repo HEAD does not match `origin` or the UI does not return **`X-Pattern-Game-UI-Version`** on port **8765** (unless **`--no-verify`**). Prefer this when iterating on the pattern-game web UI so “pushed” cannot be mistaken for “live on clawbot.”

**Not** the same as [`workspace_sync.md`](workspace_sync.md) (OpenClaw identity/skills copies on the gateway). **One-shot** push + Black Box UI stack + SeanV3/Jupiter: see **`python3 scripts/jupsync.py --full-stack`** in `scripts/jupsync.py`.

---

## 5. OpenClaw / gateway workspace sync (separate from Git)

Repo content must still be reflected into OpenClaw workspace paths on the gateway when agents/skills/registry change. Follow **[`workspace_sync.md`](workspace_sync.md)** after relevant pulls — that is **not** replaced by this file; it **adds** Git sync with **runtime** workspace copies.

---

## 6. What agents must do (checklist)

1. **Detect workspace:** If root path looks like `/Users/...` or local macOS → **local** clone. If like `/home/jmiller/blackbox` → **server** tree.
2. **Say where writes go:** File edits apply to the **opened** workspace only.
3. **Honor proof requirements:** If the task is phase closure or `execution_context` says clawbot — run the **required commands on clawbot** (via Remote SSH session **or** `ssh ... 'cd ~/blackbox && ...'` as appropriate).
4. **Do not refuse remote verification** on the grounds that “SSH is forbidden” when the user or the plan **directs** server sync/test. The anti-pattern is **unauthorized** server mutation **without** clarity — not **directed** remote verification.
5. **Prefer clarity over repeated lectures:** One sentence on mode (local vs Remote SSH) is enough; then execute.
6. **After substantive Black Box updates** that should reach the lab operator UI / **`UIUX.Web` stack:** run **`python3 scripts/sync.py`** from repo root when you have commit + network + SSH (see §4.1). If deploy is out of scope, state that explicitly.

---

## 7. Related docs

| Doc | Role |
|-----|------|
| [`../runtime/execution_context.md`](../runtime/execution_context.md) | Phase, primary host, **required_execution** |
| [`global_clawbot_proof_standard.md`](global_clawbot_proof_standard.md) | Mandatory proof package |
| [`workspace_sync.md`](workspace_sync.md) | Repo → OpenClaw workspace after pull |
| `scripts/sync.py` | Push + clawbot `git pull` + **UIUX.Web** docker compose (Black Box lab deploy) |
| [`agent_verification.md`](agent_verification.md) | Milestone / audit records |

---

## 8. Revision

When this workflow changes (e.g. new CI replaces manual pull), update **this file** and the short pointers in `.cursor/rules/` so agents load one story.
