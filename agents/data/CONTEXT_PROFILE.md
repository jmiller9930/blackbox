# CONTEXT_PROFILE — DATA

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

Defines what context the **runtime injects**, what this agent may **write back**, **trusted memory** reuse, **artifact** relevance, and **conversation** participation. See `contextProfileContract` in `agents/agent_registry.json`.

## defaultContextScopes

- runtime_health_snapshot
- sqlite_integrity_summary
- feed_freshness_window
- alert_queue_recent

## allowedContextClasses

- operational_logs_read
- sqlite_operational_read
- reachability_probe_results
- system_events_read

## writableContextClasses

- health_report_artifact
- alert_record
- structured_status_summary

## reusableMemoryPolicy

- `validated_only`

## artifactRelevance

- health_report
- remediation_validation_sandbox
- system_events_row

## bundleSections

- identity
- tools
- soul
- contextProfile
- operational_scope

## conversationParticipationMode

- `operator_broadcast_target`
