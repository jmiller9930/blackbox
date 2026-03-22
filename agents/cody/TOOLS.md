# TOOLS — Cody

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

## Allowed

- Repository and workspace read; structure explanation; module boundaries.
- Patch planning, file generation for approved agent/skill definitions, code review, task decomposition, agent/skill templates.
- SQLite read once persistence exists and paths are approved.
- Engineering-oriented inspection consistent with OpenClaw coding profile where configured.

## Restricted / conditional

- Shell only when explicitly authorized or for narrow inspection per policy.
- Writes only within approved repo/workspace scope; no silent broad mutation.

## Denied

- Direct trade execution; live trading signals as operator.
- Direct runtime control or alert-channel ownership unless explicitly asked.
- Messaging tool for general cross-channel comm if policy denies message.
- Uncontrolled network expansion beyond approved tools.

Align with:
- docs/cody/cody_tool_policy.md
- ~/.openclaw/openclaw.json on the gateway
