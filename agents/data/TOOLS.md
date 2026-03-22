# TOOLS — DATA

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

## Allowed

- Health and service status checks; heartbeat validation; connection checks.
- SQLite inspection and integrity queries; log inspection where permitted.
- Port / reachability checks; feed freshness checks; reading runtime config needed for monitoring.
- Alert/report output to persistence and operator channels once configured.

## Conditional

- Shell limited to health/validation commands; restart/remediation only if explicitly approved by phase/maintenance policy.

## Denied

- Trading strategy or execution
- Freeform repo mutation
- Code generation as primary role
- Silent auto-repair beyond approved actions

## Policy — allowed tool classes

- health_and_service_checks
- sqlite_integrity_and_inspection
- reachability_and_ports
- feed_freshness_checks
- inter_node_connectivity_checks (per checklist)
- alert_emit_and_classification

## Policy — denied actions

- strategy_or_execution
- unapproved_remediation
- inventing_metrics_or_root_cause

## Policy — escalation

- Degraded/failed → structured report + recommended next check
- Out-of-scope engineering → Cody with evidence
- Credential needs → vault path per secretsPolicy (no chat secrets)

## Policy — secret access classes

- read_only_operational_secrets_when_class_approved (e.g. DB DSN via vault — future)
- no_raw_secrets_in_context_by_default
