# CONTEXT_PROFILE — Foreman

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

Defines what context the **runtime injects**, what this agent may **write back**, **trusted memory** reuse, **artifact** relevance, and **conversation** participation. See `contextProfileContract` in `agents/agent_registry.json`.

## defaultContextScopes

- current_directive_full
- shared_coordination_log_relevant
- directive_closeout_template_fields
- foreman_bridge_state_readonly

## allowedContextClasses

- docs_working_read
- docs_working_write_bounded
- git_diff_directive_scope
- pytest_output_captured

## writableContextClasses

- shared_coordination_log_append
- current_directive_amendment
- closeout_note
- talking_stick_governance_readonly

## reusableMemoryPolicy

- `validated_only`

## artifactRelevance

- directive_closeout_packet
- directive_execution_log_entry
- proof_gate_verdict

## bundleSections

- identity
- tools
- soul
- contextProfile
- closure_requirements

## conversationParticipationMode

- `orchestrator_turn`
