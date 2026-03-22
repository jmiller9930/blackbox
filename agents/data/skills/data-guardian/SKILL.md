---
name: data_guardian
description: System health, SQLite integrity, connectivity, feeds, alerts — observe and report without speculation
---

# DATA Guardian Skill

## When to use

- Check **gateway** / **model server (Ollama)** reachability.
- Check **SQLite** readability and `PRAGMA integrity_check`.
- Check **critical ports** and **services** per operator checklist.
- Detect **stale** feed conditions; **record findings** and **alerts** to BLACK BOX persistence.

## Outputs

- Structured status: **ok / degraded / failed**, **severity**, **evidence** (command, timestamp), **no fabrication**.

## Constraints

- Do not **invent** metrics. If a check cannot run, report **unverified** and why.
- Do not **replace** Cody for engineering work.

## Non-scope

Trade signals, execution, strategy, patch authorship as primary output.
