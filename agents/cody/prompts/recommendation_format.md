# Recommendation format (standard)

All substantive Cody recommendations SHOULD follow this structure so humans can review, compare, and approve work consistently.

## Fields

| Field | Description |
|--------|-------------|
| **title** | Short, specific title for the recommendation. |
| **summary** | One short paragraph: what is proposed and why it matters. |
| **evidence** | Pointers to code paths, logs, docs, benchmarks, or prior decisions supporting the proposal. |
| **proposed action** | Concrete steps or patch intent (not silently applied). |
| **risk level** | One of: `low`, `medium`, `high`, `critical` (aligned with runtime risk classification). |
| **approval required** | `yes` if humans must approve before implementation or merge; `no` only for truly informational notes. |

## Example skeleton

```text
title: …
summary: …
evidence: …
proposed action: …
risk level: …
approval required: …
```

Use the structured models in `agents/cody/runtime/contracts.py` when emitting machine-readable output.
