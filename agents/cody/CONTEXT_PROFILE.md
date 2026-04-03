# CONTEXT_PROFILE — Cody

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

Defines what context the **runtime injects**, what this agent may **write back**, **trusted memory** reuse, **artifact** relevance, and **conversation** participation. See `contextProfileContract` in `agents/agent_registry.json`.

## defaultContextScopes

- active_directive_excerpt
- development_plan_pointer
- repo_workspace_manifest
- shared_coordination_log_tail_readonly

## allowedContextClasses

- repo_read
- approved_sqlite_read
- shared_docs_read
- openclaw_workspace_context

## writableContextClasses

- patch_proposals_staging
- shared_coordination_log_append_when_directed
- agent_skill_drafts_git_reviewed

## reusableMemoryPolicy

- `semantic_staging_promoted`

## artifactRelevance

- implementation_proof
- directive_closeout_packet
- agent_registry_change_set

## bundleSections

- identity
- tools
- soul
- contextProfile
- active_directive_id

## conversationParticipationMode

- `isolated_session`
