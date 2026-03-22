# Meet the Team — BLACK BOX roster

Canonical list of **agent personas** and **human roles**. Update here when names, scope, or status change; the master plan links to this file.

**Agent registry (identity + tools + soul):** [`../../agents/agent_registry.json`](../../agents/agent_registry.json) — see [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md).

## Software agents

| Agent | Role | Notes | Status |
|-------|------|-------|--------|
| **Cody** | Software engineer | Builds the system, agents, skills, repo structure | In progress |
| **DATA** | System & data guardian | Health, SQLite integrity, monitoring, alerts | In progress |
| **Mia** | Market info agent | Real-time market data (**read-only**) | Active |
| **Anna** | Analyst | Trade signals and confidence (aligned with architect trading layers) | In progress |
| **Billy** | TBot executor | Executes trades and manages positions | In development |

## Human roles (not automated agents)

| Person | Role | Notes | Status |
|--------|------|-------|--------|
| **Sean** | CEO | Strategy, goals, risk tolerance | Active |
| **John** | CTO | Architecture, security, technical direction | Active |

## Alignment notes

- **Anna / Billy** map to the architect **Analyst** / **Executor** split in [`architect_update_trading_system.md`](architect_update_trading_system.md) when implemented.
- **Mia** should remain **read-only** and must not execute trades.
- **Sean / John** set policy; agents do not replace those accountabilities.

---

*Last updated: 2026-03-22*
