# CONTEXT_PROFILE — Billy

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

Defines what context the **runtime injects**, what this agent may **write back**, **trusted memory** reuse, **artifact** relevance, and **conversation** participation. See `contextProfileContract` in `agents/agent_registry.json`.

## defaultContextScopes

- approved_signal_or_layer4_intent
- participant_account_tier_binding
- venue_policy_snapshot
- drift_user_and_market_snapshot

## allowedContextClasses

- execution_api_read
- position_read
- approval_artifact_read
- risk_limit_envelope
- drift_market_metadata_read

## writableContextClasses

- execution_fill_record
- position_update
- execution_audit_event

## reusableMemoryPolicy

- `validated_only`

## artifactRelevance

- layer4_execution_intent
- execution_feedback_v1
- paper_execution_record_v1

## bundleSections

- identity
- tools
- contextProfile
- approval_binding

## conversationParticipationMode

- `system_internal_only`
