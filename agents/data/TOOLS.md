# TOOLS — DATA

## Allowed

- Health and **service status** checks; **heartbeat** validation; **connection** checks.
- **SQLite** inspection and **integrity** queries; **log** inspection where permitted.
- **Port** / reachability checks; **feed freshness** checks; reading **runtime config** needed for monitoring.
- **Alert/report** output to persistence and operator channels once configured.

## Conditional

- **Shell** limited to health/validation commands; **restart/remediation** only if explicitly approved by phase/maintenance policy.

## Denied

- **Trading strategy** or **execution**; freeform **repo mutation**; **code generation** as primary role; silent auto-repair beyond approved actions.
