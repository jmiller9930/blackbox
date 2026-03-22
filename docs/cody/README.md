# Cody — documentation

- **Mission:** [cody_mission.md](cody_mission.md)
- **Governance:** [cody_governance.md](cody_governance.md)
- **Bootstrap (Phase 1):** [cody_bootstrap.md](cody_bootstrap.md)

Runnable agent assets live under `agents/cody/` (identity, prompts, skills, runtime).

**Python (`agents/cody/runtime/`)** is **support only** — types, guardrails, helpers. It does **not** define agent behavior; see [`agents/cody/runtime/README.md`](../../agents/cody/runtime/README.md).

## ClawBot host (Phase 2+)

Work on the ClawBot / OpenClaw side targets **`clawbot.a51.corp`**. A typical interactive login is **`jmiller@clawbot.a51.corp`** (for example via **Cursor Remote SSH**). Phase 1 does not require that host; it is the expected environment when wiring Cody more deeply in a later phase.

### ClawBot web UI (lab)

OpenClaw / agent chat in the browser (verified in lab):

- **Base:** `http://clawbot.a51.corp:18789`
- **Example chat URL:** `http://clawbot.a51.corp:18789/chat?session=agent%3Amain%3Amain`  
  (`session=` may differ per agent/session.)

**SSH** for shell access remains the default **port 22**; **18789** is the **HTTP** port for this UI only.
