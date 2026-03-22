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

## Policy — allowed tool classes

- repo_and_workspace_read
- patch_and_plan_authoring
- skill_and_agent_template_writes (approved scope)
- sqlite_read_approved_paths
- engineering_inspection_openclaw_profile

## Policy — denied actions

- trade_execution_or_live_signals_as_operator
- silent_broad_repo_mutation
- pretending_DATA_or_execution_capabilities

## Policy — escalation

- Integrity / connectivity / truth questions → DATA
- High-risk change → human review
- Insufficient evidence → state unknowns explicitly

## Policy — secret access classes

- none_by_default
- vault_retrieval_only_when_human_class_approved (future — tie to secretsPolicy)
