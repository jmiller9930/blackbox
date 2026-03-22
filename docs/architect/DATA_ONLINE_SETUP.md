# DATA online — OpenClaw (clawbot)

DATA becomes a **real second agent** when (1) **skills** are synced, (2) a **dedicated workspace** holds DATA’s identity/soul files, and (3) **`agents.list`** registers that agent. **Cody** can stay **`main`** / default; DATA is a separate `id`.

## 1. Pull repo and sync skills

```bash
cd ~/blackbox && git pull
./scripts/sync_openclaw_skills.sh
```

Confirm `data_guardian` appears in `skills list` (alongside `cody_planner`).

## 2. Bootstrap DATA workspace (from repo)

```bash
cd ~/blackbox && ./scripts/bootstrap_data_workspace.sh
```

This creates **`~/.openclaw/workspace-data/`** and copies **IDENTITY, SOUL, TOOLS, AGENTS, USER** plus the **data-guardian** skill into that workspace’s `skills/` layout.

## 3. Register DATA in `~/.openclaw/openclaw.json`

Merge an **`agents.list`** (or extend yours) so it includes **DATA** alongside **`main`**. Minimal shape (adjust paths/user if needed):

```json
"agents": {
  "defaults": { ... existing ... },
  "list": [
    {
      "id": "main",
      "default": true,
      "name": "Cody",
      "workspace": "/home/jmiller/.openclaw/workspace",
      "model": "ollama/qwen2.5-coder:7b",
      "identity": { "name": "Cody", "emoji": "🛠️" }
    },
    {
      "id": "data",
      "default": false,
      "name": "DATA",
      "workspace": "/home/jmiller/.openclaw/workspace-data",
      "model": "ollama/qwen2.5-coder:7b",
      "identity": { "name": "DATA", "emoji": "🔍" }
    }
  ]
}
```

**Important:** If your install already has `agents.list`, **merge** one new object for `data` instead of duplicating `defaults`. Back up `openclaw.json` first.

## 4. Restart gateway

```bash
systemctl --user restart openclaw-gateway.service
```

## 5. Smoke test

- Control UI: start a session **as agent `data`** (or pick DATA in the agent selector if the UI exposes it).
- Ask for a **health-style** prompt (e.g. SQLite integrity check workflow per `data_guardian` skill).

## Troubleshooting

- **Only Cody appears:** `agents.list` missing, invalid JSON, or gateway didn’t restart.
- **DATA sounds generic:** Confirm **`SOUL.md`** and **`IDENTITY.md`** exist under **`workspace-data`** (re-run bootstrap).

---

See also: [`phase_1_5_agent_hardening_spec.md`](phase_1_5_agent_hardening_spec.md), [`agents/data/SOUL.md`](../../agents/data/SOUL.md).
