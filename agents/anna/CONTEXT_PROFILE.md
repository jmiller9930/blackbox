# CONTEXT_PROFILE — Anna

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

Defines what context the **runtime injects**, what this agent may **write back**, **trusted memory** reuse, **artifact** relevance, and **conversation** participation. See `contextProfileContract` in `agents/agent_registry.json`.

## defaultContextScopes

- participant_risk_tier
- grounded_market_snapshot_or_explicit_fallback
- signal_contract_schema
- active_directive_excerpt_when_analyst_task

## allowedContextClasses

- market_data_read
- stored_series_read
- messaging_thread_recent
- registry_identity_slice

## writableContextClasses

- analysis_staging
- signal_candidate_artifact
- shared_coordination_log_append_when_directed

## reusableMemoryPolicy

- `episodic_non_canonical`

## artifactRelevance

- signal_contract_v1
- pre_trade_fast_gate_result
- strategy_selection_record
- implementation_proof_reference

## bundleSections

- identity
- tools
- soul
- contextProfile
- hydration_governance_slice
- tier_scope

## conversationParticipationMode

- `routing_multi_persona_shared_channel`
