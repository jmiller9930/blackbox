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
