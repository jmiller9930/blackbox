# Repo → OpenClaw workspace sync (drift prevention)

## Why this exists

The **repo** (`~/blackbox` or your clone) holds canonical **IDENTITY**, **SOUL**, **TOOLS**, skills, and registry.  
OpenClaw injects context from **workspace directories** on the gateway host (e.g. `~/.openclaw/workspace` for Cody / `main`, `~/.openclaw/workspace-data` for DATA).

If those copies **diverge** from the repo, agents behave inconsistently and debugging becomes unreliable.

## When to sync

Run after:

- `git pull` that changes `agents/cody/**`, `agents/data/**`, `agents/agent_registry.json`, or `scripts/render_agent_registry.py`
- Any edit to generated agent markdown you care about at runtime

## Steps (clawbot / gateway host)

From the repo root:

```bash
cd ~/blackbox
git pull
python3 scripts/render_agent_registry.py   # if registry JSON changed or you need regen
./scripts/sync_openclaw_skills.sh
./scripts/bootstrap_data_workspace.sh
cp -a agents/cody/IDENTITY.md agents/cody/SOUL.md agents/cody/TOOLS.md ~/.openclaw/workspace/
systemctl --user restart openclaw-gateway.service
```

Adjust paths if `OPENCLAW_WORKSPACE` / `OPENCLAW_WORKSPACE_DATA` differ on your host.

## Ownership (roadmap)

Per architect direction, **DATA** may eventually **own** validation that workspaces match expected artifacts; until then this remains a **human/operator** checklist.

## See also

- [`DATA_ONLINE_SETUP.md`](DATA_ONLINE_SETUP.md)
- [`agent_verification.md`](agent_verification.md)
