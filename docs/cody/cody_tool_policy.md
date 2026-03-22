# Cody — tool policy (Phase 1.5)

**Scope:** Live OpenClaw gateway on `clawbot`; default agent uses the **`coding`** tool profile unless changed.

**Authoritative gateway config:** `~/.openclaw/openclaw.json` on the gateway host.

## Explicit config (applied)

```json
"tools": {
  "profile": "coding",
  "deny": ["message"]
}
```

- **`coding`** (OpenClaw default profile): filesystem (`read`, `write`, `edit`, `apply_patch`), runtime (`exec`, `process`), session tools, memory tools, `image`. See OpenClaw `docs/gateway/configuration-reference.md` → **Tool profiles** / **Tool groups**.
- **`deny: ["message"]`:** blocks the cross-channel **`message`** tool (`group:messaging`).

## Permissions stance

| Class | Policy |
|-------|--------|
| **Filesystem** | Allowed within workspace / sandbox rules OpenClaw enforces for `group:fs`. |
| **Git** | Via `exec` / file tools where available — no separate `git` tool name in base profile; treat as **exec + fs** with repo governance. |
| **Session tools** | Allowed (`group:sessions`). |
| **Memory tools** | Allowed (`group:memory`). |
| **Shell / exec** | Allowed under `coding` (`group:runtime`); elevated/host exec follows `tools.elevated` if configured (not set in baseline). |
| **Cross-channel messaging** | **Denied** (`message`). |
| **Browser / web fetch** | **Not** included in `coding` — enable only by explicit policy change later. |
| **External network** | Not granted by `coding` for web tools; `exec` could reach network — treat as **governance + elevated** concern. |

## Control UI (lab)

- Token auth on gateway; document **lab** posture: `dangerouslyAllowHostHeaderOriginFallback` and `dangerouslyDisableDeviceAuth` may be set for convenience — review before production exposure.

## Workspace vs repo (recommended)

- **`~/.openclaw/workspace`** = **runtime** workspace (IDENTITY, SOUL, skills copy, memory).
- **`~/blackbox` (git)** = **source of truth** for Cody assets under `agents/cody/`.
- After `git pull` on the server, run **`~/blackbox/scripts/sync_cody_skill_to_openclaw.sh`** so `cody-planner` stays aligned (no symlinks that escape the workspace root).

## Phase 2 gate (architect)

Before multi-agent expansion: tool profile explicit ✓, tool policy documented ✓, workspace sync defined ✓.
