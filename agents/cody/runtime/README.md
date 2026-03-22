# Cody — Python support layer

## IMPORTANT

**Python here is SUPPORT ONLY.**

It does **not** define Cody’s agent behavior. Behavior is defined by:

- **`SKILL.md`** under `agents/cody/skills/` (OpenClaw skills)
- **`agent.md`** (identity and scope)
- **`prompts/`** (e.g. `system_prompt.md`)

This directory holds **helpers**: structured types (`contracts`), planning/recommendation/reporting utilities, CLI smoke entry (`main.py`), and safety stubs (`patch_guard`). Use them to format output, enforce guardrails in tooling, or wire tests—not as a substitute for skills or prompts in OpenClaw.
