# Repo → OpenClaw workspace sync (drift prevention)

## Directive (architect — hard requirement)

**Workspace sync is mandatory.** Repo → workspace consistency must be maintained **at all times**.

- **Sync must run after every `git pull`** that could affect agent definitions, skills, or registry-driven files.
- **Failure to sync** → **undefined agent behavior** (stale identity, wrong skills, debugging noise).

See audit protocol: [`agent_verification.md`](agent_verification.md). **Phase / runtime proof:** [`global_clawbot_proof_standard.md`](global_clawbot_proof_standard.md) (mandatory clawbot execution + persistence evidence).

---

## Why this exists

The **repo** (`~/blackbox` or your clone) holds canonical **IDENTITY**, **SOUL**, **TOOLS**, skills, and registry.  
OpenClaw injects context from **workspace directories** on the gateway host (e.g. `~/.openclaw/workspace` for Cody / `main`, `~/.openclaw/workspace-data` for DATA).

If those copies **diverge** from the repo, agents behave inconsistently and system integrity is compromised.

---

## When to sync

**After every `git pull`** (minimum). Also run after any local edit to generated agent markdown or skills you need live.

---

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

---

## Verification record

After sync on a milestone, update **[`agent_verification.md`](agent_verification.md)** with **date**, **git ref**, and **pass/fail** as applicable.

---

## Ownership (roadmap)

**DATA** may eventually **own** automated validation that workspaces match expected artifacts; until then this remains a **human/operator** requirement.

---

## See also

- [`local_remote_development_workflow.md`](local_remote_development_workflow.md) — Git local ↔ server, Cursor modes, when to verify on clawbot
- [`DATA_ONLINE_SETUP.md`](DATA_ONLINE_SETUP.md)
- [`agent_verification.md`](agent_verification.md)
